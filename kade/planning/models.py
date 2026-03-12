"""Structured trade-plan models for deterministic Phase 14 planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class EntryPlan:
    entry_style: str
    trigger_condition: str
    confirmation_signals: list[str] = field(default_factory=list)
    avoid_if: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InvalidationPlan:
    invalidation_condition: str
    soft_invalidation: list[str] = field(default_factory=list)
    hard_invalidation: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TargetPlan:
    primary_target: str
    secondary_target: str
    scale_out_guidance: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HoldPlan:
    max_hold_minutes: int
    expected_time_window: str
    stale_trade_rule: str


@dataclass(frozen=True)
class TradePlanContext:
    symbol: str
    direction: str
    ticker_state: object
    radar_context: dict[str, object]
    breadth_context: dict[str, object]
    source_mode: str = "operator_request"
    trade_idea_opinion: dict[str, object] | None = None
    target_move_board: dict[str, object] | None = None
    user_request_context: dict[str, object] | None = None


@dataclass(frozen=True)
class TradePlanDecision:
    stance: str
    confidence_label: str
    target_plausibility: str
    market_alignment: str
    regime_fit: str
    trap_risk: str
    entry_plan: EntryPlan
    invalidation_plan: InvalidationPlan
    target_plan: TargetPlan
    hold_plan: HoldPlan
    risk_posture: str
    execution_checklist: list[str]
    linked_target_move_board: dict[str, object]
    linked_trade_idea_opinion: dict[str, object]
    notes: list[str]
    debug: dict[str, object]
    generated_at: datetime
