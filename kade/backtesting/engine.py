"""Backtest engine that replays deterministic snapshots through Kade outputs."""

from __future__ import annotations

from dataclasses import asdict

from kade.backtesting.evaluator import BacktestEvaluator
from kade.backtesting.metrics import opinion_metrics, radar_metrics, scenario_metrics
from kade.backtesting.models import (
    BacktestRunInput,
    BacktestRunResult,
    OpinionEvaluationRecord,
    RadarEvaluationRecord,
    ScenarioEvaluationRecord,
)
from kade.brain.trade_idea import TradeIdeaOpinionEngine
from kade.options.scenario import TargetMoveScenarioBoard
from kade.utils.time import utc_now_iso


class BacktestEngine:
    def __init__(
        self,
        opinion_engine: TradeIdeaOpinionEngine,
        scenario_board: TargetMoveScenarioBoard,
        evaluator: BacktestEvaluator,
        report_limits: dict[str, int] | None = None,
    ) -> None:
        self.opinion_engine = opinion_engine
        self.scenario_board = scenario_board
        self.evaluator = evaluator
        self.report_limits = report_limits or {"recent_evaluations": 20}

    def run(self, run_input: BacktestRunInput) -> BacktestRunResult:
        opinion_records: list[OpinionEvaluationRecord] = []
        scenario_records: list[ScenarioEvaluationRecord] = []
        radar_records: list[RadarEvaluationRecord] = []

        for step in run_input.steps:
            if step.radar_signal:
                radar_outcome = self.evaluator.label_outcome(
                    direction=str(step.radar_signal.get("direction", "bullish")),
                    current_price=step.current_price,
                    target_price=step.current_price * (1.0 + 0.004),
                    future_prices=step.future_prices,
                )
                radar_records.append(
                    RadarEvaluationRecord(
                        symbol=step.symbol,
                        timestamp=step.timestamp.isoformat(),
                        signal=step.radar_signal,
                        realized_outcome=radar_outcome.label,
                        target_hit=self.evaluator.radar_hit(step.radar_signal, step.future_prices, step.current_price),
                    )
                )

            if step.trade_idea_request:
                opinion = self.opinion_engine.evaluate(
                    request=step.trade_idea_request,
                    ticker_state=step.ticker_state,
                    radar_context=step.radar_context,
                    breadth_context=step.breadth_context,
                )
                outcome = self.evaluator.label_outcome(
                    direction=step.trade_idea_request.direction,
                    current_price=step.trade_idea_request.current_price,
                    target_price=step.trade_idea_request.target_price,
                    future_prices=step.future_prices,
                )
                alignment = self.evaluator.evaluate_stance_alignment(opinion.stance, outcome.label)
                opinion_records.append(
                    OpinionEvaluationRecord(
                        symbol=step.symbol,
                        timestamp=step.timestamp.isoformat(),
                        request=asdict(step.trade_idea_request),
                        opinion=opinion.as_dict(),
                        realized_outcome=outcome.label,
                        target_hit=outcome.target_hit,
                        hit_step=outcome.hit_step,
                        stance_alignment=alignment,
                        calibration_note=f"stance={opinion.stance} alignment={alignment} plausibility={opinion.target_plausibility}",
                    )
                )

            if step.target_move_request:
                board = self.scenario_board.generate(step.target_move_request, step.option_chain_snapshot)
                outcome = self.evaluator.label_outcome(
                    direction=step.target_move_request.direction,
                    current_price=step.target_move_request.current_price,
                    target_price=step.target_move_request.target_price,
                    future_prices=step.future_prices,
                )
                top_useful, bucket_winner = self.evaluator.scenario_usefulness(board, outcome)
                scenario_records.append(
                    ScenarioEvaluationRecord(
                        symbol=step.symbol,
                        timestamp=step.timestamp.isoformat(),
                        request=asdict(step.target_move_request),
                        board=board,
                        realized_outcome=outcome.label,
                        target_hit=outcome.target_hit,
                        top_rank_useful=top_useful,
                        bucket_winner=bucket_winner,
                        calibration_note=f"top_rank_useful={top_useful} bucket_winner={bucket_winner}",
                    )
                )

        return BacktestRunResult(
            run_id=run_input.run_id,
            symbols=run_input.symbols,
            time_range={"start": run_input.started_at.isoformat(), "end": run_input.ended_at.isoformat()},
            opinion_evaluations=opinion_records,
            scenario_evaluations=scenario_records,
            radar_evaluations=radar_records,
            opinion_metrics=opinion_metrics(opinion_records),
            scenario_metrics=scenario_metrics(scenario_records),
            radar_metrics=radar_metrics(radar_records),
            notes=[
                "Deterministic replay only; no live trading assumptions.",
                "Scenario evaluation focuses on directionality and ranking usefulness, not exact options P&L.",
            ],
            generated_at=utc_now_iso(),
        )

    def summary_payload(self, result: BacktestRunResult) -> dict[str, object]:
        recent_limit = int(self.report_limits.get("recent_evaluations", 20))
        return {
            "run_id": result.run_id,
            "symbols": result.symbols,
            "time_range": result.time_range,
            "opinion_metrics": result.opinion_metrics,
            "scenario_metrics": result.scenario_metrics,
            "radar_metrics": result.radar_metrics,
            "notes": result.notes,
            "generated_at": result.generated_at,
            "recent_evaluations": {
                "opinion": [asdict(v) for v in result.opinion_evaluations[-recent_limit:]],
                "scenario": [asdict(v) for v in result.scenario_evaluations[-recent_limit:]],
                "radar": [asdict(v) for v in result.radar_evaluations[-recent_limit:]],
            },
        }
