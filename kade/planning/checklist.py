"""Execution checklist generation for trade plans."""

from __future__ import annotations

from kade.planning.models import EntryPlan, InvalidationPlan, TargetPlan


def build_execution_checklist(
    *,
    entry_plan: EntryPlan,
    invalidation_plan: InvalidationPlan,
    target_plan: TargetPlan,
    qqq_alignment: str,
    breadth_alignment: str,
    risk_posture: str,
    checklist_verbosity: str,
) -> list[str]:
    checks = [
        f"Confirm trigger: {entry_plan.trigger_condition}.",
        "Confirm spread/liquidity is acceptable before entry.",
        f"Confirm QQQ alignment is not adverse ({qqq_alignment}).",
        f"Confirm breadth alignment supports thesis ({breadth_alignment}).",
        f"Avoid entry if any avoid-if condition appears: {', '.join(entry_plan.avoid_if[:2])}.",
        f"Respect hard invalidation: {', '.join(invalidation_plan.hard_invalidation[:2])}.",
        f"Scale-out plan: {target_plan.scale_out_guidance[0] if target_plan.scale_out_guidance else 'Take partials into strength/weakness.'}",
    ]
    if risk_posture in {"reduced", "watch_only", "pass"}:
        checks.append(f"Size down due to posture={risk_posture}.")
    if checklist_verbosity == "brief":
        return checks[:5]
    return checks
