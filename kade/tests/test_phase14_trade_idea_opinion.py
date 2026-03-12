from datetime import datetime, timezone

from kade.brain.trade_idea import TradeIdeaOpinionEngine, TradeIdeaOpinionRequest
from kade.market.structure import TickerState
from kade.options.models import OptionContract
from kade.options.scenario import TargetMoveScenarioBoard, TargetMoveScenarioRequest
from kade.runtime.interaction import InteractionRuntimeState
from kade.tests.test_phase8_interaction import _interaction

TRADE_IDEA_CONFIG = {
    "stance_thresholds": {"strong": 3.0, "agree": 1.5, "cautious": 0.0},
    "target_plausibility": {
        "realistic_ratio_max": 0.95,
        "stretched_ratio_max": 1.45,
        "realistic_score_min": 0.9,
        "stretched_score_min": -0.1,
    },
    "time_horizon_buckets": {
        "short_minutes": 30,
        "medium_minutes": 90,
        "short_move_proxy_pct": 0.7,
        "medium_move_proxy_pct": 1.0,
        "long_move_proxy_pct": 1.3,
    },
    "alignment_importance": {"market": 1.2, "qqq": 0.8, "breadth": 0.7},
    "trap_risk_penalties": {"low": 0.0, "moderate": 0.6, "high": 1.2},
    "explanation_limits": {"supporting_reasons_limit": 4, "cautionary_reasons_limit": 4},
    "radar_score": {"high": 70, "low": 40},
}

