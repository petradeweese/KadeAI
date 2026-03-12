"""Review analyzer orchestration and label logic."""

from __future__ import annotations

from kade.review.evaluator import evaluate_discipline, evaluate_outcome
from kade.review.models import TradeReviewContext, TradeReviewResult
from kade.utils.time import utc_now_iso


class TradeReviewAnalyzer:
    def __init__(self, config: dict[str, object] | None = None) -> None:
        self.config = config or {}

    def review(self, context: TradeReviewContext) -> TradeReviewResult:
        discipline = evaluate_discipline(context, dict(self.config.get("discipline", {})))
        outcome = evaluate_outcome(context, discipline)

        review_label = self._review_label(discipline.discipline_label, outcome.outcome_label, outcome.plan_quality_label)
        strengths = discipline.strengths + [item for item in outcome.strengths if item not in discipline.strengths]
        mistakes = discipline.mistakes + [item for item in outcome.mistakes if item not in discipline.mistakes]
        lessons = self._build_lessons(review_label, discipline.plan_followed, outcome.setup_worked_as_expected)
        summary = self._summary(review_label, context.plan, discipline, outcome)

        final_status = outcome.final_status
        reviewed_at = context.now_iso or utc_now_iso()
        plan = context.plan
        metrics = {
            "stale_respected": discipline.stale_respected,
            "cancellation_correctness": discipline.cancellation_correctness,
            "setup_worked_as_expected": outcome.setup_worked_as_expected,
        }
        return TradeReviewResult(
            plan_id=str(plan.get("plan_id", "unknown")),
            symbol=str(plan.get("symbol", "")),
            direction=str(plan.get("direction", "")),
            final_status=final_status,
            review_label=review_label,
            discipline_label=discipline.discipline_label,
            plan_quality_label=outcome.plan_quality_label,
            outcome_label=outcome.outcome_label,
            invalidation_respected=discipline.invalidation_respected,
            posture_respected=discipline.posture_respected,
            checklist_adherence=discipline.checklist_adherence,
            plan_followed=discipline.plan_followed,
            summary=summary,
            strengths=strengths,
            mistakes=mistakes,
            lessons=lessons,
            metrics=metrics,
            reviewed_at=reviewed_at,
            debug={
                "discipline": discipline.debug,
                "outcome": outcome.debug,
                "tracking_snapshot_count": len(context.tracking_snapshots),
                "final_status": final_status,
            },
        )

    def _review_label(self, discipline_label: str, outcome_label: str, quality_label: str) -> str:
        if discipline_label == "invalidation_ignored":
            return "invalidation_ignored"
        if quality_label == "low_quality_setup":
            return "low_quality_setup"
        if outcome_label == "cancelled_correctly":
            return "cancelled_correctly"
        if outcome_label == "stale_but_managed":
            return "stale_but_managed"
        if discipline_label == "posture_not_respected":
            return "drifted_from_plan"
        if discipline_label == "disciplined" and outcome_label == "target_reached_or_positive":
            return "well_executed"
        if quality_label == "high_quality_setup" and discipline_label != "disciplined":
            return "high_quality_setup_poor_followthrough"
        if discipline_label == "disciplined":
            return "mostly_disciplined"
        if discipline_label == "mixed":
            return "drifted_from_plan"
        return "unknown"

    def _summary(self, review_label: str, plan: dict[str, object], discipline: object, outcome: object) -> str:
        symbol = plan.get("symbol", "symbol")
        return f"Review for {symbol}: {review_label}. Discipline={getattr(discipline, 'discipline_label', 'unknown')}, outcome={getattr(outcome, 'outcome_label', 'unknown')}."

    def _build_lessons(self, review_label: str, plan_followed: bool, setup_worked: bool) -> list[str]:
        lessons = [
            "Separate setup quality from execution discipline.",
            "Keep invalidation and posture constraints explicit before activation.",
        ]
        if not plan_followed:
            lessons.append("Tighten lifecycle actions when invalidated or stale.")
        if plan_followed and not setup_worked:
            lessons.append("A disciplined loss can still validate process quality.")
        if review_label == "cancelled_correctly":
            lessons.append("Standing down is a valid win when plan conditions degrade.")
        return lessons[: int(self.config.get("lesson_limit", 4))]
