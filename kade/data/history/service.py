"""Developer-friendly orchestration for history download and replay dataset construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kade.data.history.cache import HistoryCache
from kade.data.history.dataset_builder import ReplayDatasetBuilder
from kade.data.history.downloader import HistoryDownloadConfig, HistoryDownloader
from kade.data.history.loader import HistoricalDataLoader
from kade.data.history.models import DownloadSummary, HistoryCacheStatus
from kade.data.history.session import SessionPolicy
from kade.integrations.marketdata.base import MarketDataProvider


@dataclass
class HistoryService:
    downloader: HistoryDownloader
    loader: HistoricalDataLoader
    dataset_builder: ReplayDatasetBuilder
    cache: HistoryCache

    @classmethod
    def from_config(
        cls,
        provider: MarketDataProvider,
        logger: object,
        history_config: dict[str, object],
        mental_model_config: dict[str, object],
    ) -> "HistoryService":
        root = Path(str(history_config.get("root_dir", ".kade_storage/history")))
        cache = HistoryCache(root)
        download_cfg = dict(history_config.get("downloader", {}))
        replay_cfg = dict(history_config.get("replay", {}))
        downloader = HistoryDownloader(
            provider=provider,
            cache=cache,
            logger=logger,
            config=HistoryDownloadConfig(
                timeframe="1m",
                chunk_days=int(download_cfg.get("chunk_days", 5)),
                requests_per_minute=int(download_cfg.get("requests_per_minute", 180)),
                pacing_sleep_seconds=float(download_cfg.get("pacing_sleep_seconds", 0.35)),
                request_window_minutes=int(download_cfg.get("request_window_minutes", 390)),
                session_timezone=str(download_cfg.get("session_timezone", "America/New_York")),
                session_open=str(download_cfg.get("session_open", "09:30")),
                session_close=str(download_cfg.get("session_close", "16:00")),
                expected_bars_per_session=int(download_cfg.get("expected_bars_per_session", 390)),
                partial_session_tolerance=int(download_cfg.get("partial_session_tolerance", 1)),
                ignore_extended_hours=bool(download_cfg.get("ignore_extended_hours", True)),
            ),
        )
        loader = HistoricalDataLoader(cache)
        dataset_builder = ReplayDatasetBuilder(loader=loader, mental_model_config=mental_model_config, replay_config=replay_cfg)
        return cls(downloader=downloader, loader=loader, dataset_builder=dataset_builder, cache=cache)

    def download(self, symbols: list[str], start: datetime, end: datetime) -> DownloadSummary:
        return self.downloader.download_missing(symbols=symbols, start=start, end=end)

    def cache_status(self, symbols: list[str], start: datetime, end: datetime) -> HistoryCacheStatus:
        ranges = {symbol: self.cache.cached_ranges(symbol, timeframe="1m") for symbol in symbols}
        missing = {}
        policy = SessionPolicy(
            timezone_name=self.downloader.config.session_timezone,
            session_open=self.downloader.config.session_open,
            session_close=self.downloader.config.session_close,
            expected_bars_per_session=self.downloader.config.expected_bars_per_session,
            partial_session_tolerance=self.downloader.config.partial_session_tolerance,
            ignore_extended_hours=self.downloader.config.ignore_extended_hours,
        )
        session_status: dict[str, list[dict[str, object]]] = {}
        for symbol in symbols:
            missing_days = self.cache.missing_dates(symbol, start, end, timeframe="1m")
            missing[symbol] = [{"start": day.isoformat(), "end": day.isoformat()} for day in missing_days]
            statuses: list[dict[str, object]] = []
            for day in self.cache.iter_dates(start.date(), end.date()):
                statuses.append(self.cache.session_coverage(symbol, day, policy, timeframe="1m").to_payload())
            session_status[symbol] = statuses
        return HistoryCacheStatus(symbols=symbols, date_ranges=ranges, session_status=session_status, missing_ranges=missing)
