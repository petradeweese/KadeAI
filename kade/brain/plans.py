"""Session trade-plan tracking for Phase 5."""

from __future__ import annotations

from datetime import datetime, timedelta
from logging import Logger
from typing import Callable

from kade.brain.models import PlanStatusEvent, TradePlan
from kade.logging_utils import LogCategory, get_logger, log_event
from kade.utils.time import parse_utc_iso, utc_now

VALID_STATUSES = {"watching", "ready", "triggered", "active", "exited", "cancelled"}
ALLOWED_TRANSITIONS = {
    "watching": {"ready", "triggered", "cancelled"},
    "ready": {"triggered", "cancelled"},
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
        source_mode: str = "operator_request",
        stance: str = "cautious",
        confidence_label: str = "medium",
        target_plausibility: str = "possible_but_stretched",
        market_alignment: str = "mixed",
        regime_fit: str = "unclear",
        trap_risk: str = "unknown",
        entry_plan: dict[str, object] | None = None,
        invalidation_plan: dict[str, object] | None = None,
        target_plan: dict[str, object] | None = None,
        hold_plan: dict[str, object] | None = None,
        risk_posture: str = "watch_only",
        execution_checklist: list[str] | None = None,
        linked_target_move_board: dict[str, object] | None = None,
        linked_trade_idea_opinion: dict[str, object] | None = None,
        debug: dict[str, object] | None = None,
    ) -> TradePlan:
        self._validate_status(status)
        now = utc_now()
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
            source_mode=source_mode,
            stance=stance,
            confidence_label=confidence_label,
            target_plausibility=target_plausibility,
            market_alignment=market_alignment,
            regime_fit=regime_fit,
            trap_risk=trap_risk,
            entry_plan=entry_plan or {},
            invalidation_plan=invalidation_plan or {},
            target_plan=target_plan or {},
            hold_plan=hold_plan or {},
            risk_posture=risk_posture,
            execution_checklist=execution_checklist or [],
            linked_target_move_board=linked_target_move_board or {},
            linked_trade_idea_opinion=linked_trade_idea_opinion or {},
            debug=debug or {},
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
                changed_at=utc_now(),
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
        plan.updated_at = utc_now()
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
        now = now or utc_now()
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
            "source_mode": plan.source_mode,
            "stance": plan.stance,
            "confidence_label": plan.confidence_label,
            "target_plausibility": plan.target_plausibility,
            "market_alignment": plan.market_alignment,
            "regime_fit": plan.regime_fit,
            "trap_risk": plan.trap_risk,
            "entry_plan": plan.entry_plan,
            "invalidation_plan": plan.invalidation_plan,
            "target_plan": plan.target_plan,
            "hold_plan": plan.hold_plan,
            "risk_posture": plan.risk_posture,
            "execution_checklist": plan.execution_checklist,
            "linked_target_move_board": plan.linked_target_move_board,
            "linked_trade_idea_opinion": plan.linked_trade_idea_opinion,
            "debug": plan.debug,
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
            source_mode=str(payload.get("source_mode", "operator_request")),
            stance=str(payload.get("stance", "cautious")),
            confidence_label=str(payload.get("confidence_label", "medium")),
            target_plausibility=str(payload.get("target_plausibility", "possible_but_stretched")),
            market_alignment=str(payload.get("market_alignment", "mixed")),
            regime_fit=str(payload.get("regime_fit", "unclear")),
            trap_risk=str(payload.get("trap_risk", "unknown")),
            entry_plan=dict(payload.get("entry_plan", {})),
            invalidation_plan=dict(payload.get("invalidation_plan", {})),
            target_plan=dict(payload.get("target_plan", {})),
            hold_plan=dict(payload.get("hold_plan", {})),
            risk_posture=str(payload.get("risk_posture", "watch_only")),
            execution_checklist=[str(item) for item in payload.get("execution_checklist", [])],
            linked_target_move_board=dict(payload.get("linked_target_move_board", {})),
            linked_trade_idea_opinion=dict(payload.get("linked_trade_idea_opinion", {})),
            debug=dict(payload.get("debug", {})),
            created_at=parse_utc_iso(str(payload["created_at"])),
            updated_at=parse_utc_iso(str(payload["updated_at"])),
        )

    def _deserialize_event(self, payload: dict[str, object]) -> PlanStatusEvent:
        return PlanStatusEvent(
            plan_id=str(payload["plan_id"]),
            from_status=str(payload["from_status"]),
            to_status=str(payload["to_status"]),
            changed_at=parse_utc_iso(str(payload["changed_at"])),
            reason=str(payload["reason"]) if payload.get("reason") is not None else None,
        )

    def _trigger_autosave(self) -> None:
        if self.autosave:
            self.autosave()
