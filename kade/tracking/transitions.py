"""Trade-plan tracking transition helpers."""

from __future__ import annotations

from kade.tracking.models import TradePlanEvaluation


class PlanStatusTransitions:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config

    def resolve(self, status: str, evaluation: TradePlanEvaluation, execution_state: str | None = None) -> tuple[str, list[str]]:
        actions: list[str] = []
        invalidation = evaluation.invalidation.state
        trigger = evaluation.trigger.state
        stale = evaluation.staleness.state

        if invalidation == "hard_invalidated":
            if status in {"watching", "ready", "triggered"}:
                actions.append("cancelled_due_to_hard_invalidation")
                return "cancelled", actions
            if status == "active" and bool(self.config.get("allow_cancel_active_on_hard_invalidation", False)):
                actions.append("cancelled_active_due_to_hard_invalidation")
                return "cancelled", actions

        if stale == "stale" and status in {"watching", "ready"} and bool(self.config.get("auto_cancel_stale_watch", False)):
            actions.append("cancelled_due_to_staleness")
            return "cancelled", actions

        if status == "watching":
            if trigger == "triggered":
                actions.append("watching_to_triggered")
                return "triggered", actions
            if trigger == "ready":
                actions.append("watching_to_ready")
                return "ready", actions
        elif status == "ready" and trigger == "triggered":
            actions.append("ready_to_triggered")
            return "triggered", actions
        elif status == "triggered":
            active_states = set(self.config.get("active_execution_states", ["filled", "active", "in_position"]))
            auto_promote = bool(self.config.get("auto_triggered_to_active", False))
            if execution_state in active_states:
                actions.append("triggered_to_active_with_execution_evidence")
                return "active", actions
            if auto_promote:
                actions.append("triggered_to_active_auto")
                return "active", actions
        elif status == "active":
            exit_states = set(self.config.get("exit_execution_states", ["closed", "exited", "flat"]))
            if execution_state in exit_states:
                actions.append("active_to_exited")
                return "exited", actions

        return status, actions
