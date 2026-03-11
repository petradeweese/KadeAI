"""Polling market loop for Phase 2B ticker state updates."""

from __future__ import annotations

import time
from collections.abc import Callable
from logging import Logger

from kade.logging_utils import LogCategory, get_logger, log_event
from kade.market.context_intelligence import MarketContextIntelligence
from kade.market.state_builder import MentalModelBuilder
from kade.market.structure import MarketDataClient, TickerState


class MarketStateLoop:
    def __init__(
        self,
        market_client: MarketDataClient,
        watchlist: list[str],
        timeframes: dict[str, str],
        bars_limit: int,
        mental_model_config: dict,
        logger: Logger | None = None,
    ) -> None:
        self.market_client = market_client
        self.watchlist = watchlist
        self.timeframes = timeframes
        self.bars_limit = bars_limit
        self.model_builder = MentalModelBuilder(mental_model_config)
        self.context_intelligence = MarketContextIntelligence(mental_model_config)
        self.logger = logger or get_logger(__name__)
        self.latest_states: dict[str, TickerState] = {}
        self.latest_debug: dict[str, dict[str, float | str | None]] = {}
        self.latest_breadth: dict[str, float | str | None] = {
            "bias": "unknown",
            "advancing_ratio": None,
            "confirmation": "unknown",
        }

    def update_once(self) -> tuple[dict[str, TickerState], dict[str, dict[str, float | str | None]]]:
        bars_by_symbol: dict[str, dict[str, list]] = {}
        for symbol in self.watchlist:
            bars_by_symbol[symbol] = {
                "trigger": self.market_client.get_bars(symbol, self.timeframes["trigger"], self.bars_limit),
                "bias": self.market_client.get_bars(symbol, self.timeframes["bias"], self.bars_limit),
                "context": self.market_client.get_bars(symbol, self.timeframes["context"], self.bars_limit),
            }

        qqq_result = self.model_builder.build(
            symbol="QQQ",
            bars_trigger=bars_by_symbol["QQQ"]["trigger"],
            bars_bias=bars_by_symbol["QQQ"]["bias"],
            bars_context=bars_by_symbol["QQQ"]["context"],
            qqq_trend=None,
        )
        self.latest_states["QQQ"] = qqq_result.state
        self.latest_debug["QQQ"] = qqq_result.debug

        for symbol in self.watchlist:
            if symbol == "QQQ":
                continue
            result = self.model_builder.build(
                symbol=symbol,
                bars_trigger=bars_by_symbol[symbol]["trigger"],
                bars_bias=bars_by_symbol[symbol]["bias"],
                bars_context=bars_by_symbol[symbol]["context"],
                qqq_trend=qqq_result.state.trend,
            )
            self.latest_states[symbol] = result.state
            self.latest_debug[symbol] = result.debug

        spy_state = self.latest_states.get("SPY")
        spy_debug = self.latest_debug.get("SPY")
        baseline_regime = self.context_intelligence.baseline_regime(
            qqq_state=self.latest_states["QQQ"],
            spy_state=spy_state,
            qqq_debug=self.latest_debug["QQQ"],
            spy_debug=spy_debug,
        )

        breadth = self.context_intelligence.breadth_snapshot(self.latest_states)
        previous_breadth = self.latest_breadth.get("bias")
        self.latest_breadth = {
            "bias": breadth.bias,
            "advancing_ratio": breadth.advancing_ratio,
            "confirmation": breadth.confirmation,
            "baseline_regime": baseline_regime,
        }
        if previous_breadth != breadth.bias:
            log_event(
                self.logger,
                LogCategory.MARKET_EVENT,
                "Breadth context updated",
                breadth_bias=breadth.bias,
                advancing_ratio=breadth.advancing_ratio,
                baseline_regime=baseline_regime,
            )

        for symbol in self.watchlist:
            state = self.latest_states[symbol]
            debug = self.latest_debug[symbol]
            previous_regime = state.regime
            previous_trap = state.trap_risk

            state.regime = self.context_intelligence.ticker_regime(baseline_regime, state, debug)
            state.trap_risk = self.context_intelligence.trap_risk(state, debug, bars_by_symbol[symbol]["trigger"])
            state.qqq_confirmation = self.context_intelligence.qqq_confirmation_with_breadth(
                state.qqq_confirmation,
                breadth.bias,
            )
            debug["baseline_regime"] = baseline_regime
            debug["breadth_bias"] = breadth.bias
            debug["breadth_confirmation"] = breadth.confirmation
            debug["breadth_advancing_ratio"] = breadth.advancing_ratio

            if previous_regime != state.regime:
                log_event(
                    self.logger,
                    LogCategory.MARKET_EVENT,
                    "Regime changed",
                    symbol=symbol,
                    regime=state.regime,
                    baseline_regime=baseline_regime,
                )
            if previous_trap != state.trap_risk and state.trap_risk in {"moderate", "high"}:
                log_event(
                    self.logger,
                    LogCategory.MARKET_EVENT,
                    "Trap risk detected",
                    symbol=symbol,
                    trap_risk=state.trap_risk,
                )

            log_event(
                self.logger,
                LogCategory.MARKET_EVENT,
                "Ticker state updated",
                symbol=symbol,
                trend=state.trend,
                regime=state.regime,
                trap_risk=state.trap_risk,
                confidence=state.confidence_label,
            )

        return self.latest_states, self.latest_debug

    def run_forever(
        self,
        poll_seconds: int,
        max_iterations: int | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            self.update_once()
            iterations += 1
            sleep_fn(poll_seconds)
