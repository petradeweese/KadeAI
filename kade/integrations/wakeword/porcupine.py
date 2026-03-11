"""Porcupine-compatible wake-word adapter boundary with deterministic local matching."""

from __future__ import annotations

from datetime import datetime

from kade.integrations.wakeword.base import WakeWordDetector
from kade.voice.models import WakeWordEvent


class PorcupineWakeWordDetector(WakeWordDetector):
    provider_name = "porcupine"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        cfg = config or {}
        self.keyword = str(cfg.get("keyword", "Kade"))
        self.sensitivity = float(cfg.get("sensitivity", 0.5))
        self.enabled = bool(cfg.get("enabled", False))

    def detect(self, text_sample: str, now: datetime | None = None) -> WakeWordEvent | None:
        now = now or datetime.utcnow()
        if self.keyword.lower() in text_sample.lower():
            return WakeWordEvent(
                wake_word=self.keyword,
                detected_at=now,
                source=self.provider_name,
            )
        return None
