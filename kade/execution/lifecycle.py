"""Deterministic execution lifecycle state machine scaffolding for future broker integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


VALID_TRANSITIONS: dict[str, set[str]] = {
    "staged": {"confirmed", "cancelled", "expired", "rejected"},
    "confirmed": {"submitted", "cancelled", "expired", "rejected"},
    "submitted": {"partially_filled", "filled", "cancelled", "rejected", "expired"},
    "partially_filled": {"partially_filled", "filled", "cancelled", "expired", "rejected"},
    "filled": set(),
    "cancelled": set(),
    "rejected": set(),
    "expired": set(),
}


@dataclass(frozen=True)
class ExecutionLifecycleEvent:
    from_state: str
    to_state: str
    reason: str
    happened_at: str


@dataclass
class ExecutionLifecycle:
    state: str = "staged"
    events: list[ExecutionLifecycleEvent] = field(default_factory=list)

    def transition(self, to_state: str, reason: str, now: datetime | None = None) -> bool:
        if to_state not in VALID_TRANSITIONS.get(self.state, set()):
            return False
        now = now or datetime.utcnow()
        self.events.append(
            ExecutionLifecycleEvent(
                from_state=self.state,
                to_state=to_state,
                reason=reason,
                happened_at=now.isoformat(),
            )
        )
        self.state = to_state
        return True

    def snapshot(self) -> dict[str, object]:
        return {
            "state": self.state,
            "events": [event.__dict__ for event in self.events],
        }
