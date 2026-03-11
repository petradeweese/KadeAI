"""Rule-based advisor reasoning engine for Phase 5."""

from __future__ import annotations

from datetime import datetime
from logging import Logger

from kade.brain.memory import ConversationMemory
from kade.brain.models import AdvisorOutput, TradePlan
from kade.logging_utils import LogCategory, get_logger, log_event
from kade.market.structure import TickerState
from kade.utils.time import utc_now


class AdvisorReasoningEngine:
    def __init__(self, config: dict, logger: Logger | None = None) -> None:
        self.config = config
        self.logger = logger or get_logger(__name__)

    def build_advice(
        self,
        symbol: str,
        ticker_state: TickerState,
        radar_context: dict[str, object],
        breadth_context: dict[str, object],
        active_plans: list[TradePlan],
        memory: ConversationMemory,
        options_plan: dict[str, object] | None = None,
    ) -> AdvisorOutput:
        support: list[str] = []
        cautions: list[str] = []
        score = 0

        if ticker_state.trend in {"bullish", "bearish"}:
            support.append(f"Trend is {ticker_state.trend} on trigger timeframe.")
            score += 1
        momentum = str(ticker_state.momentum or "unknown")
        if momentum in {"strong_up", "strong_down"}:
            support.append(f"Momentum is strong ({momentum}).")
            score += 1
        elif momentum in {"up_bias", "down_bias"}:
            support.append(f"Momentum has directional bias ({momentum}).")
            score += 1
        elif momentum == "mixed":
            cautions.append("Momentum is mixed.")
            score -= 1

        qqq_confirmation = str(ticker_state.qqq_confirmation or "unknown")
        if qqq_confirmation in {"confirmed", "confirmed_breadth_aligned"}:
            support.append(f"QQQ confirmation is {qqq_confirmation}.")
            score += 1
        elif qqq_confirmation in {"divergent", "divergent_risk_off", "mixed_breadth"}:
            cautions.append(f"QQQ confirmation is {qqq_confirmation}.")
            score -= 1

        breadth_bias = str(breadth_context.get("bias", "unknown"))
        if breadth_bias in {"risk_on", "risk_off"}:
            support.append(f"Breadth bias is {breadth_context.get('bias')}.")
            score += 1
        elif breadth_bias == "mixed":
            cautions.append("Breadth is mixed.")
            score -= 1

        trap_risk = str(ticker_state.trap_risk or "unknown")
        if trap_risk in {"high", "moderate"}:
            cautions.append(f"Trap risk is {trap_risk}.")
            score -= 1 if trap_risk == "moderate" else 2

        if ticker_state.regime in {"range", "slow", "unknown"}:
            cautions.append(f"Regime is {ticker_state.regime}.")
            score -= 1

        radar_score = float(radar_context.get("score", 0.0) or 0.0)
        if radar_score >= 70:
            support.append("Radar score is in a high-conviction range.")
            score += 1
        elif radar_score <= 40:
            cautions.append("Radar conviction is currently light.")
            score -= 1

        if options_plan:
            support.append("Options plan is available for defined risk.")
            score += 1

        linked_plan = next((plan for plan in active_plans if plan.symbol == symbol), None)
        if linked_plan:
            support.append(f"Active plan is {linked_plan.status} with defined invalidation.")

        recent_symbol_memory = memory.recall_for_symbol(symbol, limit=3)
        if recent_symbol_memory:
            support.append("Recent conversation context is available.")

        stance = self._pick_stance(score)
        summary = self._build_summary(stance, support, cautions)
        suggested_action = self._suggest_action(stance, linked_plan)

        output = AdvisorOutput(
            symbol=symbol,
            stance=stance,
            summary=summary,
            supporting_reasons=support[:4],
            cautionary_reasons=cautions[:4],
            suggested_action=suggested_action,
            linked_plan_id=linked_plan.plan_id if linked_plan else None,
            generated_at=utc_now(),
            debug={
                "score": score,
                "radar_score": radar_score,
                "trap_risk": trap_risk,
                "momentum": momentum,
                "qqq_confirmation": qqq_confirmation,
                "breadth_bias": breadth_bias,
                "regime": ticker_state.regime,
                "memory_hits": len(recent_symbol_memory),
            },
        )
        log_event(
            self.logger,
            LogCategory.REASONING_EVENT,
            "Advisor output generated",
            symbol=symbol,
            stance=output.stance,
            linked_plan_id=output.linked_plan_id,
        )
        return output

    def _pick_stance(self, score: int) -> str:
        if score >= 4:
            return "strong"
        if score >= 2:
            return "agree"
        if score >= 0:
            return "cautious"
        return "pass"

    def _build_summary(self, stance: str, support: list[str], cautions: list[str]) -> str:
        support_fragment = support[0] if support else "Signals are mixed."
        caution_fragment = cautions[0] if cautions else "No major caution flags."
        if stance == "strong":
            return f"Setup looks strong. {support_fragment} {caution_fragment}"
        if stance == "agree":
            return f"Confidence is moderate. {support_fragment} {caution_fragment}"
        if stance == "cautious":
            return f"I'd stay cautious. {support_fragment} {caution_fragment}"
        return f"Best to pass for now. {caution_fragment}"

    def _suggest_action(self, stance: str, linked_plan: TradePlan | None) -> str:
        if stance == "strong":
            return "Prepare execution checklist and wait for trigger confirmation."
        if stance == "agree":
            return "Keep the setup on watch and confirm volume before entry."
        if stance == "cautious":
            return "Reduce size expectations and wait for cleaner confirmation."
        if linked_plan:
            return "Keep plan parked in watching status until conditions improve."
        return "Skip this setup and reassess on next loop."
