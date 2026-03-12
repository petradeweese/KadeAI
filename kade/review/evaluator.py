"""Rule-based discipline and outcome evaluators."""

from __future__ import annotations

from kade.review.models import DisciplineEvaluation, PlanOutcomeEvaluation, TradeReviewContext


def evaluate_discipline(context: TradeReviewContext, config: dict[str, object]) -> DisciplineEvaluation:
    plan = context.plan
    snapshots = context.tracking_snapshots
    latest = snapshots[-1] if snapshots else {}
    invalidation_state = str(latest.get("invalidation_state", "valid"))
    staleness_state = str(latest.get("staleness_state", "fresh"))
    posture_state = str(latest.get("posture_state", "neutral"))
    final_status = str(context.final_status or context.plan.get("status") or latest.get("status_after") or "unknown")

    respected_when_hard_invalidated = final_status in {"cancelled", "exited"}
    invalidation_respected = invalidation_state != "hard_invalidated" or respected_when_hard_invalidated

    required_conservative_postures = set(config.get("conservative_postures", ["watch_only", "capital_preservation"]))
    risk_posture = str(plan.get("risk_posture", "watch_only"))
    aggressive_execution = str(dict(context.execution_state or {}).get("lifecycle", {}).get("state", "")) in {"submitted", "partially_filled", "filled"}
    posture_respected = not (risk_posture in required_conservative_postures and aggressive_execution)
    posture_respected = posture_respected and posture_state != "posture_not_respected"

    stale_respected = staleness_state != "stale" or final_status in {"cancelled", "exited"} or "de_risk" in " ".join(latest.get("actions", []))
    cancellation_correctness = not (final_status == "cancelled" and invalidation_state == "valid" and staleness_state == "fresh")

    checklist_len = len(list(plan.get("execution_checklist", [])))
    checklist_completed = min(int(dict(context.realized_outcome or {}).get("checklist_completed", checklist_len)), checklist_len)
    checklist_adherence = 1.0 if checklist_len == 0 else round(checklist_completed / checklist_len, 4)

    plan_followed = invalidation_respected and posture_respected and stale_respected and checklist_adherence >= float(config.get("min_checklist_adherence_for_followed", 0.6))

    strengths: list[str] = []
    mistakes: list[str] = []
    if invalidation_respected:
        strengths.append("Invalidation policy respected.")
    else:
        mistakes.append("Hard invalidation occurred without exit or cancellation.")
    if posture_respected:
        strengths.append("Risk posture behavior stayed aligned.")
    else:
        mistakes.append("Execution behavior exceeded planned posture.")
    if stale_respected:
        strengths.append("Stale-state management stayed within rules.")
    else:
        mistakes.append("Plan lingered in stale state without de-risking.")

    if not invalidation_respected:
        discipline_label = "invalidation_ignored"
    elif not posture_respected:
        discipline_label = "posture_not_respected"
    elif not stale_respected:
        discipline_label = "stale_not_respected"
    elif plan_followed:
        discipline_label = "disciplined"
    else:
        discipline_label = "mixed"

    return DisciplineEvaluation(
        discipline_label=discipline_label,
        invalidation_respected=invalidation_respected,
        posture_respected=posture_respected,
        stale_respected=stale_respected,
        cancellation_correctness=cancellation_correctness,
        checklist_adherence=checklist_adherence,
        plan_followed=plan_followed,
        strengths=strengths,
        mistakes=mistakes,
        debug={
            "latest_snapshot": latest,
            "final_status": final_status,
            "risk_posture": risk_posture,
            "aggressive_execution": aggressive_execution,
        },
    )


def evaluate_outcome(context: TradeReviewContext, discipline: DisciplineEvaluation) -> PlanOutcomeEvaluation:
    plan = context.plan
    snapshots = context.tracking_snapshots
    latest = snapshots[-1] if snapshots else {}
    final_status = str(context.final_status or plan.get("status") or latest.get("status_after") or "unknown")
    realized = context.realized_outcome or {}

    pnl = float(realized.get("realized_pnl", 0.0)) if realized.get("realized_pnl") is not None else 0.0
    target_hit = bool(realized.get("target_hit", False)) or latest.get("trigger_state") == "triggered"

    confidence = str(plan.get("confidence_label", "medium"))
    trap_risk = str(plan.get("trap_risk", "unknown"))
    market_alignment = str(plan.get("market_alignment", "mixed"))
    if confidence in {"high", "very_high"} and trap_risk in {"low", "medium"} and market_alignment in {"aligned", "strongly_aligned"}:
        quality = "high_quality_setup"
    elif confidence in {"low", "very_low"} or trap_risk == "high":
        quality = "low_quality_setup"
    else:
        quality = "mixed_quality_setup"

    if final_status == "cancelled" and discipline.invalidation_respected:
        outcome_label = "cancelled_correctly"
    elif latest.get("staleness_state") == "stale" and discipline.stale_respected:
        outcome_label = "stale_but_managed"
    elif target_hit or pnl > 0:
        outcome_label = "target_reached_or_positive"
    elif final_status in {"cancelled", "exited"}:
        outcome_label = "closed_without_target"
    else:
        outcome_label = "incomplete_or_unknown"

    setup_worked = target_hit or pnl > 0
    strengths: list[str] = []
    mistakes: list[str] = []
    if setup_worked:
        strengths.append("Setup produced favorable follow-through.")
    else:
        mistakes.append("Setup follow-through was weak or incomplete.")

    return PlanOutcomeEvaluation(
        outcome_label=outcome_label,
        plan_quality_label=quality,
        setup_worked_as_expected=setup_worked,
        final_status=final_status,
        strengths=strengths,
        mistakes=mistakes,
        debug={
            "realized": realized,
            "latest_snapshot": latest,
            "target_hit": target_hit,
            "realized_pnl": pnl,
        },
    )
