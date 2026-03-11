"""Persistence boundary for conversation memory."""

from __future__ import annotations

from pathlib import Path

from kade.storage.base import JsonFileStore


class MemoryStore(JsonFileStore):
    def __init__(self, root_dir: Path) -> None:
        super().__init__(root_dir=root_dir, filename="memory.json")

    def load_memory(self) -> dict[str, list[dict[str, object]]]:
        payload = self.load(default={})
        return {
            "intents": list(payload.get("intents", [])),
            "responses": list(payload.get("responses", [])),
            "notes": list(payload.get("notes", [])),
        }

    def save_memory(self, memory_payload: dict[str, list[dict[str, object]]]) -> None:
        self.save(memory_payload)
