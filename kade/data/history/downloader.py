"""Downloader that fetches only missing 1-minute ranges and fills local history cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time

from kade.data.history.cache import HistoryCache
from kade.data.history.models import DownloadSummary
from kade.data.history.session import SessionPolicy
from kade.integrations.marketdata.base import MarketDataProvider
from kade.logging_utils import LogCategory, log_event
from kade.utils.time import utc_now_iso


@dataclass
class HistoryDownloadConfig:
    timeframe: str = "1m"
    chunk_days: int = 5
    requests_per_minute: int = 180
    pacing_sleep_seconds: float = 0.35
    request_window_minutes: int = 390
    session_timezone: str = "America/New_York"
    session_open: str = "09:30"
    session_close: str = "16:00"
    expected_bars_per_session: int = 390
    partial_session_tolerance: int = 1
    ignore_extended_hours: bool = True


class HistoryDownloader:
    def __init__(
        self,
        provider: MarketDataProvider,
        cache: HistoryCache,
        logger: object,
        config: HistoryDownloadConfig,
        sleeper: callable | None = None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.logger = logger
        self.config = config
        self._sleeper = sleeper or time.sleep

    def download_missing(self, symbols: list[str], start: datetime, end: datetime) -> DownloadSummary:
        started = utc_now_iso()
        requests_made = 0
        bars_downloaded = 0
        files_written = 0
        skipped = 0
        missing_dates_total = 0
        sessions_checked = 0
        sessions_complete = 0
        sessions_partial = 0
        sessions_missing = 0
        missing_windows_requested = 0
        request_windows: list[dict[str, str]] = []
        policy = SessionPolicy(
            timezone_name=self.config.session_timezone,
            session_open=self.config.session_open,
            session_close=self.config.session_close,
            expected_bars_per_session=self.config.expected_bars_per_session,
            partial_session_tolerance=self.config.partial_session_tolerance,
            ignore_extended_hours=self.config.ignore_extended_hours,
        )

        for symbol in symbols:
            missing_dates = self.cache.missing_dates(symbol, start, end, timeframe=self.config.timeframe)
            missing_dates_total += len(missing_dates)
            skipped += len(self.cache.get_cached_dates(symbol, timeframe=self.config.timeframe))
            session_windows, counts = self._missing_windows_for_symbol(symbol, start, end, policy)
            sessions_checked += counts["checked"]
            sessions_complete += counts["complete"]
            sessions_partial += counts["partial"]
            sessions_missing += counts["missing"]
            for window_start, window_end in session_windows:
                missing_windows_requested += 1
                self._pace(requests_made)
                bars = self.provider.get_historical_bars(symbol, self.config.timeframe, window_start, window_end)
                requests_made += 1
                bars_downloaded += len(bars)
                files_written += self.cache.write_bars(symbol, bars, timeframe=self.config.timeframe)
                request_windows.append({"symbol": symbol, "start": window_start.isoformat(), "end": window_end.isoformat()})
                log_event(
                    self.logger,
                    LogCategory.MARKET_EVENT,
                    "Historical bars downloaded",
                    symbol=symbol,
                    requested_start=window_start.isoformat(),
                    requested_end=window_end.isoformat(),
                    bars=len(bars),
                )

        return DownloadSummary(
            symbols=symbols,
            started_at=started,
            completed_at=utc_now_iso(),
            requests_made=requests_made,
            bars_downloaded=bars_downloaded,
            cached_files_written=files_written,
            skipped_cached_dates=skipped,
            missing_dates_requested=missing_dates_total,
            sessions_checked=sessions_checked,
            sessions_complete=sessions_complete,
            sessions_partial=sessions_partial,
            sessions_missing=sessions_missing,
            missing_windows_requested=missing_windows_requested,
            request_windows=request_windows,
        )

    def _missing_windows_for_symbol(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        policy: SessionPolicy,
    ) -> tuple[list[tuple[datetime, datetime]], dict[str, int]]:
        windows: list[tuple[datetime, datetime]] = []
        counts = {"checked": 0, "complete": 0, "partial": 0, "missing": 0}
        start_utc = self._utc(start)
        end_utc = self._utc(end)
        for day in self.cache.iter_dates(start_utc.date(), end_utc.date()):
            coverage = self.cache.session_coverage(symbol, day, policy, timeframe=self.config.timeframe)
            counts["checked"] += 1
            if coverage.state == "complete":
                counts["complete"] += 1
                continue
            counts[coverage.state] += 1
            for missing_start, missing_end in self._chunk_windows(coverage.missing_windows):
                clipped_start = max(start_utc, missing_start)
                clipped_end = min(end_utc, missing_end)
                if clipped_start < clipped_end:
                    windows.append((clipped_start, clipped_end))
        return windows, counts

    def _chunk_windows(self, windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
        chunked: list[tuple[datetime, datetime]] = []
        for start, end in windows:
            cursor = start
            while cursor < end:
                chunk_end = min(end, cursor + timedelta(minutes=self.config.request_window_minutes))
                chunked.append((cursor, chunk_end))
                cursor = chunk_end
        return chunked

    @staticmethod
    def _utc(ts: datetime) -> datetime:
        return ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    def _pace(self, requests_made: int) -> None:
        if requests_made <= 0:
            return
        if self.config.requests_per_minute > 0:
            min_gap = 60.0 / float(self.config.requests_per_minute)
            sleep_s = max(min_gap, self.config.pacing_sleep_seconds)
            self._sleeper(sleep_s)
