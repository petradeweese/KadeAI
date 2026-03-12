from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError

from kade.dashboard.app import create_app_status
from kade.data.history.cache import HistoryCache
from kade.data.history.downloader import HistoryDownloadConfig, HistoryDownloader
from kade.data.history.service import HistoryService
from kade.data.history.session import SessionPolicy, classify_session_coverage
from kade.integrations.marketdata.base import MarketDataProvider

from kade.integrations.health import ProviderHealth
from kade.integrations.marketdata.mock import MockMarketDataProvider
from kade.logging_utils import get_logger
from kade.market.structure import Bar, Quote, Trade


class RetryProvider(MarketDataProvider):
    provider_name = "retry"

    def __init__(self, failures: list[Exception]) -> None:
        self.failures = failures
        self.calls = 0

    def get_latest_quote(self, symbol: str) -> Quote:
        raise NotImplementedError

    def get_latest_trade(self, symbol: str) -> Trade:
        raise NotImplementedError

    def get_bars(self, symbol: str, timeframe: str, limit: int = 200) -> list[Bar]:
        raise NotImplementedError

    def get_historical_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Bar]:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return [
            Bar(
                symbol=symbol,
                timestamp=start,
                open=100,
                high=101,
                low=99,
                close=100.5,
                volume=1000,
            )
        ]


    def health_snapshot(self, active: bool) -> ProviderHealth:
        return ProviderHealth(provider_type="market_data", provider_name=self.provider_name, state="ready", active=active, metadata={})


def _http_error(code: int) -> HTTPError:
    return HTTPError(url="https://example", code=code, msg="boom", hdrs=None, fp=BytesIO())


def test_weekend_skip_behavior() -> None:
    policy = SessionPolicy(skip_weekends=True)
    day = datetime(2026, 1, 3, tzinfo=timezone.utc).date()  # Saturday

    coverage = classify_session_coverage(day, [], policy)

    assert coverage.state == "skipped_non_session"
    assert coverage.skipped_reason == "weekend"
    assert coverage.expected_bars == 0


def test_holiday_skip_behavior() -> None:
    policy = SessionPolicy(skip_weekends=True, holidays=("2026-01-05",))
    day = datetime(2026, 1, 5, tzinfo=timezone.utc).date()

    coverage = classify_session_coverage(day, [], policy)

    assert coverage.state == "skipped_non_session"
    assert coverage.skipped_reason == "holiday"


def test_session_completeness_trading_vs_non_trading_day() -> None:
    policy = SessionPolicy(skip_weekends=True)
    trading_day = datetime(2026, 1, 5, tzinfo=timezone.utc).date()
    weekend_day = datetime(2026, 1, 4, tzinfo=timezone.utc).date()

    trading = classify_session_coverage(trading_day, [], policy)
    non_trading = classify_session_coverage(weekend_day, [], policy)

    assert trading.state == "missing"
    assert non_trading.state == "skipped_non_session"


def test_retry_backoff_for_retryable_transport_failures(tmp_path) -> None:
    provider = RetryProvider([_http_error(429), _http_error(503)])
    cache = HistoryCache(tmp_path / "history")
    slept: list[float] = []
    downloader = HistoryDownloader(
        provider=provider,
        cache=cache,
        logger=get_logger(__name__),
        config=HistoryDownloadConfig(max_retries=3, backoff_seconds=(0.1, 0.2, 0.3)),
        sleeper=lambda seconds: slept.append(seconds),
    )

    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    end = datetime(2026, 1, 5, 14, 31, tzinfo=timezone.utc)
    summary = downloader.download_missing(["AAPL"], start, end)

    assert summary.retry_count == 2
    assert summary.requests_made == 1
    assert slept == [0.1, 0.2]


def test_no_retry_for_non_retryable_http_status(tmp_path) -> None:
    provider = RetryProvider([_http_error(400)])
    cache = HistoryCache(tmp_path / "history")
    downloader = HistoryDownloader(
        provider=provider,
        cache=cache,
        logger=get_logger(__name__),
        config=HistoryDownloadConfig(max_retries=3),
        sleeper=lambda _: None,
    )

    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    end = datetime(2026, 1, 5, 14, 31, tzinfo=timezone.utc)
    summary = downloader.download_missing(["AAPL"], start, end)

    assert summary.retry_count == 0
    assert provider.calls == 1
    assert len(summary.failed_windows) == 1


def test_persisted_history_index_roundtrip(tmp_path) -> None:
    cache = HistoryCache(tmp_path / "history")
    provider = MockMarketDataProvider()
    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    bar = provider.get_historical_bars("NVDA", "1m", start, start)[0]
    cache.write_bars("NVDA", [bar])
    policy = SessionPolicy()

    first = cache.session_coverage("NVDA", start.date(), policy)
    second_cache = HistoryCache(tmp_path / "history")
    second = second_cache.session_coverage("NVDA", start.date(), policy)

    assert first.state == second.state
    assert second_cache.index_store.path.exists()


def test_index_assisted_session_lookup_without_recompute(tmp_path) -> None:
    cache = HistoryCache(tmp_path / "history")
    provider = MockMarketDataProvider()
    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    bar = provider.get_historical_bars("NVDA", "1m", start, start)[0]
    cache.write_bars("NVDA", [bar])
    policy = SessionPolicy()

    _ = cache.session_coverage("NVDA", start.date(), policy)

    def fail_load(*args, **kwargs):
        raise AssertionError("load_day should not be called when index is fresh")

    cache.load_day = fail_load  # type: ignore[assignment]
    from_index = cache.session_coverage("NVDA", start.date(), policy)
    assert from_index.state in {"partial", "complete", "missing"}


def test_operator_payload_shape_with_hardening_metadata() -> None:
    payload = create_app_status(
        voice_payload={
            "historical_data": {
                "cache_status": {
                    "symbols": ["NVDA"],
                    "date_ranges": {"NVDA": []},
                    "session_status": {"NVDA": []},
                    "missing_ranges": {"NVDA": []},
                    "index_status": {"indexed_days": 1, "stale_days": 0, "recomputed_days": 0},
                },
                "last_download": {
                    "symbols": ["NVDA"],
                    "requests_made": 2,
                    "retry_count": 1,
                    "failed_windows": [],
                    "skipped_non_session_days": 1,
                },
            }
        }
    )

    historical = payload["operator_console"]["historical_data"]
    assert "cache_status" in historical
    assert "last_download" in historical
    assert "index_status" in historical["cache_status"]


def test_history_service_reports_index_status(tmp_path) -> None:
    service = HistoryService.from_config(
        provider=MockMarketDataProvider(),
        logger=get_logger(__name__),
        history_config={"root_dir": str(tmp_path / "history"), "downloader": {"holiday_dates": ["2026-01-01"]}},
        mental_model_config={},
    )
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, 23, 59, tzinfo=timezone.utc)
    status = service.cache_status(["NVDA"], start, end)

    assert "indexed_days" in status.index_status
    assert any(item["state"] == "skipped_non_session" for item in status.session_status["NVDA"])
