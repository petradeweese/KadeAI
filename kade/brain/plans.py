"""Session trade-plan tracking for Phase 5."""

from __future__ import annotations

from datetime import datetime, timedelta
from logging import Logger
from typing import Callable

from kade.brain.models import PlanStatusEvent, TradePlan
from kade.logging_utils import LogCategory, get_logger, log_event

VALID_STATUSES = {"watching", "triggered", "active", "exited", "cancelled"}
ALLOWED_TRANSITIONS = {
    "watching": {"triggered", "cancelled"},
    "triggered": {"active", "cancelled"},
    "active": {"exited", "cancelled"},
    "exited": set(),
    "cancelled": set(),
}


class SessionPlanTracker:
    def __init__(self, config: dict, logger: Logger | None = None, autosave: Callable[[], None] | None = None) -> None:
        self.config = config
        self.logger = logger or get_logger(__name__)
        self.autosave = autosave
        self.plans: dict[str, TradePlan] = {}
        self.status_events: list[PlanStatusEvent] = []

    def create_plan(
        self,
        symbol: str,
        direction: str,
        trigger_condition: str,
        target_exit_idea: str,
        max_hold_minutes: int,
        invalidation_concept: str,
        status: str = "watching",
        notes: list[str] | None = None,
    ) -> TradePlan:
        self._validate_status(status)
        now = datetime.utcnow()
        plan_id = f"plan-{symbol}-{int(now.timestamp() * 1000)}"
        plan = TradePlan(
            plan_id=plan_id,
            symbol=symbol,
            direction=direction,
            trigger_condition=trigger_condition,
            target_exit_idea=target_exit_idea,
            max_hold_minutes=max_hold_minutes,
            invalidation_concept=invalidation_concept,
            status=status,
            created_at=now,
            updated_at=now,
            notes=notes or [],
        )
        self.plans[plan_id] = plan
        log_event(self.logger, LogCategory.REASONING_EVENT, "Plan created", plan_id=plan_id, symbol=symbol, status=status)
        self._trigger_autosave()
        return plan

    def update_status(self, plan_id: str, new_status: str, reason: str | None = None) -> TradePlan:
        plan = self.plans[plan_id]
        self._validate_status(new_status)
        if new_status != plan.status and new_status not in ALLOWED_TRANSITIONS[plan.status]:
            raise ValueError(f"Invalid status transition: {plan.status} -> {new_status}")

        if new_status != plan.status:
            event = PlanStatusEvent(
                plan_id=plan_id,
                from_status=plan.status,
                to_status=new_status,
                changed_at=datetime.utcnow(),
                reason=reason,
            )
            self.status_events.append(event)
            log_event(
                self.logger,
                LogCategory.REASONING_EVENT,
                "Plan status changed",
                plan_id=plan_id,
                symbol=plan.symbol,
                from_status=plan.status,
                to_status=new_status,
            )
            plan.status = new_status
            plan.updated_at = event.changed_at
            self._trigger_autosave()
        return plan

    def add_note(self, plan_id: str, note: str) -> TradePlan:
        plan = self.plans[plan_id]
        plan.notes.append(note)
        plan.updated_at = datetime.utcnow()
        log_event(self.logger, LogCategory.REASONING_EVENT, "Plan note added", plan_id=plan_id, symbol=plan.symbol)
        self._trigger_autosave()
        return plan

    def restore(self, payload: dict[str, object]) -> None:
        self.plans = {item["plan_id"]: self._deserialize_plan(item) for item in payload.get("plans", [])}
        self.status_events = [self._deserialize_event(item) for item in payload.get("events", [])]

    def plans_for_symbol(self, symbol: str, include_closed: bool = True) -> list[TradePlan]:
        plans = [plan for plan in self.plans.values() if plan.symbol == symbol]
        if not include_closed:
            plans = [plan for plan in plans if plan.status not in {"exited", "cancelled"}]
        return sorted(plans, key=lambda plan: plan.updated_at, reverse=True)

    def active_plans(self) -> list[TradePlan]:
        return [plan for plan in self.plans.values() if plan.status in {"watching", "triggered", "active"}]

    def cleanup_expired(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.utcnow()
        expiry_minutes = self.config.get("plans", {}).get("expiration_minutes", 480)
        cutoff = now - timedelta(minutes=expiry_minutes)
        removed: list[str] = []
        for plan_id, plan in list(self.plans.items()):
            if plan.updated_at < cutoff and plan.status in {"exited", "cancelled"}:
                removed.append(plan_id)
                del self.plans[plan_id]
        if removed:
            log_event(self.logger, LogCategory.REASONING_EVENT, "Expired plans cleaned", removed_count=len(removed))
            self._trigger_autosave()
        return removed

    def snapshot(self) -> dict[str, object]:
        return {
            "active": [self._serialize(plan) for plan in self.active_plans()],
            "all": [self._serialize(plan) for plan in sorted(self.plans.values(), key=lambda p: p.updated_at, reverse=True)],
            "events": [
                {
                    "plan_id": event.plan_id,
                    "from_status": event.from_status,
                    "to_status": event.to_status,
                    "changed_at": event.changed_at.isoformat(),
                    "reason": event.reason,
                }
                for event in self.status_events[-20:]
            ],
        }

    def persistence_payload(self) -> dict[str, object]:
        return {
            "plans": [self._serialize(plan) for plan in sorted(self.plans.values(), key=lambda p: p.updated_at)],
            "events": [
                {
                    "plan_id": event.plan_id,
                    "from_status": event.from_status,
                    "to_status": event.to_status,
                    "changed_at": event.changed_at.isoformat(),
                    "reason": event.reason,
                }
                for event in self.status_events
            ],
        }

    def _validate_status(self, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Unsupported plan status: {status}")

    def _serialize(self, plan: TradePlan) -> dict[str, object]:
        return {
            "plan_id": plan.plan_id,
            "symbol": plan.symbol,
            "direction": plan.direction,
            "trigger_condition": plan.trigger_condition,
            "target_exit_idea": plan.target_exit_idea,
            "max_hold_minutes": plan.max_hold_minutes,
            "invalidation_concept": plan.invalidation_concept,
            "status": plan.status,
            "notes": plan.notes,
            "created_at": plan.created_at.isoformat(),
            "updated_at": plan.updated_at.isoformat(),
        }

    def _deserialize_plan(self, payload: dict[str, object]) -> TradePlan:
        return TradePlan(
            plan_id=str(payload["plan_id"]),
            symbol=str(payload["symbol"]),
            direction=str(payload["direction"]),
            trigger_condition=str(payload["trigger_condition"]),
            target_exit_idea=str(payload["target_exit_idea"]),
            max_hold_minutes=int(payload["max_hold_minutes"]),
            invalidation_concept=str(payload["invalidation_concept"]),
            status=str(payload["status"]),
            notes=[str(item) for item in payload.get("notes", [])],
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            updated_at=datetime.fromisoformat(str(payload["updated_at"])),
        )

    def _deserialize_event(self, payload: dict[str, object]) -> PlanStatusEvent:
        return PlanStatusEvent(
            plan_id=str(payload["plan_id"]),
            from_status=str(payload["from_status"]),
            to_status=str(payload["to_status"]),
            changed_at=datetime.fromisoformat(str(payload["changed_at"])),
            reason=str(payload["reason"]) if payload.get("reason") is not None else None,
        )

    def _trigger_autosave(self) -> None:
        if self.autosave:
            self.autosave()
