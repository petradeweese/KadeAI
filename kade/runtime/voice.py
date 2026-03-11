"""Voice runtime wiring helpers."""

from __future__ import annotations

from typing import Callable


def build_voice_handlers(
    *,
    session_state: dict[str, object],
    persist_session: Callable[[], None],
    states: dict[str, object],
    plan_active_count: Callable[[], int],
    latest_radar: Callable[[], dict[str, object]],
    latest_breadth: Callable[[], dict[str, object]],
    memory_snapshot: Callable[[int], dict[str, object]],
    advisor_by_symbol: dict[str, dict[str, object]],
) -> dict[str, Callable[..., dict[str, object]]]:
    def switch_mode(mode: str) -> dict[str, object]:
        return {"mode": mode, "summary": f"Mode set to {mode}."}

    def done_for_day() -> dict[str, object]:
        session_state["done_for_day"] = True
        persist_session()
        return {"summary": "Done-for-day state enabled."}

    def emergency_shutdown() -> dict[str, object]:
        session_state["emergency_shutdown"] = True
        persist_session()
        return {"summary": "Emergency shutdown guardrails are active."}

    def radar() -> dict[str, object]:
        top = latest_radar().get("queue", [])[:1]
        if not top:
            return {"summary": "No radar setup is currently queued."}
        idea = top[0]
        return {"top_symbol": idea.get("symbol"), "summary": f"Top conviction score is {idea.get('score', 'n/a')}."}

    def status() -> dict[str, object]:
        return {"summary": f"Tracking {len(states)} symbols with {plan_active_count()} active plans."}

    def market_overview() -> dict[str, object]:
        return {"summary": f"Market breadth is {latest_breadth().get('bias', 'unknown')}."}

    def memory_watchlist() -> dict[str, object]:
        recent_intents = memory_snapshot(5).get("intents", [])
        watched = [item.get("symbol") for item in recent_intents if item.get("symbol")]
        return {"watching": sorted(set(watched))}

    def symbol_status(symbol: str) -> dict[str, object]:
        if symbol not in states:
            return {"summary": f"{symbol} is not currently in the watchlist."}
        state = states[symbol]
        return {"summary": f"{symbol} is {state.trend} with {state.momentum} momentum."}

    def symbol_opinion(symbol: str) -> dict[str, object]:
        advice = advisor_by_symbol.get(symbol)
        if not advice:
            return {"summary": f"No active advisor view for {symbol} yet."}
        return {"summary": advice["summary"], "stance": advice["stance"]}

    def fallback(mode: str, transcript: str) -> dict[str, object]:
        return {"summary": f"I heard: {transcript}. Try radar, status, or mode commands."}

    return {
        "switch_mode": switch_mode,
        "done_for_day": done_for_day,
        "emergency_shutdown": emergency_shutdown,
        "radar": radar,
        "status": status,
        "market_overview": market_overview,
        "memory_watchlist": memory_watchlist,
        "symbol_status": symbol_status,
        "symbol_opinion": symbol_opinion,
        "fallback": fallback,
    }
