"""Deterministic bar resampling from canonical 1-minute bars."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from kade.market.structure import Bar


_INTERVALS = {"1m": 1, "5m": 5, "15m": 15}


def timeframe_to_minutes(timeframe: str) -> int:
    if timeframe not in _INTERVALS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return _INTERVALS[timeframe]


def resample_bars(bars_1m: list[Bar], target_timeframe: str) -> list[Bar]:
    interval = timeframe_to_minutes(target_timeframe)
    if interval == 1:
        return list(sorted(bars_1m, key=lambda bar: bar.timestamp))

    ordered = sorted(bars_1m, key=lambda bar: bar.timestamp)
    buckets: dict[datetime, list[Bar]] = defaultdict(list)
    for bar in ordered:
        ts = bar.timestamp if bar.timestamp.tzinfo else bar.timestamp.replace(tzinfo=timezone.utc)
        minute = (ts.minute // interval) * interval
        bucket_start = ts.replace(minute=minute, second=0, microsecond=0)
        buckets[bucket_start].append(bar)

    output: list[Bar] = []
    for bucket_start in sorted(buckets):
        chunk = sorted(buckets[bucket_start], key=lambda item: item.timestamp)
        output.append(
            Bar(
                symbol=chunk[0].symbol,
                timestamp=bucket_start,
                open=chunk[0].open,
                high=max(item.high for item in chunk),
                low=min(item.low for item in chunk),
                close=chunk[-1].close,
                volume=sum(float(item.volume) for item in chunk),
            )
        )
    return output
