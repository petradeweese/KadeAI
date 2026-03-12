"""Tracking snapshot formatters for runtime/operator payloads."""

from __future__ import annotations

from kade.tracking.models import PlanTrackingSnapshot


def to_payload(snapshot: PlanTrackingSnapshot) -> dict[str, object]:
    return {
        "plan_id": snapshot.plan_id,
        "symbol": snapshot.symbol,
        "status_before": snapshot.status_before,
        "status_after": snapshot.status_after,
        "trigger_state": snapshot.trigger_state,
        "invalidation_state": snapshot.invalidation_state,
        "staleness_state": snapshot.staleness_state,
        "posture_state": snapshot.posture_state,
        "summary": snapshot.summary,
        "reasons": list(snapshot.reasons),
        "actions": list(snapshot.actions),
        "updated_at": snapshot.updated_at,
        "debug": dict(snapshot.debug),
    }
