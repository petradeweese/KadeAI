from datetime import datetime, timezone

from kade.dashboard.app import create_app_status
from kade.market.structure import TickerState
from kade.planning import TradePlanBuilder, TradePlanContext
from kade.runtime.interaction import InteractionRuntimeState
from kade.tests.test_phase8_interaction import _interaction

PLANNING_CONFIG = {
    "stance_to_risk_posture": {"strong": "full", "agree": "full", "cautious": "reduced", "pass": "watch_only"},
    "stale_trade_timing_minutes": 20,
    "checklist_verbosity": "standard",
}


def _ticker(**kwargs: str | float | None) -> TickerState:
    base = {
        "symbol": "NVDA",
        "last_price": 188.2,
        "vwap": 187.9,
        "trend": "bearish",
        "structure": "breakdown",
        "momentum": "strong_down",
        "volume_state": "expanding",
        "qqq_confirmation": "divergent_risk_off",
        "regime": "momentum",
        "trap_risk": "low",
        "confidence_label": "high",
        "confidence_reason": "trend continuation",
        "updated_at": datetime.now(timezone.utc),
    }
    base.update(kwargs)
    return TickerState(**base)


def _state() -> InteractionRuntimeState:
    return InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )


def test_bearish_and_bullish_plan_generation() -> None:
    builder = TradePlanBuilder(PLANNING_CONFIG)
    bearish = builder.build(
        TradePlanContext(
            symbol="NVDA",
            direction="put",
            ticker_state=_ticker(),
            radar_context={"setup_tags": ["breakdown"]},
            breadth_context={"bias": "risk_off"},
            trade_idea_opinion={
                "stance": "agree",
                "confidence_label": "high",
                "target_plausibility": "realistic",
                "market_alignment": "aligned",
                "regime_fit": "fit",
                "trap_risk": "low",
                "current_price": 188.2,
                "target_price": 184.3,
                "time_horizon_minutes": 60,
                "qqq_alignment": "aligned",
                "breadth_alignment": "aligned",
            },
        )
    )
    bullish = builder.build(
        TradePlanContext(
            symbol="NVDA",
            direction="call",
            ticker_state=_ticker(trend="bullish", momentum="up_bias", qqq_confirmation="confirmed", trap_risk="moderate"),
            radar_context={"setup_tags": ["reclaim"]},
            breadth_context={"bias": "risk_on"},
            trade_idea_opinion={
                "stance": "cautious",
                "confidence_label": "medium",
                "target_plausibility": "possible_but_stretched",
                "market_alignment": "mixed",
                "regime_fit": "fit",
                "trap_risk": "moderate",
                "current_price": 188.2,
                "target_price": 191.3,
                "time_horizon_minutes": 45,
                "qqq_alignment": "aligned",
                "breadth_alignment": "aligned",
            },
        )
    )

    assert "VWAP" in bearish.entry_plan.trigger_condition
    assert bearish.risk_posture == "full"
    assert bullish.entry_plan.entry_style == "confirmation"
    assert bullish.risk_posture in {"reduced", "watch_only"}


def test_risk_posture_mapping_and_invalidation_logic() -> None:
    builder = TradePlanBuilder(PLANNING_CONFIG)
    decision = builder.build(
        TradePlanContext(
            symbol="NVDA",
            direction="put",
            ticker_state=_ticker(trap_risk="high"),
            radar_context={},
            breadth_context={"bias": "risk_off"},
            trade_idea_opinion={
                "stance": "strong",
                "target_plausibility": "realistic",
                "market_alignment": "aligned",
                "regime_fit": "fit",
                "trap_risk": "high",
                "current_price": 188.2,
                "target_price": 184.0,
                "time_horizon_minutes": 60,
            },
        )
    )

    assert decision.risk_posture == "watch_only"
    assert any("Reclaim" in item for item in decision.invalidation_plan.hard_invalidation)


