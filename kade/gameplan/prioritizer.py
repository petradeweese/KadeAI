"""Deterministic posture and watchlist prioritization logic."""

from __future__ import annotations

from kade.gameplan.models import MarketPostureAssessment, SessionRiskNote, WatchlistPriority
from kade.market.intelligence.models import MarketContextSnapshot


class MarketPostureEngine:
    def __init__(self, config: dict[str, object]) -> None:
        self.cfg = config
        self.thresholds = dict(config.get("posture_thresholds", {}))

    def classify(self, snapshot: MarketContextSnapshot) -> MarketPostureAssessment:
        regime = snapshot.regime.regime_label
        confidence = float(snapshot.regime.regime_confidence)
        macro_count = len([item for item in snapshot.key_news if item.catalyst_type in {"macro", "regulatory"}])
        earnings_density = len(snapshot.earnings)
        mover_concentration = len({item.symbol for item in snapshot.top_movers[:4]})

        reasons: list[str] = [f"Regime is {regime} at confidence {confidence:.2f}."]
        posture = "mixed"
        if macro_count >= int(self.thresholds.get("volatile_event_macro_count", 2)):
            posture = "volatile_event"
            reasons.append("Macro or regulatory catalysts are elevated.")
        elif earnings_density >= int(self.thresholds.get("catalyst_heavy_earnings_count", 5)):
            posture = "catalyst_heavy"
            reasons.append("Earnings density is above normal.")
        elif regime == "trend" and confidence >= float(self.thresholds.get("trend_favorable_confidence", 0.75)):
            posture = "trend_favorable"
            reasons.append("Trend regime has strong confidence.")
        elif regime == "trend":
            posture = "cautious_trend"
            reasons.append("Trend exists but confidence is moderate.")
        elif regime in {"chop", "range"}:
            posture = "chop_risk"
            reasons.append("Range/chop regime favors patience.")

        if snapshot.market_clock.session_label not in {"pre_market", "regular", "open"}:
            reasons.append("Session is outside normal premarket/open windows.")
        if mover_concentration <= 2 and snapshot.top_movers:
            reasons.append("Mover concentration is narrow.")

        return MarketPostureAssessment(
            posture_label=posture,
            regime_label=regime,
            regime_confidence=confidence,
            session_label=snapshot.market_clock.session_label,
            reasons=reasons,
            debug={"macro_count": macro_count, "earnings_density": earnings_density, "mover_concentration": mover_concentration},
        )


class WatchlistPrioritizer:
    def __init__(self, config: dict[str, object]) -> None:
        self.cfg = config
        self.weights = dict(config.get("watchlist_weights", {}))

    def rank(self, snapshot: MarketContextSnapshot, watchlist: list[str], explicit_symbols: list[str] | None = None) -> list[WatchlistPriority]:
        symbols = sorted(set([*watchlist, *(explicit_symbols or [])]))
        movers = {item.symbol: item for item in snapshot.top_movers}
        active = {item.symbol: item for item in snapshot.most_active}
        news_by_symbol: dict[str, list[object]] = {}
        for item in snapshot.key_news:
            for symbol in item.symbols:
                news_by_symbol.setdefault(symbol, []).append(item)

        ranked: list[WatchlistPriority] = []
        for symbol in symbols:
            score = 0.0
            reasons: list[str] = []
            context = snapshot.cross_symbol_context.get(symbol)
            if context and context.alignment_label == "aligned":
                score += float(self.weights.get("alignment", 2.0))
                reasons.append("Aligned with broad market context.")
            elif context and context.alignment_label == "conflict":
                score -= float(self.weights.get("conflict_penalty", 2.0))
                reasons.append("Conflicts with benchmark context.")

            symbol_news = news_by_symbol.get(symbol, [])
            if symbol_news:
                score += float(self.weights.get("symbol_catalyst", 1.5))
                reasons.append("Has symbol-specific catalyst.")

            if symbol in movers:
                score += float(self.weights.get("mover", 1.0))
                reasons.append("Appears in top movers.")
            if symbol in active:
                score += float(self.weights.get("activity", 1.0))
                reasons.append("Shows elevated activity.")

            if snapshot.regime.regime_label == "trend" and context and context.alignment_label == "aligned":
                score += float(self.weights.get("regime_alignment_bonus", 1.0))
                reasons.append("Aligned with trend regime.")
            if snapshot.regime.regime_label in {"chop", "range"} and symbol in movers:
                score -= float(self.weights.get("chop_mover_penalty", 1.0))
                reasons.append("High activity inside chop/range regime.")

            priority = self._priority_from_score(score)
            ranked.append(
                WatchlistPriority(
                    symbol=symbol,
                    priority=priority,
                    score=round(score, 3),
                    reasons=reasons or ["No meaningful catalyst or alignment edge."],
                    debug={"news_count": len(symbol_news), "has_mover": symbol in movers, "has_activity": symbol in active},
                )
            )

        return sorted(ranked, key=lambda item: (item.score, item.symbol), reverse=True)

    @staticmethod
    def _priority_from_score(score: float) -> str:
        if score >= 4.0:
            return "priority_high"
        if score >= 2.0:
            return "priority_medium"
        if score >= 0.75:
            return "priority_low"
        if score <= -1.0:
            return "avoid"
        return "monitor_only"


def build_risk_notes(snapshot: MarketContextSnapshot, posture: MarketPostureAssessment) -> list[SessionRiskNote]:
    notes: list[SessionRiskNote] = []
    if posture.posture_label in {"volatile_event", "catalyst_heavy"}:
        notes.append(SessionRiskNote(label="event_risk", message="Catalyst load is elevated; reduce size and demand confirmation."))
    if snapshot.regime.regime_label in {"range", "chop"}:
        notes.append(SessionRiskNote(label="chop_risk", message="Range/chop regime can whipsaw momentum entries."))
    if len(snapshot.top_movers) >= 4 and len({item.symbol for item in snapshot.top_movers[:4]}) <= 2:
        notes.append(SessionRiskNote(label="narrow_leadership", message="Leadership appears narrow; avoid broad assumptions."))
    return notes
