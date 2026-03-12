from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from kade.data.history.cache import HistoryCache
from kade.data.history.downloader import HistoryDownloadConfig, HistoryDownloader
from kade.data.history.service import HistoryService
from kade.data.history.session import SessionPolicy, classify_session_coverage
from kade.integrations.marketdata.mock import MockMarketDataProvider
from kade.logging_utils import get_logger
from kade.market.alpaca_client import AlpacaClient, AlpacaConfig


def _session_start(day: datetime) -> datetime:
    return datetime(day.year, day.month, day.day, 14, 30, tzinfo=timezone.utc)


def test_session_completeness_classification_missing_partial_complete() -> None:
    policy = SessionPolicy(partial_session_tolerance=1)
    day = datetime(2026, 1, 5, tzinfo=timezone.utc).date()
    expected = policy.expected_timestamps_utc(day)

    missing = classify_session_coverage(day, [], policy)
    partial = classify_session_coverage(day, expected[:50], policy)
    complete = classify_session_coverage(day, expected[:-1], policy)

    assert missing.state == "missing"
    assert partial.state == "partial"
    assert complete.state == "complete"


def test_downloader_fills_partial_session_and_skips_complete(tmp_path) -> None:
    cache = HistoryCache(tmp_path / "history")
    provider = MockMarketDataProvider()
    logger = get_logger(__name__)
    cfg = HistoryDownloadConfig(request_window_minutes=60)
    downloader = HistoryDownloader(provider=provider, cache=cache, logger=logger, config=cfg, sleeper=lambda _: None)

    start = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 5, 23, 59, tzinfo=timezone.utc)
    session_start = _session_start(start)

    # Seed partial day (50 bars)
    partial_bars = provider.get_historical_bars("NVDA", "1m", session_start, session_start + timedelta(minutes=49))
    cache.write_bars("NVDA", partial_bars)

    summary = downloader.download_missing(["NVDA"], start, end)
    assert summary.sessions_checked == 1
    assert summary.sessions_partial == 1
    assert summary.requests_made > 0

    # second pass should skip now-complete session
    second = downloader.download_missing(["NVDA"], start, end)
    assert second.requests_made == 0
    assert second.sessions_complete == 1


def test_rate_limit_safe_request_window_generation(tmp_path) -> None:
    cache = HistoryCache(tmp_path / "history")
    provider = MockMarketDataProvider()
    logger = get_logger(__name__)
    cfg = HistoryDownloadConfig(request_window_minutes=30)
    downloader = HistoryDownloader(provider=provider, cache=cache, logger=logger, config=cfg, sleeper=lambda _: None)

    start = datetime(2026, 1, 6, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 6, 23, 59, tzinfo=timezone.utc)
    summary = downloader.download_missing(["AAPL"], start, end)

    assert summary.missing_windows_requested >= 13
    assert all(window["start"] < window["end"] for window in summary.request_windows)


def test_alpaca_historical_transport_normalizes_utc(monkeypatch) -> None:
    class _Resp:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    payload = {
        "bars": {
            "AAPL": [
                {"t": "2026-01-05T14:30:00Z", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 100},
                {"t": "2026-01-05T14:31:00+00:00", "o": 10.5, "h": 11.2, "l": 10.2, "c": 11, "v": 150},
            ]
        }
    }

    monkeypatch.setattr("kade.market.alpaca_client.urlopen", lambda request, timeout=30: _Resp(payload))

    client = AlpacaClient(AlpacaConfig(api_key="k", secret_key="s", data_url="https://data.alpaca.markets"))
    bars = client.get_historical_bars(
        symbol="AAPL",
        timeframe="1m",
        start=datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc),
        end=datetime(2026, 1, 5, 14, 31, tzinfo=timezone.utc),
    )

    assert len(bars) == 2
    assert all(bar.timestamp.tzinfo is not None for bar in bars)
    assert bars[0].timestamp.tzinfo == timezone.utc


def test_history_service_cache_status_contains_session_status(tmp_path) -> None:
    provider = MockMarketDataProvider()
    logger = get_logger(__name__)
    service = HistoryService.from_config(
        provider=provider,
        logger=logger,
        history_config={"root_dir": str(tmp_path / "history"), "downloader": {}},
        mental_model_config={},
    )
    start = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 5, 23, 59, tzinfo=timezone.utc)
    status = service.cache_status(["NVDA"], start, end)
    assert "NVDA" in status.session_status
    assert status.session_status["NVDA"][0]["state"] in {"missing", "partial", "complete"}
