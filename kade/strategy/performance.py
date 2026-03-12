"""Core deterministic performance math helpers."""

from __future__ import annotations

from statistics import median


def safe_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def parse_price(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        text = value.lower().replace("$", "").replace(",", "").strip()
        for token in ["above", "below", "break", "reclaim", "near", "fail", "back", "at"]:
            text = text.replace(token, " ")
        for part in text.split():
            try:
                return float(part)
            except ValueError:
                continue
    return None


def win_rate(rois: list[float]) -> float:
    if not rois:
        return 0.0
    return round(sum(1 for roi in rois if roi > 0) / len(rois), 4)


def avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def median_value(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(median(values)), 4)


def max_drawdown(returns: list[float]) -> float:
    if not returns:
        return 0.0
    curve = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in returns:
        curve += value
        peak = max(peak, curve)
        drawdown = min(drawdown, curve - peak)
    return round(abs(drawdown), 4)
