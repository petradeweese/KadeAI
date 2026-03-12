from datetime import datetime, timezone

from kade.backtesting import BacktestEngine, BacktestEvaluator, BacktestReplayRunner, BacktestRunInput, EvaluationThresholds, ReplayStepInput
from kade.brain.trade_idea import TradeIdeaOpinionEngine, TradeIdeaOpinionRequest
from kade.dashboard.app import create_app_status
from kade.logging_utils import get_logger
from kade.market.structure import TickerState
from kade.options.models import OptionContract
from kade.options.scenario import TargetMoveScenarioBoard, TargetMoveScenarioRequest
from kade.runtime.interaction import InteractionRuntimeState
from kade.runtime.persistence import RuntimePersistence
from kade.runtime.timeline import RuntimeTimeline
from kade.tests.test_phase14_trade_idea_opinion import SCENARIO_CONFIG, TRADE_IDEA_CONFIG


def _ticker(symbol: str = "NVDA") -> TickerState:
    return TickerState(
        symbol=symbol,
        last_price=188.2,
        vwap=187.9,
        trend="bearish",
        structure="breakdown",
        momentum="strong_down",
        volume_state="expanding",
        qqq_confirmation="divergent_risk_off",
        regime="momentum",
        trap_risk="low",
        confidence_label="high",
        confidence_reason="trend continuation",
        updated_at=datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc),
    )


def _chain() -> list[OptionContract]:
    return [
        OptionContract("NVDA", "NVDA-0D-P-185", "put", 185, 0, 1.2, 1.3, delta=-0.48, volume=700, open_interest=1600),
        OptionContract("NVDA", "NVDA-1D-P-184", "put", 184, 1, 1.0, 1.1, delta=-0.44, volume=720, open_interest=1500),
    ]


def _run_input() -> BacktestRunInput:
    ts = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)
    return BacktestRunInput(
        run_id="phase13-demo",
        symbols=["NVDA"],
        started_at=ts,
        ended_at=datetime(2026, 1, 1, 15, 30, tzinfo=timezone.utc),
        steps=[
            ReplayStepInput(
                symbol="NVDA",
                timestamp=ts,
                bar_index=1,
                current_price=188.2,
                ticker_state=_ticker(),
                future_prices=[187.7, 186.8, 185.2, 184.1],
                radar_signal={
                    "symbol": "NVDA",
                    "direction": "bearish",
                    "score": 76.0,
                    "alignment_label": "fully_aligned",
                    "setup_tags": ["trend_continuation"],
                    "regime_fit": "regime_aligned",
                },
                radar_context={"score": 76.0, "setup_tags": ["trend_continuation"]},
                breadth_context={"bias": "risk_off"},
                trade_idea_request=TradeIdeaOpinionRequest(
                    symbol="NVDA",
                    direction="put",
                    current_price=188.2,
                    target_price=184.5,
                    time_horizon_minutes=60,
                ),
                target_move_request=TargetMoveScenarioRequest(
                    symbol="NVDA",
                    direction="put",
                    current_price=188.2,
                    target_price=184.5,
                    time_horizon_minutes=60,
                    budget=1000,
                    allowed_dtes=(0, 1),
                ),
                option_chain_snapshot=_chain(),
            )
        ],
    )


def test_backtest_engine_is_deterministic_and_generates_metrics() -> None:
    engine = BacktestEngine(
        opinion_engine=TradeIdeaOpinionEngine(TRADE_IDEA_CONFIG),
        scenario_board=TargetMoveScenarioBoard(SCENARIO_CONFIG),
        evaluator=BacktestEvaluator(EvaluationThresholds()),
    )

    first = engine.run(_run_input())
    second = engine.run(_run_input())

    assert first.opinion_metrics["count"] == 1
    assert first.scenario_metrics["count"] == 1
    assert first.radar_metrics["count"] == 1
    assert first.opinion_evaluations[0].realized_outcome == "target_hit"
    assert first.opinion_evaluations[0].stance_alignment in {"aligned", "mixed"}
    assert first.opinion_evaluations[0].realized_outcome == second.opinion_evaluations[0].realized_outcome


def test_replay_runner_emits_timeline_events_for_backtest() -> None:
    timeline = RuntimeTimeline(retention=20)
    engine = BacktestEngine(
        opinion_engine=TradeIdeaOpinionEngine(TRADE_IDEA_CONFIG),
        scenario_board=TargetMoveScenarioBoard(SCENARIO_CONFIG),
        evaluator=BacktestEvaluator(EvaluationThresholds()),
    )
    runner = BacktestReplayRunner(engine, timeline=timeline)

    result = runner.run(_run_input())
    event_types = [event["event_type"] for event in result.timeline_events]

    assert "backtest_run_started" in event_types
    assert "opinion_evaluated" in event_types
    assert "scenario_evaluated" in event_types
    assert "radar_evaluated" in event_types
    assert "backtest_run_completed" in event_types


def test_persist_backtest_summary_and_operator_console_shape(tmp_path) -> None:
    engine = BacktestEngine(
        opinion_engine=TradeIdeaOpinionEngine(TRADE_IDEA_CONFIG),
        scenario_board=TargetMoveScenarioBoard(SCENARIO_CONFIG),
        evaluator=BacktestEvaluator(EvaluationThresholds()),
    )
    summary = engine.summary_payload(engine.run(_run_input()))

    persistence = RuntimePersistence.from_config(
        {
            "root_dir": str(tmp_path),
            "history": {"backtest_limit": 5},
            "session": {},
        },
        logger=get_logger(__name__),
    )
    persisted = persistence.persist_backtest_summaries([summary])
    loaded = persistence.load_backtest_summaries()

    assert len(persisted) == 1
    assert loaded[0]["run_id"] == "phase13-demo"

    voice_payload = {
        "backtesting": {
            "latest_run_summary": summary,
            "opinion_metrics": summary["opinion_metrics"],
            "scenario_metrics": summary["scenario_metrics"],
            "radar_metrics": summary["radar_metrics"],
            "recent_evaluations": summary["recent_evaluations"],
        }
    }
    payload = create_app_status(voice_payload=voice_payload)
    backtesting_panel = payload["operator_console"]["backtesting"]

    assert backtesting_panel["latest_run_summary"]["run_id"] == "phase13-demo"


def test_interaction_dashboard_exposes_backtest_payload() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    assert state.latest_backtest_run_summary == {}
