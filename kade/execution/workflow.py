"""End-to-end paper execution workflow scaffolding."""

from __future__ import annotations

from logging import Logger

from kade.execution.models import OrderRequest
from kade.execution.paper import PaperExecutionEngine
from kade.logging_utils import LogCategory, get_logger, log_event
from kade.options.models import SelectedOptionPlan


class PaperExecutionWorkflow:
    def __init__(self, execution_config: dict, logger: Logger | None = None) -> None:
        self.engine = PaperExecutionEngine(execution_config, logger=logger)
        self.execution_config = execution_config
        self.logger = logger or get_logger(__name__)

    def build_order_requests(self, plan: SelectedOptionPlan, side: str = "buy") -> list[OrderRequest]:
        requests = [
            OrderRequest(
                symbol=plan.symbol,
                option_symbol=allocation.option_symbol,
                contracts=allocation.contracts,
                side=side,
                limit_price=allocation.premium,
                mode=self.execution_config["mode"],
                order_type=self.execution_config["order_type"],
            )
            for allocation in plan.allocations
        ]
        log_event(self.logger, LogCategory.ORDER_EVENT, "Order intents created", symbol=plan.symbol, count=len(requests))
        return requests
