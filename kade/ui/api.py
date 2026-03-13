from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from kade.chat.service import ChatService
from kade.dashboard.app import create_app_status
from kade.integrations.providers import build_llm_provider, build_market_data_provider, build_stt_provider, build_tts_provider, build_wakeword_provider
from kade.runtime.configuration import apply_runtime_env_overrides
from kade.visuals.levels import parse_first_level
from kade.runtime.interaction import InteractionOrchestrator, InteractionRuntimeState
from kade.ui.workspace import build_workspace_layout, intent_to_workspace_mode, parse_symbol_from_command
from kade.voice.formatter import SpokenResponseFormatter
from kade.voice.models import VoiceSessionState
from kade.voice.orchestrator import VoiceOrchestrator
from kade.voice.router import VoiceCommandRouter


class OperatorBackend:
    def __init__(self, llm_enabled: bool = True) -> None:
        self._runtime = self._build_interaction()
        self._history: list[dict[str, object]] = []
        self._layout_state: dict[str, object] = {
            "active_workspace_mode": "overview",
            "active_symbol": None,
            "active_view": "overview",
            "last_interpreted_intent": "",
            "active_direction": None,
            "active_horizon": None,
            "active_timeframe": "5m",
            "highlighted_panels": [],
            "collapsed_panels": [],
            "panel_priority_map": {},
        }
        runtime_cfg = self._load_provider_runtime_config()
        self._historical_provider = build_market_data_provider(runtime_cfg, route_key="historical_data_provider", allow_mock_fallback=False)
        llm_cfg = self._load_llm_config()
        if not llm_enabled:
            llm_cfg = {"provider": "mock", "providers": {"mock": {"enabled": False}}}
        llm_provider = build_llm_provider(llm_cfg)
        fallback_provider = build_llm_provider({"provider": "mock", "providers": {"mock": {"enabled": True}}})
        self._chat = ChatService(self._runtime, llm_provider=llm_provider, llm_fallback_provider=fallback_provider, llm_enabled=llm_enabled)

    def dashboard(self) -> dict[str, object]:
        voice_payload = self._runtime.dashboard_payload()
        provider_selection = dict(voice_payload.get("provider_selection", {}))
        provider_selection["llm"] = getattr(self._chat.llm_provider, "provider_name", "mock")
        voice_payload["provider_selection"] = provider_selection
        provider_diagnostics = dict(voice_payload.get("provider_diagnostics", {}))
        providers = dict(provider_diagnostics.get("providers", {}))
        providers["llm"] = {
            "provider_name": getattr(self._chat.llm_provider, "provider_name", "mock"),
            "state": "ready" if getattr(self._chat.llm_provider, "provider_name", "mock") != "mock" else "mock",
            "active": bool(self._chat.llm_enabled),
            "metadata": {"model": getattr(self._chat.llm_provider, "model", "unknown")},
        }
        provider_diagnostics["providers"] = providers
        voice_payload["provider_diagnostics"] = provider_diagnostics

        payload = create_app_status(
            voice_payload=voice_payload,
            market_intelligence_payload=self._market_intelligence(),
            premarket_gameplan_payload=self._premarket_gameplan(),
            strategy_intelligence_payload=self._strategy_intelligence(),
        )
        payload["ui_state"] = {
            "chat_history_size": len(self._history),
            **self._layout_state,
        }
        chart_timeframe = str(self._layout_state.get("active_timeframe") or "5m")
        chart_payload = self.chart_data(symbol=str(self._layout_state.get("active_symbol") or "SPY"), timeframe=chart_timeframe)
        payload["operator_console"]["visual_explainability"] = {
            **dict(payload["operator_console"].get("visual_explainability", {})),
            "active_symbol": chart_payload["symbol"],
            "active_view": chart_payload["active_view"]["mode"],
            "charts": [{"timeframe": chart_payload["timeframe"], "bars": chart_payload["bars"], "overlays": chart_payload["overlays"], "summary": chart_payload["summary"]}],
            "chart_unavailable": not bool(chart_payload["bars"]),
            "fallback": chart_payload["fallback"],
            "summary": chart_payload["summary"],
        }
        return payload

    def chart_data(self, symbol: str | None = None, timeframe: str | None = None) -> dict[str, object]:
        active_symbol = str(symbol or self._layout_state.get("active_symbol") or "SPY").upper()
        requested_timeframe = str(timeframe or self._layout_state.get("active_timeframe") or "5m")
        normalized_timeframe = requested_timeframe if requested_timeframe in {"1m", "5m", "15m", "1h"} else "5m"
        bars: list[dict[str, object]] = []
        fallback = {"available": True, "reason": "", "message": ""}
        provider_name = str(getattr(self._historical_provider, "provider_name", "unknown"))
        is_mock_provider = provider_name.startswith("mock")
        provider_health = None
        if hasattr(self._historical_provider, "health_snapshot"):
            provider_health = self._historical_provider.health_snapshot(active=True)
        try:
            provider_bars = self._historical_provider.get_bars(active_symbol, normalized_timeframe, limit=180)
            bars = [normalized for item in provider_bars if (normalized := self._normalize_chart_bar(item)) is not None]
        except Exception as exc:  # pragma: no cover - defensive fallback
            fallback = {
                "available": False,
                "reason": "provider_unavailable",
                "message": f"Chart data unavailable for {active_symbol} right now.",
                "error": str(exc),
            }

        if not bars and fallback["available"]:
            fallback = {
                "available": False,
                "reason": "bars_unavailable",
                "message": f"Chart data unavailable for {active_symbol} right now.",
            }

        if is_mock_provider:
            fallback = {
                "available": False,
                "reason": "mock_provider",
                "message": f"Chart feed is disconnected from real provider for {active_symbol}; deterministic overlays remain available.",
            }
            bars = []

        overlays = self._build_chart_overlays(active_symbol, bars)
        return {
            "symbol": active_symbol,
            "timeframe": normalized_timeframe,
            "bars": bars,
            "overlays": overlays,
            "summary": self._chart_summary(active_symbol, normalized_timeframe, overlays),
            "active_view": {
                "mode": str(self._layout_state.get("active_workspace_mode") or "overview"),
                "symbol": active_symbol,
                "timeframe": normalized_timeframe,
                "direction": self._layout_state.get("active_direction"),
                "horizon": self._layout_state.get("active_horizon"),
            },
            "fallback": fallback,
            "meta": {
                "provider": provider_name,
                "provider_state": getattr(provider_health, "state", "unknown"),
                "is_mock_provider": is_mock_provider,
                "requested_timeframe": requested_timeframe,
                "timeframe_supported": requested_timeframe in {"1m", "5m", "15m", "1h"},
            },
        }


    @staticmethod
    def _normalize_chart_bar(bar: object) -> dict[str, object] | None:
        if isinstance(bar, dict):
            ts = bar.get("timestamp") or bar.get("t")
            open_price = bar.get("open") if bar.get("open") is not None else bar.get("o")
            high_price = bar.get("high") if bar.get("high") is not None else bar.get("h")
            low_price = bar.get("low") if bar.get("low") is not None else bar.get("l")
            close_price = bar.get("close") if bar.get("close") is not None else bar.get("c")
            volume = bar.get("volume") if bar.get("volume") is not None else bar.get("v", 0.0)
        else:
            ts = getattr(bar, "timestamp", None) or getattr(bar, "t", None)
            open_price = getattr(bar, "open", None)
            if open_price is None:
                open_price = getattr(bar, "o", None)
            high_price = getattr(bar, "high", None)
            if high_price is None:
                high_price = getattr(bar, "h", None)
            low_price = getattr(bar, "low", None)
            if low_price is None:
                low_price = getattr(bar, "l", None)
            close_price = getattr(bar, "close", None)
            if close_price is None:
                close_price = getattr(bar, "c", None)
            volume = getattr(bar, "volume", None)
            if volume is None:
                volume = getattr(bar, "v", 0.0)

        if ts is None or open_price is None or high_price is None or low_price is None or close_price is None:
            return None

        timestamp = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        return {
            "timestamp": timestamp,
            "open": float(open_price),
            "high": float(high_price),
            "low": float(low_price),
            "close": float(close_price),
            "volume": float(volume or 0.0),
        }

    def command(self, command: str) -> dict[str, object]:
        result = self._runtime.submit_text_panel_command({"command": command})
        intent = str(result.get("intent", ""))
        self._update_workspace(intent=intent, symbol=parse_symbol_from_command(command), direction=None, horizon=None, active_view="command")
        self._remember("user", command)
        self._remember("kade", str(result.get("formatted_response", "Done.")), metadata={"intent": intent, "layout_state": dict(self._layout_state)})
        return {"ok": True, "result": result, "dashboard": self.dashboard(), "layout_state": dict(self._layout_state)}

    def chat(self, message: str) -> dict[str, object]:
        response = self._chat.handle_message(message)
        symbol = str(response.interpreted_action.payload.get("symbol", "")).upper() or None
        direction = str(response.interpreted_action.payload.get("direction", "")).lower() or None
        horizon = response.interpreted_action.payload.get("horizon_minutes") or response.interpreted_action.payload.get("horizon_label")
        active_view = "visual" if response.interpreted_action.intent == "visual_explain" else "chat"
        self._update_workspace(intent=response.interpreted_action.intent, symbol=symbol, direction=direction, horizon=horizon, active_view=active_view)

        self._remember("user", message)
        self._remember(
            "kade",
            response.reply,
            metadata={
                "intent": response.interpreted_action.intent,
                "interpreted_action": {
                    "intent": response.interpreted_action.intent,
                    "payload": response.interpreted_action.payload,
                    "source": response.interpreted_action.source,
                    "confidence": response.interpreted_action.confidence,
                },
                "diagnostics": {
                    "used_llm_for_parsing": response.used_llm_for_parsing,
                    "used_llm_for_formatting": response.used_llm_for_formatting,
                    "fallback_used": response.fallback_used,
                },
                "layout_state": dict(self._layout_state),
                "raw_result": response.command_response,
            },
        )
        return {
            "ok": True,
            "reply": response.reply,
            "interpreted_action": {
                "intent": response.interpreted_action.intent,
                "payload": response.interpreted_action.payload,
                "source": response.interpreted_action.source,
                "confidence": response.interpreted_action.confidence,
            },
            "command_response": response.command_response,
            "dashboard": self.dashboard(),
            "layout_state": dict(self._layout_state),
            "diagnostics": {
                "used_llm_for_parsing": response.used_llm_for_parsing,
                "used_llm_for_formatting": response.used_llm_for_formatting,
                "fallback_used": response.fallback_used,
            },
        }

    def history(self) -> dict[str, object]:
        return {"items": self._history[-80:]}

    def _update_workspace(self, intent: str, symbol: str | None, direction: str | None, horizon: object, active_view: str) -> None:
        mode = intent_to_workspace_mode(intent)
        current_symbol = symbol or self._layout_state.get("active_symbol")
        current_direction = direction or self._layout_state.get("active_direction")
        current_horizon = horizon or self._layout_state.get("active_horizon")
        current_timeframe = self._infer_timeframe(current_horizon)
        layout = build_workspace_layout(mode, active_symbol=str(current_symbol) if current_symbol else None)
        self._layout_state = {
            **layout.as_dict(),
            "active_symbol": current_symbol,
            "active_direction": current_direction,
            "active_horizon": current_horizon,
            "active_timeframe": current_timeframe,
            "active_view": active_view,
            "last_interpreted_intent": intent,
        }

    @staticmethod
    def _infer_timeframe(horizon: object) -> str:
        if isinstance(horizon, (int, float)):
            minutes = int(horizon)
            if minutes <= 30:
                return "1m"
            if minutes <= 120:
                return "5m"
            return "15m"
        return "5m"

    def _build_chart_overlays(self, symbol: str, bars: list[dict[str, object]]) -> list[dict[str, object]]:
        overlays: list[dict[str, object]] = []
        closes = [float(item["close"]) for item in bars]
        if closes:
            vwap = sum(float(item["close"]) * float(item["volume"]) for item in bars) / max(sum(float(item["volume"]) for item in bars), 1.0)
            overlays.append({"type": "vwap", "label": "VWAP", "price": round(vwap, 4), "color": "#2563eb", "reason": "Session VWAP from chart bars.", "source": "chart_bars", "priority": 4})

        plan = dict(self._runtime.state.latest_trade_plan or {})
        idea = dict(self._runtime.state.latest_trade_idea_opinion or {})
        levels = [
            (
                "entry",
                "Entry",
                parse_first_level(dict(plan.get("entry_plan", {})).get("trigger_condition"))
                or parse_first_level(plan.get("trigger"))
                or parse_first_level(idea.get("entry")),
                "#16a34a",
                "trade_plan.entry" if plan else "trade_idea_opinion.entry",
            ),
            (
                "invalidation",
                "Invalidation",
                parse_first_level(dict(plan.get("invalidation_plan", {})).get("invalidation_condition"))
                or parse_first_level(plan.get("invalidation"))
                or parse_first_level(idea.get("invalidation")),
                "#dc2626",
                "trade_plan.invalidation" if plan else "trade_idea_opinion.invalidation",
            ),
            (
                "target",
                "Target",
                parse_first_level(dict(plan.get("target_plan", {})).get("primary_target"))
                or parse_first_level(plan.get("target"))
                or parse_first_level(idea.get("target")),
                "#9333ea",
                "trade_plan.target" if plan else "trade_idea_opinion.target",
            ),
        ]
        for overlay_type, label, value, color, source in levels:
            if value is None:
                continue
            overlays.append({"type": overlay_type, "label": label, "price": float(value), "color": color, "reason": f"Deterministic {label.lower()} from trade plan.", "source": source, "priority": 1 if overlay_type == "invalidation" else 2})

        return sorted(overlays, key=lambda item: int(item.get("priority", 9)))

    def _chart_summary(self, symbol: str, timeframe: str, overlays: list[dict[str, object]]) -> dict[str, object]:
        idea = dict(self._runtime.state.latest_trade_idea_opinion or {})
        thesis = str(idea.get("summary") or f"Monitoring deterministic setup for {symbol}.")
        entry = next((item.get("price") for item in overlays if item.get("type") == "entry"), None)
        invalidation = next((item.get("price") for item in overlays if item.get("type") == "invalidation"), None)
        target = next((item.get("price") for item in overlays if item.get("type") == "target"), None)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "thesis": thesis,
            "key_levels": [f"{item['label']}: {item.get('price', 'n/a')}" for item in overlays if item.get("type") in {"entry", "invalidation", "target", "vwap"}],
            "reasoning": (
                f"Wait for {idea.get('entry', 'breakdown/breakout confirmation')}; "
                f"target around {target if target is not None else 'n/a'}; "
                f"invalidation near {invalidation if invalidation is not None else 'n/a'}; "
                f"reference entry {entry if entry is not None else 'n/a'}."
            ),
        }

    @staticmethod
    def _load_llm_config() -> dict[str, object]:
        path = Path(__file__).resolve().parents[1] / "config" / "llm.yaml"
        if not path.exists():
            return {"provider": "mock", "providers": {"mock": {"enabled": True}}}
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cfg = {"llm.yaml": dict(payload)}
        merged = apply_runtime_env_overrides(cfg)
        return dict(merged.get("llm.yaml", {}).get("llm", {}))

    @staticmethod
    def _load_provider_runtime_config() -> dict[str, object]:
        path = Path(__file__).resolve().parents[1] / "config" / "execution.yaml"
        if not path.exists():
            return {}

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        provider_block = payload.get("providers")
        if not isinstance(provider_block, dict):
            provider_block = dict(payload.get("execution", {}).get("providers", {}))

        cfg = {"execution.yaml": {"execution": {"providers": dict(provider_block)}}}
        merged = apply_runtime_env_overrides(cfg)
        return dict(merged.get("execution.yaml", {}).get("execution", {}).get("providers", {}))

    def _remember(self, role: str, text: str, metadata: dict[str, object] | None = None) -> None:
        self._history.append({"role": role, "text": text, "timestamp": datetime.utcnow().isoformat(), "metadata": metadata or {}})
        self._history = self._history[-80:]

    def _build_interaction(self) -> InteractionOrchestrator:
        state = InteractionRuntimeState(
            runtime_mode="text_first",
            voice_runtime_enabled=False,
            text_command_input_enabled=True,
            wakeword_enabled=False,
            stt_enabled=False,
            tts_enabled=False,
        )

        def _trade_idea(payload: dict[str, object]) -> dict[str, object]:
            symbol = str(payload.get("symbol", "SPY")).upper()
            direction = str(payload.get("direction", "call")).lower()
            target = payload.get("target")
            target_text = f"{float(target):.2f}" if isinstance(target, (int, float)) else "next liquidity pocket"
            return {
                "symbol": symbol,
                "stance": "watch_for_trigger",
                "direction": direction,
                "entry": "breakout confirmation",
                "invalidation": "lose prior structure",
                "target": target_text,
                "confidence": 0.66,
                "risk_posture": "normal",
                "summary": f"Deterministic setup for {symbol} ({direction}).",
            }

        def _trade_plan(payload: dict[str, object]) -> dict[str, object]:
            symbol = str(payload.get("symbol", "SPY")).upper()
            return {
                "plan_id": f"plan-{symbol}-1",
                "symbol": symbol,
                "status": "planned",
                "trigger": "break and hold",
                "invalidation": "failed retest",
                "target": "measured move",
                "entry_plan": {"trigger_condition": "Break above 101.2"},
                "invalidation_plan": {"invalidation_condition": "Lose 99.4"},
                "target_plan": {"primary_target": "103.1"},
                "checklist": ["regime aligned", "volume confirmation"],
            }

        voice = VoiceOrchestrator(
            wakeword_detector=build_wakeword_provider({"wakeword_provider": "mock", "wake_word": "Kade"}),
            router=VoiceCommandRouter(
                handlers={
                    "status": lambda: {"summary": "Runtime healthy and deterministic engines online."},
                    "radar": lambda: {"summary": "Radar refreshed with top setups."},
                    "market_overview": lambda: {"summary": "Market posture mixed with selective momentum."},
                    "memory_watchlist": lambda: {"watching": ["NVDA", "SPY", "QQQ"]},
                    "symbol_status": lambda symbol: {"summary": f"{symbol} in consolidation."},
                    "symbol_opinion": lambda symbol: {"summary": f"Watching {symbol} for trigger confirmation."},
                    "fallback": lambda mode, transcript: {"summary": transcript},
                }
            ),
            formatter=SpokenResponseFormatter(),
            tts_provider=build_tts_provider({"tts_provider": "kokoro", "kokoro": {"mock_synthesis": True}}),
            state=VoiceSessionState(wake_word="Kade"),
            enable_tts=False,
        )
        return InteractionOrchestrator(
            voice_orchestrator=voice,
            stt_provider=build_stt_provider({"stt_provider": "mock"}),
            state=state,
            trade_idea_handler=_trade_idea,
            target_move_handler=lambda payload: {"request": payload, "candidate_count": 2, "candidates": [{"symbol": payload.get("symbol", "SPY"), "scenario": "continuation"}]},
            trade_plan_handler=_trade_plan,
            trade_plan_tracking_handler=lambda payload: {"plan_id": payload.get("plan_id", "plan-SPY-1"), "status_after": "monitoring", "symbol": payload.get("symbol", "SPY")},
            trade_review_handler=lambda payload: {"latest_review": {"grade": "B", "notes": "Followed plan."}, "metrics_summary": {"discipline": 0.81}, "history": []},
            premarket_gameplan_handler=lambda payload: self._premarket_gameplan(),
            visual_explanation_handler=lambda payload: {"symbol": payload.get("symbol", "SPY"), "view_type": payload.get("view_type", "plan"), "charts": [{"timeframe": "5m", "levels": [{"label": "trigger", "value": 500.0}]}], "side_panels": [{"title": "Reasons", "items": ["Trend alignment", "Volume pickup"]}]},
            strategy_analysis_handler=lambda payload: self._strategy_intelligence(),
        )

    def _market_intelligence(self) -> dict[str, object]:
        return {
            "regime": {"label": "balanced", "confidence": 0.64},
            "key_news": [{"headline": "Rates steady", "impact": "neutral"}],
            "top_movers": [{"symbol": "NVDA", "move_pct": 1.9}],
            "most_active": [{"symbol": "SPY", "volume": 1200000}],
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _premarket_gameplan(self) -> dict[str, object]:
        return {
            "summary": {"text": "Selective momentum; focus on clean triggers."},
            "market_posture": {"posture_label": "selective-risk-on", "risk_posture": "normal"},
            "key_catalysts": ["Macro data at 10:00", "Semis relative strength"],
            "movers_to_watch": [{"symbol": "NVDA", "reason": "relative strength"}],
            "watchlist_priorities": ["NVDA", "SPY", "QQQ"],
            "risks": ["Late-day reversal risk"],
            "opportunities": ["Breakout continuation in leaders"],
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _strategy_intelligence(self) -> dict[str, object]:
        return {
            "setup_archetype_stats": [{"name": "opening drive", "win_rate": 0.58}],
            "regime_performance": [{"regime": "balanced", "expectancy": 0.22}],
            "symbol_performance": [{"symbol": "NVDA", "expectancy": 0.35}],
            "discipline_impact": {"following_plan": {"pnl": 1200}},
            "plan_calibration_summary": {"overfit_risk": "low"},
            "generated_at": datetime.utcnow().isoformat(),
        }
