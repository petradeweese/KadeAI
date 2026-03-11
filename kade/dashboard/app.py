"""Basic dashboard data wiring for Phase 2B."""

from __future__ import annotations

from kade.market.structure import TickerState


def create_app_status(
    ticker_states: dict[str, TickerState] | None = None,
    debug_values: dict[str, dict[str, float | str | None]] | None = None,
    breadth_context: dict[str, float | str | None] | None = None,
) -> dict:
    ticker_states = ticker_states or {}
    debug_values = debug_values or {}
    breadth_context = breadth_context or {}

    cards: list[dict] = []
    for symbol in sorted(ticker_states):
        state = ticker_states[symbol]
        cards.append(
            {
                "symbol": symbol,
                "last_price": state.last_price,
                "vwap": state.vwap,
                "trend": state.trend,
                "structure": state.structure,
                "momentum": state.momentum,
                "volume_state": state.volume_state,
                "qqq_confirmation": state.qqq_confirmation,
                "regime": state.regime,
                "trap_risk": state.trap_risk,
                "confidence_label": state.confidence_label,
                "confidence_reason": state.confidence_reason,
                "updated_at": state.updated_at.isoformat() if state.updated_at else None,
                "debug": debug_values.get(symbol, {}),
            }
        )

    return {
        "status": "running",
        "card_count": len(cards),
        "breadth_context": breadth_context,
        "ticker_cards": cards,
    }
