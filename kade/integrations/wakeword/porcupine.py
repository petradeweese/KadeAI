"""Porcupine-compatible wake-word adapter boundary with deterministic local matching."""

from __future__ import annotations

from datetime import datetime

from kade.integrations.health import ProviderHealth
from kade.integrations.wakeword.base import WakeWordDetector
from kade.voice.models import WakeWordEvent
from kade.utils.time import utc_now


class PorcupineWakeWordDetector(WakeWordDetector):
    provider_name = "porcupine"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        cfg = config or {}
        self.keyword = str(cfg.get("keyword", "Kade"))
        self.sensitivity = float(cfg.get("sensitivity", 0.5))
        self.enabled = bool(cfg.get("enabled", False))
        self.access_key_present = bool(str(cfg.get("access_key", "")).strip())

    def detect(self, text_sample: str, now: datetime | None = None) -> WakeWordEvent | None:
        now = now or utc_now()
        if self.keyword.lower() in text_sample.lower():
            return WakeWordEvent(
                wake_word=self.keyword,
                detected_at=now,
                source=self.provider_name,
            )
        return None

    def health_snapshot(self, active: bool) -> ProviderHealth:
        if not self.enabled:
            state = "disabled"
        elif not self.access_key_present:
            state = "degraded"
        else:
            state = "ready"
        return ProviderHealth(
            provider_type="wakeword",
            provider_name=self.provider_name,
            state=state,
            active=active,
            metadata={
                "keyword": self.keyword,
                "sensitivity": self.sensitivity,
                "access_key_present": self.access_key_present,
            },
        )
