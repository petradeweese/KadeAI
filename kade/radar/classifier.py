"""Deterministic setup-pattern tagging for radar readability and scoring."""

from __future__ import annotations

from kade.market.structure import TickerState


class SetupPatternClassifier:
    def __init__(self, config: dict) -> None:
        self.config = config

    def classify(self, state: TickerState, debug: dict[str, float | str | bool | None]) -> list[str]:
        tags: list[str] = []
        structure = state.structure or "unknown"
        momentum = state.momentum or "unknown"
        trend = state.trend or "unknown"
        trap_risk = state.trap_risk or "unknown"
        volume_state = state.volume_state or "unknown"

        if structure in {"breakout_up", "breakout_down"} and momentum in {"strong_up", "strong_down"} and trap_risk != "high":
            tags.append("breakout_continuation")

        if self._is_vwap_reclaim(state):
            tags.append("vwap_reclaim")

        if structure.startswith("trend_continuation") and momentum in {"up_bias", "down_bias", "mixed"}:
            tags.append("trend_pullback")

        if structure in {"breakout_up", "breakout_down"} and trap_risk in {"high", "moderate"}:
            tags.append("failed_breakout_risk")

        if structure == "range_or_mixed" and (state.regime in {"range", "slow"} or momentum == "mixed"):
            tags.append("range_chop")

        if momentum in {"strong_up", "strong_down"} and volume_state == "expanding" and self._is_extension(state):
            tags.append("momentum_extension")

        if trend == "unknown" and not tags:
            tags.append("range_chop")

        return sorted(set(tags))

    def _is_vwap_reclaim(self, state: TickerState) -> bool:
        if state.last_price is None or state.vwap is None:
            return False
        if state.last_price < state.vwap:
            return False
        reason = (state.confidence_reason or "").lower()
        return "vwap" in reason

    def _is_extension(self, state: TickerState) -> bool:
        if state.last_price is None or state.vwap is None or state.vwap == 0:
            return False
        distance = abs(state.last_price - state.vwap) / state.vwap
        extension_min = float(self.config.get("extension_distance_min", 0.0025))
        return distance >= extension_min
