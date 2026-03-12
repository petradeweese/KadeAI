from __future__ import annotations


class ChatFormatter:
    def format_deterministic(self, command_response: dict[str, object], intent: str) -> str:
        raw = dict(command_response.get("raw_result", {}))
        if intent == "trade_idea":
            opinion = dict(raw.get("trade_idea_opinion", {}))
            symbol = opinion.get("symbol", "N/A")
            direction = str(opinion.get("direction", "idea")).lower()
            stance = str(opinion.get("stance", "watch")).replace("_", " ")
            target = opinion.get("target", "n/a")
            entry = opinion.get("entry", "n/a")
            invalidation = opinion.get("invalidation", "n/a")

            if direction == "put":
                objective_phrase = f"Downside objective is around {target}."
            elif direction == "call":
                objective_phrase = f"Upside objective is around {target}."
            else:
                objective_phrase = f"Objective is around {target}."

            return (
                f"I'd treat {symbol} as a {stance} setup for a {direction}, not an immediate entry. "
                f"I'd want confirmation on {entry}, and I'd invalidate if {invalidation}. "
                f"{objective_phrase}"
            )
        if intent == "trade_plan":
            plan = dict(raw.get("trade_plan", {}))
            return f"Trade plan {plan.get('plan_id', 'n/a')} is {plan.get('status', 'unknown')} for {plan.get('symbol', 'N/A')}."
        if intent == "visual_explain":
            visual = dict(raw.get("visual_explainability", {}))
            return f"Visual explainability prepared for {visual.get('symbol', 'N/A')} ({visual.get('view_type', 'overview')})."
        if intent == "premarket_gameplan":
            plan = dict(raw.get("premarket_gameplan", {}))
            posture = dict(plan.get("market_posture", {})).get("posture_label", "mixed")
            return f"Premarket gameplan refreshed. Market posture: {posture}."
        if intent == "strategy_analysis":
            strat = dict(raw.get("strategy_intelligence", {}))
            return f"Strategy intelligence refreshed with {len(list(strat.get('setup_archetype_stats', [])))} setup archetype rows."

        return str(command_response.get("formatted_response") or command_response.get("raw_result", {}).get("summary") or "Done.")
