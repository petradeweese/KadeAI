"""Structured models for option selection inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TradeIntent:
    symbol: str
    direction: str
    style: str
    desired_position_size_usd: float
    max_hold_minutes: int


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    option_symbol: str
    option_type: str
    strike: float
    days_to_expiration: int
    bid: float
    ask: float
    delta: float | None = None
    volume: int = 0
    open_interest: int = 0


@dataclass(frozen=True)
class OptionCandidate:
    contract: OptionContract
    spread_pct: float
    affordability_score: float
    liquidity_score: float
    expiration_score: float
    delta_score: float
    total_score: float
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OptionAllocation:
    option_symbol: str
    contracts: int
    strike: float
    premium: float


@dataclass(frozen=True)
class SelectedOptionPlan:
    symbol: str
    profile: str
    direction: str
    target_contracts: int
    allocations: list[OptionAllocation]
    total_estimated_cost: float
    ranked_candidates: list[OptionCandidate]
