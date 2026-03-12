from datetime import datetime, timezone

from kade.dashboard.app import create_app_status
from kade.review import ReviewMetricsAggregator, TradeReviewAnalyzer, TradeReviewContext
from kade.runtime.interaction import InteractionRuntimeState
from kade.tests.test_phase8_interaction import _interaction


def _plan(**kwargs) -> dict[str, object]:
    base = {
        "plan_id": "plan-NVDA-1",
        "symbol": "NVDA",
        "direction": "put",
        "status": "cancelled",
        "risk_posture": "watch_only",
        "execution_checklist": ["align", "confirm", "size"],
        "confidence_label": "high",
        "trap_risk": "low",
        "market_alignment": "aligned",
        "stance": "cautious",
        "target_plausibility": "possible",
        "linked_target_move_board": {"setup_tags": ["trend_continuation"]},
    }
    base.update(kwargs)
    return base


def _ctx(plan: dict[str, object], snapshots: list[dict[str, object]], **kwargs) -> TradeReviewContext:
    payload = {
        "plan": plan,
        "tracking_snapshots": snapshots,
        "realized_outcome": kwargs.get("realized_outcome", {}),
        "execution_state": kwargs.get("execution_state"),
        "final_status": kwargs.get("final_status"),
        "now_iso": "2026-01-01T00:00:00+00:00",
    }
    return TradeReviewContext(**payload)


def test_well_executed_review_generation() -> None:
    analyzer = TradeReviewAnalyzer({"lesson_limit": 4, "discipline": {"conservative_postures": ["watch_only"], "min_checklist_adherence_for_followed": 0.6}})
    context = _ctx(
        _plan(status="exited", risk_posture="full"),
        [{"plan_id": "plan-NVDA-1", "trigger_state": "triggered", "invalidation_state": "valid", "staleness_state": "fresh", "posture_state": "neutral", "status_after": "exited", "actions": []}],
        realized_outcome={"target_hit": True, "realized_pnl": 120.0, "checklist_completed": 3},
        final_status="exited",
    )

    review = analyzer.review(context)
    assert review.review_label == "well_executed"
    assert review.discipline_label == "disciplined"
    assert review.plan_followed is True


def test_invalidation_ignored_detection() -> None:
    analyzer = TradeReviewAnalyzer({"discipline": {"conservative_postures": ["watch_only"]}})
    context = _ctx(
        _plan(status="active"),
        [{"plan_id": "plan-NVDA-1", "invalidation_state": "hard_invalidated", "staleness_state": "fresh", "posture_state": "neutral", "status_after": "active", "actions": []}],
        final_status="active",
    )

    review = analyzer.review(context)
    assert review.discipline_label == "invalidation_ignored"
    assert review.invalidation_respected is False


def test_posture_respected_and_not_respected_cases() -> None:
    analyzer = TradeReviewAnalyzer({"discipline": {"conservative_postures": ["watch_only"]}})
    respected = analyzer.review(
        _ctx(
            _plan(status="cancelled", risk_posture="watch_only"),
            [{"plan_id": "plan-NVDA-1", "invalidation_state": "valid", "staleness_state": "fresh", "posture_state": "neutral", "status_after": "cancelled", "actions": []}],
            execution_state={"lifecycle": {"state": "staged"}},
            final_status="cancelled",
        )
    )
    not_respected = analyzer.review(
        _ctx(
            _plan(status="active", risk_posture="watch_only"),
            [{"plan_id": "plan-NVDA-1", "invalidation_state": "valid", "staleness_state": "fresh", "posture_state": "posture_not_respected", "status_after": "active", "actions": []}],
            execution_state={"lifecycle": {"state": "submitted"}},
            final_status="active",
        )
    )

    assert respected.posture_respected is True
    assert not_respected.posture_respected is False
    assert not_respected.discipline_label == "posture_not_respected"


def test_stale_managed_correctly_case() -> None:
    analyzer = TradeReviewAnalyzer({})
    review = analyzer.review(
        _ctx(
            _plan(status="cancelled"),
            [{"plan_id": "plan-NVDA-1", "invalidation_state": "valid", "staleness_state": "stale", "posture_state": "neutral", "status_after": "cancelled", "actions": ["de_risk_then_cancel"]}],
            final_status="cancelled",
        )
    )
    assert review.outcome_label == "cancelled_correctly"
    assert review.review_label in {"cancelled_correctly", "stale_but_managed"}


