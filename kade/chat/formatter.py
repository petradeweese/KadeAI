from __future__ import annotations


class ChatFormatter:
    def format_deterministic(self, command_response: dict[str, object], intent: str) -> str:
        raw = dict(command_response.get("raw_result", {}))
        if intent == "trade_idea":
            opinion = dict(raw.get("trade_idea_opinion", {}))
            return (
                f"Trade idea for {opinion.get('symbol', 'N/A')}: stance={opinion.get('stance', 'unknown')}, "
                f"entry={opinion.get('entry', 'n/a')}, invalidation={opinion.get('invalidation', 'n/a')}, target={opinion.get('target', 'n/a')}."
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
