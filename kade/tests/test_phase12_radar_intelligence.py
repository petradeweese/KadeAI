from datetime import datetime, timezone

from kade.dashboard.app import create_app_status
from kade.market.structure import TickerState
from kade.radar import OpportunityRadar
from kade.tests.test_radar_phase3 import RADAR_CONFIG
from kade.runtime.interaction import InteractionOrchestrator
from kade.tests.test_phase11_operator_console import _state
from kade.tests.test_phase8_interaction import _interaction


def _ticker(**kwargs: str | float | None) -> TickerState:
    base = {
        "symbol": "NVDA",
        "last_price": 101.0,
        "vwap": 100.0,
        "trend": "bullish",
        "structure": "breakout_up",
        "momentum": "strong_up",
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


def test_alignment_classification_labels() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    aligned = radar.evaluate({"NVDA": _ticker()}, {"NVDA": {"trigger_trend_label": "bullish", "context_trend_label": "bullish"}}, {"bias": "risk_on"})
    weak = radar.evaluate({"MSFT": _ticker(symbol="MSFT")}, {"MSFT": {"trigger_trend_label": "bullish", "context_trend_label": "neutral"}}, {"bias": "risk_on"})
    conflict = radar.evaluate(
        {"AMD": _ticker(symbol="AMD", trend="bearish", momentum="down_bias")},
        {"AMD": {"trigger_trend_label": "bullish", "context_trend_label": "bullish"}},
        {"bias": "risk_off"},
    )

    assert aligned.per_ticker["NVDA"].alignment_label == "fully_aligned"
    assert weak.per_ticker["MSFT"].alignment_label == "weak_context"
    assert conflict.per_ticker["AMD"].alignment_label == "conflicting"


def test_regime_aware_adjustment_penalizes_conflict() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    momentum_case = radar.evaluate(
        {"NVDA": _ticker(regime="momentum")},
        {"NVDA": {"trigger_trend_label": "bullish", "context_trend_label": "bullish"}},
        {"bias": "risk_on"},
    )
    range_case = radar.evaluate(
        {"NVDA": _ticker(regime="range")},
        {"NVDA": {"trigger_trend_label": "bullish", "context_trend_label": "bullish"}},
        {"bias": "mixed"},
    )

    assert momentum_case.per_ticker["NVDA"].score > range_case.per_ticker["NVDA"].score
    assert range_case.per_ticker["NVDA"].regime_fit_label in {"regime_conflict", "neutral_fit"}


def test_setup_tags_and_explanation_payload() -> None:
    radar = OpportunityRadar(RADAR_CONFIG)
    result = radar.evaluate(
        {"NVDA": _ticker()},
        {"NVDA": {"trigger_trend_label": "bullish", "context_trend_label": "bullish"}},
        {"bias": "risk_on"},
    )
    signal = result.per_ticker["NVDA"]

    assert "breakout_continuation" in signal.setup_tags
    assert "setup_tags" in signal.debug
    assert signal.explanation["symbol"] == "NVDA"
    assert isinstance(signal.explanation["supporting_reasons"], list)
    assert signal.explanation["alignment_label"] == signal.alignment_label


def test_operator_console_radar_shape_includes_phase12_fields() -> None:
    voice_payload = {
        "latest_radar_signals": [
            {
                "symbol": "NVDA",
                "setup": "trigger_fired",
                "confidence": 81.4,
                "setup_tags": ["breakout_continuation", "vwap_reclaim"],
                "alignment_label": "fully_aligned",
                "regime_fit": "regime_aligned",
                "supporting_reasons": ["trend alignment: boost 8.00"],
                "cautionary_reasons": ["trap risk: drag 2.00", "range chop: drag 1.00"],
                "trap_risk": "moderate",
                "summary": "breakout_continuation; alignment=fully_aligned",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]
    }
    payload = create_app_status(voice_payload=voice_payload)
    signal = payload["operator_console"]["radar"]["top_signals"][0]

    assert signal["setup_tags"] == ["breakout_continuation", "vwap_reclaim"]
    assert signal["alignment_label"] == "fully_aligned"
    assert payload["operator_console"]["radar"]["quality_buckets"]["caution_heavy"][0]["symbol"] == "NVDA"


def test_timeline_captures_radar_change_events() -> None:
    interaction: InteractionOrchestrator = _interaction(_state())
    interaction.ingest_radar_signals(
        [{"symbol": "NVDA", "setup": "trigger_imminent", "confidence": 60.0, "setup_tags": ["trend_pullback"], "alignment_label": "partially_aligned", "regime_fit": "neutral_fit", "timestamp": "2026-01-01T00:00:00+00:00"}]
    )
    interaction.ingest_radar_signals(
        [{"symbol": "NVDA", "setup": "trigger_fired", "confidence": 72.0, "setup_tags": ["breakout_continuation"], "alignment_label": "fully_aligned", "regime_fit": "regime_aligned", "timestamp": "2026-01-01T00:01:00+00:00"}]
    )

    event_types = [event["event_type"] for event in interaction.dashboard_payload()["timeline"]["events"]]
    assert "radar_setup_tags_changed" in event_types
    assert "radar_alignment_changed" in event_types
    assert "radar_score_changed" in event_types