def test_cancelled_correctly_case() -> None:
    analyzer = TradeReviewAnalyzer({})
    review = analyzer.review(
        _ctx(
            _plan(status="cancelled"),
            [{"plan_id": "plan-NVDA-1", "invalidation_state": "hard_invalidated", "staleness_state": "fresh", "posture_state": "neutral", "status_after": "cancelled", "actions": []}],
            final_status="cancelled",
        )
    )
    assert review.review_label == "cancelled_correctly"


def test_deterministic_repeatability() -> None:
    analyzer = TradeReviewAnalyzer({})
    context = _ctx(
        _plan(status="cancelled"),
        [{"plan_id": "plan-NVDA-1", "invalidation_state": "valid", "staleness_state": "fresh", "posture_state": "neutral", "status_after": "cancelled", "actions": []}],
        final_status="cancelled",
    )
    one = analyzer.review(context)
    two = analyzer.review(context)

    assert one.review_label == two.review_label
    assert one.summary == two.summary
    assert one.metrics == two.metrics


def test_runtime_payload_shape_timeline_and_operator_console() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    interaction = _interaction(state)
    interaction.trade_review_handler = lambda payload: {
        "latest_review": {
            "plan_id": payload.get("plan_id", "plan-NVDA-1"),
            "symbol": "NVDA",
            "final_status": "cancelled",
            "review_label": "cancelled_correctly",
            "discipline_label": "disciplined",
            "outcome_label": "cancelled_correctly",
            "summary": "Review for NVDA: cancelled correctly.",
            "strengths": ["Invalidation policy respected."],
            "mistakes": [],
            "lessons": ["Standing down is valid."],
            "reviewed_at": "2026-01-01T00:00:00+00:00",
        },
        "metrics_summary": {"review_count": 1, "discipline_distribution": {"disciplined": 1}, "review_label_distribution": {"cancelled_correctly": 1}},
    }

    response = interaction.submit_trade_review_request({"plan_id": "plan-NVDA-1"}, now=datetime.now(timezone.utc))
    payload = interaction.dashboard_payload()
    app_status = create_app_status(voice_payload=payload)

    assert response["intent"] == "trade_review"
    assert payload["trade_review"]["latest_review"]["plan_id"] == "plan-NVDA-1"
    event_types = [event["event_type"] for event in payload["timeline"]["events"]]
    assert "trade_review_generated" in event_types
    assert "review_metrics_updated" in event_types
    assert app_status["operator_console"]["trade_review"]["latest_review"]["review_label"] == "cancelled_correctly"


def test_aggregate_metrics_rollup() -> None:
    aggregator = ReviewMetricsAggregator({"history_limit": 120})
    reviews = [
        {
            "symbol": "NVDA",
            "direction": "put",
            "review_label": "well_executed",
            "discipline_label": "disciplined",
            "invalidation_respected": True,
            "posture_respected": True,
            "final_status": "exited",
            "metrics": {"cancellation_correctness": True, "stale_respected": True},
            "plan": _plan(status="exited"),
        },
        {
            "symbol": "AAPL",
            "direction": "call",
            "review_label": "drifted_from_plan",
            "discipline_label": "posture_not_respected",
            "invalidation_respected": True,
            "posture_respected": False,
            "final_status": "cancelled",
            "metrics": {"cancellation_correctness": False, "stale_respected": False},
            "plan": _plan(plan_id="plan-AAPL-1", symbol="AAPL", direction="call", status="cancelled"),
        },
    ]
    snap = aggregator.build_snapshot(reviews, now_iso="2026-01-01T00:00:00+00:00")

    assert snap.review_count == 2
    assert snap.discipline_distribution["disciplined"] == 1
    assert snap.review_label_distribution["drifted_from_plan"] == 1
    assert snap.invalidation_respected_rate == 1.0
    assert snap.posture_respected_rate == 0.5
