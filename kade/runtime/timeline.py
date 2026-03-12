"""Bounded operator timeline for command, radar, execution, and provider events."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TimelineEvent:
    event_type: str
    timestamp: str
    payload: dict[str, object]


@dataclass
class RuntimeTimeline:
    retention: int = 200
    events: list[TimelineEvent] = field(default_factory=list)

    def add_event(self, event_type: str, timestamp: str, payload: dict[str, object]) -> dict[str, object]:
        event = TimelineEvent(event_type=event_type, timestamp=timestamp, payload=payload)
        self.events.append(event)
        self.events = self.events[-self.retention :]
        return event.__dict__

    def snapshot(self) -> dict[str, object]:
        return {"retention": self.retention, "events": [event.__dict__ for event in self.events]}
