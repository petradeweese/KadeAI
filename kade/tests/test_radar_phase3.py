from datetime import datetime, timezone

from kade.market.structure import TickerState
from kade.radar import OpportunityRadar

RADAR_CONFIG = {
    "base_score": 32,
    "state_thresholds": {
        "heads_up_min": 48,
        "trigger_imminent_min": 60,
        "trigger_fired_min": 74,
    },
    "deduplication": {"meaningful_score_delta": 6},
    "ranking": {"queue_size": 5},
    "exclude_symbols": [],
    "weights": {
        "confidence": 10,
        "trend_alignment": 8,
        "volume_expansion": 6,
        "qqq_confirmation": 6,
        "breadth_alignment": 5,
        "trap_risk": 10,
        "regime_suitability": 8,
        "timeframe_alignment": 7,
        "setup_tags": 5,
        "momentum_quality": 6,
        "structure_quality": 6,
    },
    "confidence_scores": {"high": 1.0, "moderate": 0.55, "low": 0.2, "unknown": 0.0},
    "qqq_confirmation_scores": {"confirmed": 1.0, "mixed": 0.4, "divergent": -0.7, "unknown": 0.0},
    "trap_risk_penalty": {"low": 0.0, "moderate": -0.6, "high": -1.0, "unknown": -0.2},
    "alignment": {"scores": {"fully_aligned": 1.0, "partially_aligned": 0.4, "conflicting": -0.8, "weak_context": -0.2}},
    "setup_classification": {"extension_distance_min": 0.0025},
    "setup_tag_effects": {
        "breakout_continuation": 0.9,
        "vwap_reclaim": 0.6,
        "trend_pullback": 0.45,
        "failed_breakout_risk": -0.9,
        "range_chop": -0.7,
        "momentum_extension": -0.4,
    },
    "momentum_quality_scores": {
        "strong_up": 1.0,
        "up_bias": 0.4,
        "mixed": -0.2,
        "down_bias": -0.6,
        "strong_down": -1.0,
        "unknown": -0.3,
    },
    "structure_quality_scores": {
        "breakout_up": 1.0,
        "trend_continuation_up": 0.5,
        "range_or_mixed": -0.5,
        "trend_continuation_down": -0.3,
        "breakout_down": -0.7,
        "unknown": -0.3,
    },
    "regime_setup_fit": {
        "breakout_continuation": {"momentum": 1.0, "trend": 0.7, "range": -0.8, "slow": -0.9, "unknown": -0.2},
        "vwap_reclaim": {"momentum": 0.8, "trend": 0.6, "range": -0.4, "slow": -0.5, "unknown": -0.1},
        "trend_pullback": {"trend": 1.0, "momentum": 0.5, "range": -0.3, "slow": -0.4, "unknown": -0.1},
        "failed_breakout_risk": {"momentum": -0.8, "trend": -0.6, "range": -0.2, "slow": 0.2, "unknown": -0.2},
        "range_chop": {"range": 0.9, "slow": 0.4, "trend": -0.6, "momentum": -0.7, "unknown": 0.0},
        "momentum_extension": {"momentum": -0.2, "trend": 0.3, "range": -0.6, "slow": -0.8, "unknown": -0.2},
    },
    "regime_fit_thresholds": {"aligned_min": 0.4, "conflict_max": -0.2},
    "explanations": {"max_reasons": 3},
}


def _state(symbol: str, **kwargs: str | float | None) -> TickerState:
    base = {
        "symbol": symbol,
        "last_price": 100.5,
        "vwap": 100.0,
        "trend": "bullish",
        "structure": "trend_continuation_up",
        "momentum": "up_bias",
        "volume_state": "expanding",
        "qqq_confirmation": "confirmed",
        "regime": "momentum",
        "trap_risk": "low",
        "confidence_label": "high",
        "confidence_reason": "VWAP break is valid",
        "updated_at": datetime.now(timezone.utc),
    }
    base.update(kwargs)
    return TickerState(**base)


def _debug(trigger: str = "bullish", bias: str = "bullish", context: str = "bullish") -> dict[str, float | str | None]:
    return {"trigger_trend_label": trigger, "bias_trend_label": bias, "context_trend_label": context}


