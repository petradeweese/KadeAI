"""Structured deterministic premarket gameplan models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class MarketPostureAssessment:
    posture_label: str
    regime_label: str
    regime_confidence: float
    session_label: str
    reasons: list[str] = field(default_factory=list)
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class CatalystAgendaItem:
    category: str
    scope: str
    priority: str
    headline: str
    symbols: list[str] = field(default_factory=list)
    summary: str = ""
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class WatchlistPriority:
    symbol: str
    priority: str
    score: float
    reasons: list[str] = field(default_factory=list)
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class SessionRiskNote:
    label: str
    message: str

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class GameplanSummary:
    headline: str
    posture: str
    top_symbols: list[str] = field(default_factory=list)
    catalyst_count: int = 0
    risk_count: int = 0
    opportunity_count: int = 0

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class PremarketGameplan:
    generated_at: str
    market_posture: MarketPostureAssessment
    key_catalysts: list[CatalystAgendaItem]
    earnings_today: list[dict[str, object]]
    futures_or_index_context: dict[str, object]
    movers_to_watch: list[dict[str, object]]
    most_active_context: list[dict[str, object]]
    watchlist_priorities: list[WatchlistPriority]
    risks: list[SessionRiskNote]
    opportunities: list[str]
    agenda_notes: list[str]
    summary: GameplanSummary
    debug: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "market_posture": self.market_posture.to_payload(),
            "regime_label": self.market_posture.regime_label,
            "regime_confidence": self.market_posture.regime_confidence,
            "key_catalysts": [item.to_payload() for item in self.key_catalysts],
            "earnings_today": list(self.earnings_today),
            "futures_or_index_context": dict(self.futures_or_index_context),
            "movers_to_watch": list(self.movers_to_watch),
            "most_active_context": list(self.most_active_context),
            "watchlist_priorities": [item.to_payload() for item in self.watchlist_priorities],
            "risks": [item.to_payload() for item in self.risks],
            "opportunities": list(self.opportunities),
            "agenda_notes": list(self.agenda_notes),
            "summary": self.summary.to_payload(),
            "debug": dict(self.debug),
        }
