"""Earnings event normalization."""

from __future__ import annotations

from kade.market.intelligence.models import EarningsEvent


class EarningsNormalizer:
    def __init__(self, config: dict[str, object]) -> None:
        self.limit = int(config.get("earnings_limit", 10))

    def normalize(self, raw_items: list[dict[str, object]], source: str, generated_at: str) -> list[EarningsEvent]:
        events: list[EarningsEvent] = []
        for item in raw_items[: self.limit]:
            events.append(
                EarningsEvent(
                    timestamp=generated_at,
                    source=source,
                    symbol=str(item.get("symbol", "")).upper(),
                    event_date=str(item.get("event_date") or ""),
                    timing=str(item.get("timing") or "unknown"),
                    estimate_eps=float(item["estimate_eps"]) if isinstance(item.get("estimate_eps"), (int, float)) else None,
                    debug={"raw": dict(item)},
                )
            )
        return events
