"""Text-first and voice-enabled interaction orchestration for local runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from logging import Logger

from kade.integrations.stt.base import STTProvider
from kade.logging_utils import LogCategory, get_logger, log_event
from kade.voice.models import Transcript, WakeWordEvent
from kade.voice.orchestrator import VoiceOrchestrator


@dataclass
class InteractionRuntimeState:
    runtime_mode: str
    voice_runtime_enabled: bool
    text_command_input_enabled: bool
    wakeword_enabled: bool
    stt_enabled: bool
    tts_enabled: bool
    command_history_limit: int = 25
    current_typed_command: str = ""
    latest_command_result: dict[str, object] = field(default_factory=dict)
    latest_advisor_or_status: dict[str, object] = field(default_factory=dict)
    recent_commands: list[dict[str, object]] = field(default_factory=list)

    def retain_history(self) -> None:
        self.recent_commands = self.recent_commands[-self.command_history_limit :]


class InteractionOrchestrator:
    def __init__(
        self,
        voice_orchestrator: VoiceOrchestrator,
        stt_provider: STTProvider,
        state: InteractionRuntimeState,
        logger: Logger | None = None,
    ) -> None:
        self.voice_orchestrator = voice_orchestrator
        self.stt_provider = stt_provider
        self.state = state
        self.logger = logger or get_logger(__name__)

    def submit_text_command(self, command: str, now: datetime | None = None) -> dict[str, object]:
        now = now or datetime.utcnow()
        log_event(self.logger, LogCategory.VOICE_EVENT, "Text command received", runtime_mode=self.state.runtime_mode)
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

        self._record(command=command, result=result, source="text", now=now)
        return result

    def process_voice_sample(self, audio_hint: str, now: datetime | None = None) -> dict[str, object] | None:
        now = now or datetime.utcnow()
        if not self.state.voice_runtime_enabled or not self.state.wakeword_enabled or not self.state.stt_enabled:
            log_event(self.logger, LogCategory.VOICE_EVENT, "Voice runtime disabled", runtime_mode=self.state.runtime_mode)
            return None

        if not self.voice_orchestrator.process_wake_sample(audio_hint, now=now):
            return None

        transcript = self.stt_provider.transcribe(audio_hint)
        log_event(self.logger, LogCategory.VOICE_EVENT, "STT backend invoked", provider=transcript.provider)
        result = self.voice_orchestrator.process_transcript(transcript, now=now)
        if result:
            self._record(command=transcript.text, result=result, source="voice", now=now)
        return result

    def dashboard_payload(self) -> dict[str, object]:
        payload = self.voice_orchestrator.dashboard_payload()
        payload.update(
            {
                "runtime_mode": self.state.runtime_mode,
                "text_command_input_enabled": self.state.text_command_input_enabled,
                "voice_runtime_enabled": self.state.voice_runtime_enabled,
                "wakeword_enabled": self.state.wakeword_enabled,
                "stt_enabled": self.state.stt_enabled,
                "tts_enabled": self.state.tts_enabled,
                "current_typed_command": self.state.current_typed_command,
                "latest_command_result": self.state.latest_command_result,
                "latest_advisor_or_status": self.state.latest_advisor_or_status,
                "recent_commands": self.state.recent_commands,
            }
        )
        return payload

    def _record(self, command: str, result: dict[str, object], source: str, now: datetime) -> None:
        self.state.latest_command_result = result
        if result.get("intent") in {"status", "radar", "symbol_opinion", "symbol_status", "market_overview"}:
            self.state.latest_advisor_or_status = result
        self.state.recent_commands.append(
            {
                "source": source,
                "command": command,
                "intent": result.get("intent"),
                "spoken_text": result.get("spoken_text"),
                "timestamp": now.isoformat(),
            }
        )
        self.state.retain_history()
