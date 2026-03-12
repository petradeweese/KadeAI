"""Replay dataset builder from cached 1m bars and deterministic resamples."""

from __future__ import annotations

from datetime import datetime

from kade.backtesting.models import BacktestRunInput, ReplayStepInput
from kade.brain.trade_idea import TradeIdeaOpinionRequest
from kade.data.history.loader import HistoricalDataLoader
from kade.market.state_builder import MentalModelBuilder
from kade.market.structure import TickerState
from kade.options.scenario import TargetMoveScenarioRequest


class ReplayDatasetBuilder:
    def __init__(
        self,
        loader: HistoricalDataLoader,
        mental_model_config: dict[str, object],
        replay_config: dict[str, object] | None = None,
    ) -> None:
        self.loader = loader
        self.mental_model = MentalModelBuilder(dict(mental_model_config))
        cfg = replay_config or {}
        self.trigger_lookback = int(cfg.get("trigger_lookback_bars", 20))
        self.bias_lookback = int(cfg.get("bias_lookback_bars", 20))
        self.context_lookback = int(cfg.get("context_lookback_bars", 20))
        self.future_window = int(cfg.get("future_window", 12))

    def build(self, run_id: str, symbols: list[str], start: datetime, end: datetime) -> BacktestRunInput:
        symbol_steps: list[ReplayStepInput] = []
        for symbol in symbols:
            bars_1m = self.loader.load_bars(symbol, start, end, timeframe="1m")
            bars_5m = self.loader.load_bars(symbol, start, end, timeframe="5m")
            bars_15m = self.loader.load_bars(symbol, start, end, timeframe="15m")
            for index, bar in enumerate(bars_1m):
                trigger = bars_1m[max(0, index - self.trigger_lookback + 1) : index + 1]
                bias = [b for b in bars_5m if b.timestamp <= bar.timestamp][-self.bias_lookback :]
                context = [b for b in bars_15m if b.timestamp <= bar.timestamp][-self.context_lookback :]
                if len(trigger) < 5 or not bias or not context:
                    continue
                ticker_state = self._build_ticker_state(symbol, trigger, bias, context)
                future_prices = [future_bar.close for future_bar in bars_1m[index + 1 : index + 1 + self.future_window]]
                direction = "call" if ticker_state.trend == "bullish" else "put"
                target_offset = 1.005 if direction == "call" else 0.995
                target_price = float(bar.close) * target_offset
                symbol_steps.append(
                    ReplayStepInput(
                        symbol=symbol,
                        timestamp=bar.timestamp,
                        bar_index=index,
                        current_price=float(bar.close),
                        ticker_state=ticker_state,
                        future_prices=future_prices,
                        radar_context={"trigger_bars": len(trigger), "bias_bars": len(bias), "context_bars": len(context)},
                        breadth_context={"bias": "neutral"},
                        trade_idea_request=TradeIdeaOpinionRequest(
                            symbol=symbol,
                            direction=direction,
                            current_price=float(bar.close),
                            target_price=target_price,
                            time_horizon_minutes=60,
                        ),
                        target_move_request=TargetMoveScenarioRequest(
                            symbol=symbol,
                            direction=direction,
                            current_price=float(bar.close),
                            target_price=target_price,
                            time_horizon_minutes=60,
                            budget=1000,
                            allowed_dtes=(0, 1),
                        ),
                    )
                )
        ordered_steps = sorted(symbol_steps, key=lambda item: (item.timestamp, item.symbol))
        return BacktestRunInput(run_id=run_id, symbols=symbols, started_at=start, ended_at=end, steps=ordered_steps)

    def _build_ticker_state(self, symbol: str, trigger: list, bias: list, context: list) -> TickerState:
        computation = self.mental_model.build(
            symbol=symbol,
            bars_trigger=trigger,
            bars_bias=bias,
            bars_context=context,
            qqq_trend="neutral",
        )
        return computation.state
