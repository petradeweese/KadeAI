"""Persistence boundary for trade plans and lifecycle events."""

from __future__ import annotations

from pathlib import Path

from kade.storage.base import JsonFileStore


class PlanStore(JsonFileStore):
    def __init__(self, root_dir: Path) -> None:
        super().__init__(root_dir=root_dir, filename="plans.json")

    def load_plans(self) -> dict[str, object]:
        payload = self.load(default={})
        return {
            "plans": list(payload.get("plans", [])),
            "events": list(payload.get("events", [])),
        }

    def save_plans(self, payload: dict[str, object]) -> None:
        self.save(payload)
