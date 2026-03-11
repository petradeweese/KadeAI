"""Base interface for wake-word detection providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from kade.voice.models import WakeWordEvent


class WakeWordDetector(ABC):
    provider_name: str

    @abstractmethod
    def detect(self, text_sample: str, now: datetime | None = None) -> WakeWordEvent | None:
        """Inspect a sample and emit a wake-word event when matched."""
