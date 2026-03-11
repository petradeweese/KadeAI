"""Paper execution workflow with staged orders and simulation scaffolding."""

from __future__ import annotations

from logging import Logger

from kade.execution.guardrails import ExecutionGuardrails
from kade.execution.lifecycle import ExecutionLifecycle
from kade.execution.models import ExecutionRejection, OrderRequest, OrderResult
from kade.logging_utils import LogCategory, get_logger, log_event


class PaperExecutionEngine:
    def __init__(self, execution_config: dict, logger: Logger | None = None) -> None:
        self.execution_config = execution_config
        self.paper_sim = execution_config["paper_simulation"]
        self.guardrails = ExecutionGuardrails(execution_config)
        self.logger = logger or get_logger(__name__)

    def preview_order(self, request: OrderRequest) -> dict[str, object]:
        return {
            "symbol": request.symbol,
            "option_symbol": request.option_symbol,
            "contracts": request.contracts,
            "side": request.side,
            "limit_price": request.limit_price,
            "estimated_notional": round(request.contracts * request.limit_price * 100, 2),
        }

    def stage_order(
        self,
        request: OrderRequest,
        trades_today: int,
        daily_realized_pnl: float,
        confirm: bool,
    ) -> OrderResult | ExecutionRejection:
        slippage = self._simulated_slippage(request.limit_price)
        guardrail_failure = self.guardrails.validate(request, trades_today, daily_realized_pnl, requested_slippage=slippage)
        if guardrail_failure:
            log_event(self.logger, LogCategory.ORDER_EVENT, "Order rejected by guardrail", code=guardrail_failure.code)
            return ExecutionRejection(request=request, failure=guardrail_failure)

        lifecycle = ExecutionLifecycle()
        log_event(self.logger, LogCategory.ORDER_EVENT, "Execution lifecycle state change", state=lifecycle.state, reason="staged")

        if not confirm:
            return OrderResult(
                request=request,
                status="pending_confirmation",
                filled_contracts=0,
                remaining_contracts=request.contracts,
                avg_fill_price=None,
                simulated_slippage=slippage,
                notes=["Awaiting confirmation"],
                lifecycle=lifecycle.snapshot(),
            )

        lifecycle.transition("confirmed", "user_confirmed")
        lifecycle.transition("submitted", "paper_submission")
        result = self._simulate_fill(request, slippage, lifecycle=lifecycle)
        log_event(
            self.logger,
            LogCategory.ORDER_EVENT,
            "Paper order simulated",
            symbol=request.symbol,
            status=result.status,
            filled=result.filled_contracts,
            remaining=result.remaining_contracts,
        )
        return result

    def _simulate_fill(self, request: OrderRequest, slippage: float, lifecycle: ExecutionLifecycle) -> OrderResult:
        partial_ratio = self.paper_sim["partial_fill_ratio"] if self.paper_sim["allow_partial_fills"] else 1.0
        filled = int(request.contracts * partial_ratio)
        if request.contracts > 0 and filled == 0:
            filled = 1
        filled = min(filled, request.contracts)
        remaining = request.contracts - filled

        fill_price = round(request.limit_price + slippage, 2)
        nudged_price = None
        notes: list[str] = []
        status = "filled"
        if remaining > 0:
            status = "partially_filled"
            notes.append("Partial fill simulated")
            lifecycle.transition("partially_filled", "paper_fill_update")
            if self.paper_sim["adaptive_nudging_enabled"]:
                nudged_price = round(request.limit_price + self.paper_sim["nudge_step"], 2)
                notes.append("Adaptive nudge suggested")
                notes.append("Nudge pending follow-up fill")
        else:
            lifecycle.transition("filled", "paper_fill_update")

        log_event(self.logger, LogCategory.ORDER_EVENT, "Execution lifecycle state change", state=lifecycle.state)

        return OrderResult(
            request=request,
            status=status,
            filled_contracts=filled,
            remaining_contracts=remaining,
            avg_fill_price=fill_price if filled > 0 else None,
            simulated_slippage=slippage,
            nudged_limit_price=nudged_price,
            notes=notes,
            lifecycle=lifecycle.snapshot(),
        )

    def _simulated_slippage(self, limit_price: float) -> float:
        slippage_from_bps = limit_price * (self.paper_sim["slippage_bps"] / 10000)
        return round(min(self.paper_sim["max_slippage_per_contract"], slippage_from_bps), 4)
