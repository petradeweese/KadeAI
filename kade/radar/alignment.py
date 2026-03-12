"""Multi-timeframe alignment helpers for deterministic radar confirmation."""

from __future__ import annotations

from dataclasses import dataclass

from kade.market.structure import TickerState


@dataclass(frozen=True)
class AlignmentResult:
    label: str
    trigger_trend: str
    bias_trend: str
    context_trend: str
    score: float


class TimeframeAlignmentClassifier:
    """Classifies setup alignment across trigger/bias/context timeframes."""

    def __init__(self, config: dict) -> None:
        self.config = config

    def classify(self, state: TickerState, debug: dict[str, float | str | bool | None]) -> AlignmentResult:
        trigger_trend = str(debug.get("trigger_trend_label") or "unknown")
        bias_trend = str(state.trend or debug.get("bias_trend_label") or "unknown")
        context_trend = str(debug.get("context_trend_label") or "unknown")
        expected = self._expected_direction(state)

        trend_map = {"trigger": trigger_trend, "bias": bias_trend, "context": context_trend}
        matched = sum(1 for trend in trend_map.values() if trend == expected)
        conflicting = sum(1 for trend in trend_map.values() if trend not in {expected, "neutral", "unknown"})

        if context_trend in {"unknown", "neutral"}:
            label = "weak_context"
        elif matched == 3:
            label = "fully_aligned"
        elif conflicting >= 2 or (trigger_trend != expected and bias_trend != expected):
            label = "conflicting"
        elif matched >= 2:
            label = "partially_aligned"
        else:
            label = "weak_context"

        score = float(self.config.get("scores", {}).get(label, 0.0))
        return AlignmentResult(
            label=label,
            trigger_trend=trigger_trend,
            bias_trend=bias_trend,
            context_trend=context_trend,
            score=score,
        )

    @staticmethod
    def _expected_direction(state: TickerState) -> str:
        if state.momentum in {"strong_down", "down_bias"} or state.trend == "bearish":
            return "bearish"
        return "bullish"
