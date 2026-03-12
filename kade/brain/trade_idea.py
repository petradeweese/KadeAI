"""Deterministic trade-idea opinion synthesis built on existing radar and market context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from logging import Logger

from kade.logging_utils import LogCategory, get_logger, log_event
from kade.market.structure import TickerState
from kade.utils.time import utc_now


@dataclass
class TradeIdeaOpinionRequest:
    symbol: str
    direction: str
    current_price: float
    target_price: float
    time_horizon_minutes: int
    user_context: str | None = None
    profile: str | None = None


@dataclass
class TradeIdeaOpinion:
    symbol: str
    direction: str
    current_price: float
    target_price: float
    time_horizon_minutes: int
    stance: str
    confidence_label: str
    target_plausibility: str
    market_alignment: str
    qqq_alignment: str
    breadth_alignment: str
    regime_fit: str
    trap_risk: str
    summary: str
    supporting_reasons: list[str] = field(default_factory=list)
    cautionary_reasons: list[str] = field(default_factory=list)
    suggested_next_step: str = ""
    timestamp: str = ""
    debug: dict[str, float | int | str | bool | None] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "current_price": self.current_price,
            "target_price": self.target_price,
            "time_horizon_minutes": self.time_horizon_minutes,
            "stance": self.stance,
            "confidence_label": self.confidence_label,
            "target_plausibility": self.target_plausibility,
            "market_alignment": self.market_alignment,
            "qqq_alignment": self.qqq_alignment,
            "breadth_alignment": self.breadth_alignment,
            "regime_fit": self.regime_fit,
            "trap_risk": self.trap_risk,
            "summary": self.summary,
            "supporting_reasons": self.supporting_reasons,
            "cautionary_reasons": self.cautionary_reasons,
            "suggested_next_step": self.suggested_next_step,
            "timestamp": self.timestamp,
            "debug": self.debug,
        }


class TradeIdeaOpinionEngine:
    def __init__(self, config: dict[str, object], logger: Logger | None = None) -> None:
        self.config = config
        self.logger = logger or get_logger(__name__)

    def evaluate(
        self,
        request: TradeIdeaOpinionRequest,
        ticker_state: TickerState,
        radar_context: dict[str, object],
        breadth_context: dict[str, object],
    ) -> TradeIdeaOpinion:
        normalized_direction = self._normalize_direction(request.direction)
        move_pct = self._move_pct(request.current_price, request.target_price)

        log_event(
            self.logger,
            LogCategory.COMMAND_EVENT,
            "Trade idea request received",
            symbol=request.symbol,
            direction=normalized_direction,
            target=request.target_price,
            horizon=request.time_horizon_minutes,
        )

        market_alignment, qqq_alignment, breadth_alignment = self._alignment_labels(normalized_direction, ticker_state, breadth_context)
        regime_fit = self._regime_fit_label(normalized_direction, ticker_state.regime)
        trap_risk = str(ticker_state.trap_risk or "unknown")
        target_plausibility, plausibility_reason, plausibility_score = self._target_plausibility(
            move_pct=move_pct,
            time_horizon_minutes=request.time_horizon_minutes,
            momentum=str(ticker_state.momentum or "unknown"),
            alignment_label=market_alignment,
            trap_risk=trap_risk,
            regime_fit=regime_fit,
        )

        support, cautions, score, confidence_score = self._score_and_reasons(
            direction=normalized_direction,
            ticker_state=ticker_state,
            radar_context=radar_context,
            market_alignment=market_alignment,
            qqq_alignment=qqq_alignment,
            breadth_alignment=breadth_alignment,
            regime_fit=regime_fit,
            trap_risk=trap_risk,
            target_plausibility=target_plausibility,
            plausibility_reason=plausibility_reason,
        )

        stance = self._stance_from_score(score)
        confidence_label = self._confidence_label(confidence_score)
        summary = self._summary(stance, request.symbol, target_plausibility, market_alignment, support, cautions)

        opinion = TradeIdeaOpinion(
            symbol=request.symbol,
            direction=normalized_direction,
            current_price=request.current_price,
            target_price=request.target_price,
            time_horizon_minutes=request.time_horizon_minutes,
            stance=stance,
            confidence_label=confidence_label,
            target_plausibility=target_plausibility,
            market_alignment=market_alignment,
            qqq_alignment=qqq_alignment,
            breadth_alignment=breadth_alignment,
            regime_fit=regime_fit,
            trap_risk=trap_risk,
            summary=summary,
            supporting_reasons=support[: self._limit("supporting_reasons_limit", 4)],
            cautionary_reasons=cautions[: self._limit("cautionary_reasons_limit", 4)],
            suggested_next_step=self._next_step(stance, target_plausibility),
            timestamp=utc_now().isoformat(),
            debug={
                "score": score,
                "confidence_score": confidence_score,
                "plausibility_score": round(plausibility_score, 3),
                "move_pct": round(move_pct, 4),
                "radar_score": float(radar_context.get("score", 0.0) or 0.0),
                "setup_tags": ",".join(radar_context.get("setup_tags", [])),
            },
        )

        log_event(
            self.logger,
            LogCategory.REASONING_EVENT,
            "Trade idea opinion generated",
            symbol=opinion.symbol,
            stance=opinion.stance,
            plausibility=opinion.target_plausibility,
            alignment=opinion.market_alignment,
            trap_risk=opinion.trap_risk,
        )
        return opinion

    def _score_and_reasons(
        self,
        direction: str,
        ticker_state: TickerState,
        radar_context: dict[str, object],
        market_alignment: str,
        qqq_alignment: str,
        breadth_alignment: str,
        regime_fit: str,
        trap_risk: str,
        target_plausibility: str,
        plausibility_reason: str,
    ) -> tuple[list[str], list[str], float, float]:
        weights = dict(self.config.get("alignment_importance", {}))
        penalties = dict(self.config.get("trap_risk_penalties", {}))
        support: list[str] = []
        cautions: list[str] = []
        score = 0.0
        confidence_score = 0.0

        radar_score = float(radar_context.get("score", 0.0) or 0.0)
        radar_rules = dict(self.config.get("radar_score", {}))
        if radar_score >= float(radar_rules.get("high", 70)):
            support.append("Radar score is high for this setup.")
            score += 1.2
            confidence_score += 1.0
        elif radar_score <= float(radar_rules.get("low", 40)):
            cautions.append("Radar conviction is currently light.")
            score -= 1.0
            confidence_score -= 0.7

        if market_alignment == "aligned":
            support.append("Direction aligns with trend and market context.")
            score += float(weights.get("market", 1.2))
            confidence_score += 0.8
        elif market_alignment == "mixed":
            cautions.append("Directional alignment is mixed.")
            score -= 0.6
        else:
            cautions.append("Direction conflicts with trend and context.")
            score -= 1.6
            confidence_score -= 1.0

        if qqq_alignment == "aligned":
            support.append("QQQ confirmation supports this direction.")
            score += float(weights.get("qqq", 0.8))
        elif qqq_alignment == "conflicting":
            cautions.append("QQQ confirmation is conflicting.")
            score -= float(weights.get("qqq", 0.8))

        if breadth_alignment == "aligned":
            support.append("Breadth bias is supportive.")
            score += float(weights.get("breadth", 0.7))
        elif breadth_alignment == "conflicting":
            cautions.append("Breadth bias is opposing this idea.")
            score -= float(weights.get("breadth", 0.7))

        if regime_fit == "fit":
            support.append(f"Regime ({ticker_state.regime}) fits directional continuation.")
            score += 0.7
        elif regime_fit == "unclear":
            cautions.append(f"Regime ({ticker_state.regime}) is less supportive for continuation.")
            score -= 0.6

        momentum = str(ticker_state.momentum or "unknown")
        if self._momentum_supports(direction, momentum):
            support.append(f"Momentum context ({momentum}) supports the move.")
            score += 1.0
        elif momentum == "mixed":
            cautions.append("Momentum is mixed.")
            score -= 0.6

        if target_plausibility == "realistic":
            support.append(plausibility_reason)
            score += 1.0
            confidence_score += 0.8
        elif target_plausibility == "possible_but_stretched":
            cautions.append(plausibility_reason)
            score -= 0.2
        elif target_plausibility == "unlikely":
            cautions.append(plausibility_reason)
            score -= 1.2
            confidence_score -= 0.7
        else:
            cautions.append(plausibility_reason)
            score -= 0.4

        penalty = float(penalties.get(trap_risk, 0.5 if trap_risk == "moderate" else 1.0 if trap_risk == "high" else 0.0))
        if penalty > 0:
            cautions.append(f"Trap risk is {trap_risk}.")
            score -= penalty
            confidence_score -= penalty / 2.0

        setup_tags = list(radar_context.get("setup_tags", []))
        if setup_tags:
            support.append(f"Setup tags: {', '.join(setup_tags[:2])}.")

        return support, cautions, score, confidence_score

    def _target_plausibility(
        self,
        move_pct: float,
        time_horizon_minutes: int,
        momentum: str,
        alignment_label: str,
        trap_risk: str,
        regime_fit: str,
    ) -> tuple[str, str, float]:
        horizon_cfg = dict(self.config.get("time_horizon_buckets", {}))
        plausibility_cfg = dict(self.config.get("target_plausibility", {}))
        range_proxy = float(horizon_cfg.get("short_move_proxy_pct", 0.7 if time_horizon_minutes <= 30 else 1.0 if time_horizon_minutes <= 90 else 1.3))
        if time_horizon_minutes > int(horizon_cfg.get("short_minutes", 30)):
            range_proxy = float(horizon_cfg.get("medium_move_proxy_pct", 1.0))
        if time_horizon_minutes > int(horizon_cfg.get("medium_minutes", 90)):
            range_proxy = float(horizon_cfg.get("long_move_proxy_pct", 1.3))
        ratio = (move_pct / range_proxy) if range_proxy > 0 else 99.0

        score = 0.0
        if ratio <= float(plausibility_cfg.get("realistic_ratio_max", 0.95)):
            score += 1.1
        elif ratio <= float(plausibility_cfg.get("stretched_ratio_max", 1.45)):
            score += 0.2
        else:
            score -= 1.1

        if momentum in {"strong_up", "strong_down"}:
            score += 0.4
        elif momentum in {"up_bias", "down_bias"}:
            score += 0.2
        elif momentum == "mixed":
            score -= 0.4

        if alignment_label == "aligned":
            score += 0.4
        elif alignment_label == "conflicting":
            score -= 0.6

        if regime_fit == "fit":
            score += 0.2
        elif regime_fit == "unclear":
            score -= 0.2

        if trap_risk == "high":
            score -= 0.5
        elif trap_risk == "moderate":
            score -= 0.2

        if score >= float(plausibility_cfg.get("realistic_score_min", 0.9)):
            return "realistic", "Target move looks realistic if current momentum holds.", score
        if score >= float(plausibility_cfg.get("stretched_score_min", -0.1)):
            return "possible_but_stretched", "Target is possible but stretched without extra acceleration.", score
        return "unlikely", "Target is unlikely in the stated window without a stronger acceleration regime.", score

    def _normalize_direction(self, direction: str) -> str:
        lowered = direction.strip().lower()
        mapping = {
            "put": "bearish",
            "short": "bearish",
            "bear": "bearish",
            "bearish": "bearish",
            "call": "bullish",
            "long": "bullish",
            "bull": "bullish",
            "bullish": "bullish",
        }
        return mapping.get(lowered, lowered)

    def _alignment_labels(
        self,
        direction: str,
        ticker_state: TickerState,
        breadth_context: dict[str, object],
    ) -> tuple[str, str, str]:
        trend = str(ticker_state.trend or "unknown")
        qqq_state = str(ticker_state.qqq_confirmation or "unknown")
        breadth = str(breadth_context.get("bias", "unknown"))

        aligned_trend = (direction == "bullish" and trend == "bullish") or (direction == "bearish" and trend == "bearish")
        qqq_aligned = (direction == "bullish" and "confirmed" in qqq_state and "divergent" not in qqq_state) or (
            direction == "bearish" and qqq_state in {"divergent", "divergent_risk_off"}
        )
        qqq_conflicting = (direction == "bullish" and qqq_state in {"divergent", "divergent_risk_off", "mixed_breadth"}) or (
            direction == "bearish" and "confirmed" in qqq_state and "divergent" not in qqq_state
        )

        breadth_aligned = (direction == "bullish" and breadth == "risk_on") or (direction == "bearish" and breadth == "risk_off")
        breadth_conflicting = (direction == "bullish" and breadth == "risk_off") or (direction == "bearish" and breadth == "risk_on")

        if aligned_trend and (qqq_aligned or breadth_aligned):
            market_alignment = "aligned"
        elif not aligned_trend and (qqq_conflicting or breadth_conflicting):
            market_alignment = "conflicting"
        else:
            market_alignment = "mixed"

        qqq_alignment = "aligned" if qqq_aligned else "conflicting" if qqq_conflicting else "mixed"
        breadth_alignment = "aligned" if breadth_aligned else "conflicting" if breadth_conflicting else "mixed"
        return market_alignment, qqq_alignment, breadth_alignment

    def _regime_fit_label(self, direction: str, regime: str | None) -> str:
        regime_value = str(regime or "unknown")
        if regime_value in {"momentum", "trend"}:
            return "fit"
        if regime_value in {"range", "slow", "unknown"}:
            return "unclear"
        if direction == "bearish" and regime_value == "risk_off":
            return "fit"
        return "neutral"

    def _stance_from_score(self, score: float) -> str:
        threshold = dict(self.config.get("stance_thresholds", {}))
        if score >= float(threshold.get("strong", 3.0)):
            return "strong"
        if score >= float(threshold.get("agree", 1.5)):
            return "agree"
        if score >= float(threshold.get("cautious", 0.0)):
            return "cautious"
        return "pass"

    def _confidence_label(self, confidence_score: float) -> str:
        if confidence_score >= 1.5:
            return "high"
        if confidence_score >= 0.4:
            return "medium"
        if confidence_score >= -0.4:
            return "low"
        return "very_low"

    def _summary(self, stance: str, symbol: str, plausibility: str, alignment: str, support: list[str], cautions: list[str]) -> str:
        if stance == "strong":
            prefix = f"I strongly agree with this {symbol} idea right now."
        elif stance == "agree":
            prefix = f"I agree with this {symbol} idea, with normal caution."
        elif stance == "cautious":
            prefix = f"I would stay cautious on this {symbol} idea."
        else:
            prefix = f"I would pass on this {symbol} idea for now."
        support_line = support[0] if support else "Signals are mixed."
        caution_line = cautions[0] if cautions else "No immediate caution flags."
        return f"{prefix} Target looks {plausibility} and market alignment is {alignment}. {support_line} {caution_line}"

    def _next_step(self, stance: str, plausibility: str) -> str:
        if stance == "strong":
            return "Wait for trigger confirmation and execute only with predefined invalidation."
        if stance == "agree":
            return "Track the next confirmation candle and keep risk size normal."
        if plausibility == "unlikely":
            return "Either widen the time window or tighten the target before acting."
        return "Let one more market update confirm alignment before committing."

    def _momentum_supports(self, direction: str, momentum: str) -> bool:
        return (direction == "bullish" and momentum in {"strong_up", "up_bias"}) or (direction == "bearish" and momentum in {"strong_down", "down_bias"})

    def _move_pct(self, current_price: float, target_price: float) -> float:
        if current_price <= 0:
            return 0.0
        return abs(target_price - current_price) / current_price * 100.0

    def _limit(self, key: str, default: int) -> int:
        return int(dict(self.config.get("explanation_limits", {})).get(key, default))
