"""Downloader that fetches only missing 1-minute ranges and fills local history cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import time

from kade.data.history.cache import HistoryCache
from kade.data.history.models import DownloadSummary
from kade.integrations.marketdata.base import MarketDataProvider
from kade.logging_utils import LogCategory, log_event
from kade.utils.time import utc_now_iso


@dataclass
class HistoryDownloadConfig:
    timeframe: str = "1m"
    chunk_days: int = 5
    requests_per_minute: int = 180
    pacing_sleep_seconds: float = 0.35


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
        request_windows: list[dict[str, str]] = []

        for symbol in symbols:
            missing_dates = self.cache.missing_dates(symbol, start, end, timeframe=self.config.timeframe)
            missing_dates_total += len(missing_dates)
            skipped += len(self.cache.get_cached_dates(symbol, timeframe=self.config.timeframe))
            for chunk in self._chunk_dates(missing_dates, self.config.chunk_days):
                chunk_start = datetime.combine(chunk[0], datetime.min.time(), tzinfo=start.tzinfo)
                chunk_end = datetime.combine(chunk[-1], datetime.max.time(), tzinfo=end.tzinfo)
                self._pace(requests_made)
                bars = self.provider.get_historical_bars(symbol, self.config.timeframe, chunk_start, chunk_end)
                requests_made += 1
                bars_downloaded += len(bars)
                files_written += self.cache.write_bars(symbol, bars, timeframe=self.config.timeframe)
                request_windows.append({"symbol": symbol, "start": chunk_start.isoformat(), "end": chunk_end.isoformat()})
                log_event(
                    self.logger,
                    LogCategory.MARKET_EVENT,
                    "Historical bars downloaded",
                    symbol=symbol,
                    requested_start=chunk_start.isoformat(),
                    requested_end=chunk_end.isoformat(),
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
            request_windows=request_windows,
        )

    def _pace(self, requests_made: int) -> None:
        if requests_made <= 0:
            return
        if self.config.requests_per_minute > 0:
            min_gap = 60.0 / float(self.config.requests_per_minute)
            sleep_s = max(min_gap, self.config.pacing_sleep_seconds)
            self._sleeper(sleep_s)

    @staticmethod
    def _chunk_dates(days: list[date], chunk_days: int) -> list[list[date]]:
        if not days:
            return []
        chunks: list[list[date]] = []
        cursor = 0
        while cursor < len(days):
            chunks.append(days[cursor : cursor + chunk_days])
            cursor += chunk_days
        return chunks
