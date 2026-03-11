"""Persistence boundary for session/day state and advisor history."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from kade.storage.base import JsonFileStore
from kade.utils.time import utc_now


class SessionStore(JsonFileStore):
    def __init__(self, root_dir: Path) -> None:
        super().__init__(root_dir=root_dir, filename="session.json")

    def load_session(self) -> dict[str, object]:
        payload = self.load(default={})
        return {
            "day_key": payload.get("day_key"),
            "trades_today": int(payload.get("trades_today", 0) or 0),
            "daily_realized_pnl": float(payload.get("daily_realized_pnl", 0.0) or 0.0),
            "done_for_day": bool(payload.get("done_for_day", False)),
            "emergency_shutdown": bool(payload.get("emergency_shutdown", False)),
            "recent_voice_events": list(payload.get("recent_voice_events", [])),
            "advisor_history": list(payload.get("advisor_history", [])),
            "last_rollover_at": payload.get("last_rollover_at"),
        }

    def save_session(self, payload: dict[str, object]) -> None:
        self.save(payload)


def rollover_session(payload: dict[str, object], now: datetime | None = None) -> dict[str, object]:
    now = now or utc_now()
    day_key = now.date().isoformat()
    if payload.get("day_key") == day_key:
        payload.setdefault("day_key", day_key)
        return payload
    next_payload = dict(payload)
    next_payload.update(
        {
            "day_key": day_key,
            "trades_today": 0,
            "daily_realized_pnl": 0.0,
            "done_for_day": False,
            "recent_voice_events": [],
            "last_rollover_at": now.isoformat(),
        }
    )
    return next_payload
