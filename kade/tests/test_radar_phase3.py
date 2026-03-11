from datetime import datetime, timezone

from kade.market.structure import TickerState
from kade.radar import OpportunityRadar

RADAR_CONFIG = {
    "base_score": 35,
    "state_thresholds": {
        "heads_up_min": 45,
        "trigger_imminent_min": 58,
        "trigger_fired_min": 72,
    },
    "deduplication": {"meaningful_score_delta": 6},
    "ranking": {"queue_size": 5},
    "exclude_symbols": [],
    "weights": {
        "confidence": 12,
        "trend_alignment": 10,
        "volume_expansion": 8,
        "qqq_confirmation": 7,
        "breadth_alignment": 6,
        "trap_risk": 10,
        "regime_suitability": 6,
    },
    "confidence_scores": {"high": 1.0, "moderate": 0.55, "low": 0.2, "unknown": 0.0},
    "qqq_confirmation_scores": {"confirmed": 1.0, "mixed": 0.4, "divergent": -0.7, "unknown": 0.0},
    "trap_risk_penalty": {"low": 0.0, "moderate": -0.6, "high": -1.0, "unknown": -0.2},
    "regime_bonus": {"momentum": 1.0, "trend": 0.6, "range": -0.5, "uncertain": -0.2, "unknown": 0.0},
}


def _state(symbol: str, **kwargs: str | float | None) -> TickerState:
    base = {
        "symbol": symbol,
        "trend": "bullish",
        "structure": "trend_continuation_up",
        "momentum": "up_bias",
        "volume_state": "expanding",
        "qqq_confirmation": "confirmed",
        "regime": "momentum",
        "trap_risk": "low",
        "confidence_label": "high",
        "confidence_reason": "test",
        "updated_at": datetime.now(timezone.utc),
    }
    base.update(kwargs)
    return TickerState(**base)


def test_radar_state_classification_heads_up_and_trigger_fired() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    states = {
        "MSFT": _state("MSFT", confidence_label="moderate", structure="range_or_mixed", momentum="up_bias"),
        "NVDA": _state("NVDA", structure="breakout_up", momentum="strong_up"),
    }

    result = radar.evaluate(states, debug_payloads={}, breadth_context={"bias": "risk_on"})

    assert result.per_ticker["MSFT"].state in {"heads_up", "trigger_imminent"}
    assert result.per_ticker["NVDA"].state == "trigger_fired"


def test_radar_deduplicates_same_state_without_meaningful_score_change() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    states = {"NVDA": _state("NVDA", structure="breakout_up", momentum="strong_up")}

    first = radar.evaluate(states, debug_payloads={}, breadth_context={"bias": "risk_on"})
    second = radar.evaluate(states, debug_payloads={}, breadth_context={"bias": "risk_on"})

    assert len(first.events) == 1
    assert second.events == []


def test_radar_emits_escalation_event_on_state_upgrade() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    first_states = {"AMD": _state("AMD", structure="range_or_mixed", momentum="up_bias", confidence_label="moderate")}
    second_states = {"AMD": _state("AMD", structure="breakout_up", momentum="strong_up", confidence_label="high")}

    radar.evaluate(first_states, debug_payloads={}, breadth_context={"bias": "risk_on"})
    second = radar.evaluate(second_states, debug_payloads={}, breadth_context={"bias": "risk_on"})

    assert len(second.events) == 1
    assert second.events[0].event_type == "escalation"
    assert second.events[0].state == "trigger_fired"


def test_radar_prioritization_ranks_highest_score_first() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    states = {
        "META": _state("META", confidence_label="low", volume_state="stable", qqq_confirmation="mixed", regime="trend"),
        "NVDA": _state("NVDA", structure="breakout_up", momentum="strong_up"),
        "AMD": _state("AMD", confidence_label="moderate", trap_risk="moderate"),
    }

    result = radar.evaluate(states, debug_payloads={}, breadth_context={"bias": "risk_on"})

    assert result.ranked[0].symbol == "NVDA"
    assert result.ranked[0].score >= result.ranked[1].score >= result.ranked[2].score


def test_radar_trap_risk_penalty_reduces_score() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    low_trap = {"QQQ": _state("QQQ", trap_risk="low")}
    high_trap = {"QQQ": _state("QQQ", trap_risk="high")}

    low_result = radar.evaluate(low_trap, debug_payloads={}, breadth_context={"bias": "risk_on"})
    high_result = radar.evaluate(high_trap, debug_payloads={}, breadth_context={"bias": "risk_on"})

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

    result = radar.evaluate(states, debug_payloads={}, breadth_context={"bias": "risk_on"})

    assert [item.symbol for item in result.ranked] == ["NVDA"]
    assert [item.symbol for item in result.queue] == ["NVDA"]
    assert [event.symbol for event in result.events] == ["NVDA"]
