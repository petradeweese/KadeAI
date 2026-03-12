from datetime import datetime, timedelta, timezone

from kade.brain import SessionPlanTracker
from kade.dashboard.app import create_app_status
from kade.market.structure import TickerState
from kade.runtime.interaction import InteractionRuntimeState
from kade.tests.test_phase8_interaction import _interaction
from kade.tracking import TradePlanMonitor, TradePlanTrackingContext

TRACKING_CFG = {
    "history_limit": 40,
    "evaluation": {"stale_ratio_of_hold": 0.65, "default_stale_minutes": 20, "aging_minutes": 10},
    "transitions": {"auto_triggered_to_active": True, "auto_cancel_stale_watch": False, "allow_cancel_active_on_hard_invalidation": False},
}


def _ticker(**kwargs):
    base = {
        "symbol": "NVDA",
        "last_price": 188.2,
        "vwap": 188.5,
        "trend": "bearish",
        "structure": "breakdown",
        "momentum": "down_bias",
        "volume_state": "expanding",
        "qqq_confirmation": "divergent_risk_off",
        "regime": "momentum",
        "trap_risk": "low",
        "confidence_label": "high",
        "confidence_reason": "trend continuation",
        "updated_at": datetime.now(timezone.utc),
    }
    base.update(kwargs)
    return TickerState(**base)


def _plan_tracker(status: str = "watching") -> tuple[SessionPlanTracker, str]:
    tracker = SessionPlanTracker(config={"plans": {"expiration_minutes": 480}})
    plan = tracker.create_plan(
        symbol="NVDA",
        direction="put",
        trigger_condition="Continuation below VWAP",
        target_exit_idea="184.3",
        max_hold_minutes=60,
        invalidation_concept="Reclaim VWAP",
        status=status,
        hold_plan={"max_hold_minutes": 60, "stale_trade_rule": "If no progress after 20 minutes, cancel or de-risk"},
    )
    return tracker, plan.plan_id


def test_watching_to_ready_transition() -> None:
    tracker, plan_id = _plan_tracker("watching")
    plan = tracker.plans[plan_id]
    monitor = TradePlanMonitor(tracker, TRACKING_CFG)

    snap = monitor.evaluate(
        TradePlanTrackingContext(plan=plan, ticker_state=_ticker(last_price=188.7, momentum="down_bias", vwap=None), radar_context={}, breadth_context={"bias": "risk_off"})
    )

    assert snap.status_before == "watching"
    assert snap.status_after == "ready"
    assert tracker.plans[plan_id].status == "ready"


def test_ready_to_triggered_transition() -> None:
    tracker, plan_id = _plan_tracker("ready")
    plan = tracker.plans[plan_id]
    monitor = TradePlanMonitor(tracker, TRACKING_CFG)

    snap = monitor.evaluate(
        TradePlanTrackingContext(plan=plan, ticker_state=_ticker(last_price=188.0, momentum="strong_down"), radar_context={"alignment_label": "aligned"}, breadth_context={"bias": "risk_off"})
    )

    assert snap.status_after in {"triggered", "active"}
    assert snap.trigger_state == "triggered"


def test_hard_invalidation_cancels_non_active_plan() -> None:
    tracker, plan_id = _plan_tracker("ready")
    plan = tracker.plans[plan_id]
    monitor = TradePlanMonitor(tracker, TRACKING_CFG)

    snap = monitor.evaluate(
        TradePlanTrackingContext(plan=plan, ticker_state=_ticker(last_price=189.2, trend="bullish", momentum="up_bias", vwap=188.5), radar_context={}, breadth_context={"bias": "risk_on"})
    )

    assert snap.invalidation_state == "hard_invalidated"
    assert snap.status_after == "cancelled"


def test_stale_plan_detection_is_deterministic() -> None:
    tracker, plan_id = _plan_tracker("watching")
    plan = tracker.plans[plan_id]
    plan.updated_at = datetime.now(timezone.utc) - timedelta(minutes=25)
    monitor = TradePlanMonitor(tracker, TRACKING_CFG)

    one = monitor.evaluate(TradePlanTrackingContext(plan=plan, ticker_state=_ticker(), radar_context={}, breadth_context={"bias": "risk_off"}), apply_transition=False)
    two = monitor.evaluate(TradePlanTrackingContext(plan=plan, ticker_state=_ticker(), radar_context={}, breadth_context={"bias": "risk_off"}), apply_transition=False)

    assert one.staleness_state == "stale"
    assert one.trigger_state == two.trigger_state
    assert one.invalidation_state == two.invalidation_state
    assert one.staleness_state == two.staleness_state


def test_runtime_payload_shape_and_timeline_operator_console() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    interaction = _interaction(state)
    interaction.trade_plan_tracking_handler = lambda payload: {
        "plan_id": payload.get("plan_id", "plan-1"),
        "symbol": "NVDA",
        "status_before": "watching",
        "status_after": "ready",
        "trigger_state": "ready",
        "invalidation_state": "valid",
        "staleness_state": "fresh",
        "posture_state": "neutral",
        "summary": "Plan is valid and now ready.",
        "reasons": ["Downside alignment remains intact."],
        "actions": ["maintain_readiness"],
        "updated_at": "2026-01-01T00:00:00+00:00",
        "debug": {},
    }

    response = interaction.submit_trade_plan_tracking_request({"plan_id": "plan-1", "symbol": "NVDA"})
    payload = interaction.dashboard_payload()
    app_status = create_app_status(voice_payload=payload)

    assert response["intent"] == "trade_plan_tracking"
    assert payload["trade_plan_tracking"]["plan_id"] == "plan-1"
    event_types = [event["event_type"] for event in payload["timeline"]["events"]]
    assert "trade_plan_evaluated" in event_types
    assert "trade_plan_ready" in event_types
    assert app_status["operator_console"]["trade_plan_tracking"]["status_after"] == "ready"
