"""Coordinator for deterministic plan tracking evaluations."""

from __future__ import annotations

from kade.brain import SessionPlanTracker
from kade.tracking.evaluator import TradePlanEvaluator
from kade.tracking.models import PlanTrackingSnapshot, TradePlanTrackingContext
from kade.tracking.transitions import PlanStatusTransitions
from kade.utils.time import utc_now_iso


class TradePlanMonitor:
    def __init__(self, plan_tracker: SessionPlanTracker, config: dict[str, object]) -> None:
        self.plan_tracker = plan_tracker
        self.config = config
        self.evaluator = TradePlanEvaluator(dict(config.get("evaluation", {})))
        self.transitions = PlanStatusTransitions(dict(config.get("transitions", {})))

    def evaluate(self, context: TradePlanTrackingContext, apply_transition: bool = True) -> PlanTrackingSnapshot:
        evaluation = self.evaluator.evaluate(context)
        before = context.plan.status
        after = before
        transition_actions: list[str] = []

        if apply_transition:
            after, transition_actions = self.transitions.resolve(before, evaluation, execution_state=context.execution_state)
            if after != before:
                self.plan_tracker.update_status(context.plan.plan_id, after, reason=evaluation.summary)

        return PlanTrackingSnapshot(
            plan_id=context.plan.plan_id,
            symbol=context.plan.symbol,
            status_before=before,
            status_after=after,
            trigger_state=evaluation.trigger.state,
            invalidation_state=evaluation.invalidation.state,
            staleness_state=evaluation.staleness.state,
            posture_state=evaluation.posture_state,
            summary=evaluation.summary,
            reasons=evaluation.reasons,
            actions=evaluation.actions + transition_actions,
            updated_at=utc_now_iso(),
            debug={
                "trigger": evaluation.trigger.debug,
                "invalidation": evaluation.invalidation.debug,
                "staleness": evaluation.staleness.debug,
                **evaluation.debug,
            },
        )
