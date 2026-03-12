"""Market state and mental-model scaffolding for Phase 2A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from kade.market.indicators import (
    consolidation_breakout,
    higher_highs_lower_highs,
    macd,
    regression_trend_slope,
    rsi,
    volume_acceleration,
    vwap,
)
from kade.market.structure import Bar, TickerState


@dataclass
class ConfidenceResult:
    label: str
    reason: str
    score: float


@dataclass
class TickerComputationResult:
    state: TickerState
    debug: dict[str, float | str | None]


class MentalModelBuilder:
    """Converts raw indicators into deterministic ticker state labels."""

    def __init__(self, config: dict) -> None:
        self.config = config

    def build(
        self,
        symbol: str,
        bars_trigger: list[Bar],
        bars_bias: list[Bar],
        bars_context: list[Bar],
        qqq_trend: str | None,
    ) -> TickerComputationResult:
        trigger_closes = [b.close for b in bars_trigger]
        bias_closes = [b.close for b in bars_bias]
        context_closes = [b.close for b in bars_context]
        context_highs = [b.high for b in bars_context]
        trigger_volumes = [b.volume for b in bars_trigger]

        last_price = trigger_closes[-1] if trigger_closes else None
        trigger_vwap = vwap(bars_trigger)
        trigger_slope = regression_trend_slope(trigger_closes)
        slope = regression_trend_slope(bias_closes)
        context_slope = regression_trend_slope(context_closes)
        rsi_value = rsi(trigger_closes)
        macd_value = macd(trigger_closes)
        macd_hist = macd_value[2] if macd_value else None
        volume_accel = volume_acceleration(trigger_volumes)
        structure_breakout = consolidation_breakout(context_closes)
        swing_structure = higher_highs_lower_highs(context_highs)

        trigger_trend = self._trend_label(trigger_slope)
        trend = self._trend_label(slope)
        context_trend = self._trend_label(context_slope)
        structure = self._structure_label(structure_breakout, swing_structure)
        momentum = self._momentum_label(rsi_value, macd_hist)
        volume_state = self._volume_label(volume_accel)
        qqq_confirmation = self._qqq_confirmation(trend, qqq_trend)
        confidence = self._confidence_result(
            last_price=last_price,
            trigger_vwap=trigger_vwap,
            trend=trend,
            momentum=momentum,
            volume_state=volume_state,
            qqq_confirmation=qqq_confirmation,
        )

        ticker_state = TickerState(
            symbol=symbol,
            last_price=last_price,
            vwap=trigger_vwap,
            trend=trend,
            structure=structure,
            momentum=momentum,
            volume_state=volume_state,
            qqq_confirmation=qqq_confirmation,
            regime="unknown",
            trap_risk="unknown",
            confidence_label=confidence.label,
            confidence_reason=confidence.reason,
            updated_at=datetime.now(timezone.utc),
        )

        debug = {
            "trigger_trend_slope": trigger_slope,
            "trend_slope": slope,
            "context_trend_slope": context_slope,
            "trigger_trend_label": trigger_trend,
            "bias_trend_label": trend,
            "context_trend_label": context_trend,
            "rsi": rsi_value,
            "macd_hist": macd_hist,
            "volume_acceleration": volume_accel,
            "structure_breakout": structure_breakout,
            "swing_structure": swing_structure,
            "confidence_score_internal": confidence.score,
        }
        return TickerComputationResult(state=ticker_state, debug=debug)

    def _trend_label(self, slope: float | None) -> str:
        if slope is None:
            return "unknown"
        bullish = self.config["trend_slope"]["bullish"]
        bearish = self.config["trend_slope"]["bearish"]
        if slope >= bullish:
            return "bullish"
        if slope <= bearish:
            return "bearish"
        return "neutral"

    def _structure_label(self, breakout: str, swings: str) -> str:
        if breakout in {"breakout_up", "breakout_down"}:
            return breakout
        if swings == "higher_highs":
            return "trend_continuation_up"
        if swings == "lower_highs":
            return "trend_continuation_down"
        return "range_or_mixed"

    def _momentum_label(self, rsi_value: float | None, macd_hist: float | None) -> str:
        if rsi_value is None or macd_hist is None:
            return "unknown"
        rsi_bull = self.config["momentum_rsi"]["bullish"]
        rsi_bear = self.config["momentum_rsi"]["bearish"]
        macd_bull = self.config["momentum_macd_hist"]["bullish"]
        macd_bear = self.config["momentum_macd_hist"]["bearish"]

        if rsi_value >= rsi_bull and macd_hist >= macd_bull:
            return "strong_up"
        if rsi_value <= rsi_bear and macd_hist <= macd_bear:
            return "strong_down"
        if rsi_value >= 50 and macd_hist >= 0:
            return "up_bias"
        if rsi_value <= 50 and macd_hist <= 0:
            return "down_bias"
        return "mixed"

    def _volume_label(self, volume_accel: float | None) -> str:
        if volume_accel is None:
            return "unknown"
        if volume_accel >= self.config["volume_acceleration"]["strong"]:
            return "expanding"
        if volume_accel <= self.config["volume_acceleration"]["weak"]:
            return "contracting"
        return "stable"

    def _qqq_confirmation(self, trend: str, qqq_trend: str | None) -> str:
        if qqq_trend is None:
            return "unknown"
        if trend == qqq_trend:
            return "confirmed"
        if trend == "neutral" or qqq_trend == "neutral":
            return "mixed"
        return "divergent"

    def _confidence_result(
        self,
        last_price: float | None,
        trigger_vwap: float | None,
        trend: str,
        momentum: str,
        volume_state: str,
        qqq_confirmation: str,
    ) -> ConfidenceResult:
        score = 0.5
        reasons_for: list[str] = []
        reasons_against: list[str] = []

        if last_price is not None and trigger_vwap is not None:
            if last_price >= trigger_vwap:
                score += 0.1
                reasons_for.append("VWAP break is valid")
            else:
                score -= 0.1
                reasons_against.append("price is below VWAP")

        if trend == "bullish":
            score += 0.1
            reasons_for.append("trend slope is bullish")
        elif trend == "bearish":
            score -= 0.1
            reasons_against.append("trend slope is bearish")

        if momentum in {"strong_up", "up_bias"}:
            score += 0.1
            reasons_for.append("momentum supports continuation")
        elif momentum in {"strong_down", "down_bias"}:
            score -= 0.1
            reasons_against.append("momentum is fading")

        if volume_state == "expanding":
            score += 0.1
            reasons_for.append("volume expansion is healthy")
        elif volume_state == "contracting":
            score -= 0.1
            reasons_against.append("volume expansion is weaker than typical winning setups")

        if qqq_confirmation == "confirmed":
            score += 0.1
            reasons_for.append("QQQ confirms")
        elif qqq_confirmation == "divergent":
            score -= 0.1
            reasons_against.append("QQQ is not confirming")

        score = max(0.0, min(1.0, score))
        high_min = self.config["confidence"]["high_min"]
        moderate_min = self.config["confidence"]["moderate_min"]
        if score >= high_min:
            label = "high"
        elif score >= moderate_min:
            label = "moderate"
        else:
            label = "low"

        if reasons_for and reasons_against:
            reason = f"Confidence is {label} because {reasons_for[0]}, but {reasons_against[0]}."
        elif reasons_for:
            reason = f"Confidence is {label} because {reasons_for[0]}."
        elif reasons_against:
            reason = f"Confidence is {label} because {reasons_against[0]}."
        else:
            reason = f"Confidence is {label} due to mixed signals."

        return ConfidenceResult(label=label, reason=reason, score=score)
