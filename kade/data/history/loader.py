"""High-level history cache loader with deterministic timeframe derivation."""

from __future__ import annotations

from datetime import datetime

from kade.data.history.cache import HistoryCache
from kade.data.history.resample import resample_bars
from kade.market.structure import Bar


class HistoricalDataLoader:
    def __init__(self, cache: HistoryCache) -> None:
        self.cache = cache

    def load_bars(self, symbol: str, start: datetime, end: datetime, timeframe: str = "1m") -> list[Bar]:
        bars_1m = self.cache.load_range(symbol, start, end, timeframe="1m")
        if timeframe == "1m":
            return bars_1m
        return resample_bars(bars_1m, timeframe)
