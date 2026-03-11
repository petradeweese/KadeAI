from datetime import datetime, timezone

from kade.market.indicators import (
    consolidation_breakout,
    higher_highs_lower_highs,
    macd,
    regression_trend_slope,
    rsi,
    volume_acceleration,
    vwap,
)
from kade.market.structure import Bar


def _bar(close: float, volume: float = 1000) -> Bar:
    return Bar(
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        open=close - 0.2,
        high=close + 0.3,
        low=close - 0.3,
        close=close,
        volume=volume,
    )


def test_vwap_returns_value() -> None:
    bars = [_bar(100, 1000), _bar(101, 1200), _bar(102, 1500)]
    value = vwap(bars)
    assert value is not None
    assert 100 < value < 102


def test_rsi_in_uptrend_above_midline() -> None:
    closes = [float(100 + i) for i in range(20)]
    value = rsi(closes, period=14)
    assert value is not None
    assert value > 50


def test_macd_returns_tuple() -> None:
    closes = [100 + (i * 0.5) for i in range(40)]
    result = macd(closes)
    assert result is not None
    assert len(result) == 3


def test_volume_acceleration_positive_when_recent_volume_rises() -> None:
    volumes = [100] * 20 + [300, 320, 350, 400, 420]
    value = volume_acceleration(volumes, short_period=5, long_period=20)
    assert value is not None
    assert value > 0


def test_regression_slope_positive_for_rising_series() -> None:
    values = [1, 2, 3, 4, 5]
    slope = regression_trend_slope(values)
    assert slope is not None
    assert slope > 0


def test_higher_highs_detection() -> None:
    highs = [1, 2, 3, 4]
    assert higher_highs_lower_highs(highs, lookback=3) == "higher_highs"


def test_consolidation_breakout_up_detection() -> None:
    closes = [100] * 20 + [101]
    assert consolidation_breakout(closes, window=20, breakout_pct=0.001) == "breakout_up"