SCENARIO_CONFIG = {
    "default_profile": "fast_intraday",
    "default_allowed_dtes": [0, 1, 2],
    "bucket_top_n": 2,
    "profiles": {
        "fast_intraday": {
            "min_open_interest": 200,
            "min_volume": 100,
            "max_spread_pct": 0.12,
            "entry_aggressiveness": 0.5,
            "entry_spread_penalty_multiplier": 0.15,
            "slippage_haircut_pct": 0.04,
            "spread_haircut_multiplier": 0.3,
            "fallback_delta": 0.32,
            "target_price_floor_multiplier": 0.65,
            "short_window_minutes": 30,
            "short_window_uplift": 0.08,
            "gamma_uplift_by_dte": {0: 0.2, 1: 0.12, 2: 0.06},
            "target_delta_range": [0.3, 0.65],
            "dte_preferences": {0: 1.0, 1: 0.9, 2: 0.8},
            "ranking_weights": {
                "estimated_percent_return": 1.3,
                "estimated_total_gain": 1.0,
                "liquidity": 1.2,
                "spread_quality": 1.1,
                "delta_suitability": 1.0,
                "dte_fit": 1.0,
            },
        }
    },
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


def _contracts() -> list[OptionContract]:
    return [
        OptionContract("NVDA", "NVDA-0D-P-185", "put", 185, 0, 1.3, 1.4, delta=-0.48, volume=650, open_interest=1500),
        OptionContract("NVDA", "NVDA-1D-P-184", "put", 184, 1, 1.0, 1.1, delta=-0.42, volume=700, open_interest=1400),
        OptionContract("NVDA", "NVDA-2D-P-182", "put", 182, 2, 0.75, 0.85, delta=-0.35, volume=550, open_interest=1300),
    ]


def test_trade_idea_opinion_bearish_and_bullish_cases() -> None:
    engine = TradeIdeaOpinionEngine(TRADE_IDEA_CONFIG)
    bearish = engine.evaluate(
        request=TradeIdeaOpinionRequest(symbol="NVDA", direction="put", current_price=188.2, target_price=184.3, time_horizon_minutes=60),
        ticker_state=_ticker(),
        radar_context={"score": 77.5, "setup_tags": ["breakout_continuation", "vwap_reclaim"]},
        breadth_context={"bias": "risk_off"},
    )
    bullish = engine.evaluate(
        request=TradeIdeaOpinionRequest(symbol="NVDA", direction="call", current_price=188.2, target_price=191.6, time_horizon_minutes=45),
        ticker_state=_ticker(),
        radar_context={"score": 45.0, "setup_tags": ["failed_reclaim"]},
        breadth_context={"bias": "risk_off"},
    )

    assert bearish.stance in {"agree", "strong"}
    assert bearish.market_alignment == "aligned"
    assert bullish.stance in {"cautious", "pass"}
    assert bullish.market_alignment in {"mixed", "conflicting"}


def test_target_plausibility_realistic_stretched_unlikely() -> None:
    engine = TradeIdeaOpinionEngine(TRADE_IDEA_CONFIG)
    state = _ticker()
    radar = {"score": 72.0, "setup_tags": ["trend_follow"]}

    realistic = engine.evaluate(
        TradeIdeaOpinionRequest("NVDA", "put", 188.2, 187.3, 60),
        state,
        radar,
        {"bias": "risk_off"},
    )
    stretched = engine.evaluate(
        TradeIdeaOpinionRequest("NVDA", "put", 188.2, 187.0, 30),
        _ticker(momentum="mixed", trap_risk="moderate", regime="range"),
        radar,
        {"bias": "risk_off"},
    )
    unlikely = engine.evaluate(
        TradeIdeaOpinionRequest("NVDA", "put", 188.2, 180.0, 15),
        state,
        radar,
        {"bias": "risk_off"},
    )

    assert realistic.target_plausibility == "realistic"
    assert stretched.target_plausibility == "possible_but_stretched"
    assert unlikely.target_plausibility == "unlikely"


def test_trade_idea_determinism_for_fixed_inputs() -> None:
    engine = TradeIdeaOpinionEngine(TRADE_IDEA_CONFIG)
    request = TradeIdeaOpinionRequest("NVDA", "put", 188.2, 184.3, 60)
    state = _ticker()
    radar = {"score": 77.5, "setup_tags": ["breakdown"]}
    breadth = {"bias": "risk_off"}

    one = engine.evaluate(request, state, radar, breadth)
    two = engine.evaluate(request, state, radar, breadth)

    assert one.stance == two.stance
    assert one.summary == two.summary
    assert one.target_plausibility == two.target_plausibility


def test_runtime_operator_console_and_timeline_trade_idea_payload() -> None:
    interaction = _interaction(_state())
    interaction.trade_idea_handler = lambda payload: {
        "symbol": str(payload.get("symbol", "NVDA")),
        "direction": "bearish",
        "current_price": 188.2,
        "target_price": 184.3,
        "time_horizon_minutes": 60,
        "stance": "agree",
        "confidence_label": "medium",
        "target_plausibility": "possible_but_stretched",
        "market_alignment": "aligned",
        "qqq_alignment": "aligned",
        "breadth_alignment": "aligned",
        "regime_fit": "fit",
        "trap_risk": "moderate",
        "summary": "I agree with this idea, with caution.",
        "supporting_reasons": ["trend aligns"],
        "cautionary_reasons": ["target stretched"],
        "suggested_next_step": "wait for confirmation",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }

    response = interaction.submit_trade_idea_opinion(
        {"symbol": "NVDA", "direction": "put", "current_price": 188.2, "target_price": 184.3, "time_horizon_minutes": 60}
    )
    payload = interaction.dashboard_payload()

    assert response["intent"] == "trade_idea_opinion"
    assert payload["trade_idea_opinion"]["stance"] == "agree"
    assert any(event["event_type"] == "trade_idea_opinion_generated" for event in payload["timeline"]["events"])


def test_opinion_mode_stays_separate_from_target_move_scenario_mode() -> None:
    interaction = _interaction(_state())
    board = TargetMoveScenarioBoard(SCENARIO_CONFIG)

    interaction.trade_idea_handler = lambda payload: {
        "symbol": str(payload["symbol"]),
        "direction": "bearish",
        "current_price": float(payload["current_price"]),
        "target_price": float(payload["target_price"]),
        "time_horizon_minutes": int(payload["time_horizon_minutes"]),
        "stance": "agree",
        "confidence_label": "high",
        "target_plausibility": "realistic",
        "market_alignment": "aligned",
        "qqq_alignment": "aligned",
        "breadth_alignment": "aligned",
        "regime_fit": "fit",
        "trap_risk": "low",
        "summary": "Agree.",
        "supporting_reasons": ["aligned"],
        "cautionary_reasons": [],
        "suggested_next_step": "confirm",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    interaction.target_move_handler = lambda payload: board.generate(
        TargetMoveScenarioRequest(
            symbol=str(payload["symbol"]),
            direction=str(payload["direction"]),
            current_price=float(payload.get("current_price", payload.get("current"))),
            target_price=float(payload.get("target_price", payload.get("target"))),
            time_horizon_minutes=int(payload.get("time_horizon_minutes", payload.get("minutes"))),
            budget=float(payload.get("budget", 1000)),
            allowed_dtes=tuple(int(v) for v in payload.get("allowed_dtes", [0, 1, 2])),
        ),
        _contracts(),
    )

    opinion_response = interaction.submit_text_panel_command(
        {
            "command": "trade_idea symbol=NVDA direction=put current_price=188.2 target_price=184.3 time_horizon_minutes=60",
        }
    )
    scenario_response = interaction.submit_text_panel_command(
        {
            "command": "target_move symbol=NVDA direction=put current=188.2 target=184.3 budget=1000 minutes=60 dtes=0,1,2",
        }
    )

    assert opinion_response["intent"] == "trade_idea_opinion"
    assert "target_move_board" not in opinion_response["raw_result"]
    assert scenario_response["intent"] == "target_move_scenario"
    assert "trade_idea_opinion" not in scenario_response["raw_result"]
