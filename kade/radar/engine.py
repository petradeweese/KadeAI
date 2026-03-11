"""Opportunity Radar engine for deterministic setup detection and ranking."""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger

from kade.logging_utils import LogCategory, get_logger, log_event
from kade.market.structure import TickerState


SETUP_ORDER = {
    "no_setup": 0,
    "heads_up": 1,
    "trigger_imminent": 2,
    "trigger_fired": 3,
}


@dataclass
class RadarTickerResult:
    symbol: str
    state: str
    score: float
    rank: int
    reasons: list[str]
    debug: dict[str, float | str | bool | None]


@dataclass
class RadarEvent:
    symbol: str
    event_type: str
    previous_state: str | None
    state: str
    previous_score: float | None
    score: float


@dataclass
class RadarCycleResult:
    per_ticker: dict[str, RadarTickerResult]
    ranked: list[RadarTickerResult]
    queue: list[RadarTickerResult]
    events: list[RadarEvent]


class OpportunityRadar:
    """Classifies setup states, ranks opportunities, and deduplicates alert emissions."""

    def __init__(self, config: dict, logger: Logger | None = None) -> None:
        self.config = config
        self.logger = logger or get_logger(__name__)
        self._memory: dict[str, dict[str, float | str]] = {}

    def evaluate(
        self,
        ticker_states: dict[str, TickerState],
        debug_payloads: dict[str, dict[str, float | str | None]],
        breadth_context: dict[str, float | str | None],
    ) -> RadarCycleResult:
        candidates: list[RadarTickerResult] = []

        for symbol, state in ticker_states.items():
            debug_values = debug_payloads.get(symbol, {})
            score, reasons, score_debug = self._score_state(state, breadth_context)
            setup_state = self._classify_state(state, score)
            merged_debug = {
                **score_debug,
                "confidence_reason": state.confidence_reason,
                "trend": state.trend,
                "structure": state.structure,
                "momentum": state.momentum,
                "volume_state": state.volume_state,
                "qqq_confirmation": state.qqq_confirmation,
                "regime": state.regime,
                "trap_risk": state.trap_risk,
                "breadth_bias": breadth_context.get("bias"),
                "trend_slope": debug_values.get("trend_slope"),
                "volume_acceleration": debug_values.get("volume_acceleration"),
            }
            candidates.append(
                RadarTickerResult(
                    symbol=symbol,
                    state=setup_state,
                    score=score,
                    rank=0,
                    reasons=reasons,
                    debug=merged_debug,
                )
            )

        excluded_symbols = set(self.config.get("exclude_symbols", []))
        actionable_candidates = [candidate for candidate in candidates if candidate.symbol not in excluded_symbols]
        ranked = sorted(actionable_candidates, key=lambda item: (-item.score, item.symbol))
        for index, candidate in enumerate(ranked, start=1):
            candidate.rank = index

        per_ticker = {candidate.symbol: candidate for candidate in ranked}
        queue = [candidate for candidate in ranked if candidate.state != "no_setup"][: self.config["ranking"]["queue_size"]]
        events = self._events_from_changes(ranked)

        for event in events:
            message = {
                "state_change": f"{event.state} detected",
                "priority_change": "Radar priority improved",
                "escalation": f"{event.state} detected",
            }[event.event_type]
            log_event(
                self.logger,
                LogCategory.RADAR_EVENT,
                message,
                symbol=event.symbol,
                previous_state=event.previous_state,
                state=event.state,
                previous_score=event.previous_score,
                score=event.score,
            )

        return RadarCycleResult(per_ticker=per_ticker, ranked=ranked, queue=queue, events=events)

    def _score_state(
        self,
        state: TickerState,
        breadth_context: dict[str, float | str | None],
    ) -> tuple[float, list[str], dict[str, float | str | bool | None]]:
        weights = self.config["weights"]
        confidence_map = self.config["confidence_scores"]
        trap_penalty = self.config["trap_risk_penalty"]
        regime_bonus = self.config["regime_bonus"]

        score = float(self.config["base_score"])
        reasons: list[str] = []
        debug: dict[str, float | str | bool | None] = {}

        confidence_contrib = confidence_map.get(state.confidence_label or "unknown", 0.0) * weights["confidence"]
        score += confidence_contrib
        debug["confidence_contrib"] = confidence_contrib
        if confidence_contrib > 0:
            reasons.append(f"confidence={state.confidence_label}")

        trend_alignment = self._trend_alignment(state)
        trend_contrib = trend_alignment * weights["trend_alignment"]
        score += trend_contrib
        debug["trend_alignment_contrib"] = trend_contrib
        debug["trend_alignment"] = trend_alignment > 0

        volume_contrib = (1.0 if state.volume_state == "expanding" else 0.0) * weights["volume_expansion"]
        score += volume_contrib
        debug["volume_contrib"] = volume_contrib
        if volume_contrib > 0:
            reasons.append("volume expansion")

        qqq_contrib = self.config["qqq_confirmation_scores"].get(state.qqq_confirmation or "unknown", 0.0) * weights[
            "qqq_confirmation"
        ]
        score += qqq_contrib
        debug["qqq_contrib"] = qqq_contrib

        breadth_contrib = self._breadth_alignment(state, breadth_context.get("bias")) * weights["breadth_alignment"]
        score += breadth_contrib
        debug["breadth_contrib"] = breadth_contrib

        trap_contrib = trap_penalty.get(state.trap_risk or "unknown", 0.0) * weights["trap_risk"]
        score += trap_contrib
        debug["trap_contrib"] = trap_contrib
        if trap_contrib < 0:
            reasons.append(f"trap risk={state.trap_risk}")

        regime_contrib = regime_bonus.get(state.regime or "unknown", 0.0) * weights["regime_suitability"]
        score += regime_contrib
        debug["regime_contrib"] = regime_contrib

        bounded_score = max(0.0, min(100.0, score))
        debug["raw_score"] = score
        debug["bounded_score"] = bounded_score

        if trend_alignment > 0:
            reasons.append("trend and momentum aligned")

        return bounded_score, reasons, debug

    def _classify_state(self, state: TickerState, score: float) -> str:
        thresholds = self.config["state_thresholds"]
        if self._trigger_fired_condition(state, score, thresholds):
            return "trigger_fired"
        if self._trigger_imminent_condition(state, score, thresholds):
            return "trigger_imminent"
        if score >= thresholds["heads_up_min"]:
            return "heads_up"
        return "no_setup"

    def _trigger_imminent_condition(self, state: TickerState, score: float, thresholds: dict) -> bool:
        return score >= thresholds["trigger_imminent_min"] and self._trend_alignment(state) > 0

    def _trigger_fired_condition(self, state: TickerState, score: float, thresholds: dict) -> bool:
        breakout = state.structure in {"breakout_up", "breakout_down"}
        strong_momentum = state.momentum in {"strong_up", "strong_down"}
        trap_ok = state.trap_risk != "high"
        return score >= thresholds["trigger_fired_min"] and breakout and strong_momentum and trap_ok

    def _trend_alignment(self, state: TickerState) -> float:
        bullish = state.trend == "bullish" and state.momentum in {"up_bias", "strong_up"}
        bearish = state.trend == "bearish" and state.momentum in {"down_bias", "strong_down"}
        if bullish or bearish:
            return 1.0
        if state.trend == "neutral":
            return 0.0
        return -0.5

    def _breadth_alignment(self, state: TickerState, breadth_bias: str | None) -> float:
        if breadth_bias == "risk_on" and state.trend == "bullish":
            return 1.0
        if breadth_bias == "risk_off" and state.trend == "bearish":
            return 1.0
        if breadth_bias == "mixed":
            return 0.0
        return -0.5

    def _events_from_changes(self, ranked: list[RadarTickerResult]) -> list[RadarEvent]:
        events: list[RadarEvent] = []
        score_delta_threshold = self.config["deduplication"]["meaningful_score_delta"]

        for candidate in ranked:
            previous = self._memory.get(candidate.symbol)
            previous_state = previous["state"] if previous else None
            previous_score = float(previous["score"]) if previous else None

            should_emit = False
            event_type = "state_change"

            if previous is None:
                should_emit = candidate.state != "no_setup"
            elif candidate.state != previous_state:
                should_emit = True
                if SETUP_ORDER.get(candidate.state, 0) > SETUP_ORDER.get(str(previous_state), 0):
                    event_type = "escalation"
            elif candidate.score - (previous_score or 0.0) >= score_delta_threshold and candidate.state != "no_setup":
                should_emit = True
                event_type = "priority_change"

            if should_emit:
                events.append(
                    RadarEvent(
                        symbol=candidate.symbol,
                        event_type=event_type,
                        previous_state=str(previous_state) if previous_state else None,
                        state=candidate.state,
                        previous_score=previous_score,
                        score=candidate.score,
                    )
                )

            self._memory[candidate.symbol] = {"state": candidate.state, "score": candidate.score}

        return events
