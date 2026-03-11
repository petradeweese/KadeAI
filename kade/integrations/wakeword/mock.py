"""Mock wake-word detector for always-on listening simulation."""

from __future__ import annotations

from datetime import datetime

from kade.integrations.health import ProviderHealth
from kade.integrations.wakeword.base import WakeWordDetector
from kade.voice.models import WakeWordEvent
from kade.utils.time import utc_now


class MockWakeWordDetector(WakeWordDetector):
    provider_name = "mock"

    def __init__(self, wake_word: str = "Kade") -> None:
        self.wake_word = wake_word

    def detect(self, text_sample: str, now: datetime | None = None) -> WakeWordEvent | None:
        now = now or utc_now()
        if self.wake_word.lower() in text_sample.lower():
            return WakeWordEvent(wake_word=self.wake_word, detected_at=now, source=self.provider_name)
        return None

    def developer_trigger(self, now: datetime | None = None) -> WakeWordEvent:
        return WakeWordEvent(wake_word=self.wake_word, detected_at=now or utc_now(), source="developer")

    def health_snapshot(self, active: bool) -> ProviderHealth:
        return ProviderHealth(
            provider_type="wakeword",
            provider_name=self.provider_name,
            state="mock",
            active=active,
            metadata={"wake_word": self.wake_word, "deterministic": True},
        )
