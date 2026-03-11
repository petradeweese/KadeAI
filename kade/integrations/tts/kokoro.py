"""Kokoro TTS provider integration boundary (mockable for development)."""

from __future__ import annotations

from datetime import datetime

from kade.integrations.tts.base import TTSOutput, TTSProvider


class KokoroTTSProvider(TTSProvider):
    provider_name = "kokoro"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        config = config or {}
        self.voice = str(config.get("voice", "Puck"))
        self.mock_synthesis = bool(config.get("mock_synthesis", True))
        self.model = str(config.get("model", "kokoro-v1"))

    def synthesize(self, text: str) -> TTSOutput:
        metadata = {"model": self.model, "mock_synthesis": self.mock_synthesis}
        audio_uri = None
        if self.mock_synthesis:
            audio_uri = f"mock://kokoro/{self.voice.lower()}/{abs(hash(text)) % 100000}"
        return TTSOutput(
            provider=self.provider_name,
            voice=self.voice,
            text=text,
            generated_at=datetime.utcnow(),
            audio_uri=audio_uri,
            metadata=metadata,
        )
