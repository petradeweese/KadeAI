"""Base file-backed storage helpers for deterministic JSON persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class StoreMetadata:
    path: str
    loaded_at: str | None = None
    saved_at: str | None = None


class JsonFileStore:
    def __init__(self, root_dir: Path, filename: str) -> None:
        self.root_dir = root_dir
        self.path = root_dir / filename
        self.metadata = StoreMetadata(path=str(self.path))

    def load(self, default: Any) -> Any:
        if not self.path.exists():
            self.metadata.loaded_at = datetime.utcnow().isoformat()
            return default
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.metadata.loaded_at = datetime.utcnow().isoformat()
        return payload

    def save(self, payload: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temp_path.replace(self.path)
        self.metadata.saved_at = datetime.utcnow().isoformat()

    def metadata_snapshot(self) -> dict[str, str | None]:
        return {
            "path": self.metadata.path,
            "loaded_at": self.metadata.loaded_at,
            "saved_at": self.metadata.saved_at,
        }
