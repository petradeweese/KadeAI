"""Deterministic command replay tooling for local debug workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path

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

    def replay_command(self, index: int) -> dict[str, object] | None:
        if index < 0 or index >= len(self.records):
            return None
        record = self.records[index].__dict__
        self.last_replay = {
            "requested_index": index,
            "returned": 1,
            "item": record,
            "generated_at": utc_now_iso(),
        }
        return record

    def replay_session(self) -> list[dict[str, object]]:
        return self.replay_recent(len(self.records))

    def export_replay_log(self, path: str = ".kade_storage/replay_log.json") -> str:
        payload = {
            "generated_at": utc_now_iso(),
            "retention_limit": self.retention_limit,
            "records": [r.__dict__ for r in self.records],
        }
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(output)

    def snapshot(self) -> dict[str, object]:
        return {
            "retention_limit": self.retention_limit,
            "records": [r.__dict__ for r in self.records],
            "last_replay": self.last_replay,
        }
