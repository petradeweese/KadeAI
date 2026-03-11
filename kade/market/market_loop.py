"""Polling market loop for Phase 2A ticker state updates."""

from __future__ import annotations

import time
from collections.abc import Callable
from logging import Logger

from kade.logging_utils import LogCategory, get_logger, log_event
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
        self.logger = logger or get_logger(__name__)
        self.latest_states: dict[str, TickerState] = {}
        self.latest_debug: dict[str, dict[str, float | str | None]] = {}

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

            log_event(
                self.logger,
                LogCategory.MARKET_EVENT,
                "Ticker state updated",
                symbol=symbol,
                trend=result.state.trend,
                confidence=result.state.confidence_label,
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
