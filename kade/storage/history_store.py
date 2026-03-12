"""Persistence for historical downloader/cache status snapshots."""

from __future__ import annotations

from pathlib import Path

from kade.storage.base import JsonFileStore


class HistoryStore(JsonFileStore):
    def __init__(self, root_dir: Path) -> None:
        super().__init__(root_dir=root_dir, filename="history_runtime.json")

    def load_runtime(self) -> dict[str, object]:
        payload = self.load(default={})
        return {
            "last_download": dict(payload.get("last_download", {})),
            "cache_status": dict(payload.get("cache_status", {})),
            "recent_downloads": list(payload.get("recent_downloads", [])),
            "index_status": dict(payload.get("index_status", {})),
        }

    def save_runtime(self, payload: dict[str, object]) -> None:
        self.save(payload)
