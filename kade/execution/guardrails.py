"""Config-driven execution guardrails."""

from __future__ import annotations

from kade.execution.models import GuardrailFailure, OrderRequest


class ExecutionGuardrails:
    def __init__(self, execution_config: dict) -> None:
        self.execution_config = execution_config
        self.guardrails = execution_config["guardrails"]

    def validate(
        self,
        request: OrderRequest,
        trades_today: int,
        daily_realized_pnl: float,
        requested_slippage: float,
    ) -> GuardrailFailure | None:
        if self.execution_config.get("paper_mode_only", True) and request.mode != "paper":
            return GuardrailFailure("paper_only", "Only paper mode is allowed", {"mode": request.mode})
        if self.execution_config.get("limit_orders_only", True) and request.order_type != "limit":
            return GuardrailFailure("limit_only", "Only limit orders are allowed", {"order_type": request.order_type})
        if trades_today >= self.guardrails["max_trades_per_day"]:
            return GuardrailFailure(
                "max_trades_reached",
                "Max trades per day reached",
                {"trades_today": trades_today, "max": self.guardrails["max_trades_per_day"]},
            )
        if daily_realized_pnl <= -abs(self.guardrails["daily_loss_limit_usd"]):
            return GuardrailFailure(
                "daily_loss_limit",
                "Daily loss limit reached",
                {"daily_realized_pnl": daily_realized_pnl, "limit": self.guardrails["daily_loss_limit_usd"]},
            )
        if requested_slippage > self.guardrails["max_slippage_cap_per_contract"]:
            return GuardrailFailure(
                "slippage_cap",
                "Requested slippage exceeds cap",
                {
                    "requested_slippage": requested_slippage,
                    "max_slippage": self.guardrails["max_slippage_cap_per_contract"],
                },
            )
        if request.contracts <= 0 or request.limit_price <= 0:
            return GuardrailFailure("invalid_intent", "Invalid order intent values", {"contracts": request.contracts})
        return None
