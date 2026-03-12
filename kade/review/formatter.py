"""Format review outputs for runtime and operator console."""

from __future__ import annotations

from dataclasses import asdict

from kade.review.models import ReviewMetricsSnapshot, TradeReviewResult


def review_to_payload(result: TradeReviewResult, include_debug: bool = True) -> dict[str, object]:
    payload = asdict(result)
    if not include_debug:
        payload.pop("debug", None)
    return payload


def metrics_to_payload(snapshot: ReviewMetricsSnapshot, compact: bool = False) -> dict[str, object]:
    payload = asdict(snapshot)
    if compact:
        return {
            "review_count": payload["review_count"],
            "discipline_distribution": payload["discipline_distribution"],
            "review_label_distribution": payload["review_label_distribution"],
            "invalidation_respected_rate": payload["invalidation_respected_rate"],
            "posture_respected_rate": payload["posture_respected_rate"],
            "cancellation_correctness_rate": payload["cancellation_correctness_rate"],
            "stale_management_rate": payload["stale_management_rate"],
            "generated_at": payload["generated_at"],
        }
    return payload
