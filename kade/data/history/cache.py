"""File-backed 1-minute historical bar cache."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from kade.data.history.session import SessionCoverage, SessionPolicy, classify_session_coverage
from kade.market.structure import Bar
from kade.storage.history_index_store import HistoryIndexStore
from kade.utils.time import utc_now_iso


class HistoryCache:
    def __init__(self, root_dir: Path | str) -> None:
        self.root_dir = Path(root_dir)
        self.index_store = HistoryIndexStore(self.root_dir)
        self._session_index = self._load_index()

    def symbol_timeframe_dir(self, symbol: str, timeframe: str = "1m") -> Path:
        return self.root_dir / symbol.upper() / timeframe

    def _day_path(self, symbol: str, day: date, timeframe: str = "1m") -> Path:
        return self.symbol_timeframe_dir(symbol, timeframe) / f"{day.isoformat()}.json"

    def write_bars(self, symbol: str, bars: list[Bar], timeframe: str = "1m") -> int:
        by_day: dict[date, list[Bar]] = {}
        for bar in sorted(bars, key=lambda item: item.timestamp):
            ts = self._utc(bar.timestamp)
            by_day.setdefault(ts.date(), []).append(
                Bar(
                    symbol=symbol.upper(),
                    timestamp=ts,
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=float(bar.volume),
                )
            )

        files_written = 0
        for day, day_bars in by_day.items():
            path = self._day_path(symbol, day, timeframe)
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = self.load_day(symbol, day, timeframe=timeframe) if path.exists() else []
            merged_by_ts = {self._utc(bar.timestamp): bar for bar in existing}
            for bar in day_bars:
                merged_by_ts[self._utc(bar.timestamp)] = bar
            merged = [merged_by_ts[key] for key in sorted(merged_by_ts.keys())]
            payload = {
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "date": day.isoformat(),
                "bars": [self._bar_payload(bar) for bar in merged],
            }
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            files_written += 1
            self._mark_index_stale(symbol, day, timeframe)
        return files_written

    def load_range(self, symbol: str, start: datetime, end: datetime, timeframe: str = "1m") -> list[Bar]:
        start_utc, end_utc = self._utc(start), self._utc(end)
        bars: list[Bar] = []
        for day in self._iter_dates(start_utc.date(), end_utc.date()):
            path = self._day_path(symbol, day, timeframe)
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            symbol_name = str(payload.get("symbol", symbol.upper()))
            for item in payload.get("bars", []):
                bar = self._bar_from_payload(item, symbol=symbol_name)
                if start_utc <= bar.timestamp <= end_utc:
                    bars.append(bar)
        return sorted(bars, key=lambda item: item.timestamp)

    def get_cached_dates(self, symbol: str, timeframe: str = "1m") -> set[date]:
        directory = self.symbol_timeframe_dir(symbol, timeframe)
        if not directory.exists():
            return set()
        dates: set[date] = set()
        for path in directory.glob("*.json"):
            try:
                dates.add(date.fromisoformat(path.stem))
            except ValueError:
                continue
        return dates

    def load_day(self, symbol: str, day: date, timeframe: str = "1m") -> list[Bar]:
        path = self._day_path(symbol, day, timeframe)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        symbol_name = str(payload.get("symbol", symbol.upper()))
        bars = [self._bar_from_payload(item, symbol=symbol_name) for item in payload.get("bars", [])]
        return sorted(bars, key=lambda item: item.timestamp)

    def session_coverage(
        self,
        symbol: str,
        day: date,
        policy: SessionPolicy,
        timeframe: str = "1m",
    ) -> SessionCoverage:
        indexed = self._coverage_from_index(symbol, day, timeframe)
        if indexed is not None and not self._index_is_stale(symbol, day, timeframe):
            return indexed
        bars = self.load_day(symbol, day, timeframe)
        coverage = classify_session_coverage(day, [self._utc(bar.timestamp) for bar in bars], policy)
        self._save_coverage_index(symbol, day, timeframe, coverage)
        return coverage

    def missing_dates(self, symbol: str, start: datetime, end: datetime, timeframe: str = "1m") -> list[date]:
        start_utc, end_utc = self._utc(start), self._utc(end)
        available = self.get_cached_dates(symbol, timeframe)
        return [day for day in self._iter_dates(start_utc.date(), end_utc.date()) if day not in available]

    def cached_ranges(self, symbol: str, timeframe: str = "1m") -> list[dict[str, str]]:
        days = sorted(self.get_cached_dates(symbol, timeframe))
        if not days:
            return []
        ranges: list[dict[str, str]] = []
        start_day = days[0]
        previous = days[0]
        for day in days[1:]:
            if day == previous + timedelta(days=1):
                previous = day
                continue
            ranges.append({"start": start_day.isoformat(), "end": previous.isoformat()})
            start_day = day
            previous = day
        ranges.append({"start": start_day.isoformat(), "end": previous.isoformat()})
        return ranges

    def index_status(self, symbols: list[str], start_day: date, end_day: date, timeframe: str = "1m") -> dict[str, int]:
        indexed = 0
        stale = 0
        total = 0
        for symbol in symbols:
            for day in self.iter_dates(start_day, end_day):
                total += 1
                if self._coverage_from_index(symbol, day, timeframe) is None:
                    continue
                indexed += 1
                if self._index_is_stale(symbol, day, timeframe):
                    stale += 1
        return {"indexed_days": indexed, "stale_days": stale, "recomputed_days": max(total - indexed, 0)}

    @staticmethod
    def _bar_payload(bar: Bar) -> dict[str, object]:
        return {
            "timestamp": HistoryCache._utc(bar.timestamp).isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }

    @staticmethod
    def _bar_from_payload(payload: dict[str, object], symbol: str) -> Bar:
        return Bar(
            symbol=symbol,
            timestamp=HistoryCache._utc(datetime.fromisoformat(str(payload["timestamp"]))),
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            volume=float(payload["volume"]),
        )

    @staticmethod
    def _utc(ts: datetime) -> datetime:
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    @staticmethod
    def iter_dates(start_day: date, end_day: date) -> list[date]:
        return HistoryCache._iter_dates(start_day, end_day)

    @staticmethod
    def _iter_dates(start_day: date, end_day: date) -> list[date]:
        days: list[date] = []
        cursor = start_day
        while cursor <= end_day:
            days.append(cursor)
            cursor += timedelta(days=1)
        return days

    @staticmethod
    def date_bounds(day: date) -> tuple[datetime, datetime]:
        start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        end = datetime.combine(day, time.max, tzinfo=timezone.utc)
        return start, end

    def _load_index(self) -> dict[str, dict[str, object]]:
        payload = self.index_store.load_index()
        sessions = payload.get("sessions", {})
        return dict(sessions) if isinstance(sessions, dict) else {}

    def _persist_index(self) -> None:
        self.index_store.save_index({"sessions": self._session_index})

    def _index_key(self, symbol: str, day: date, timeframe: str) -> str:
        return f"{symbol.upper()}|{timeframe}|{day.isoformat()}"

    def _coverage_from_index(self, symbol: str, day: date, timeframe: str) -> SessionCoverage | None:
        key = self._index_key(symbol, day, timeframe)
        entry = self._session_index.get(key)
        if not isinstance(entry, dict):
            return None
        windows = []
        for item in entry.get("missing_windows", []):
            if not isinstance(item, dict):
                continue
            start = datetime.fromisoformat(str(item.get("start")))
            end = datetime.fromisoformat(str(item.get("end")))
            windows.append((start, end))
        return SessionCoverage(
            trading_date=day,
            state=str(entry.get("status", "missing")),
            expected_bars=int(entry.get("expected_bar_count", 0)),
            actual_bars=int(entry.get("actual_bar_count", 0)),
            missing_bars=max(int(entry.get("expected_bar_count", 0)) - int(entry.get("actual_bar_count", 0)), 0),
            missing_windows=windows,
            skipped_reason=str(entry.get("skipped_reason")) if entry.get("skipped_reason") else None,
        )

    def _save_coverage_index(self, symbol: str, day: date, timeframe: str, coverage: SessionCoverage) -> None:
        key = self._index_key(symbol, day, timeframe)
        source_path = str(self._day_path(symbol, day, timeframe))
        self._session_index[key] = {
            "symbol": symbol.upper(),
            "date": day.isoformat(),
            "timeframe": timeframe,
            "status": coverage.state,
            "expected_bar_count": coverage.expected_bars,
            "actual_bar_count": coverage.actual_bars,
            "missing_window_count": len(coverage.missing_windows),
            "missing_windows": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in coverage.missing_windows],
            "last_checked_at": utc_now_iso(),
            "source_file": source_path,
            "source_mtime_ns": self._day_path(symbol, day, timeframe).stat().st_mtime_ns if self._day_path(symbol, day, timeframe).exists() else 0,
            "stale": False,
            "skipped_reason": coverage.skipped_reason,
        }
        self._persist_index()

    def _mark_index_stale(self, symbol: str, day: date, timeframe: str) -> None:
        key = self._index_key(symbol, day, timeframe)
        entry = self._session_index.get(key)
        if not isinstance(entry, dict):
            return
        entry["stale"] = True
        self._session_index[key] = entry
        self._persist_index()

    def _index_is_stale(self, symbol: str, day: date, timeframe: str) -> bool:
        key = self._index_key(symbol, day, timeframe)
        entry = self._session_index.get(key)
        if not isinstance(entry, dict):
            return True
        if bool(entry.get("stale", False)):
            return True
        path = self._day_path(symbol, day, timeframe)
        source_mtime_ns = int(entry.get("source_mtime_ns", 0))
        if not path.exists():
            return source_mtime_ns != 0
        return source_mtime_ns != path.stat().st_mtime_ns
