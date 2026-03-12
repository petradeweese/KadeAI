"""Deterministic chart data assembly for visual explainability."""

from __future__ import annotations

from kade.data.history.resample import resample_bars
from kade.market.structure import Bar


class ChartDataAssembler:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config
        self.window_sizes = dict(config.get("bar_window_sizes", {"1m": 80, "5m": 60, "15m": 50}))

    def bars_for_timeframe(self, bars_1m: list[Bar], timeframe: str) -> list[dict[str, object]]:
        window = int(self.window_sizes.get(timeframe, 50))
        if not bars_1m:
            return []
        if timeframe == "1m":
            bars = list(sorted(bars_1m, key=lambda bar: bar.timestamp))
        else:
            bars = resample_bars(bars_1m, timeframe)
        trimmed = bars[-window:] if window > 0 else []
        return [
            {
                "timestamp": bar.timestamp.isoformat(),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }
            for bar in trimmed
        ]
