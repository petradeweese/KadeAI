from __future__ import annotations


class ChatFormatter:
    def format_deterministic(self, command_response: dict[str, object], intent: str) -> str:
        raw = dict(command_response.get("raw_result", {}))
        if intent in {"trade_idea", "trade_followup"}:
            opinion = dict(raw.get("trade_idea_opinion", {}))
            symbol = opinion.get("symbol", "N/A")
            direction = str(opinion.get("direction", "idea")).lower()
            stance = str(opinion.get("stance", "watch")).replace("_", " ")
            target = opinion.get("target", "n/a")
            entry = opinion.get("entry", "n/a")
            invalidation = opinion.get("invalidation", "n/a")
            confidence_text = self._confidence_label(opinion.get("confidence"))
            risk_posture = str(opinion.get("risk_posture", "normal")).replace("_", " ")
            summary = self._clean_summary(str(opinion.get("summary", "")))

            direction_word = "downside" if direction == "put" else "upside" if direction == "call" else "directional"
            opening = (
                f"NVDA still looks like a watch-first put setup to me right now."
                if str(symbol).upper() == "NVDA" and direction == "put"
                else f"On {symbol}, this still looks more like a {stance} {direction} setup than an immediate entry."
            )

            return (
                f"{opening} "
                f"I would want to see {entry} before treating the move as active, otherwise it can easily turn into chop. "
                f"Your {target} exit makes sense if the {direction_word} leg actually follows through with pace after the trigger. "
                f"If we get {invalidation}, that is the part of the tape that weakens the idea quickly. "
                f"Right now I would stay patient and keep it conditional instead of leaning early. "
                f"Overall conviction reads {confidence_text}, with a {risk_posture} risk posture until price confirms. "
                f"Without live bars in front of me, I would still treat this as a conditional setup and wait for cleaner confirmation. "
                f"{summary}".strip()
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

    @staticmethod
    def _confidence_label(confidence: object) -> str:
        if isinstance(confidence, (int, float)):
            value = float(confidence)
            if value >= 0.78:
                return "strong"
            if value >= 0.58:
                return "moderate"
            return "measured"
        return "measured"

    @staticmethod
    def _clean_summary(summary: str) -> str:
        text = summary.strip()
        if not text:
            return ""
        if text.lower().startswith("deterministic setup for"):
            return ""
        return text
