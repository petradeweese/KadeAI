"""Operator-friendly gameplan summary formatting."""

from __future__ import annotations

from kade.gameplan.models import GameplanSummary, MarketPostureAssessment, SessionRiskNote, WatchlistPriority, CatalystAgendaItem


class PremarketGameplanFormatter:
    def build_summary(
        self,
        *,
        posture: MarketPostureAssessment,
        catalysts: list[CatalystAgendaItem],
        priorities: list[WatchlistPriority],
        risks: list[SessionRiskNote],
        opportunities: list[str],
    ) -> GameplanSummary:
        top_symbols = [item.symbol for item in priorities if item.priority in {"priority_high", "priority_medium"}][:3]
        headline = f"Market posture is {posture.posture_label}. Regime is {posture.regime_label} ({posture.regime_confidence:.2f})."
        return GameplanSummary(
            headline=headline,
            posture=posture.posture_label,
            top_symbols=top_symbols,
            catalyst_count=len(catalysts),
            risk_count=len(risks),
            opportunity_count=len(opportunities),
        )

    def agenda_notes(self, summary: GameplanSummary, catalysts: list[CatalystAgendaItem], priorities: list[WatchlistPriority]) -> list[str]:
        notes = [summary.headline]
        if catalysts:
            notes.append(f"Key catalysts: {', '.join(item.headline for item in catalysts[:3])}.")
        if priorities:
            top = [item.symbol for item in priorities[:3]]
            notes.append(f"Top watchlist focus: {', '.join(top)}.")
        return notes
