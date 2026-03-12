"""Premarket gameplan service orchestration."""

from __future__ import annotations

from kade.gameplan.agenda import CatalystAgendaBuilder
from kade.gameplan.formatter import PremarketGameplanFormatter
from kade.gameplan.models import PremarketGameplan
from kade.gameplan.prioritizer import MarketPostureEngine, WatchlistPrioritizer, build_risk_notes
from kade.market.intelligence.models import MarketContextSnapshot
from kade.market.structure import TickerState


class PremarketGameplanService:
    def __init__(self, config: dict[str, object]) -> None:
        self.cfg = config
        self.posture = MarketPostureEngine(config)
        self.agenda = CatalystAgendaBuilder(config)
        self.prioritizer = WatchlistPrioritizer(config)
        self.formatter = PremarketGameplanFormatter()

    def build_premarket_gameplan(
        self,
        *,
        snapshot: MarketContextSnapshot,
        watchlist: list[str],
        ticker_states: dict[str, TickerState] | None = None,
        explicit_symbols: list[str] | None = None,
    ) -> PremarketGameplan:
        ticker_states = ticker_states or {}
        posture = self.posture.classify(snapshot)
        catalysts = self.agenda.build(snapshot, watchlist)
        priorities = self.prioritizer.rank(snapshot, watchlist, explicit_symbols=explicit_symbols)
        opportunities = self._opportunities(posture.posture_label, priorities)
        risks = build_risk_notes(snapshot, posture)
        limits = dict(self.cfg.get("output_limits", {}))
        summary = self.formatter.build_summary(
            posture=posture,
            catalysts=catalysts,
            priorities=priorities,
            risks=risks,
            opportunities=opportunities,
        )

        plan = PremarketGameplan(
            generated_at=snapshot.generated_at,
            market_posture=posture,
            key_catalysts=catalysts,
            earnings_today=[event.to_payload() for event in snapshot.earnings[: int(limits.get("earnings_today", 8))]],
            futures_or_index_context={
                "session_label": snapshot.market_clock.session_label,
                "is_open": snapshot.market_clock.is_open,
                "regime_label": snapshot.regime.regime_label,
                "regime_confidence": snapshot.regime.regime_confidence,
            },
            movers_to_watch=[item.to_payload() for item in snapshot.top_movers[: int(limits.get("movers_to_watch", 8))]],
            most_active_context=[item.to_payload() for item in snapshot.most_active[: int(limits.get("most_active", 8))]],
            watchlist_priorities=priorities,
            risks=risks,
            opportunities=opportunities,
            agenda_notes=self.formatter.agenda_notes(summary, catalysts, priorities),
            summary=summary,
            debug={"watchlist_size": len(watchlist), "ticker_state_count": len(ticker_states)},
        )
        return plan

    def refresh_daily_gameplan(
        self,
        *,
        snapshot: MarketContextSnapshot,
        watchlist: list[str],
        ticker_states: dict[str, TickerState] | None = None,
        explicit_symbols: list[str] | None = None,
    ) -> dict[str, object]:
        return self.build_premarket_gameplan(
            snapshot=snapshot,
            watchlist=watchlist,
            ticker_states=ticker_states,
            explicit_symbols=explicit_symbols,
        ).to_payload()

    @staticmethod
    def _opportunities(posture_label: str, priorities: list[object]) -> list[str]:
        items: list[str] = []
        if posture_label in {"trend_favorable", "cautious_trend"}:
            items.append("Trend continuation setups can be prioritized when aligned.")
        high = [item.symbol for item in priorities if item.priority == "priority_high"]
        if high:
            items.append(f"High-priority watchlist names: {', '.join(high[:3])}.")
        if not items:
            items.append("Selective monitoring posture; wait for cleaner alignment.")
        return items
