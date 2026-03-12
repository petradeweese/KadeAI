"""Rule-based trade-plan evaluation against current market context."""

from __future__ import annotations

from datetime import datetime

from kade.planning.rules import normalize_direction
from kade.tracking.models import (
    InvalidationEvaluation,
    StalenessEvaluation,
    TradePlanEvaluation,
    TradePlanTrackingContext,
    TriggerEvaluation,
)
from kade.utils.time import utc_now


class TradePlanEvaluator:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config

    def evaluate(self, context: TradePlanTrackingContext) -> TradePlanEvaluation:
        direction = normalize_direction(context.plan.direction)
        trigger = self._evaluate_trigger(context, direction)
        invalidation = self._evaluate_invalidation(context, direction)
        staleness = self._evaluate_staleness(context)

        posture = "neutral"
        if invalidation.state in {"soft_warning", "hard_invalidated"} or staleness.state in {"aging", "stale"}:
            posture = "degrading"
        elif trigger.state == "triggered" and invalidation.state == "valid" and staleness.state == "fresh":
            posture = "improving"

        reasons = trigger.reasons + invalidation.reasons + staleness.reasons
        actions: list[str] = []
        if invalidation.state == "hard_invalidated":
            actions.append("cancel_plan")
        elif trigger.state == "triggered":
            actions.append("prepare_execution_workflow")
        elif trigger.state == "ready":
            actions.append("maintain_readiness")

        if staleness.state == "stale":
            actions.append("stand_down_if_no_change")

        summary = self._summary(trigger.state, invalidation.state, staleness.state, posture)
        return TradePlanEvaluation(
            trigger=trigger,
            invalidation=invalidation,
            staleness=staleness,
            posture_state=posture,
            summary=summary,
            reasons=reasons[: int(self.config.get("reason_limit", 8))],
            actions=actions[: int(self.config.get("action_limit", 5))],
            debug={
                "direction": direction,
                "execution_state": context.execution_state,
                "status": context.plan.status,
            },
        )

    def _evaluate_trigger(self, context: TradePlanTrackingContext, direction: str) -> TriggerEvaluation:
        state = context.ticker_state
        breadth = str(context.breadth_context.get("bias", "unknown"))
        momentum = str(state.momentum or "unknown")
        trend = str(state.trend or "unknown")
        qqq = str(state.qqq_confirmation or "mixed")
        structure = str(state.structure or "")
        radar_alignment = str(context.radar_context.get("alignment_label") or context.radar_context.get("market_alignment") or "mixed")
        allow_radar_only_trigger = bool(self.config.get("allow_radar_only_trigger", True))

        if direction == "bearish":
            ready = (trend == "bearish") and (momentum in {"down_bias", "strong_down"}) and breadth != "risk_on"
            triggered = ready and (
                (state.vwap is not None and (state.last_price or 0) <= state.vwap)
                or ("break" in structure.lower() and momentum == "strong_down")
                or (allow_radar_only_trigger and radar_alignment == "aligned")
            )
            reasons = [
                "Downside alignment remains intact." if ready else "Downside alignment is not fully intact.",
                "Continuation trigger below VWAP/structure confirmed." if triggered else "Continuation trigger has not fired.",
                f"QQQ confirmation: {qqq}.",
            ]
        else:
            ready = (trend == "bullish") and (momentum in {"up_bias", "strong_up"}) and breadth != "risk_off"
            triggered = ready and (
                (state.vwap is not None and (state.last_price or 0) >= state.vwap)
                or ("reclaim" in structure.lower() and momentum in {"up_bias", "strong_up"})
                or (allow_radar_only_trigger and radar_alignment == "aligned")
            )
            reasons = [
                "Upside alignment remains intact." if ready else "Upside alignment is not fully intact.",
                "Continuation trigger above VWAP/structure confirmed." if triggered else "Continuation trigger has not fired.",
                f"QQQ confirmation: {qqq}.",
            ]

        if triggered:
            trigger_state = "triggered"
        elif ready:
            trigger_state = "ready"
        else:
            trigger_state = "not_ready"

        return TriggerEvaluation(
            state=trigger_state,
            reasons=reasons,
            debug={"trend": trend, "momentum": momentum, "breadth": breadth, "radar_alignment": radar_alignment, "allow_radar_only_trigger": allow_radar_only_trigger},
        )

    def _evaluate_invalidation(self, context: TradePlanTrackingContext, direction: str) -> InvalidationEvaluation:
        state = context.ticker_state
        breadth = str(context.breadth_context.get("bias", "unknown"))
        momentum = str(state.momentum or "unknown")
        trend = str(state.trend or "unknown")
        qqq = str(state.qqq_confirmation or "mixed")
        hard = False
        soft = False
        reasons: list[str] = []

        if direction == "bearish":
            soft = momentum in {"mixed", "up_bias"} or breadth == "risk_on" or qqq in {"confirmed", "bullish"}
            hard = (state.vwap is not None and (state.last_price or 0) > state.vwap) or trend == "bullish"
        else:
            soft = momentum in {"mixed", "down_bias"} or breadth == "risk_off" or qqq in {"divergent_risk_off", "bearish"}
            hard = (state.vwap is not None and (state.last_price or 0) < state.vwap) or trend == "bearish"

        if hard:
            inval_state = "hard_invalidated"
            reasons.append("Thesis is hard invalidated by directional contradiction.")
        elif soft:
            inval_state = "soft_warning"
            reasons.append("Thesis is weakening and requires caution.")
        else:
            inval_state = "valid"
            reasons.append("Thesis remains valid.")

        reasons.extend([f"Breadth bias: {breadth}.", f"Momentum: {momentum}.", f"QQQ confirmation: {qqq}."])
        return InvalidationEvaluation(state=inval_state, reasons=reasons, debug={"trend": trend})

    def _evaluate_staleness(self, context: TradePlanTrackingContext) -> StalenessEvaluation:
        now = context.now or utc_now()
        elapsed = context.elapsed_minutes
        if elapsed is None:
            updated_at = context.plan.updated_at
            if isinstance(updated_at, datetime):
                elapsed = max(int((now - updated_at).total_seconds() // 60), 0)
            else:
                elapsed = 0

        hold_plan = context.plan.hold_plan if isinstance(context.plan.hold_plan, dict) else {}
        hold_minutes = int(hold_plan.get("max_hold_minutes", context.plan.max_hold_minutes or 60))
        stale_ratio = float(self.config.get("stale_ratio_of_hold", 0.65))
        stale_minutes = int(self.config.get("default_stale_minutes", max(15, int(hold_minutes * stale_ratio))))
        aging_minutes = int(self.config.get("aging_minutes", max(5, stale_minutes // 2)))

        if elapsed >= stale_minutes:
            state = "stale"
            reasons = [f"No meaningful progress for {elapsed} minutes; setup is stale."]
        elif elapsed >= aging_minutes:
            state = "aging"
            reasons = [f"Setup has been lingering for {elapsed} minutes."]
        else:
            state = "fresh"
            reasons = ["Setup timing remains fresh."]

        return StalenessEvaluation(
            state=state,
            reasons=reasons,
            debug={"elapsed_minutes": elapsed, "aging_minutes": aging_minutes, "stale_minutes": stale_minutes},
        )

    @staticmethod
    def _summary(trigger: str, invalidation: str, staleness: str, posture: str) -> str:
        return f"Trigger={trigger}; invalidation={invalidation}; staleness={staleness}; posture={posture}."
