from kade.dashboard.app import create_app_status
from kade.runtime.interaction import InteractionRuntimeState
from kade.strategy import StrategyIntelligenceService
from kade.tests.test_phase8_interaction import _interaction


def _plan(plan_id: str, symbol: str, direction: str, status: str, trigger: str, target: str, invalidation: str, regime: str = "trend") -> dict[str, object]:
    return {
        "plan_id": plan_id,
        "symbol": symbol,
        "direction": direction,
        "status": status,
        "trigger_condition": trigger,
        "target_exit_idea": target,
        "invalidation_concept": invalidation,
        "entry_plan": {"trigger_condition": trigger},
        "target_plan": {"primary_target": target},
        "invalidation_plan": {"invalidation_condition": invalidation},
        "risk_posture": "normal",
        "target_plausibility": "realistic",
        "max_hold_minutes": 45,
        "regime_fit": regime,
        "linked_target_move_board": {"setup_tags": ["momentum"]},
        "created_at": "2026-01-01T10:00:00+00:00",
        "updated_at": "2026-01-01T11:00:00+00:00",
    }


def _tracking(plan_id: str, invalidation_state: str = "safe") -> dict[str, object]:
    return {"plan_id": plan_id, "summary": "tracking", "invalidation_state": invalidation_state, "elapsed_minutes": 30}


def _review(plan_id: str, review_label: str, roi: float, outcome_label: str = "target_reached_or_positive") -> dict[str, object]:
    return {
        "plan_id": plan_id,
        "review_label": review_label,
        "discipline_label": "disciplined" if review_label in {"well_executed", "mostly_disciplined"} else "mixed",
        "outcome_label": outcome_label,
        "final_status": "exited",
        "realized_outcome": {"roi": roi},
        "hold_minutes": 25,
        "invalidation_respected": review_label != "invalidation_ignored",
        "reviewed_at": "2026-01-01T11:05:00+00:00",
        "exit_price": "105.0",
    }


def _service() -> StrategyIntelligenceService:
    return StrategyIntelligenceService(
        {
            "lookback_limits": {"default": 50, "min": 10, "max": 250},
            "archetype_rules": {},
            "calibration_thresholds": {"realistic_ratio_min": 0.75, "stretched_ratio_min": 0.45},
        }
    )


def test_archetype_classification_is_deterministic() -> None:
    svc = _service()
    trade = svc.analyze_completed_trades(
        [_plan("p1", "NVDA", "long", "exited", "VWAP reclaim above 101", "103", "below 99")],
        [_tracking("p1")],
        [_review("p1", "well_executed", 0.03)],
    )[0]
    first = svc.classify_setup_archetype(trade).to_payload()
    second = svc.classify_setup_archetype(trade).to_payload()

    assert first["archetype_label"] == "vwap_reclaim"
    assert first == second


def test_regime_symbol_and_discipline_aggregations() -> None:
    svc = _service()
    trades = svc.analyze_completed_trades(
        [
            _plan("p1", "NVDA", "long", "exited", "VWAP reclaim above 101", "104", "below 99", regime="trend"),
            _plan("p2", "AAPL", "short", "exited", "failed breakdown below 190", "186", "above 193", regime="chop"),
        ],
        [_tracking("p1"), _tracking("p2", invalidation_state="invalidated")],
        [_review("p1", "well_executed", 0.04), _review("p2", "drifted_from_plan", -0.03, outcome_label="stopped")],
    )
    enriched = [{**t, "setup_archetype": svc.classify_setup_archetype(t).archetype_label} for t in trades]

    regime = svc.compute_regime_performance(enriched)
    symbols = svc.compute_symbol_performance(enriched)
    discipline = svc.compute_discipline_impact(enriched)

    assert {item["regime"] for item in regime} == {"trend", "chop"}
    assert {item["symbol"] for item in symbols} == {"NVDA", "AAPL"}
    assert discipline["disciplined_count"] == 1
    assert discipline["undisciplined_count"] == 1


def test_plan_calibration_and_snapshot_shape_repeatable() -> None:
    svc = _service()
    plans = [_plan("p1", "NVDA", "long", "exited", "VWAP reclaim above 100", "103", "below 99")]
    tracking = [_tracking("p1")]
    reviews = [_review("p1", "well_executed", 0.02)]
    first = svc.build_strategy_snapshot(plans, tracking, reviews, lookback=20, now_iso="2026-01-01T12:00:00+00:00").to_payload()
    second = svc.build_strategy_snapshot(plans, tracking, reviews, lookback=20, now_iso="2026-01-01T12:00:00+00:00").to_payload()

    assert first["plan_calibration_summary"]["target_realism"] in {"realistic", "stretched", "unrealistic"}
    assert first["grouped_statistics"]["symbol"][0]["group_key"] == "NVDA"
    assert first == second


def test_runtime_strategy_request_and_dashboard_panel_shape() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    interaction = _interaction(state)
    interaction.strategy_analysis_handler = lambda payload: {
        "setup_archetype_stats": [{"archetype_label": "vwap_reclaim", "trade_count": 4}],
        "regime_performance": [{"regime": "trend", "trade_count": 4}],
        "symbol_performance": [{"symbol": "NVDA", "trade_count": 4}],
        "discipline_impact": {"disciplined_win_rate": 0.75},
        "plan_calibration_summary": {"target_realism": "realistic"},
        "recent_trades_summary": {"trade_count": 4},
        "generated_at": "2026-01-01T12:00:00+00:00",
    }

    result = interaction.submit_strategy_analysis_request({"lookback": 50})
    assert result["intent"] == "strategy_analysis"
    assert interaction.dashboard_payload()["strategy_intelligence"]["recent_trades_summary"]["trade_count"] == 4

    app = create_app_status(strategy_intelligence_payload=interaction.dashboard_payload()["strategy_intelligence"])
    panel = app["operator_console"]["strategy_intelligence"]
    assert panel["setup_archetypes"][0]["archetype_label"] == "vwap_reclaim"
