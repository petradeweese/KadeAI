"""Persistence boundary for backtest summaries and recent evaluations."""

from __future__ import annotations

from pathlib import Path

from kade.storage.base import JsonFileStore


class BacktestStore(JsonFileStore):
    def __init__(self, root_dir: Path) -> None:
        super().__init__(root_dir=root_dir, filename="backtest_summaries.json")

    def load_summaries(self) -> list[dict[str, object]]:
        payload = self.load(default={})
        return list(payload.get("summaries", []))

    def save_summaries(self, summaries: list[dict[str, object]]) -> None:
        self.save({"summaries": summaries})
