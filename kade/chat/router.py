from __future__ import annotations

from kade.chat.models import InterpretedAction


class ChatActionRouter:
    """Converts interpreted intents to deterministic interaction panel payloads."""

    def to_panel_payload(self, action: InterpretedAction) -> dict[str, object]:
        if action.intent == "explicit_command":
            return {"command": str(action.payload.get("command", ""))}
        if action.intent == "status":
            return {"command": "status"}
        if action.intent == "radar":
            return {"command": "radar"}
        if action.intent == "premarket_gameplan":
            return {"premarket_gameplan_request": action.payload or {}}
        if action.intent == "trade_idea":
            return {"trade_idea_request": action.payload or {}}
        if action.intent == "trade_followup":
            return {"trade_idea_request": action.payload or {}}
        if action.intent == "target_move":
            return {"target_move_request": action.payload or {}}
        if action.intent == "trade_plan":
            return {"trade_plan_request": action.payload or {}}
        if action.intent == "trade_plan_check":
            return {"trade_plan_tracking_request": action.payload or {}}
        if action.intent == "trade_review":
            return {"trade_review_request": action.payload or {}}
        if action.intent == "visual_explain":
            return {"visual_explain_request": action.payload or {}}
        if action.intent == "strategy_analysis":
            return {"strategy_analysis_request": action.payload or {}}
        return {"command": "status"}
