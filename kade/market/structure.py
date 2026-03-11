"""Structured market models used across Kade market modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid_price: float
    ask_price: float
    bid_size: float | None = None
    ask_size: float | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True)
class Trade:
    symbol: str
    price: float
    size: float
    timestamp: datetime


@dataclass
class IndicatorSnapshot:
    symbol: str
    timestamp: datetime
    values: dict[str, float | bool | None] = field(default_factory=dict)


@dataclass
class TickerState:
    """Canonical per-ticker state container for future mental model logic."""

    symbol: str
    last_price: float | None = None
    vwap: float | None = None
    trend: str | None = None
    structure: str | None = None
    momentum: str | None = None
    volume_state: str | None = None
    qqq_confirmation: str | None = None
    regime: str | None = None
    trap_risk: str | None = None
    confidence_label: str | None = None
    confidence_reason: str | None = None
    updated_at: datetime | None = None


class MarketDataClient(Protocol):
    """Protocol for market data clients (Alpaca and future providers)."""

    def get_latest_quote(self, symbol: str) -> Quote:
        ...

    def get_latest_trade(self, symbol: str) -> Trade:
        ...

    def get_bars(self, symbol: str, timeframe: str, limit: int) -> list[Bar]:
        ...
