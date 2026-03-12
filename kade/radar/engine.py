"""Opportunity Radar engine for deterministic setup detection and ranking."""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger

from kade.logging_utils import LogCategory, get_logger, log_event
from kade.market.structure import TickerState
from kade.radar.alignment import TimeframeAlignmentClassifier
from kade.radar.classifier import SetupPatternClassifier
from kade.radar.explanations import RadarExplanationBuilder

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
    setup_tags: list[str]
    alignment_label: str
    regime_fit_label: str
    explanation: dict[str, object]
    debug: dict[str, float | str | bool | None | list[str] | dict[str, float]]


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
        self._memory: dict[str, dict[str, float | str | tuple[str, ...]]] = {}
        self.alignment_classifier = TimeframeAlignmentClassifier(config.get("alignment", {}))
        self.pattern_classifier = SetupPatternClassifier(config.get("setup_classification", {}))
        self.explanation_builder = RadarExplanationBuilder(config.get("explanations", {}))

    def evaluate(
        self,
        ticker_states: dict[str, TickerState],
        debug_payloads: dict[str, dict[str, float | str | None]],
        breadth_context: dict[str, float | str | None],
    ) -> RadarCycleResult:
        candidates: list[RadarTickerResult] = []

        for symbol, state in ticker_states.items():
            debug_values = debug_payloads.get(symbol, {})
            setup_tags = self.pattern_classifier.classify(state, debug_values)
            alignment = self.alignment_classifier.classify(state, debug_values)
            score, reasons, score_debug = self._score_state(
                state=state,
                breadth_context=breadth_context,
                setup_tags=setup_tags,
                alignment_label=alignment.label,
            )
            setup_state = self._classify_state(state, score)
            explanation = self.explanation_builder.build(
                symbol=symbol,
                score=score,
                setup_tags=setup_tags,
                alignment_label=alignment.label,
                regime_fit_label=str(score_debug.get("regime_fit_label", "neutral_fit")),
                trap_risk=state.trap_risk or "unknown",
                contributions=dict(score_debug.get("contributions", {})),
                timestamp=state.updated_at,
            )
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
                "trigger_trend_label": alignment.trigger_trend,
                "bias_trend_label": alignment.bias_trend,
                "context_trend_label": alignment.context_trend,
                "setup_tags": setup_tags,
            }
            candidates.append(
                RadarTickerResult(
                    symbol=symbol,
                    state=setup_state,
                    score=score,
                    rank=0,
                    reasons=reasons,
                    setup_tags=setup_tags,
                    alignment_label=alignment.label,
                    regime_fit_label=str(score_debug.get("regime_fit_label", "neutral_fit")),
                    explanation=explanation,
                    debug=merged_debug,
                )
            )

            log_event(
                self.logger,
                LogCategory.RADAR_EVENT,
                "Radar setup classified",
                symbol=symbol,
                setup_tags=",".join(setup_tags),
                alignment=alignment.label,
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
            log_event(
                self.logger,
                LogCategory.RADAR_EVENT,
                "Radar change",
                symbol=event.symbol,
                event_type=event.event_type,
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
        setup_tags: list[str],
        alignment_label: str,
    ) -> tuple[float, list[str], dict[str, float | str | bool | None | dict[str, float]]]:
        weights = self.config["weights"]
        confidence_map = self.config["confidence_scores"]
        trap_penalty = self.config["trap_risk_penalty"]

        score = float(self.config["base_score"])
        reasons: list[str] = []
        contributions: dict[str, float] = {}

        confidence_contrib = confidence_map.get(state.confidence_label or "unknown", 0.0) * weights["confidence"]
        score += confidence_contrib
        contributions["confidence"] = confidence_contrib

        trend_alignment = self._trend_alignment(state)
        trend_contrib = trend_alignment * weights["trend_alignment"]
        score += trend_contrib
        contributions["trend_alignment"] = trend_contrib

        volume_contrib = (1.0 if state.volume_state == "expanding" else 0.0) * weights["volume_expansion"]
        score += volume_contrib
        contributions["volume_expansion"] = volume_contrib

        qqq_contrib = self.config["qqq_confirmation_scores"].get(state.qqq_confirmation or "unknown", 0.0) * weights["qqq_confirmation"]
        score += qqq_contrib
        contributions["qqq_confirmation"] = qqq_contrib

        breadth_contrib = self._breadth_alignment(state, breadth_context.get("bias")) * weights["breadth_alignment"]
        score += breadth_contrib
        contributions["breadth_alignment"] = breadth_contrib

        trap_contrib = trap_penalty.get(state.trap_risk or "unknown", 0.0) * weights["trap_risk"]
        score += trap_contrib
        contributions["trap_risk"] = trap_contrib

        alignment_contrib = self.config.get("alignment", {}).get("scores", {}).get(alignment_label, 0.0) * weights["timeframe_alignment"]
        score += alignment_contrib
        contributions["timeframe_alignment"] = alignment_contrib

        tag_effects = self.config.get("setup_tag_effects", {})
        tag_contrib = sum(float(tag_effects.get(tag, 0.0)) for tag in setup_tags) * weights["setup_tags"]
        score += tag_contrib
        contributions["setup_tags"] = tag_contrib

        momentum_quality = self.config.get("momentum_quality_scores", {}).get(state.momentum or "unknown", 0.0)
        momentum_contrib = momentum_quality * weights["momentum_quality"]
        score += momentum_contrib
        contributions["momentum_quality"] = momentum_contrib

        structure_quality = self.config.get("structure_quality_scores", {}).get(state.structure or "unknown", 0.0)
        structure_contrib = structure_quality * weights["structure_quality"]
        score += structure_contrib
        contributions["structure_quality"] = structure_contrib

        regime_fit, regime_fit_label = self._regime_fit_score(setup_tags=setup_tags, regime=state.regime or "unknown")
        regime_contrib = regime_fit * weights["regime_suitability"]
        score += regime_contrib
        contributions["regime_fit"] = regime_contrib

        bounded_score = max(0.0, min(100.0, score))

        if confidence_contrib > 0:
            reasons.append(f"confidence={state.confidence_label}")
        if alignment_label == "fully_aligned":
            reasons.append("multi-timeframe alignment")
        if regime_fit_label == "regime_aligned":
            reasons.append("regime supports setup")
        if trap_contrib < 0:
            reasons.append(f"trap risk={state.trap_risk}")

        debug: dict[str, float | str | bool | None | dict[str, float]] = {
            "raw_score": score,
            "bounded_score": bounded_score,
            "alignment_label": alignment_label,
            "regime_fit_label": regime_fit_label,
            "regime_fit_score": regime_fit,
            "contributions": contributions,
        }
        return bounded_score, reasons, debug

    def _regime_fit_score(self, setup_tags: list[str], regime: str) -> tuple[float, str]:
        matrix = self.config.get("regime_setup_fit", {})
        if not setup_tags:
            return 0.0, "neutral_fit"
        values = [float(dict(matrix.get(tag, {})).get(regime, 0.0)) for tag in setup_tags]
        avg_fit = sum(values) / len(values)
        if avg_fit >= self.config.get("regime_fit_thresholds", {}).get("aligned_min", 0.4):
            return avg_fit, "regime_aligned"
        if avg_fit <= self.config.get("regime_fit_thresholds", {}).get("conflict_max", -0.2):
            return avg_fit, "regime_conflict"
        return avg_fit, "neutral_fit"

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
            previous_tags = tuple(previous.get("setup_tags", ())) if previous else ()
            previous_alignment = str(previous.get("alignment_label")) if previous else None
            previous_regime_fit = str(previous.get("regime_fit_label")) if previous else None

            if previous is None and candidate.state != "no_setup":
                events.append(RadarEvent(candidate.symbol, "state_change", None, candidate.state, None, candidate.score))
            elif previous is not None:
                if candidate.state != previous_state:
                    event_type = "escalation" if SETUP_ORDER.get(candidate.state, 0) > SETUP_ORDER.get(str(previous_state), 0) else "state_change"
                    events.append(RadarEvent(candidate.symbol, event_type, str(previous_state), candidate.state, previous_score, candidate.score))
                elif candidate.state != "no_setup":
                    score_delta = candidate.score - (previous_score or 0.0)
                    if score_delta >= score_delta_threshold:
                        events.append(RadarEvent(candidate.symbol, "score_upgraded", str(previous_state), candidate.state, previous_score, candidate.score))
                    elif score_delta <= -score_delta_threshold:
                        events.append(RadarEvent(candidate.symbol, "score_downgraded", str(previous_state), candidate.state, previous_score, candidate.score))

                if tuple(candidate.setup_tags) != previous_tags:
                    events.append(RadarEvent(candidate.symbol, "setup_tags_changed", str(previous_state), candidate.state, previous_score, candidate.score))
                if candidate.alignment_label != previous_alignment:
                    events.append(RadarEvent(candidate.symbol, "alignment_changed", str(previous_state), candidate.state, previous_score, candidate.score))
                if candidate.regime_fit_label != previous_regime_fit:
                    events.append(RadarEvent(candidate.symbol, "regime_fit_changed", str(previous_state), candidate.state, previous_score, candidate.score))

            self._memory[candidate.symbol] = {
                "state": candidate.state,
                "score": candidate.score,
                "setup_tags": tuple(candidate.setup_tags),
                "alignment_label": candidate.alignment_label,
                "regime_fit_label": candidate.regime_fit_label,
            }

        return events
