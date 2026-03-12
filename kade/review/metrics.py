"""Aggregate deterministic metrics for trade reviews."""

from __future__ import annotations

from collections import Counter

from kade.review.models import ReviewMetricsSnapshot
from kade.utils.time import utc_now_iso


class ReviewMetricsAggregator:
    def __init__(self, config: dict[str, object] | None = None) -> None:
        self.config = config or {}

    def build_snapshot(self, reviews: list[dict[str, object]], now_iso: str | None = None) -> ReviewMetricsSnapshot:
        count = len(reviews)
        discipline_dist = Counter(str(item.get("discipline_label", "unknown")) for item in reviews)
        review_dist = Counter(str(item.get("review_label", "unknown")) for item in reviews)

        def _rate(key: str, truthy: object = "true") -> float:
            if count == 0:
                return 0.0
            hits = 0
            for item in reviews:
                value = self._nested_value(item, key)
                if truthy == "true":
                    if bool(value):
                        hits += 1
                elif value == truthy:
                    hits += 1
            return round(hits / count, 4)

        return ReviewMetricsSnapshot(
            review_count=count,
            discipline_distribution=dict(discipline_dist),
            review_label_distribution=dict(review_dist),
            invalidation_respected_rate=_rate("invalidation_respected"),
            posture_respected_rate=_rate("posture_respected"),
            cancellation_correctness_rate=_rate("metrics.cancellation_correctness"),
            stale_management_rate=_rate("metrics.stale_respected"),
            performance_by_symbol=self._group(reviews, "symbol"),
            performance_by_direction=self._group(reviews, "direction"),
            performance_by_stance=self._group(reviews, "plan.stance"),
            performance_by_risk_posture=self._group(reviews, "plan.risk_posture"),
            performance_by_target_plausibility=self._group(reviews, "plan.target_plausibility"),
            performance_by_plan_status=self._group(reviews, "final_status"),
            performance_by_setup_tag=self._group_setup_tags(reviews),
            generated_at=now_iso or utc_now_iso(),
            debug={"retention_limit": int(self.config.get("history_limit", 120))},
        )

    def _nested_value(self, obj: dict[str, object], dotted: str) -> object:
        cur: object = obj
        for key in dotted.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur

    def _nested_get(self, obj: dict[str, object], dotted: str, default: str = "unknown") -> str:
        value = self._nested_value(obj, dotted)
        return str(value if value is not None else default)

    def _group(self, reviews: list[dict[str, object]], field: str) -> dict[str, dict[str, int]]:
        grouped: dict[str, Counter[str]] = {}
        for review in reviews:
            key = self._nested_get(review, field)
            grouped.setdefault(key, Counter())
            grouped[key][str(review.get("review_label", "unknown"))] += 1
        return {key: dict(counter) for key, counter in grouped.items()}

    def _group_setup_tags(self, reviews: list[dict[str, object]]) -> dict[str, dict[str, int]]:
        grouped: dict[str, Counter[str]] = {}
        for review in reviews:
            plan = review.get("plan") if isinstance(review.get("plan"), dict) else {}
            board = plan.get("linked_target_move_board") if isinstance(plan.get("linked_target_move_board"), dict) else {}
            tags = board.get("setup_tags")
            normalized = tags if isinstance(tags, list) and tags else ["untagged"]
            for tag in normalized:
                grouped.setdefault(str(tag), Counter())
                grouped[str(tag)][str(review.get("review_label", "unknown"))] += 1
        return {key: dict(counter) for key, counter in grouped.items()}
