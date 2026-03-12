from datetime import datetime, timedelta, timezone

from kade.backtesting.models import ReplayStepInput
from kade.dashboard.app import create_app_status
from kade.data.history.cache import HistoryCache
from kade.data.history.dataset_builder import ReplayDatasetBuilder
from kade.data.history.downloader import HistoryDownloadConfig, HistoryDownloader
from kade.data.history.loader import HistoricalDataLoader
from kade.data.history.resample import resample_bars
from kade.integrations.marketdata.mock import MockMarketDataProvider
from kade.logging_utils import get_logger


def _bars(symbol: str, start: datetime, minutes: int) -> list:
    provider = MockMarketDataProvider()
    end = start + timedelta(minutes=minutes - 1)
    return provider.get_historical_bars(symbol, "1m", start, end)


def _mental_model_config() -> dict:
    return {
        "trend_slope": {"bullish": 0.02, "bearish": -0.02},
        "momentum_rsi": {"bullish": 55, "bearish": 45},
        "momentum_macd_hist": {"bullish": 0.01, "bearish": -0.01},
        "volume_acceleration": {"strong": 1.05, "weak": 0.95},
        "confidence": {"high_min": 0.65, "moderate_min": 0.5},
    }


def test_cache_roundtrip_and_missing_ranges(tmp_path) -> None:
    cache = HistoryCache(tmp_path / "history")
    start = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    bars = _bars("NVDA", start, 10)
    cache.write_bars("NVDA", bars)

    loaded = cache.load_range("NVDA", start, start + timedelta(minutes=9))
    assert len(loaded) == 10
    assert loaded[0].timestamp == start

    missing = cache.missing_dates("NVDA", start - timedelta(days=1), start)
    assert (start - timedelta(days=1)).date() in missing


def test_downloader_skips_cached_and_tracks_requests(tmp_path) -> None:
    cache = HistoryCache(tmp_path / "history")
    provider = MockMarketDataProvider()
    logger = get_logger(__name__)
    slept: list[float] = []
    downloader = HistoryDownloader(
        provider=provider,
        cache=cache,
        logger=logger,
        config=HistoryDownloadConfig(chunk_days=1, requests_per_minute=120, pacing_sleep_seconds=0.1),
        sleeper=lambda seconds: slept.append(seconds),
    )

    start = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)
    end = start + timedelta(days=2)
    first = downloader.download_missing(["NVDA"], start, end)
    second = downloader.download_missing(["NVDA"], start, end)

    assert first.requests_made >= 2
    assert first.bars_downloaded > 0
    assert second.requests_made == 0
    assert all(value >= 0.1 for value in slept)


def test_resample_1m_to_5m_and_15m_is_deterministic() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    bars = _bars("NVDA", start, 15)
    bars_5m = resample_bars(bars, "5m")
    bars_15m = resample_bars(bars, "15m")

    assert len(bars_5m) == 3
    assert bars_5m[0].open == bars[0].open
    assert bars_5m[0].close == bars[4].close
    assert bars_5m[0].volume == sum(bar.volume for bar in bars[:5])

    assert len(bars_15m) == 1
    assert bars_15m[0].high == max(bar.high for bar in bars)


def test_replay_dataset_builder_from_cache_multi_symbol(tmp_path) -> None:
    cache = HistoryCache(tmp_path / "history")
    loader = HistoricalDataLoader(cache)
    start = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    end = start + timedelta(minutes=79)
    cache.write_bars("NVDA", _bars("NVDA", start, 80))
    cache.write_bars("TSLA", _bars("TSLA", start, 80))

    builder = ReplayDatasetBuilder(
        loader=loader,
        mental_model_config=_mental_model_config(),
        replay_config={"future_window": 6, "trigger_lookback_bars": 10, "bias_lookback_bars": 6, "context_lookback_bars": 4},
    )
    run_input = builder.build("phase13b-demo", ["NVDA", "TSLA"], start, end)

    assert run_input.symbols == ["NVDA", "TSLA"]
    assert run_input.steps
    assert isinstance(run_input.steps[0], ReplayStepInput)
    assert run_input.steps[0].future_prices


def test_operator_console_historical_payload_shape() -> None:
    payload = create_app_status(
        voice_payload={
            "historical_data": {
                "cache_status": {"symbols": ["NVDA"], "date_ranges": {"NVDA": []}, "session_status": {"NVDA": []}, "missing_ranges": {"NVDA": []}},
                "last_download": {"symbols": ["NVDA"], "requests_made": 2},
            }
        }
    )
    historical = payload["operator_console"]["historical_data"]
    assert "cache_status" in historical
    assert "last_download" in historical
