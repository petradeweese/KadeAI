"""Dashboard data wiring for Kade status visibility."""

from __future__ import annotations

from kade.market.structure import TickerState


def create_app_status(
    ticker_states: dict[str, TickerState] | None = None,
    debug_values: dict[str, dict[str, float | str | None]] | None = None,
    breadth_context: dict[str, float | str | None] | None = None,
    radar_payload: dict[str, object] | None = None,
    options_payload: dict[str, object] | None = None,
    execution_payload: dict[str, object] | None = None,
    memory_payload: dict[str, object] | None = None,
    plan_payload: dict[str, object] | None = None,
    advisor_payload: dict[str, object] | None = None,
    style_payload: dict[str, object] | None = None,
) -> dict:
    ticker_states = ticker_states or {}
    debug_values = debug_values or {}
    breadth_context = breadth_context or {}
    radar_payload = radar_payload or {"queue": [], "ranked": [], "by_symbol": {}, "events": []}
    options_payload = options_payload or {"by_symbol": {}}
    execution_payload = execution_payload or {"orders": [], "rejections": [], "debug": {}}
    memory_payload = memory_payload or {"recent": [], "intents": [], "responses": [], "notes": []}
    plan_payload = plan_payload or {"active": [], "all": [], "events": []}
    advisor_payload = advisor_payload or {"by_symbol": {}, "top_radar": []}
    style_payload = style_payload or {}

    cards: list[dict] = []
    by_symbol = radar_payload.get("by_symbol", {})
    options_by_symbol = options_payload.get("by_symbol", {})
    advisor_by_symbol = advisor_payload.get("by_symbol", {})
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
                "radar_state": by_symbol.get(symbol, {}).get("state", "no_setup"),
                "radar_rank": by_symbol.get(symbol, {}).get("rank"),
                "radar_debug": by_symbol.get(symbol, {}).get("debug", {}),
                "updated_at": state.updated_at.isoformat() if state.updated_at else None,
                "debug": debug_values.get(symbol, {}),
                "option_candidates": options_by_symbol.get(symbol, {}).get("candidates", [])[:3],
                "selected_option_plan": options_by_symbol.get(symbol, {}).get("selected_plan"),
                "advisor_stance": advisor_by_symbol.get(symbol, {}).get("stance"),
                "advisor_summary": advisor_by_symbol.get(symbol, {}).get("summary"),
                "advisor_debug": advisor_by_symbol.get(symbol, {}).get("debug", {}),
            }
        )

    return {
        "status": "running",
        "card_count": len(cards),
        "breadth_context": breadth_context,
        "style_profile": style_payload,
        "memory": memory_payload,
        "plans": plan_payload,
        "advisor": advisor_payload,
        "radar": {
            "queue": radar_payload.get("queue", []),
            "top_ranked": radar_payload.get("ranked", [])[:3],
            "events": radar_payload.get("events", []),
        },
        "execution": execution_payload,
        "ticker_cards": cards,
    }
