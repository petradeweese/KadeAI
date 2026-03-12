"""Structured strategy intelligence models for deterministic analytics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class SetupArchetypeResult:
    archetype_label: str
    confidence: float
    reasoning: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SetupArchetype:
    plan_id: str
    symbol: str
    setup_type: str
    regime: str
    posture: str
    direction: str
    entry_price: float | None
    target_price: float | None
    invalidation_price: float | None
    outcome: str
    roi: float
    discipline_label: str
    archetype_label: str
    confidence: float
    reasoning: list[str]
    created_at: str
    completed_at: str

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GroupedPerformanceStats:
    group_key: str
    dimension: str
    win_rate: float
    average_roi: float
    median_roi: float
    trade_count: int
    max_drawdown: float
    avg_hold_minutes: float

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RegimePerformanceSummary:
    regime: str
    trade_count: int
    win_rate: float
    avg_roi: float
    disciplined_rate: float

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SymbolPerformanceSummary:
    symbol: str
    trade_count: int
    win_rate: float
    avg_roi: float
    best_setup: str
    worst_setup: str

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlanCalibrationResult:
    target_realism: str
    target_hit_rate: float
    avg_target_distance: float
    avg_actual_move: float
    invalidation_hit_rate: float
    invalidation_respect_rate: float
    avg_loss_if_ignored: float
    discipline_rate: float
    avg_time_to_target: float
    avg_time_to_stop: float
    time_horizon_accuracy: float
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DisciplineImpactSummary:
    disciplined_win_rate: float
    undisciplined_win_rate: float
    avg_roi_disciplined: float
    avg_roi_undisciplined: float
    disciplined_count: int
    undisciplined_count: int

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyPerformanceSnapshot:
    trade_count: int
    win_rate: float
    average_roi: float
    median_roi: float
    max_drawdown: float
    avg_hold_minutes: float

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyAnalyticsSnapshot:
    setup_archetype_stats: list[dict[str, object]]
    regime_performance: list[dict[str, object]]
    symbol_performance: list[dict[str, object]]
    discipline_impact: dict[str, object]
    plan_calibration_summary: dict[str, object]
    recent_trades_summary: dict[str, object]
    grouped_statistics: dict[str, list[dict[str, object]]]
    generated_at: str

    def to_payload(self) -> dict[str, object]:
        return asdict(self)
