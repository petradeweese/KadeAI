from datetime import datetime, timezone

from kade.options.models import OptionContract
from kade.options.scenario import TargetMoveScenarioBoard, TargetMoveScenarioRequest
from kade.runtime.interaction import InteractionRuntimeState
from kade.tests.test_phase8_interaction import _interaction


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


def _contracts() -> list[OptionContract]:
    return [
        OptionContract("NVDA", "NVDA-0D-P-185", "put", 185, 0, 1.3, 1.4, delta=-0.48, volume=650, open_interest=1500),
        OptionContract("NVDA", "NVDA-1D-P-184", "put", 184, 1, 1.0, 1.1, delta=-0.42, volume=700, open_interest=1400),
        OptionContract("NVDA", "NVDA-2D-P-182", "put", 182, 2, 0.75, 0.85, delta=-0.35, volume=550, open_interest=1300),
        OptionContract("NVDA", "NVDA-0D-C-190", "call", 190, 0, 1.1, 1.2, delta=0.45, volume=700, open_interest=1400),
    ]


def _request() -> TargetMoveScenarioRequest:
    return TargetMoveScenarioRequest(
        symbol="NVDA",
        direction="put",
        current_price=188.2,
        target_price=184.0,
        time_horizon_minutes=25,
        budget=1000.0,
        allowed_dtes=(0, 1, 2),
    )


def test_budget_sizing_excludes_unaffordable_contracts() -> None:
    board = TargetMoveScenarioBoard(SCENARIO_CONFIG)
    request = TargetMoveScenarioRequest(**{**_request().__dict__, "budget": 90.0})

    result = board.generate(request, _contracts())

    assert result["candidates"] == []


def test_target_value_estimation_is_deterministic() -> None:
    board = TargetMoveScenarioBoard(SCENARIO_CONFIG)

    first = board.generate(_request(), _contracts())
    second = board.generate(_request(), _contracts())

    assert [c["option_symbol"] for c in first["candidates"]] == [c["option_symbol"] for c in second["candidates"]]
    assert first["candidates"][0]["estimated_target_option_price"] == second["candidates"][0]["estimated_target_option_price"]


def test_includes_0dte_candidates_when_allowed() -> None:
    board = TargetMoveScenarioBoard(SCENARIO_CONFIG)

    result = board.generate(_request(), _contracts())

    assert any(candidate["dte"] == 0 for candidate in result["candidates"])


def test_ranking_and_bucket_labels_present() -> None:
    board = TargetMoveScenarioBoard(SCENARIO_CONFIG)

    result = board.generate(_request(), _contracts())

    assert result["candidates"][0]["ranking_score"] >= result["candidates"][-1]["ranking_score"]
    assert set(result["buckets"]) == {"highest_estimated_return", "best_balance", "safer_fill", "aggressive_cheap"}


def test_operator_console_payload_and_timeline_event() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    scenario_engine = TargetMoveScenarioBoard(SCENARIO_CONFIG)

    interaction = _interaction(state)
    interaction.target_move_handler = lambda payload: scenario_engine.generate(
        TargetMoveScenarioRequest(
            symbol=str(payload["symbol"]),
            direction=str(payload["direction"]),
            current_price=float(payload["current_price"]),
            target_price=float(payload["target_price"]),
            time_horizon_minutes=int(payload["time_horizon_minutes"]),
            budget=float(payload["budget"]),
            allowed_dtes=tuple(int(v) for v in payload["allowed_dtes"]),
        ),
        _contracts(),
    )

    now = datetime.now(timezone.utc)
    response = interaction.submit_target_move_request(
        {
            "symbol": "NVDA",
            "direction": "put",
            "current_price": 188.2,
            "target_price": 184.0,
            "time_horizon_minutes": 25,
            "budget": 1000,
            "allowed_dtes": [0, 1, 2],
        },
        now=now,
    )
    payload = interaction.dashboard_payload()

    assert response["intent"] == "target_move_scenario"
    assert payload["target_move_board"]["request"]["symbol"] == "NVDA"
    assert any(event["event_type"] == "target_move_scenario_generated" for event in payload["timeline"]["events"])


def test_structured_target_move_text_command_path() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    scenario_engine = TargetMoveScenarioBoard(SCENARIO_CONFIG)
    interaction = _interaction(state)
    interaction.target_move_handler = lambda payload: scenario_engine.generate(
        TargetMoveScenarioRequest(
            symbol=str(payload["symbol"]),
            direction=str(payload["direction"]),
            current_price=float(payload.get("current", payload.get("current_price"))),
            target_price=float(payload.get("target", payload.get("target_price"))),
            time_horizon_minutes=int(payload.get("minutes", payload.get("time_horizon_minutes"))),
            budget=float(payload["budget"]),
            allowed_dtes=tuple(int(v) for v in payload.get("allowed_dtes", [0, 1, 2])),
        ),
        _contracts(),
    )

    response = interaction.submit_text_panel_command(
        {"command": "target_move symbol=NVDA direction=put current=188.2 target=184 budget=1000 minutes=25 dtes=0,1,2"}
    )

    assert response["intent"] == "target_move_scenario"
    assert response["raw_result"]["target_move_board"]["request"]["allowed_dtes"] == [0, 1, 2]
