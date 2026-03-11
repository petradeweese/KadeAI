"""Base interface for swappable STT providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from kade.integrations.health import ProviderHealth
from kade.voice.models import Transcript


class STTProvider(ABC):
    provider_name: str

    @abstractmethod
    def transcribe(self, audio_hint: str) -> Transcript:
        """Return a deterministic transcript payload for the current command window."""

    @abstractmethod
    def health_snapshot(self, active: bool) -> ProviderHealth:
        """Return current backend readiness and runtime metadata."""
