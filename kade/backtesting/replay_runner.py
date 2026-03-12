"""Replay runner integration for timeline-inspectable backtest sessions."""

from __future__ import annotations

from dataclasses import asdict

from kade.backtesting.engine import BacktestEngine
from kade.backtesting.models import BacktestRunInput, ReplayRunnerResult
from kade.runtime.timeline import RuntimeTimeline


class BacktestReplayRunner:
    def __init__(self, engine: BacktestEngine, timeline: RuntimeTimeline | None = None) -> None:
        self.engine = engine
        self.timeline = timeline or RuntimeTimeline()

    def run(self, run_input: BacktestRunInput) -> ReplayRunnerResult:
        self.timeline.add_event(
            "backtest_run_started",
            run_input.started_at.isoformat(),
            {"run_id": run_input.run_id, "symbols": run_input.symbols, "step_count": len(run_input.steps)},
        )
        for step in run_input.steps:
            ts = step.timestamp.isoformat()
            if step.trade_idea_request:
                self.timeline.add_event("opinion_evaluated", ts, {"symbol": step.symbol, "bar_index": step.bar_index})
            if step.target_move_request:
                self.timeline.add_event("scenario_evaluated", ts, {"symbol": step.symbol, "bar_index": step.bar_index})
            if step.radar_signal:
                self.timeline.add_event("radar_evaluated", ts, {"symbol": step.symbol, "bar_index": step.bar_index})

        result = self.engine.run(run_input)
        self.timeline.add_event(
            "backtest_run_completed",
            result.generated_at,
            {
                "run_id": result.run_id,
                "opinion_count": len(result.opinion_evaluations),
                "scenario_count": len(result.scenario_evaluations),
                "radar_count": len(result.radar_evaluations),
            },
        )
        return ReplayRunnerResult(run_result=result, timeline_events=[asdict(e) for e in self.timeline.events])
