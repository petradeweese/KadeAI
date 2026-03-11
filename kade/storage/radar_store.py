"""Persistence boundary for radar event history."""

from __future__ import annotations

from pathlib import Path

from kade.storage.base import JsonFileStore


class RadarStore(JsonFileStore):
    def __init__(self, root_dir: Path) -> None:
        super().__init__(root_dir=root_dir, filename="radar_history.json")

    def load_events(self) -> list[dict[str, object]]:
        payload = self.load(default={})
        return list(payload.get("events", []))

    def save_events(self, events: list[dict[str, object]]) -> None:
        self.save({"events": events})
