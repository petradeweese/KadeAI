"""Indicator calculations for Kade Phase 1 market intelligence."""

from __future__ import annotations



from .structure import Bar


def vwap(bars: list[Bar]) -> float | None:
    if not bars:
        return None
    weighted_sum = sum(((bar.high + bar.low + bar.close) / 3) * bar.volume for bar in bars)
    volume_sum = sum(bar.volume for bar in bars)
    if volume_sum == 0:
        return None
    return weighted_sum / volume_sum


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = max(delta, 0)
        loss = abs(min(delta, 0))
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema_values = [values[0]]
    for price in values[1:]:
        ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float] | None:
    if len(closes) < slow:
        return None
    fast_ema = _ema(closes, fast)
    slow_ema = _ema(closes, slow)
    macd_line_series = [f - s for f, s in zip(fast_ema[-len(slow_ema):], slow_ema)]
    signal_series = _ema(macd_line_series, signal)
    macd_line = macd_line_series[-1]
    signal_line = signal_series[-1]
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def volume_acceleration(volumes: list[float], short_period: int = 5, long_period: int = 20) -> float | None:
    if len(volumes) < long_period:
        return None
    short_avg = sum(volumes[-short_period:]) / short_period
    long_avg = sum(volumes[-long_period:]) / long_period
    if long_avg == 0:
        return None
    return (short_avg - long_avg) / long_avg


def regression_trend_slope(values: list[float]) -> float | None:
    n = len(values)
    if n < 2:
        return None
    x_values = list(range(n))
    x_mean = sum(x_values) / n
    y_mean = sum(values) / n
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        return None
    return numerator / denominator


def higher_highs_lower_highs(highs: list[float], lookback: int = 3) -> str:
    if len(highs) < lookback + 1:
        return "insufficient_data"
    recent = highs[-(lookback + 1):]
    diffs = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]
    if all(diff > 0 for diff in diffs):
        return "higher_highs"
    if all(diff < 0 for diff in diffs):
        return "lower_highs"
    return "mixed"


def consolidation_breakout(closes: list[float], window: int = 20, breakout_pct: float = 0.003) -> str:
    if len(closes) < window + 1:
        return "insufficient_data"
    base = closes[-(window + 1) : -1]
    current = closes[-1]
    upper = max(base)
    lower = min(base)
    range_size = upper - lower

    if current > upper:
        return "breakout_up"
    if current < lower:
        return "breakout_down"
    if range_size == 0:
        return "consolidating"

    normalized_range = range_size / max(abs(sum(base) / len(base)), 1e-9)
    if normalized_range < breakout_pct:
        return "consolidating"
    return "inside_range"
