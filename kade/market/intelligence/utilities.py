"""Utility helpers for deterministic market intelligence processing."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from kade.utils.time import ensure_utc


def as_utc_iso(value: str | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    normalized = value.replace("Z", "+00:00")
    return ensure_utc(datetime.fromisoformat(normalized)).isoformat()


def infer_session_label(is_open: bool, now_iso: str, open_iso: str | None, close_iso: str | None) -> str:
    if is_open:
        return "regular"
    if open_iso is None or close_iso is None:
        return "unknown"
    now = datetime.fromisoformat(now_iso)
    open_ts = datetime.fromisoformat(open_iso)
    close_ts = datetime.fromisoformat(close_iso)
    if now < open_ts:
        return "premarket"
    if now > close_ts:
        return "after_hours"
    return "closed"


def normalize_symbol_list(symbols: list[str] | None) -> list[str]:
    values = [str(symbol).strip().upper() for symbol in (symbols or []) if str(symbol).strip()]
    return sorted(set(values))


def dedupe_news_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, object]] = []
    for item in items:
        key = (str(item.get("headline", "")).strip().lower(), str(item.get("timestamp", "")).strip())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def breakdown(labels: list[str]) -> dict[str, int]:
    counts = Counter(labels)
    return {key: counts[key] for key in sorted(counts)}


def short_summary(text: str, limit: int = 180) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."
