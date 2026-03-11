"""Conversation and session memory primitives for Phase 5."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from logging import Logger
from typing import Callable

from kade.brain.models import MemoryItem
from kade.logging_utils import LogCategory, get_logger, log_event


class ConversationMemory:
    def __init__(self, config: dict, logger: Logger | None = None, autosave: Callable[[], None] | None = None) -> None:
        self.config = config
        self.logger = logger or get_logger(__name__)
        self.autosave = autosave
        memory_cfg = config.get("memory", {})
        self.recent_intents = deque(maxlen=memory_cfg.get("recent_intents_limit", 25))
        self.recent_responses = deque(maxlen=memory_cfg.get("recent_responses_limit", 25))
        self.structured_notes = deque(maxlen=memory_cfg.get("structured_notes_limit", 50))

    def record_user_intent(self, content: str, symbol: str | None = None, **metadata: object) -> MemoryItem:
        item = self._build_item("user_intent", content, symbol, metadata)
        self.recent_intents.append(item)
        self._log_write(item)
        self._trigger_autosave()
        return item

    def record_kade_response(self, content: str, symbol: str | None = None, **metadata: object) -> MemoryItem:
        item = self._build_item("kade_response", content, symbol, metadata)
        self.recent_responses.append(item)
        self._log_write(item)
        self._trigger_autosave()
        return item

    def add_structured_note(self, content: str, symbol: str | None = None, **metadata: object) -> MemoryItem:
        item = self._build_item("structured_note", content, symbol, metadata)
        self.structured_notes.append(item)
        self._log_write(item)
        self._trigger_autosave()
        return item

    def restore(self, payload: dict[str, list[dict[str, object]]]) -> None:
        self.recent_intents.clear()
        self.recent_responses.clear()
        self.structured_notes.clear()
        for raw in payload.get("intents", []):
            self.recent_intents.append(self._deserialize(raw))
        for raw in payload.get("responses", []):
            self.recent_responses.append(self._deserialize(raw))
        for raw in payload.get("notes", []):
            self.structured_notes.append(self._deserialize(raw))

    def recall_for_symbol(self, symbol: str, limit: int = 8) -> list[MemoryItem]:
        pooled = [*self.recent_intents, *self.recent_responses, *self.structured_notes]
        filtered = [item for item in pooled if item.symbol in {None, symbol}]
        return sorted(filtered, key=lambda item: item.created_at, reverse=True)[:limit]

    def recent_items(self, limit: int = 10) -> list[MemoryItem]:
        pooled = [*self.recent_intents, *self.recent_responses, *self.structured_notes]
        return sorted(pooled, key=lambda item: item.created_at, reverse=True)[:limit]

    def snapshot(self, limit: int = 10) -> dict[str, list[dict[str, object]]]:
        return {
            "recent": [self._serialize(item) for item in self.recent_items(limit)],
            "intents": [self._serialize(item) for item in list(self.recent_intents)],
            "responses": [self._serialize(item) for item in list(self.recent_responses)],
            "notes": [self._serialize(item) for item in list(self.structured_notes)],
        }

    def _build_item(
        self,
        item_type: str,
        content: str,
        symbol: str | None,
        metadata: dict[str, object],
    ) -> MemoryItem:
        now = datetime.utcnow()
        item_id = f"{item_type}-{int(now.timestamp() * 1000)}-{len(content)}"
        normalized_meta = {key: value for key, value in metadata.items() if isinstance(value, (str, int, float, bool))}
        return MemoryItem(
            item_id=item_id,
            item_type=item_type,
            symbol=symbol,
            content=content,
            created_at=now,
            metadata=normalized_meta,
        )

    def _serialize(self, item: MemoryItem) -> dict[str, object]:
        return {
            "item_id": item.item_id,
            "item_type": item.item_type,
            "symbol": item.symbol,
            "content": item.content,
            "created_at": item.created_at.isoformat(),
            "metadata": item.metadata,
        }

    def _deserialize(self, payload: dict[str, object]) -> MemoryItem:
        return MemoryItem(
            item_id=str(payload.get("item_id", "missing-item-id")),
            item_type=str(payload.get("item_type", "unknown")),
            symbol=payload.get("symbol") if isinstance(payload.get("symbol"), str) else None,
            content=str(payload.get("content", "")),
            created_at=datetime.fromisoformat(str(payload.get("created_at"))),
            metadata=payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {},
        )

    def _log_write(self, item: MemoryItem) -> None:
        log_event(
            self.logger,
            LogCategory.REASONING_EVENT,
            "Memory write",
            item_type=item.item_type,
            symbol=item.symbol,
            item_id=item.item_id,
        )

    def _trigger_autosave(self) -> None:
        if self.autosave:
            self.autosave()