def test_radar_state_classification_heads_up_and_trigger_fired() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    states = {
        "MSFT": _state("MSFT", confidence_label="moderate", structure="range_or_mixed", momentum="up_bias"),
        "NVDA": _state("NVDA", structure="breakout_up", momentum="strong_up"),
    }

    result = radar.evaluate(states, debug_payloads={"MSFT": _debug(), "NVDA": _debug()}, breadth_context={"bias": "risk_on"})

    assert result.per_ticker["MSFT"].state in {"heads_up", "trigger_imminent"}
    assert result.per_ticker["NVDA"].state == "trigger_fired"


def test_radar_deduplicates_same_state_without_meaningful_score_change() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    states = {"NVDA": _state("NVDA", structure="breakout_up", momentum="strong_up")}

    first = radar.evaluate(states, debug_payloads={"NVDA": _debug()}, breadth_context={"bias": "risk_on"})
    second = radar.evaluate(states, debug_payloads={"NVDA": _debug()}, breadth_context={"bias": "risk_on"})

    assert len(first.events) >= 1
    assert second.events == []


def test_radar_emits_escalation_event_on_state_upgrade() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    first_states = {"AMD": _state("AMD", structure="range_or_mixed", momentum="up_bias", confidence_label="moderate")}
    second_states = {"AMD": _state("AMD", structure="breakout_up", momentum="strong_up", confidence_label="high")}

    radar.evaluate(first_states, debug_payloads={"AMD": _debug()}, breadth_context={"bias": "risk_on"})
    second = radar.evaluate(second_states, debug_payloads={"AMD": _debug()}, breadth_context={"bias": "risk_on"})

    assert any(event.event_type in {"escalation", "state_change"} for event in second.events)
    assert second.per_ticker["AMD"].state == "trigger_fired"


def test_radar_prioritization_ranks_highest_score_first() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    states = {
        "META": _state("META", confidence_label="low", volume_state="stable", qqq_confirmation="mixed", regime="trend"),
        "NVDA": _state("NVDA", structure="breakout_up", momentum="strong_up"),
        "AMD": _state("AMD", confidence_label="moderate", trap_risk="moderate"),
    }

    result = radar.evaluate(states, debug_payloads={"META": _debug(), "NVDA": _debug(), "AMD": _debug()}, breadth_context={"bias": "risk_on"})

    assert result.ranked[0].symbol == "NVDA"
    assert result.ranked[0].score >= result.ranked[1].score >= result.ranked[2].score


def test_radar_trap_risk_penalty_reduces_score() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    low_trap = {"QQQ": _state("QQQ", trap_risk="low")}
    high_trap = {"QQQ": _state("QQQ", trap_risk="high")}

    low_result = radar.evaluate(low_trap, debug_payloads={"QQQ": _debug()}, breadth_context={"bias": "risk_on"})
    high_result = radar.evaluate(high_trap, debug_payloads={"QQQ": _debug()}, breadth_context={"bias": "risk_on"})

    assert high_result.per_ticker["QQQ"].score < low_result.per_ticker["QQQ"].score


def test_radar_excluded_symbols_not_in_actionable_outputs() -> None:
    config = dict(RADAR_CONFIG)
    config["exclude_symbols"] = ["QQQ", "SPY"]
    radar = OpportunityRadar(config)
    states = {
        "QQQ": _state("QQQ", structure="breakout_up", momentum="strong_up"),
        "SPY": _state("SPY", structure="breakout_up", momentum="strong_up"),
        "NVDA": _state("NVDA", structure="breakout_up", momentum="strong_up"),
    }

    result = radar.evaluate(
        states,
        debug_payloads={"QQQ": _debug(), "SPY": _debug(), "NVDA": _debug()},
        breadth_context={"bias": "risk_on"},
    )

    assert [item.symbol for item in result.ranked] == ["NVDA"]
    assert [item.symbol for item in result.queue] == ["NVDA"]
    assert any(event.symbol == "NVDA" for event in result.events)
