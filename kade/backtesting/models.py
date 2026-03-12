"""Structured models for deterministic replay/backtest runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from kade.brain.trade_idea import TradeIdeaOpinion, TradeIdeaOpinionRequest
from kade.market.structure import TickerState
from kade.options.models import OptionContract
from kade.options.scenario import TargetMoveScenarioRequest


@dataclass(frozen=True)
class ReplayStepInput:
    symbol: str
    timestamp: datetime
    bar_index: int
    current_price: float
    ticker_state: TickerState
    future_prices: list[float]
    radar_signal: dict[str, object] | None = None
    radar_context: dict[str, object] = field(default_factory=dict)
    breadth_context: dict[str, object] = field(default_factory=dict)
    option_chain_snapshot: list[OptionContract] = field(default_factory=list)
    trade_idea_request: TradeIdeaOpinionRequest | None = None
    target_move_request: TargetMoveScenarioRequest | None = None


@dataclass(frozen=True)
class BacktestRunInput:
    run_id: str
    symbols: list[str]
    started_at: datetime
    ended_at: datetime
    steps: list[ReplayStepInput]


@dataclass(frozen=True)
class OutcomeLabel:
    label: str
    target_hit: bool
    hit_step: int | None
    max_move_pct: float
    min_move_pct: float


@dataclass(frozen=True)
class OpinionEvaluationRecord:
    symbol: str
    timestamp: str
    request: dict[str, object]
    opinion: dict[str, object]
    realized_outcome: str
    target_hit: bool
    hit_step: int | None
    stance_alignment: str
    calibration_note: str


@dataclass(frozen=True)
class ScenarioEvaluationRecord:
    symbol: str
    timestamp: str
    request: dict[str, object]
    board: dict[str, object]
    realized_outcome: str
    target_hit: bool
    top_rank_useful: bool
    bucket_winner: str
    calibration_note: str


@dataclass(frozen=True)
class RadarEvaluationRecord:
    symbol: str
    timestamp: str
    signal: dict[str, object]
    realized_outcome: str
    target_hit: bool


@dataclass(frozen=True)
class BacktestRunResult:
    run_id: str
    symbols: list[str]
    time_range: dict[str, str]
    opinion_evaluations: list[OpinionEvaluationRecord]
    scenario_evaluations: list[ScenarioEvaluationRecord]
    radar_evaluations: list[RadarEvaluationRecord]
    opinion_metrics: dict[str, object]
    scenario_metrics: dict[str, object]
    radar_metrics: dict[str, object]
    notes: list[str]
    generated_at: str


@dataclass(frozen=True)
class ReplayRunnerResult:
    run_result: BacktestRunResult
    timeline_events: list[dict[str, object]]
