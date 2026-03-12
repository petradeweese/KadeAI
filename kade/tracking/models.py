"""Deterministic trade-plan tracking models for Phase 15."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from kade.brain.models import TradePlan
from kade.market.structure import TickerState


@dataclass(frozen=True)
class TradePlanTrackingContext:
    plan: TradePlan
    ticker_state: TickerState
    radar_context: dict[str, object]
    breadth_context: dict[str, object]
    elapsed_minutes: int | None = None
    execution_state: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class TriggerEvaluation:
    state: str
    reasons: list[str] = field(default_factory=list)
    debug: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class InvalidationEvaluation:
    state: str
    reasons: list[str] = field(default_factory=list)
    debug: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StalenessEvaluation:
    state: str
    reasons: list[str] = field(default_factory=list)
    debug: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TradePlanEvaluation:
    trigger: TriggerEvaluation
    invalidation: InvalidationEvaluation
    staleness: StalenessEvaluation
    posture_state: str
    summary: str
    reasons: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    debug: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanTrackingSnapshot:
    plan_id: str
    symbol: str
    status_before: str
    status_after: str
    trigger_state: str
    invalidation_state: str
    staleness_state: str
    posture_state: str
    summary: str
    reasons: list[str]
    actions: list[str]
    updated_at: str
    debug: dict[str, object] = field(default_factory=dict)
