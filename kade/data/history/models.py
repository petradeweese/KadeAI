"""Models for historical bar caching, downloading, and replay dataset assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from kade.market.structure import Bar


@dataclass(frozen=True)
class DateRange:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class CacheFileSummary:
    symbol: str
    timeframe: str
    trading_date: date
    path: str
    bar_count: int


@dataclass(frozen=True)
class DownloadRequest:
    symbols: list[str]
    start: datetime
    end: datetime


@dataclass(frozen=True)
class DownloadChunk:
    symbol: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class DownloadSummary:
    symbols: list[str]
    started_at: str
    completed_at: str
    requests_made: int
    bars_downloaded: int
    cached_files_written: int
    skipped_cached_dates: int
    missing_dates_requested: int
    request_windows: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class HistoryCacheStatus:
    symbols: list[str]
    date_ranges: dict[str, list[dict[str, str]]]
    missing_ranges: dict[str, list[dict[str, str]]]


@dataclass(frozen=True)
class ResampleSpec:
    source_timeframe: str
    target_timeframe: str
    interval_minutes: int


@dataclass(frozen=True)
class ReplayDataset:
    run_id: str
    symbols: list[str]
    started_at: datetime
    ended_at: datetime
    bars_1m: dict[str, list[Bar]]
