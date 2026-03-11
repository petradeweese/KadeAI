"""Base interface for swappable TTS providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TTSOutput:
    provider: str
    voice: str
    text: str
    generated_at: datetime
    audio_uri: str | None = None
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)


class TTSProvider(ABC):
    provider_name: str

    @abstractmethod
    def synthesize(self, text: str) -> TTSOutput:
        """Return speech payload metadata; playback handled elsewhere."""
