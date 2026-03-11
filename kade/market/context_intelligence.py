"""Phase 2B market context intelligence (regime, breadth, trap heuristics)."""

from __future__ import annotations

from dataclasses import dataclass

from kade.market.structure import Bar, TickerState


@dataclass
class BreadthSnapshot:
    bias: str
    advancing_ratio: float | None
    confirmation: str


class MarketContextIntelligence:
    """Deterministic, config-driven context classification helpers."""

    def __init__(self, config: dict) -> None:
        self.config = config

    def baseline_regime(
        self,
        qqq_state: TickerState | None,
        spy_state: TickerState | None,
        qqq_debug: dict[str, float | str | None],
        spy_debug: dict[str, float | str | None] | None,
    ) -> str:
        regime_cfg = self.config["regime"]
        qqq_slope = self._as_float(qqq_debug.get("trend_slope"))
        spy_slope = self._as_float((spy_debug or {}).get("trend_slope"))
        strong_slope = regime_cfg["baseline_strong_slope"]

        if qqq_slope is not None and abs(qqq_slope) >= strong_slope:
            return "trend"
        if qqq_state and qqq_state.momentum in {"strong_up", "strong_down"}:
            return "momentum"
        if qqq_state and qqq_state.volume_state == "contracting":
            return "slow"
        if (
            qqq_state
            and spy_state
            and qqq_state.trend == "neutral"
            and spy_state.trend == "neutral"
            and qqq_slope is not None
            and spy_slope is not None
            and abs(qqq_slope) <= regime_cfg["baseline_range_slope_max"]
            and abs(spy_slope) <= regime_cfg["baseline_range_slope_max"]
        ):
            return "range"
        return "unknown"

    def breadth_snapshot(self, states: dict[str, TickerState]) -> BreadthSnapshot:
        breadth_cfg = self.config["breadth"]
        excluded = set(breadth_cfg.get("exclude_symbols", []))
        tracked = [state for symbol, state in states.items() if symbol not in excluded]
        if not tracked:
            return BreadthSnapshot(bias="unknown", advancing_ratio=None, confirmation="unknown")

        advancing = sum(1 for state in tracked if state.trend == "bullish")
        declining = sum(1 for state in tracked if state.trend == "bearish")
        total = len(tracked)
        ratio = advancing / total if total else None

        if ratio is None:
            bias = "unknown"
        elif ratio >= breadth_cfg["bullish_ratio_min"]:
            bias = "risk_on"
        elif ratio <= breadth_cfg["bearish_ratio_max"]:
            bias = "risk_off"
        else:
            bias = "mixed"

        if advancing > declining:
            confirmation = "advancers_lead"
        elif declining > advancing:
            confirmation = "decliners_lead"
        else:
            confirmation = "balanced"

        return BreadthSnapshot(bias=bias, advancing_ratio=ratio, confirmation=confirmation)

    def ticker_regime(
        self,
        baseline_regime: str,
        state: TickerState,
        debug: dict[str, float | str | None],
    ) -> str:
        regime_cfg = self.config["regime"]
        slope = self._as_float(debug.get("trend_slope"))
        if slope is None:
            return baseline_regime if baseline_regime != "unknown" else "unknown"

        if abs(slope) >= regime_cfg["momentum_slope_min"] and state.momentum in {"strong_up", "strong_down"}:
            return "momentum"
        if abs(slope) >= regime_cfg["trend_slope_min"]:
            return "trend"
        if abs(slope) <= regime_cfg["range_slope_max"] and state.structure == "range_or_mixed":
            return "range"
        if state.volume_state == "contracting":
            return "slow"

        return baseline_regime if baseline_regime != "unknown" else "unknown"

    def trap_risk(self, state: TickerState, debug: dict[str, float | str | None], bars_trigger: list[Bar]) -> str:
        trap_cfg = self.config["trap_detection"]
        if len(bars_trigger) < 3 or state.last_price is None or state.vwap is None:
            return "unknown"

        signals = 0
        volume_accel = self._as_float(debug.get("volume_acceleration"))
        breakout = debug.get("structure_breakout")

        vwap_distance = abs(state.last_price - state.vwap) / state.vwap if state.vwap else 0.0
        if state.last_price >= state.vwap and vwap_distance <= trap_cfg["weak_vwap_break_distance_max"]:
            signals += 1

        recent_low = min(bar.low for bar in bars_trigger[-3:])
        if state.last_price >= state.vwap and state.last_price <= recent_low * (1 + trap_cfg["failed_reclaim_buffer"]):
            signals += 1

        if breakout == "breakout_up" and volume_accel is not None and volume_accel <= trap_cfg["low_volume_breakout_acceleration_max"]:
            signals += 1

        if signals >= trap_cfg["high_signal_count_min"]:
            return "high"
        if signals >= trap_cfg["moderate_signal_count_min"]:
            return "moderate"
        return "low"

    def qqq_confirmation_with_breadth(self, qqq_confirmation: str | None, breadth_bias: str) -> str:
        if qqq_confirmation is None:
            return "unknown"
        if qqq_confirmation == "confirmed" and breadth_bias == "risk_on":
            return "confirmed_breadth_aligned"
        if qqq_confirmation == "divergent" and breadth_bias == "risk_off":
            return "divergent_risk_off"
        if breadth_bias == "mixed":
            return "mixed_breadth"
        return qqq_confirmation

    @staticmethod
    def _as_float(value: float | str | None) -> float | None:
        return float(value) if isinstance(value, (int, float)) else None
