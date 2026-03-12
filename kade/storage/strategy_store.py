"""Persistence for strategy intelligence snapshots."""

from __future__ import annotations

from pathlib import Path

from kade.storage.base import JsonFileStore


class StrategyStore(JsonFileStore):
    def __init__(self, root_dir: Path) -> None:
        super().__init__(root_dir=root_dir, filename="strategy_runtime.json")

    def load_runtime(self) -> dict[str, object]:
        payload = self.load(default={})
        return {
            "latest_strategy_snapshot": dict(payload.get("latest_strategy_snapshot", {})),
            "strategy_history": list(payload.get("strategy_history", [])),
        }

    def save_runtime(self, payload: dict[str, object]) -> None:
        self.save(payload)
