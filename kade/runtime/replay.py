"""Deterministic command replay tooling for local debug workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from kade.utils.time import utc_now_iso


@dataclass
class ReplayRecord:
    command: str
    intent: str
    spoken_text: str
    provider_mode: str
    source: str
    timestamp: str


@dataclass
class ReplayRuntime:
    retention_limit: int = 40
    records: list[ReplayRecord] = field(default_factory=list)
    last_replay: dict[str, object] = field(default_factory=dict)

    def add_record(self, command: str, result: dict[str, object], source: str, timestamp: datetime) -> None:
        tts_provider = str(dict(result.get("tts", {})).get("provider", "unknown"))
        self.records.append(
            ReplayRecord(
                command=command,
                intent=str(result.get("intent", "unknown")),
                spoken_text=str(result.get("spoken_text", "")),
                provider_mode=tts_provider,
                source=source,
                timestamp=timestamp.isoformat(),
            )
        )
        self.records = self.records[-self.retention_limit :]

    def replay_recent(self, count: int) -> list[dict[str, object]]:
        replay_items = [r.__dict__ for r in self.records[-count:]]
        self.last_replay = {
            "requested": count,
            "returned": len(replay_items),
            "items": replay_items,
            "generated_at": utc_now_iso(),
        }
        return replay_items

    def snapshot(self) -> dict[str, object]:
        return {
            "retention_limit": self.retention_limit,
            "records": [r.__dict__ for r in self.records],
            "last_replay": self.last_replay,
        }
