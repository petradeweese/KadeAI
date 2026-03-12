from __future__ import annotations

from datetime import datetime

from kade.chat.service import ChatService
from kade.dashboard.app import create_app_status
from kade.integrations.providers import build_llm_provider, build_stt_provider, build_tts_provider, build_wakeword_provider
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
            "highlighted_panels": [],
            "collapsed_panels": [],
            "panel_priority_map": {},
        }
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
        return payload

    def command(self, command: str) -> dict[str, object]:
        result = self._runtime.submit_text_panel_command({"command": command})
        intent = str(result.get("intent", ""))
        self._update_workspace(intent=intent, symbol=parse_symbol_from_command(command), active_view="command")
        self._remember("user", command)
        self._remember("kade", str(result.get("formatted_response", "Done.")), metadata={"intent": intent, "layout_state": dict(self._layout_state)})
        return {"ok": True, "result": result, "dashboard": self.dashboard(), "layout_state": dict(self._layout_state)}

    def chat(self, message: str) -> dict[str, object]:
        response = self._chat.handle_message(message)
        symbol = str(response.interpreted_action.payload.get("symbol", "")).upper() or None
        active_view = "visual" if response.interpreted_action.intent == "visual_explain" else "chat"
        self._update_workspace(intent=response.interpreted_action.intent, symbol=symbol, active_view=active_view)

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

    def _update_workspace(self, intent: str, symbol: str | None, active_view: str) -> None:
        mode = intent_to_workspace_mode(intent)
        current_symbol = symbol or self._layout_state.get("active_symbol")
        layout = build_workspace_layout(mode, active_symbol=str(current_symbol) if current_symbol else None)
        self._layout_state = {
            **layout.as_dict(),
            "active_symbol": current_symbol,
            "active_view": active_view,
            "last_interpreted_intent": intent,
        }

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
