"""Session policy and completeness helpers for 1-minute historical bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SessionPolicy:
    timezone_name: str = "America/New_York"
    session_open: str = "09:30"
    session_close: str = "16:00"
    expected_bars_per_session: int = 390
    partial_session_tolerance: int = 1
    ignore_extended_hours: bool = True
    skip_weekends: bool = True
    holidays: tuple[str, ...] = ()
    early_close_dates: tuple[str, ...] = ()

    def is_trading_day(self, day: date) -> bool:
        if self.skip_weekends and day.weekday() >= 5:
            return False
        return day.isoformat() not in set(self.holidays)

    def skip_reason(self, day: date) -> str | None:
        if self.skip_weekends and day.weekday() >= 5:
            return "weekend"
        if day.isoformat() in set(self.holidays):
            return "holiday"
        return None

    def session_bounds_utc(self, day: date) -> tuple[datetime, datetime]:
        tz = ZoneInfo(self.timezone_name)
        open_local = datetime.combine(day, self._parse_hhmm(self.session_open), tzinfo=tz)
        close_local = datetime.combine(day, self._parse_hhmm(self.session_close), tzinfo=tz)
        return open_local.astimezone(timezone.utc), close_local.astimezone(timezone.utc)

    def expected_timestamps_utc(self, day: date) -> list[datetime]:
        start_utc, end_utc = self.session_bounds_utc(day)
        timestamps: list[datetime] = []
        cursor = start_utc.replace(second=0, microsecond=0)
        while cursor < end_utc:
            timestamps.append(cursor)
            cursor += timedelta(minutes=1)
        if self.expected_bars_per_session > 0:
            return timestamps[: self.expected_bars_per_session]
        return timestamps

    @staticmethod
    def _parse_hhmm(value: str) -> time:
        hh, mm = value.strip().split(":", 1)
        return time(hour=int(hh), minute=int(mm))


@dataclass(frozen=True)
class SessionCoverage:
    trading_date: date
    state: str
    expected_bars: int
    actual_bars: int
    missing_bars: int
    missing_windows: list[tuple[datetime, datetime]]
    skipped_reason: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "date": self.trading_date.isoformat(),
            "state": self.state,
            "expected_bars": self.expected_bars,
            "actual_bars": self.actual_bars,
            "missing_bars": self.missing_bars,
            "missing_windows": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in self.missing_windows],
            "skipped_reason": self.skipped_reason,
        }


def classify_session_coverage(day: date, timestamps: list[datetime], policy: SessionPolicy) -> SessionCoverage:
    if not policy.is_trading_day(day):
        return SessionCoverage(
            trading_date=day,
            state="skipped_non_session",
            expected_bars=0,
            actual_bars=0,
            missing_bars=0,
            missing_windows=[],
            skipped_reason=policy.skip_reason(day),
        )
    expected = policy.expected_timestamps_utc(day)
    expected_set = set(expected)
    seen = {ts.replace(second=0, microsecond=0) for ts in timestamps if ts.replace(second=0, microsecond=0) in expected_set}
    missing = sorted(expected_set - seen)
    windows = _group_missing_windows(missing)
    expected_count = len(expected)
    actual_count = len(seen)
    missing_count = len(missing)
    if actual_count == 0:
        state = "missing"
    elif missing_count <= policy.partial_session_tolerance:
        state = "complete"
    else:
        state = "partial"
    return SessionCoverage(
        trading_date=day,
        state=state,
        expected_bars=expected_count,
        actual_bars=actual_count,
        missing_bars=missing_count,
        missing_windows=windows,
    )


def _group_missing_windows(missing_timestamps: list[datetime]) -> list[tuple[datetime, datetime]]:
    if not missing_timestamps:
        return []
    windows: list[tuple[datetime, datetime]] = []
    start = missing_timestamps[0]
    previous = missing_timestamps[0]
    for ts in missing_timestamps[1:]:
        if ts == previous + timedelta(minutes=1):
            previous = ts
            continue
        windows.append((start, previous + timedelta(minutes=1)))
        start = ts
        previous = ts
    windows.append((start, previous + timedelta(minutes=1)))
    return windows
