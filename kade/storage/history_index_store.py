"""Persistence for per-day historical completeness index."""

from __future__ import annotations

from pathlib import Path

from kade.storage.base import JsonFileStore


class HistoryIndexStore(JsonFileStore):
    def __init__(self, root_dir: Path) -> None:
        super().__init__(root_dir=root_dir, filename="history_session_index.json")

    def load_index(self) -> dict[str, object]:
        payload = self.load(default={})
        return dict(payload)

    def save_index(self, payload: dict[str, object]) -> None:
        self.save(payload)
