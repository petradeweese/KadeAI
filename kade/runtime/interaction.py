"""Text-first and voice-enabled interaction orchestration for local runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from logging import Logger
from typing import Callable

from kade.integrations.stt.base import STTProvider
from kade.logging_utils import LogCategory, get_logger, log_event
from kade.runtime.replay import ReplayRuntime
from kade.runtime.timeline import RuntimeTimeline
from kade.voice.models import Transcript, WakeWordEvent
from kade.voice.orchestrator import VoiceOrchestrator
from kade.utils.time import utc_now, utc_now_iso


@dataclass
class InteractionRuntimeState:
    runtime_mode: str
    voice_runtime_enabled: bool
    text_command_input_enabled: bool
    wakeword_enabled: bool
    stt_enabled: bool
    tts_enabled: bool
    command_history_limit: int = 25
    execution_history_limit: int = 50
    radar_top_signals_limit: int = 5
    provider_health_history_limit: int = 20
    current_typed_command: str = ""
    latest_command_result: dict[str, object] = field(default_factory=dict)
    latest_advisor_or_status: dict[str, object] = field(default_factory=dict)
    latest_routed_intent: str = ""
    latest_formatted_response: str = ""
    recent_commands: list[dict[str, object]] = field(default_factory=list)
    provider_health: dict[str, dict[str, object]] = field(default_factory=dict)
    provider_health_history: list[dict[str, object]] = field(default_factory=list)
    latest_radar_signals: list[dict[str, object]] = field(default_factory=list)
    execution_lifecycle_history: list[dict[str, object]] = field(default_factory=list)
    latest_staged_orders: list[dict[str, object]] = field(default_factory=list)
    last_execution_results: list[dict[str, object]] = field(default_factory=list)
    provider_diagnostics: dict[str, object] = field(default_factory=dict)
    latest_target_move_board: dict[str, object] = field(default_factory=dict)
    latest_trade_idea_opinion: dict[str, object] = field(default_factory=dict)
    latest_backtest_run_summary: dict[str, object] = field(default_factory=dict)
    recent_backtest_evaluations: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    latest_historical_data: dict[str, object] = field(default_factory=dict)

    def retain_history(self) -> None:
        self.recent_commands = self.recent_commands[-self.command_history_limit :]
        self.provider_health_history = self.provider_health_history[-self.provider_health_history_limit :]
        self.execution_lifecycle_history = self.execution_lifecycle_history[-self.execution_history_limit :]
        self.latest_staged_orders = self.latest_staged_orders[-self.execution_history_limit :]
        self.last_execution_results = self.last_execution_results[-self.execution_history_limit :]
        self.latest_radar_signals = self.latest_radar_signals[-self.radar_top_signals_limit :]


class InteractionOrchestrator:
    def __init__(
        self,
        voice_orchestrator: VoiceOrchestrator,
        stt_provider: STTProvider,
        state: InteractionRuntimeState,
        logger: Logger | None = None,
        replay_runtime: ReplayRuntime | None = None,
        timeline: RuntimeTimeline | None = None,
        target_move_handler: Callable[[dict[str, object]], dict[str, object]] | None = None,
        trade_idea_handler: Callable[[dict[str, object]], dict[str, object]] | None = None,
    ) -> None:
        self.voice_orchestrator = voice_orchestrator
        self.stt_provider = stt_provider
        self.state = state
        self.logger = logger or get_logger(__name__)
        self.replay_runtime = replay_runtime or ReplayRuntime()
        self.timeline = timeline or RuntimeTimeline()
        self.target_move_handler = target_move_handler
        self.trade_idea_handler = trade_idea_handler

    def submit_text_command(self, command: str, now: datetime | None = None, include_debug: bool = True) -> dict[str, object]:
        now = now or utc_now()
        log_event(
            self.logger,
            LogCategory.COMMAND_EVENT,
            "Command received",
            runtime_mode=self.state.runtime_mode,
            command=command,
        )
        self.timeline.add_event("command_received", now.isoformat(), {"command": command, "source": "text"})
        self.state.current_typed_command = command
        self.voice_orchestrator.handle_wake_event(
            WakeWordEvent(
                wake_word=self.voice_orchestrator.state.wake_word,
                detected_at=now,
                source="text_path",
            )
        )
        result = self.voice_orchestrator.process_transcript(
            Transcript(text=command, received_at=now, provider="text_input", metadata={"path": "text_first"}),
            now=now,
        ) or {"intent": "ignored", "spoken_text": "No command window open.", "tts": {"provider": "disabled", "voice": "none"}}

        if not self.state.tts_enabled and "tts" in result:
            result["tts"] = {"provider": "disabled", "voice": "none", "audio_uri": None, "metadata": {"reason": "tts_disabled"}}

        response = self._build_response(command=command, result=result, source="text", now=now, include_debug=include_debug)
        self._refresh_provider_health()
        return response

    def submit_text_panel_command(self, payload: dict[str, object], now: datetime | None = None) -> dict[str, object]:
        if payload.get("target_move_request"):
            return self.submit_target_move_request(dict(payload["target_move_request"]), now=now)
        if payload.get("trade_idea_request"):
            return self.submit_trade_idea_opinion(dict(payload["trade_idea_request"]), now=now)

        command = str(payload.get("command", "")).strip()
        include_debug = bool(payload.get("include_debug", True))
        if not command:
            return {
                "intent": "invalid",
                "formatted_response": "Command cannot be empty.",
                "advisor_radar_status_summary": {"runtime_mode": self.state.runtime_mode},
                "provider_mode": {},
                "timestamp": utc_now_iso(),
            }
        if command.lower().startswith("target_move"):
            parsed = self._parse_target_move_command(command)
            return self.submit_target_move_request(parsed, now=now)
        if command.lower().startswith("trade_idea"):
            parsed = self._parse_trade_idea_command(command)
            return self.submit_trade_idea_opinion(parsed, now=now)
        return self.submit_text_command(command=command, now=now, include_debug=include_debug)

    def submit_target_move_request(self, request_payload: dict[str, object], now: datetime | None = None) -> dict[str, object]:
        now = now or utc_now()
        if not self.target_move_handler:
            return {
                "intent": "target_move_scenario_unavailable",
                "formatted_response": "Target-move scenario handler is not configured.",
                "advisor_radar_status_summary": {"runtime_mode": self.state.runtime_mode},
                "provider_mode": {},
                "timestamp": now.isoformat(),
            }

        board = self.target_move_handler(request_payload)
        self.state.latest_target_move_board = board
        self.timeline.add_event("target_move_scenario_generated", now.isoformat(), {"request": board.get("request", {}), "buckets": board.get("buckets", {})})
        response = {
            "intent": "target_move_scenario",
            "formatted_response": f"Generated {len(board.get('candidates', []))} target-move scenario candidates.",
            "advisor_radar_status_summary": self.state.latest_advisor_or_status,
            "provider_mode": {
                "stt": self.stt_provider.provider_name,
                "tts": "disabled",
                "wakeword": self.voice_orchestrator.wakeword_detector.provider_name,
            },
            "timestamp": now.isoformat(),
            "raw_result": {"intent": "target_move_scenario", "target_move_board": board},
        }
        self._record(command=f"target_move {request_payload}", result={"intent": "target_move_scenario", "spoken_text": response["formatted_response"], "target_move_board": board}, source="text_panel", now=now)
        self._refresh_provider_health()
        return response

    def submit_trade_idea_opinion(self, request_payload: dict[str, object], now: datetime | None = None) -> dict[str, object]:
        now = now or utc_now()
        if self.trade_idea_handler is None:
            return {
                "intent": "trade_idea_opinion",
                "formatted_response": "Trade-idea opinion mode is not configured.",
                "advisor_radar_status_summary": self.state.latest_advisor_or_status,
                "provider_mode": {},
                "timestamp": now.isoformat(),
                "raw_result": {"intent": "trade_idea_opinion", "trade_idea_opinion": {}},
            }

        opinion = self.trade_idea_handler(request_payload)
        self.state.latest_trade_idea_opinion = opinion
        self.timeline.add_event(
            "trade_idea_opinion_generated",
            now.isoformat(),
            {
                "request": {
                    "symbol": request_payload.get("symbol"),
                    "direction": request_payload.get("direction"),
                    "current_price": request_payload.get("current_price", request_payload.get("current")),
                    "target_price": request_payload.get("target_price", request_payload.get("target")),
                    "time_horizon_minutes": request_payload.get("time_horizon_minutes", request_payload.get("minutes")),
                },
                "stance": opinion.get("stance"),
                "target_plausibility": opinion.get("target_plausibility"),
                "market_alignment": opinion.get("market_alignment"),
                "summary": opinion.get("summary"),
            },
        )
        response = {
            "intent": "trade_idea_opinion",
            "formatted_response": str(opinion.get("summary", "Generated trade idea opinion.")),
            "advisor_radar_status_summary": self.state.latest_advisor_or_status,
            "provider_mode": {
                "stt": self.stt_provider.provider_name,
                "tts": "disabled",
                "wakeword": self.voice_orchestrator.wakeword_detector.provider_name,
            },
            "timestamp": now.isoformat(),
            "raw_result": {"intent": "trade_idea_opinion", "trade_idea_opinion": opinion},
        }
        self._record(
            command=f"trade_idea {request_payload}",
            result={"intent": "trade_idea_opinion", "spoken_text": response["formatted_response"], "trade_idea_opinion": opinion},
            source="text_panel",
            now=now,
        )
        self._refresh_provider_health()
        return response

    def command_history_viewer(self) -> dict[str, object]:
        return {"count": len(self.state.recent_commands), "history": list(self.state.recent_commands)}

    def replay_last_command(self) -> dict[str, object] | None:
        if not self.replay_runtime.records:
            return None
        return self.replay_runtime.replay_command(len(self.replay_runtime.records) - 1)

    def replay_recent_commands(self, count: int = 5) -> dict[str, object]:
        replay = self.replay_runtime.replay_recent(count)
        log_event(self.logger, LogCategory.COMMAND_EVENT, "Replay requested", count=count, returned=len(replay))
        return {"replay": replay, "debug": self.replay_runtime.last_replay}

    def process_voice_sample(self, audio_hint: str, now: datetime | None = None) -> dict[str, object] | None:
        now = now or utc_now()
        if not self.state.voice_runtime_enabled or not self.state.wakeword_enabled or not self.state.stt_enabled:
            log_event(self.logger, LogCategory.VOICE_EVENT, "Voice runtime disabled", runtime_mode=self.state.runtime_mode)
            self._refresh_provider_health()
            return None

        if not self.voice_orchestrator.process_wake_sample(audio_hint, now=now):
            return None

        transcript = self.stt_provider.transcribe(audio_hint)
        log_event(self.logger, LogCategory.VOICE_EVENT, "STT backend invoked", provider=transcript.provider)
        result = self.voice_orchestrator.process_transcript(transcript, now=now)
        if result:
            response = self._build_response(command=transcript.text, result=result, source="voice", now=now, include_debug=True)
            self._refresh_provider_health()
            return response
        return result

    def dashboard_payload(self) -> dict[str, object]:
        payload = self.voice_orchestrator.dashboard_payload()
        payload.update(
            {
                "runtime_mode": self.state.runtime_mode,
                "command_input_mode": "text_panel" if self.state.text_command_input_enabled else "voice_only",
                "text_command_input_enabled": self.state.text_command_input_enabled,
                "voice_runtime_enabled": self.state.voice_runtime_enabled,
                "wakeword_enabled": self.state.wakeword_enabled,
                "stt_enabled": self.state.stt_enabled,
                "tts_enabled": self.state.tts_enabled,
                "current_typed_command": self.state.current_typed_command,
                "latest_routed_intent": self.state.latest_routed_intent,
                "latest_formatted_response": self.state.latest_formatted_response,
                "latest_command_result": self.state.latest_command_result,
                "latest_advisor_or_status": self.state.latest_advisor_or_status,
                "recent_commands": self.state.recent_commands,
                "provider_health": self.state.provider_health,
                "provider_health_history": self.state.provider_health_history,
                "replay_debug": self.replay_runtime.snapshot(),
                "text_panel_commands": ["status", "radar", "what do you think about NVDA", "what is NVDA doing", "what was I watching"],
                "timeline": self.timeline.snapshot(),
                "provider_diagnostics": self.state.provider_diagnostics,
                "latest_radar_signals": self.state.latest_radar_signals,
                "execution_monitor": {
                    "latest_staged_orders": self.state.latest_staged_orders,
                    "last_execution_results": self.state.last_execution_results,
                    "lifecycle_history": self.state.execution_lifecycle_history,
                },
                "target_move_board": self.state.latest_target_move_board,
                "trade_idea_opinion": self.state.latest_trade_idea_opinion,
                "backtesting": {
                    "latest_run_summary": self.state.latest_backtest_run_summary,
                    "recent_evaluations": self.state.recent_backtest_evaluations,
                },
                "historical_data": self.state.latest_historical_data,
            }
        )
        return payload


    def ingest_historical_data(self, payload: dict[str, object]) -> None:
        self.state.latest_historical_data = payload
        self.timeline.add_event("historical_data_updated", utc_now_iso(), {"keys": sorted(payload.keys())})

    def ingest_backtest_summary(self, summary: dict[str, object]) -> None:
        self.state.latest_backtest_run_summary = summary
        self.state.recent_backtest_evaluations = dict(summary.get("recent_evaluations", {}))
        timestamp = str(summary.get("generated_at", utc_now_iso()))
        self.timeline.add_event("backtest_run_completed", timestamp, {"run_id": summary.get("run_id")})

    def _parse_target_move_command(self, command: str) -> dict[str, object]:
        parsed: dict[str, object] = {}
        for part in command.split():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            parsed[key.strip().lower()] = value.strip()
        if "dtes" in parsed:
            parsed["allowed_dtes"] = [int(token.strip()) for token in str(parsed.pop("dtes")).split(",") if token.strip()]
        return parsed

    def _parse_trade_idea_command(self, command: str) -> dict[str, object]:
        parsed: dict[str, object] = {}
        for part in command.split():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            parsed[key.strip().lower()] = value.strip()
        return parsed

    def set_provider_diagnostics(self, diagnostics: dict[str, object]) -> None:
        self.state.provider_diagnostics = diagnostics
        self.timeline.add_event("provider_diagnostic", utc_now_iso(), diagnostics)

    def ingest_radar_signals(self, signals: list[dict[str, object]]) -> None:
        trimmed = signals[: self.state.radar_top_signals_limit]
        previous = {str(item.get("symbol")): item for item in self.state.latest_radar_signals}
        self.state.latest_radar_signals = trimmed
        for signal in trimmed:
            timestamp = str(signal.get("timestamp", utc_now_iso()))
            self.timeline.add_event("radar_signal", timestamp, signal)
            symbol = str(signal.get("symbol"))
            prior = previous.get(symbol)
            if prior is not None:
                if signal.get("setup_tags") != prior.get("setup_tags"):
                    self.timeline.add_event("radar_setup_tags_changed", timestamp, {"symbol": symbol, "previous": prior.get("setup_tags"), "current": signal.get("setup_tags")})
                if signal.get("alignment_label") != prior.get("alignment_label"):
                    self.timeline.add_event("radar_alignment_changed", timestamp, {"symbol": symbol, "previous": prior.get("alignment_label"), "current": signal.get("alignment_label")})
                if signal.get("regime_fit") != prior.get("regime_fit"):
                    self.timeline.add_event("radar_regime_fit_changed", timestamp, {"symbol": symbol, "previous": prior.get("regime_fit"), "current": signal.get("regime_fit")})
                if isinstance(signal.get("confidence"), (float, int)) and isinstance(prior.get("confidence"), (float, int)):
                    if abs(float(signal["confidence"]) - float(prior["confidence"])) >= 3:
                        self.timeline.add_event("radar_score_changed", timestamp, {"symbol": symbol, "previous": prior.get("confidence"), "current": signal.get("confidence")})
            log_event(
                self.logger,
                LogCategory.RADAR_EVENT,
                "Radar signal",
                symbol=signal.get("symbol"),
                setup=signal.get("setup") or signal.get("signal_type"),
                confidence=signal.get("confidence"),
                alignment=signal.get("alignment_label"),
                regime_fit=signal.get("regime_fit"),
            )

    def ingest_execution_events(self, events: list[dict[str, object]]) -> None:
        self.state.execution_lifecycle_history.extend(events)
        self.state.latest_staged_orders = [e for e in events if str(e.get("status", "")).startswith("staged")]
        self.state.last_execution_results = events[-3:]
        self.state.retain_history()
        for event in events:
            self.timeline.add_event("execution_event", str(event.get("timestamp", utc_now_iso())), event)
            log_event(
                self.logger,
                LogCategory.EXECUTION_EVENT,
                "Execution lifecycle",
                symbol=event.get("symbol"),
                status=event.get("status"),
                lifecycle_state=event.get("lifecycle_state"),
            )

    def _build_response(
        self,
        command: str,
        result: dict[str, object],
        source: str,
        now: datetime,
        include_debug: bool,
    ) -> dict[str, object]:
        self._record(command=command, result=result, source=source, now=now)
        response = {
            "intent": result.get("intent", "unknown"),
            "formatted_response": result.get("spoken_text", ""),
            "advisor_radar_status_summary": self.state.latest_advisor_or_status,
            "provider_mode": {
                "stt": self.stt_provider.provider_name,
                "tts": dict(result.get("tts", {})).get("provider", "unknown"),
                "wakeword": self.voice_orchestrator.wakeword_detector.provider_name,
            },
            "timestamp": now.isoformat(),
            "raw_result": result,
        }
        if include_debug:
            response["debug"] = {
                "source": source,
                "timestamp": now.isoformat(),
                "recent_commands": self.state.recent_commands,
            }
        return response

    def _refresh_provider_health(self) -> None:
        health_map = {
            "wakeword": self.voice_orchestrator.wakeword_detector.health_snapshot(active=self.state.wakeword_enabled).as_dict(),
            "stt": self.stt_provider.health_snapshot(active=self.state.stt_enabled).as_dict(),
            "tts": self.voice_orchestrator.tts_provider.health_snapshot(active=self.state.tts_enabled).as_dict(),
        }
        self.state.provider_health = health_map
        snapshot = {"timestamp": utc_now_iso(), "providers": health_map}
        self.state.provider_health_history.append(snapshot)
        self.state.retain_history()
        for name, provider in health_map.items():
            log_event(
                self.logger,
                LogCategory.VOICE_EVENT,
                "Provider readiness checked",
                provider_type=name,
                provider_name=provider["provider_name"],
                state=provider["state"],
                active=provider["active"],
            )

    def _record(self, command: str, result: dict[str, object], source: str, now: datetime) -> None:
        self.state.latest_command_result = result
        self.state.latest_routed_intent = str(result.get("intent", ""))
        self.state.latest_formatted_response = str(result.get("spoken_text", ""))
        self.timeline.add_event(
            "intent_routed",
            now.isoformat(),
            {"command": command, "intent": self.state.latest_routed_intent, "source": source},
        )
        if result.get("intent") in {"status", "radar", "symbol_opinion", "symbol_status", "market_overview"}:
            self.state.latest_advisor_or_status = result
            self.timeline.add_event("advisor_response", now.isoformat(), {"intent": result.get("intent"), "response": result.get("spoken_text")})
        record = {
            "source": source,
            "command": command,
            "intent": result.get("intent"),
            "spoken_text": result.get("spoken_text"),
            "timestamp": now.isoformat(),
            "provider_mode": dict(result.get("tts", {})).get("provider", "unknown"),
        }
        self.state.recent_commands.append(record)
        self.replay_runtime.add_record(command=command, result=result, source=source, timestamp=now)
        self.state.retain_history()
