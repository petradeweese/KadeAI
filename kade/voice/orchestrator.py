"""Voice session orchestration for always-listening wake-word pipeline."""

from __future__ import annotations

from datetime import datetime
from logging import Logger

from kade.integrations.tts.base import TTSProvider
from kade.integrations.wakeword.base import WakeWordDetector
from kade.logging_utils import LogCategory, get_logger, log_event
from kade.voice.formatter import SpokenResponseFormatter
from kade.voice.models import Transcript, VoiceCommandEvent, VoiceSessionState, WakeWordEvent
from kade.voice.router import VoiceCommandRouter


class VoiceOrchestrator:
    def __init__(
        self,
        wakeword_detector: WakeWordDetector,
        router: VoiceCommandRouter,
        formatter: SpokenResponseFormatter,
        tts_provider: TTSProvider,
        state: VoiceSessionState,
        logger: Logger | None = None,
        enable_tts: bool = True,
    ) -> None:
        self.wakeword_detector = wakeword_detector
        self.router = router
        self.formatter = formatter
        self.tts_provider = tts_provider
        self.state = state
        self.logger = logger or get_logger(__name__)
        self.enable_tts = enable_tts

    def process_wake_sample(self, text_sample: str, now: datetime | None = None) -> bool:
        now = now or datetime.utcnow()
        event = self.wakeword_detector.detect(text_sample, now=now)
        if not event:
            return False
        return self.handle_wake_event(event)

    def handle_wake_event(self, event: WakeWordEvent) -> bool:
        if not self.state.can_accept_wake(event.detected_at):
            return False
        self.state.open_command_window(event.detected_at)
        log_event(self.logger, LogCategory.VOICE_EVENT, "Wake word detected", wake_word=event.wake_word)
        return True

    def process_transcript(self, transcript: Transcript, now: datetime | None = None) -> dict[str, object] | None:
        now = now or datetime.utcnow()
        if not self.state.command_window_active(now):
            return None

        self.state.last_transcript = transcript.text
        log_event(self.logger, LogCategory.VOICE_EVENT, "Transcript received", transcript=transcript.text)

        routed = self.router.route(transcript.text, self.state.current_mode)
        log_event(self.logger, LogCategory.VOICE_EVENT, "Command routed", intent=routed.intent)

        if routed.mode_after:
            self.state.current_mode = routed.mode_after
            log_event(self.logger, LogCategory.VOICE_EVENT, "Mode changed", mode=self.state.current_mode)
        if routed.intent == "done_for_day":
            self.state.done_for_day = True
        if routed.intent == "emergency_shutdown":
            self.state.emergency_shutdown = True

        spoken = self.formatter.format(routed, self.state.current_mode)
        log_event(self.logger, LogCategory.VOICE_EVENT, "Response formatted", response_type=spoken.response_type)

        if self.enable_tts:
            tts_output = self.tts_provider.synthesize(spoken.text)
            log_event(
                self.logger,
                LogCategory.VOICE_EVENT,
                "TTS provider invoked",
                provider=tts_output.provider,
                voice=tts_output.voice,
            )
        else:
            tts_output = self.tts_provider.synthesize("")
            tts_output = tts_output.__class__(
                provider="disabled",
                voice="none",
                text=spoken.text,
                generated_at=tts_output.generated_at,
                audio_uri=None,
                metadata={"reason": "tts_disabled"},
            )

        self.state.last_spoken_response = spoken.text
        self.state.recent_events.append(
            VoiceCommandEvent(
                intent=routed.intent,
                command=routed.command,
                transcript=transcript.text,
                spoken_response=spoken.text,
                happened_at=now,
            )
        )
        self.state.recent_events = self.state.recent_events[-10:]
        self.state.close_command_window(now)

        return {
            "intent": routed.intent,
            "response_type": spoken.response_type,
            "spoken_text": spoken.text,
            "tts": {
                "provider": tts_output.provider,
                "voice": tts_output.voice,
                "audio_uri": tts_output.audio_uri,
                "metadata": tts_output.metadata,
            },
        }

    def dashboard_payload(self) -> dict[str, object]:
        return {
            "listening_mode": self.state.listening_mode,
            "wake_state": self.state.wake_state,
            "current_mode": self.state.current_mode,
            "last_transcript": self.state.last_transcript,
            "last_spoken_response": self.state.last_spoken_response,
            "tts_provider": self.tts_provider.provider_name,
            "voice_profile": getattr(self.tts_provider, "voice", "unknown"),
            "done_for_day": self.state.done_for_day,
            "emergency_shutdown": self.state.emergency_shutdown,
            "recent_voice_events": [
                {
                    "intent": event.intent,
                    "command": event.command,
                    "transcript": event.transcript,
                    "spoken_response": event.spoken_response,
                    "happened_at": event.happened_at.isoformat(),
                }
                for event in self.state.recent_events
            ],
        }
