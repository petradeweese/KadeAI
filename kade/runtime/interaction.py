"""Text-first and voice-enabled interaction orchestration for local runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from logging import Logger

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
    ) -> None:
        self.voice_orchestrator = voice_orchestrator
        self.stt_provider = stt_provider
        self.state = state
        self.logger = logger or get_logger(__name__)
        self.replay_runtime = replay_runtime or ReplayRuntime()
        self.timeline = timeline or RuntimeTimeline()

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
        return self.submit_text_command(command=command, now=now, include_debug=include_debug)

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
            }
        )
        return payload

    def set_provider_diagnostics(self, diagnostics: dict[str, object]) -> None:
        self.state.provider_diagnostics = diagnostics
        self.timeline.add_event("provider_diagnostic", utc_now_iso(), diagnostics)

    def ingest_radar_signals(self, signals: list[dict[str, object]]) -> None:
        trimmed = signals[: self.state.radar_top_signals_limit]
        self.state.latest_radar_signals = trimmed
        for signal in trimmed:
            self.timeline.add_event("radar_signal", str(signal.get("timestamp", utc_now_iso())), signal)
            log_event(
                self.logger,
                LogCategory.RADAR_EVENT,
                "Radar signal",
                symbol=signal.get("symbol"),
                setup=signal.get("setup") or signal.get("signal_type"),
                confidence=signal.get("confidence"),
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
