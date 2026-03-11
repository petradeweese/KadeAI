"""Whisper-compatible STT adapter boundary with deterministic fallback behavior."""

from __future__ import annotations

from datetime import datetime

from kade.integrations.stt.base import STTProvider
from kade.voice.models import Transcript


class WhisperSTTProvider(STTProvider):
    provider_name = "whisper"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        cfg = config or {}
        self.model = str(cfg.get("model", "tiny.en"))
        self.language = str(cfg.get("language", "en"))
        self.temperature = float(cfg.get("temperature", 0.0))
        self.mock_runtime = bool(cfg.get("enabled", False)) is False

    def transcribe(self, audio_hint: str) -> Transcript:
        text = audio_hint.strip() or ""
        return Transcript(
            text=text,
            received_at=datetime.utcnow(),
            provider=self.provider_name,
            metadata={
                "model": self.model,
                "language": self.language,
                "temperature": self.temperature,
                "mock_runtime": self.mock_runtime,
            },
        )

    def developer_transcript(self, text: str) -> Transcript:
        return Transcript(
            text=text,
            received_at=datetime.utcnow(),
            provider=self.provider_name,
            metadata={"source": "developer", "model": self.model, "mock_runtime": self.mock_runtime},
        )
