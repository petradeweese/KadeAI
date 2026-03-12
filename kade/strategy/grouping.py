"""Grouping utilities for strategy analytics."""

from __future__ import annotations

from collections import defaultdict

from kade.strategy.models import GroupedPerformanceStats
from kade.strategy.performance import avg, max_drawdown, median_value, safe_float, win_rate


GROUP_DIMENSIONS = [
    "symbol",
    "direction",
    "setup_archetype",
    "regime",
    "risk_posture",
    "target_plausibility",
    "discipline_label",
]


def compute_grouped_statistics(trades: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    output: dict[str, list[dict[str, object]]] = {}
    for dimension in GROUP_DIMENSIONS:
        grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
        for trade in trades:
            key = str(trade.get(dimension, "unknown"))
            grouped[key].append(trade)
        buckets: list[dict[str, object]] = []
        for key in sorted(grouped):
            rows = grouped[key]
            rois = [safe_float(item.get("roi")) for item in rows]
            holds = [safe_float(item.get("hold_minutes")) for item in rows]
            stats = GroupedPerformanceStats(
                group_key=key,
                dimension=dimension,
                win_rate=win_rate(rois),
                average_roi=avg(rois),
                median_roi=median_value(rois),
                trade_count=len(rows),
                max_drawdown=max_drawdown(rois),
                avg_hold_minutes=avg(holds),
            )
            buckets.append(stats.to_payload())
        output[dimension] = buckets
    return output
