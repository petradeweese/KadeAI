"""Deterministic market intelligence domain models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class MarketClockSnapshot:
    timestamp: str
    source: str
    is_open: bool
    next_open: str | None
    next_close: str | None
    session_label: str
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class MarketCalendarDay:
    date: str
    source: str
    open_time: str | None
    close_time: str | None
    session_label: str

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class NewsItem:
    timestamp: str
    source: str
    headline: str
    summary: str
    symbols: list[str]
    url: str | None
    catalyst_type: str
    relevance_label: str
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class NewsSummary:
    timestamp: str
    source: str
    headline_count: int
    catalyst_breakdown: dict[str, int]
    key_items: list[NewsItem]

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["key_items"] = [item.to_payload() for item in self.key_items]
        return payload


@dataclass
class SymbolMover:
    timestamp: str
    source: str
    symbol: str
    move_pct: float
    last_price: float | None
    volume: float | None
    direction: str
    mover_type: str
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class SymbolActivity:
    timestamp: str
    source: str
    symbol: str
    volume: float
    trade_count: int | None
    last_price: float | None

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class EarningsEvent:
    timestamp: str
    source: str
    symbol: str
    event_date: str
    timing: str
    estimate_eps: float | None = None
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RegimeSnapshot:
    timestamp: str
    source: str
    regime_label: str
    regime_confidence: float
    reasons: list[str]
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class CrossSymbolContext:
    timestamp: str
    source: str
    symbol: str
    benchmark_symbols: list[str]
    sector_proxy: str | None
    alignment_label: str
    reasons: list[str]
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class MarketContextSnapshot:
    generated_at: str
    source: str
    market_clock: MarketClockSnapshot
    market_calendar: list[MarketCalendarDay]
    regime: RegimeSnapshot
    key_news: list[NewsItem]
    top_movers: list[SymbolMover]
    most_active: list[SymbolActivity]
    earnings: list[EarningsEvent]
    cross_symbol_context: dict[str, CrossSymbolContext]
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "source": self.source,
            "market_clock": self.market_clock.to_payload(),
            "market_calendar": [day.to_payload() for day in self.market_calendar],
            "regime": self.regime.to_payload(),
            "key_news": [item.to_payload() for item in self.key_news],
            "top_movers": [item.to_payload() for item in self.top_movers],
            "most_active": [item.to_payload() for item in self.most_active],
            "earnings": [item.to_payload() for item in self.earnings],
            "cross_symbol_context": {symbol: context.to_payload() for symbol, context in self.cross_symbol_context.items()},
            "debug": dict(self.debug),
        }
