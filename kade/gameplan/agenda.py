"""Deterministic catalyst agenda assembly."""

from __future__ import annotations

from collections import defaultdict

from kade.gameplan.models import CatalystAgendaItem
from kade.market.intelligence.models import MarketContextSnapshot


class CatalystAgendaBuilder:
    def __init__(self, config: dict[str, object]) -> None:
        self.cfg = config
        self.limits = dict(config.get("output_limits", {}))

    def build(self, snapshot: MarketContextSnapshot, watchlist: list[str]) -> list[CatalystAgendaItem]:
        priorities = dict(self.cfg.get("catalyst_priorities", {}))
        priority_scores = {
            key: int(value)
            for key, value in priorities.items()
            if key in {"market_wide", "sector", "symbol"} and isinstance(value, (int, float))
        }
        dedup: dict[str, CatalystAgendaItem] = {}
        for item in snapshot.key_news:
            scope = self._scope(item.symbols, watchlist)
            score = priority_scores.get(scope, 1)
            if item.catalyst_type in {"macro", "regulatory"}:
                score += 2
            elif item.catalyst_type == "earnings":
                score += 1
            key = f"{item.headline.lower()}::{scope}"
            existing = dedup.get(key)
            entry = CatalystAgendaItem(
                category=item.catalyst_type,
                scope=scope,
                priority=self._priority_label(score),
                headline=item.headline,
                summary=item.summary,
                symbols=list(item.symbols),
                debug={"relevance": item.relevance_label, "score": score},
            )
            if existing is None or float(existing.debug.get("score", 0)) < score:
                dedup[key] = entry

        earnings_by_symbol: defaultdict[str, list[object]] = defaultdict(list)
        for event in snapshot.earnings:
            earnings_by_symbol[event.symbol].append(event)
        for symbol, events in earnings_by_symbol.items():
            if symbol in watchlist:
                dedup[f"earnings::{symbol}"] = CatalystAgendaItem(
                    category="earnings",
                    scope="symbol",
                    priority="priority_high",
                    headline=f"{symbol} earnings {events[0].timing}",
                    summary="Watch earnings timing and implied volatility impact.",
                    symbols=[symbol],
                    debug={"event_count": len(events), "score": 5},
                )

        max_items = int(self.limits.get("key_catalysts", 8))
        ranked = sorted(dedup.values(), key=lambda item: (float(item.debug.get("score", 0)), item.headline), reverse=True)
        return ranked[:max_items]

    @staticmethod
    def _scope(symbols: list[str], watchlist: list[str]) -> str:
        if not symbols:
            return "market_wide"
        overlap = [symbol for symbol in symbols if symbol in set(watchlist)]
        if overlap:
            return "symbol"
        if len(symbols) >= 3:
            return "sector"
        return "symbol"

    @staticmethod
    def _priority_label(score: float) -> str:
        if score >= 5:
            return "priority_high"
        if score >= 3:
            return "priority_medium"
        return "priority_low"
