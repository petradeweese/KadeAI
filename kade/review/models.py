"""Deterministic trade review models for Phase 16."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TradeReviewContext:
    plan: dict[str, object]
    tracking_snapshots: list[dict[str, object]] = field(default_factory=list)
    final_status: str | None = None
    execution_state: dict[str, object] | None = None
    exit_reason: str | None = None
    realized_outcome: dict[str, object] | None = None
    notes: str | None = None
    now_iso: str | None = None


@dataclass(frozen=True)
class DisciplineEvaluation:
    discipline_label: str
    invalidation_respected: bool
    posture_respected: bool
    stale_respected: bool
    cancellation_correctness: bool
    checklist_adherence: float
    plan_followed: bool
    strengths: list[str] = field(default_factory=list)
    mistakes: list[str] = field(default_factory=list)
    debug: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanOutcomeEvaluation:
    outcome_label: str
    plan_quality_label: str
    setup_worked_as_expected: bool
    final_status: str
    strengths: list[str] = field(default_factory=list)
    mistakes: list[str] = field(default_factory=list)
    debug: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TradeReviewResult:
    plan_id: str
    symbol: str
    direction: str
    final_status: str
    review_label: str
    discipline_label: str
    plan_quality_label: str
    outcome_label: str
    invalidation_respected: bool
    posture_respected: bool
    checklist_adherence: float
    plan_followed: bool
    summary: str
    strengths: list[str]
    mistakes: list[str]
    lessons: list[str]
    metrics: dict[str, object]
    reviewed_at: str
    debug: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewMetricsSnapshot:
    review_count: int
    discipline_distribution: dict[str, int]
    review_label_distribution: dict[str, int]
    invalidation_respected_rate: float
    posture_respected_rate: float
    cancellation_correctness_rate: float
    stale_management_rate: float
    performance_by_symbol: dict[str, dict[str, int]]
    performance_by_direction: dict[str, dict[str, int]]
    performance_by_stance: dict[str, dict[str, int]]
    performance_by_risk_posture: dict[str, dict[str, int]]
    performance_by_target_plausibility: dict[str, dict[str, int]]
    performance_by_plan_status: dict[str, dict[str, int]]
    performance_by_setup_tag: dict[str, dict[str, int]]
    generated_at: str
    debug: dict[str, object] = field(default_factory=dict)
