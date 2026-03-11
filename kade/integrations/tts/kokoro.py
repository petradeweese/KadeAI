"""Kokoro TTS provider integration boundary (mockable for development)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from kade.integrations.health import ProviderHealth
from kade.integrations.tts.base import TTSOutput, TTSProvider


class KokoroTTSProvider(TTSProvider):
    provider_name = "kokoro"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        config = config or {}
        self.voice = str(config.get("voice", "Puck"))
        self.mock_synthesis = bool(config.get("mock_synthesis", True))
        self.model = str(config.get("model", "kokoro-v1"))
        self.output_mode = str(config.get("output_mode", "artifact_uri"))
        self.artifact_dir = Path(str(config.get("artifact_dir", ".kade_storage/tts")))
        self.artifact_uri_prefix = str(config.get("artifact_uri_prefix", "file://"))

    def synthesize(self, text: str) -> TTSOutput:
        metadata = {
            "model": self.model,
            "mock_synthesis": self.mock_synthesis,
            "artifact_ready": True,
            "output_mode": self.output_mode,
        }
        audio_uri = None
        if text.strip():
            slug = f"{abs(hash(text)) % 100000}.txt"
            artifact_path = self.artifact_dir / slug
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(text, encoding="utf-8")
            metadata["artifact_path"] = artifact_path.as_posix()
            audio_uri = f"{self.artifact_uri_prefix}{artifact_path.as_posix()}"
        if self.mock_synthesis:
            metadata["provider_mode"] = "mock"
            audio_uri = f"mock://kokoro/{self.voice.lower()}/{abs(hash(text)) % 100000}"
        else:
            metadata["provider_mode"] = "runtime"
        return TTSOutput(
            provider=self.provider_name,
            voice=self.voice,
            text=text,
            generated_at=datetime.utcnow(),
            audio_uri=audio_uri,
            metadata=metadata,
        )

    def health_snapshot(self, active: bool) -> ProviderHealth:
        state = "mock" if self.mock_synthesis else "ready"
        return ProviderHealth(
            provider_type="tts",
            provider_name=self.provider_name,
            state=state,
            active=active,
            metadata={
                "voice": self.voice,
                "model": self.model,
                "output_mode": self.output_mode,
                "artifact_dir": self.artifact_dir.as_posix(),
            },
        )
