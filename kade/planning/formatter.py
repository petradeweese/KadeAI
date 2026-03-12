"""Plan formatter helpers for UI/runtime payloads."""

from __future__ import annotations


def top_scenario_summary(board: dict[str, object] | None) -> dict[str, object]:
    if not board:
        return {}
    top = list(board.get("candidates", []))[:1]
    if not top:
        return {"candidate_count": 0}
    item = top[0]
    return {
        "candidate_count": len(list(board.get("candidates", []))),
        "top_option_symbol": item.get("option_symbol"),
        "estimated_percent_return": item.get("estimated_percent_return"),
        "risk_label": item.get("risk_label"),
    }
