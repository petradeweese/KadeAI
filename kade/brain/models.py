"""Structured models for Phase 5 memory, plans, style, and advisor reasoning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MemoryItem:
    item_id: str
    item_type: str
    symbol: str | None
    content: str
    created_at: datetime
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)


@dataclass
class TradePlan:
    plan_id: str
    symbol: str
    direction: str
    trigger_condition: str
    target_exit_idea: str
    max_hold_minutes: int
    invalidation_concept: str
    status: str
    created_at: datetime
    updated_at: datetime
    notes: list[str] = field(default_factory=list)
    source_mode: str = "operator_request"
    stance: str = "cautious"
    confidence_label: str = "medium"
    target_plausibility: str = "possible_but_stretched"
    market_alignment: str = "mixed"
    regime_fit: str = "unclear"
    trap_risk: str = "unknown"
    entry_plan: dict[str, object] = field(default_factory=dict)
    invalidation_plan: dict[str, object] = field(default_factory=dict)
    target_plan: dict[str, object] = field(default_factory=dict)
    hold_plan: dict[str, object] = field(default_factory=dict)
    risk_posture: str = "watch_only"
    execution_checklist: list[str] = field(default_factory=list)
    linked_target_move_board: dict[str, object] = field(default_factory=dict)
    linked_trade_idea_opinion: dict[str, object] = field(default_factory=dict)
    debug: dict[str, object] = field(default_factory=dict)


@dataclass
class PlanStatusEvent:
    plan_id: str
    from_status: str
    to_status: str
    changed_at: datetime
    reason: str | None = None


@dataclass
class StyleProfile:
    profile_name: str
    tone: str
    verbosity: str
    directness: str
    common_phrases: list[str] = field(default_factory=list)


@dataclass
class AdvisorOutput:
    symbol: str
    stance: str
    summary: str
    supporting_reasons: list[str]
    cautionary_reasons: list[str]
    suggested_action: str
    linked_plan_id: str | None = None
    generated_at: datetime | None = None
    debug: dict[str, float | str | int | bool | None] = field(default_factory=dict)
