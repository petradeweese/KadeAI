"""Options selection pipeline orchestration."""

from __future__ import annotations

from logging import Logger

from kade.logging_utils import LogCategory, get_logger, log_event
from kade.market.structure import TickerState
from kade.options.models import OptionContract, SelectedOptionPlan, TradeIntent
from kade.options.selector import OptionSelector
from kade.options.sizing import SplitSizer


class OptionsSelectionPipeline:
    def __init__(self, config: dict, logger: Logger | None = None) -> None:
        self.selector = OptionSelector(config)
        self.sizer = SplitSizer(config["split_sizing"])
        self.profile = config["default_profile"]
        self.logger = logger or get_logger(__name__)

    def build_plan(
        self,
        intent: TradeIntent,
        contracts: list[OptionContract],
        ticker_state: TickerState | None = None,
        radar_context: dict[str, object] | None = None,
    ) -> SelectedOptionPlan:
        ranked = self.selector.select_candidates(intent, contracts, ticker_state=ticker_state, radar_context=radar_context)
        plan = self.sizer.build_plan(intent, ranked, profile=self.profile)
        log_event(
            self.logger,
            LogCategory.ORDER_EVENT,
            "Options plan generated",
            symbol=intent.symbol,
            profile=self.profile,
            candidates=len(ranked),
            allocations=len(plan.allocations),
            estimated_cost=plan.total_estimated_cost,
        )
        return plan