def test_checklist_and_target_move_link_are_deterministic() -> None:
    builder = TradePlanBuilder(PLANNING_CONFIG)
    context = TradePlanContext(
        symbol="NVDA",
        direction="put",
        ticker_state=_ticker(),
        radar_context={"setup_tags": ["breakdown"]},
        breadth_context={"bias": "risk_off"},
        trade_idea_opinion={
            "stance": "agree",
            "target_plausibility": "possible_but_stretched",
            "market_alignment": "aligned",
            "trap_risk": "moderate",
            "current_price": 188.2,
            "target_price": 184.3,
            "time_horizon_minutes": 60,
        },
        target_move_board={
            "candidates": [{"option_symbol": "NVDA-0D-P-185", "estimated_percent_return": 38.2, "risk_label": "balanced_risk"}],
        },
    )

    one = builder.build(context)
    two = builder.build(context)

    assert one.execution_checklist == two.execution_checklist
    assert one.linked_target_move_board["top_option_symbol"] == "NVDA-0D-P-185"


def test_runtime_trade_plan_payload_timeline_and_operator_shape() -> None:
    interaction = _interaction(_state())
    interaction.trade_plan_handler = lambda payload: {
        "plan_id": "plan-NVDA-1",
        "symbol": "NVDA",
        "direction": "bearish",
        "stance": "agree",
        "risk_posture": "reduced",
        "status": "ready",
        "entry_plan": {"trigger_condition": "Continuation below VWAP", "entry_style": "confirmation"},
        "invalidation_plan": {"invalidation_condition": "Reclaim VWAP"},
        "target_plan": {"primary_target": "184.3", "secondary_target": "183.0"},
        "hold_plan": {"max_hold_minutes": 60, "expected_time_window": "first 30m", "stale_trade_rule": "exit if stale"},
        "execution_checklist": ["confirm trigger"],
        "linked_target_move_board": {"top_option_symbol": "NVDA-0D-P-185"},
        "generated_at": "2026-01-01T00:00:00+00:00",
    }

    response = interaction.submit_trade_plan_request({"symbol": "NVDA", "direction": "put"})
    payload = interaction.dashboard_payload()
    app_status = create_app_status(voice_payload=payload)

    assert response["intent"] == "trade_plan"
    assert payload["trade_plan"]["plan_id"] == "plan-NVDA-1"
    assert any(event["event_type"] == "trade_plan_generated" for event in payload["timeline"]["events"])
    assert app_status["operator_console"]["trade_plan"]["symbol"] == "NVDA"


def test_trade_plan_separation_from_opinion_and_target_move_modes() -> None:
    interaction = _interaction(_state())
    interaction.trade_plan_handler = lambda payload: {"plan_id": "plan-1", "symbol": "NVDA", "status": "watching", "risk_posture": "watch_only"}

    response = interaction.submit_text_panel_command({"command": "trade_plan symbol=NVDA direction=put target=184.3 minutes=60"})

    assert response["intent"] == "trade_plan"
    assert "trade_plan" in response["raw_result"]
    assert "trade_idea_opinion" not in response["raw_result"]
    assert "target_move_board" not in response["raw_result"]


def test_safe_fallbacks_when_opinion_and_target_board_missing() -> None:
    builder = TradePlanBuilder(PLANNING_CONFIG)
    decision = builder.build(
        TradePlanContext(
            symbol="NVDA",
            direction="put",
            ticker_state=_ticker(vwap=None, last_price=None),
            radar_context={},
            breadth_context={"bias": "risk_on"},
            trade_idea_opinion=None,
            target_move_board=None,
            user_request_context=None,
        )
    )

    assert decision.linked_target_move_board == {}
    assert decision.linked_trade_idea_opinion["symbol"] == "NVDA"
    assert decision.target_plan.primary_target.startswith("Primary target: 0.00")
    assert "VWAP" not in " ".join(decision.invalidation_plan.hard_invalidation)


def test_fallback_resolution_prefers_request_context_values() -> None:
    builder = TradePlanBuilder(PLANNING_CONFIG)
    decision = builder.build(
        TradePlanContext(
            symbol="NVDA",
            direction="call",
            ticker_state=_ticker(last_price=188.0, trend="bullish", momentum="up_bias"),
            radar_context={},
            breadth_context={"bias": "risk_off"},
            trade_idea_opinion={"stance": "pass", "target_plausibility": "possible"},
            user_request_context={"current_price": 187.5, "target_price": 190.0, "time_horizon_minutes": 35},
        )
    )

    assert "190.00" in decision.target_plan.primary_target
    assert decision.hold_plan.max_hold_minutes == 35
    assert decision.risk_posture in {"watch_only", "pass"}
