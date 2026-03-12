"""Runtime bootstrap helpers to keep entrypoint orchestration concise."""

from __future__ import annotations

from kade.dashboard.app import create_app_status


def build_dashboard_state(
    states: dict[str, object],
    debug_values: dict[str, dict[str, float | str | None]],
    latest_breadth: dict[str, float | str | None],
    latest_radar: dict[str, object],
    options_payload: dict[str, object],
    execution_payload: dict[str, object],
    memory_payload: dict[str, object],
    plan_payload: dict[str, object],
    advisor_payload: dict[str, object],
    style_payload: dict[str, object],
    voice_payload: dict[str, object],
    persistence_payload: dict[str, object],
    session_payload: dict[str, object],
    history_payload: dict[str, object],
    market_intelligence_payload: dict[str, object] | None = None,
    premarket_gameplan_payload: dict[str, object] | None = None,
    strategy_intelligence_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return create_app_status(
        states,
        debug_values,
        latest_breadth,
        latest_radar,
        options_payload,
        execution_payload,
        memory_payload,
        plan_payload,
        advisor_payload,
        style_payload,
        voice_payload,
        persistence_payload=persistence_payload,
        session_payload=session_payload,
        history_payload=history_payload,
        market_intelligence_payload=market_intelligence_payload,
        premarket_gameplan_payload=premarket_gameplan_payload,
        strategy_intelligence_payload=strategy_intelligence_payload,
    )


def print_runtime_summary(
    dashboard_state: dict[str, object], session_state: dict[str, object], history_payload: dict[str, list[dict[str, object]]]
) -> None:
    print("Kade Phase 11 initialized")
    print(f"Ticker cards: {dashboard_state['card_count']}")
    print(f"Radar queue: {len(dashboard_state['radar']['queue'])}")
    print(f"Active plans: {len(dashboard_state['plans'].get('active', []))}")
    print(f"Recent memory entries: {len(dashboard_state['memory'].get('recent', []))}")
    print(f"Advisor outputs: {len(dashboard_state['advisor'].get('by_symbol', {}))}")
    print(f"Session: day={session_state.get('day_key')} trades_today={session_state.get('trades_today')}")
    print(
        "History sizes: "
        f"radar={len(history_payload['radar'])} "
        f"advisor={len(history_payload['advisor'])} "
        f"execution={len(history_payload['execution'])}"
    )
