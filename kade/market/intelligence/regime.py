"""Rule-based market regime engine."""

from __future__ import annotations

from datetime import datetime

from kade.market.intelligence.models import RegimeSnapshot


class MarketRegimeEngine:
    def __init__(self, config: dict[str, object]) -> None:
        self.cfg = config

    def evaluate(self, *, generated_at: str, market_clock_open: bool, breadth_bias: str, spy_trend_pct: float | None, qqq_trend_pct: float | None, volume_bias: str, intraday_range_state: str, has_major_news: bool) -> RegimeSnapshot:
        trend_threshold = float(self.cfg.get("trend_threshold_pct", 0.35))
        chop_threshold = float(self.cfg.get("chop_threshold_pct", 0.12))
        volatile_threshold = float(self.cfg.get("volatile_threshold_pct", 1.2))
        confidence = 0.45
        reasons: list[str] = []
        label = "range"

        avg_trend = self._avg_abs(spy_trend_pct, qqq_trend_pct)
        signed_alignment = self._aligned_direction(spy_trend_pct, qqq_trend_pct)

        if has_major_news:
            label = "news_event"
            confidence = 0.85
            reasons.append("major catalyst headlines detected")

        elif avg_trend is not None and avg_trend >= volatile_threshold:
            label = "volatile"
            confidence = 0.8
            reasons.append(f"index trend magnitude elevated ({avg_trend:.2f}%)")

        elif avg_trend is not None and avg_trend >= trend_threshold and signed_alignment:
            label = "trend"
            confidence = 0.76
            reasons.append("SPY and QQQ trend direction aligned")

        elif avg_trend is not None and avg_trend <= chop_threshold and intraday_range_state == "compressed":
            label = "chop"
            confidence = 0.7
            reasons.append("low directional progress with compressed range")

        if breadth_bias in {"risk_on", "risk_off"}:
            confidence = min(0.95, confidence + 0.08)
            reasons.append(f"breadth is {breadth_bias}")
        if volume_bias in {"expanding", "elevated"}:
            confidence = min(0.95, confidence + 0.05)
            reasons.append(f"volume is {volume_bias}")
        if not market_clock_open:
            confidence = max(0.35, confidence - 0.1)
            reasons.append("market is not in regular session")

        return RegimeSnapshot(
            timestamp=generated_at,
            source="market_regime_engine",
            regime_label=label,
            regime_confidence=round(confidence, 3),
            reasons=reasons[:6],
            debug={
                "breadth_bias": breadth_bias,
                "spy_trend_pct": spy_trend_pct,
                "qqq_trend_pct": qqq_trend_pct,
                "volume_bias": volume_bias,
                "intraday_range_state": intraday_range_state,
                "has_major_news": has_major_news,
                "evaluated_at": datetime.fromisoformat(generated_at).isoformat(),
            },
        )

    @staticmethod
    def _avg_abs(a: float | None, b: float | None) -> float | None:
        values = [abs(x) for x in [a, b] if isinstance(x, (int, float))]
        if not values:
            return None
        return sum(values) / len(values)

    @staticmethod
    def _aligned_direction(a: float | None, b: float | None) -> bool:
        if a is None or b is None:
            return False
        return (a >= 0 and b >= 0) or (a < 0 and b < 0)
