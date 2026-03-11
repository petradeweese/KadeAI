"""Whisper-compatible STT adapter boundary with deterministic fallback behavior."""

from __future__ import annotations

from datetime import datetime

from kade.integrations.health import ProviderHealth
from kade.integrations.stt.base import STTProvider
from kade.voice.models import Transcript
from kade.utils.time import utc_now


class WhisperSTTProvider(STTProvider):
    provider_name = "whisper"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        cfg = config or {}
        self.model = str(cfg.get("model", "tiny.en"))
        self.language = str(cfg.get("language", "en"))
        self.temperature = float(cfg.get("temperature", 0.0))
        self.enabled = bool(cfg.get("enabled", False))
        self.runtime_mode = str(cfg.get("runtime_mode", "deterministic_text"))
        self.supports_realtime_audio = bool(cfg.get("supports_realtime_audio", False))
        self.supports_deterministic_text = bool(cfg.get("supports_deterministic_text", True))

    def transcribe(self, audio_hint: str) -> Transcript:
        text = audio_hint.strip() or ""
        return Transcript(
            text=text,
            received_at=utc_now(),
            provider=self.provider_name,
            metadata={
                "model": self.model,
                "language": self.language,
                "temperature": self.temperature,
                "runtime_mode": self.runtime_mode,
                "supports_realtime_audio": self.supports_realtime_audio,
                "supports_deterministic_text": self.supports_deterministic_text,
                "enabled": self.enabled,
                "deterministic": self.runtime_mode.startswith("deterministic"),
                "supports_deterministic_text": self.supports_deterministic_text,
            },
        )

    def developer_transcript(self, text: str) -> Transcript:
        return Transcript(
            text=text,
            received_at=utc_now(),
            provider=self.provider_name,
            metadata={"source": "developer", "model": self.model, "runtime_mode": self.runtime_mode},
        )

    def health_snapshot(self, active: bool) -> ProviderHealth:
        if not self.enabled and self.runtime_mode.startswith("deterministic"):
            state = "mock"
        elif self.enabled and self.supports_realtime_audio:
            state = "ready"
        elif self.enabled:
            state = "degraded"
        else:
            state = "disabled"
        return ProviderHealth(
            provider_type="stt",
            provider_name=self.provider_name,
            state=state,
            active=active,
            metadata={
                "model": self.model,
                "language": self.language,
                "temperature": self.temperature,
                "runtime_mode": self.runtime_mode,
                "supports_realtime_audio": self.supports_realtime_audio,
                "supports_deterministic_text": self.supports_deterministic_text,
                "enabled": self.enabled,
            },
        )
