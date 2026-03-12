from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from kade.chat.service import ChatService
from kade.dashboard.app import create_app_status
from kade.integrations.providers import build_llm_provider, build_market_data_provider, build_stt_provider, build_tts_provider, build_wakeword_provider
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
        self._historical_provider = build_market_data_provider(runtime_cfg, route_key="historical_data_provider")
        llm_provider = build_llm_provider({"provider": "mock", "providers": {"mock": {"enabled": llm_enabled}}})
        self._chat = ChatService(self._runtime, llm_provider=llm_provider, llm_enabled=llm_enabled)

    def dashboard(self) -> dict[str, object]:
        voice_payload = self._runtime.dashboard_payload()
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
        try:
            provider_bars = self._historical_provider.get_bars(active_symbol, normalized_timeframe, limit=180)
            bars = [
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": float(bar.volume),
                }
                for bar in provider_bars
            ]
        except Exception as exc:  # pragma: no cover - defensive fallback
            fallback = {
                "available": False,
                "reason": "provider_unavailable",
                "message": f"Chart data unavailable for {active_symbol} right now.",
                "error": str(exc),
            }

        if not bars:
            fallback = {
                "available": False,
                "reason": "bars_unavailable",
                "message": f"Chart data unavailable for {active_symbol} right now.",
            }

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
                "provider": self._historical_provider.provider_name,
                "requested_timeframe": requested_timeframe,
                "timeframe_supported": requested_timeframe in {"1m", "5m", "15m", "1h"},
            },
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
        levels = [
            ("entry", "Entry", parse_first_level(dict(plan.get("entry_plan", {})).get("trigger_condition")) or parse_first_level(plan.get("trigger")), "#16a34a", "trade_plan.entry"),
            ("invalidation", "Invalidation", parse_first_level(dict(plan.get("invalidation_plan", {})).get("invalidation_condition")) or parse_first_level(plan.get("invalidation")), "#dc2626", "trade_plan.invalidation"),
            ("target", "Target", parse_first_level(dict(plan.get("target_plan", {})).get("primary_target")) or parse_first_level(plan.get("target")), "#9333ea", "trade_plan.target"),
        ]
        for overlay_type, label, value, color, source in levels:
            if value is None:
                continue
            overlays.append({"type": overlay_type, "label": label, "price": float(value), "color": color, "reason": f"Deterministic {label.lower()} from trade plan.", "source": source, "priority": 1 if overlay_type == "invalidation" else 2})

        return sorted(overlays, key=lambda item: int(item.get("priority", 9)))

    def _chart_summary(self, symbol: str, timeframe: str, overlays: list[dict[str, object]]) -> dict[str, object]:
        thesis = str(dict(self._runtime.state.latest_trade_idea_opinion or {}).get("summary") or f"Monitoring deterministic setup for {symbol}.")
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "thesis": thesis,
            "key_levels": [f"{item['label']}: {item.get('price', 'n/a')}" for item in overlays if item.get("type") in {"entry", "invalidation", "target", "vwap"}],
            "reasoning": "Levels are sourced from deterministic trade plan and computed chart VWAP.",
        }

    @staticmethod
    def _load_provider_runtime_config() -> dict[str, object]:
        path = Path(__file__).resolve().parents[1] / "config" / "execution.yaml"
        if not path.exists():
            return {}
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return dict(payload.get("execution", {}).get("providers", {}))

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
            return {
                "symbol": symbol,
                "stance": "watch_for_trigger",
                "direction": direction,
                "entry": "breakout confirmation",
                "invalidation": "lose prior structure",
                "target": "next liquidity pocket",
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
