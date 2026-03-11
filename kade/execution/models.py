"""Execution models for paper order workflow and guardrails."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    option_symbol: str
    contracts: int
    side: str
    limit_price: float
    mode: str
    order_type: str


@dataclass(frozen=True)
class GuardrailFailure:
    code: str
    reason: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionRejection:
    request: OrderRequest
    failure: GuardrailFailure


@dataclass(frozen=True)
class OrderResult:
    request: OrderRequest
    status: str
    filled_contracts: int
    remaining_contracts: int
    avg_fill_price: float | None
    simulated_slippage: float
    nudged_limit_price: float | None = None
    notes: list[str] = field(default_factory=list)
