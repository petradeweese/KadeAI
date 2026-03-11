from datetime import datetime, timedelta

from kade.brain.memory import ConversationMemory
from kade.brain.plans import SessionPlanTracker
from kade.brain.reasoning import AdvisorReasoningEngine
from kade.brain.style_profile import StyleProfileManager
from kade.market.context_intelligence import MarketContextIntelligence
from kade.market.structure import TickerState
from kade.utils.time import utc_now

BRAIN_CONFIG = {
    "memory": {
        "recent_intents_limit": 3,
        "recent_responses_limit": 3,
        "structured_notes_limit": 3,
    },
    "plans": {"expiration_minutes": 10},
    "style_profile": {
        "defaults": {
            "profile_name": "petra",
            "tone": "calm_analytical",
            "verbosity": "balanced",
            "directness": "direct",
            "common_phrases": ["Let it confirm"],
        }
    },
}

MARKET_CONTEXT_CONFIG = {
    "regime": {
        "baseline_strong_slope": 0.20,
        "baseline_range_slope_max": 0.04,
        "momentum_slope_min": 0.08,
        "trend_slope_min": 0.05,
        "range_slope_max": 0.03,
    },
    "breadth": {
        "exclude_symbols": ["QQQ", "SPY"],
        "bullish_ratio_min": 0.60,
        "bearish_ratio_max": 0.40,
    },
    "trap_detection": {
        "weak_vwap_break_distance_max": 0.0015,
        "failed_reclaim_buffer": 0.001,
        "low_volume_breakout_acceleration_max": 1.05,
        "moderate_signal_count_min": 1,
        "high_signal_count_min": 2,
    },
}


def test_memory_stores_and_recalls_by_symbol() -> None:
    memory = ConversationMemory(BRAIN_CONFIG)
    memory.record_user_intent("Watching NVDA puts on VWAP break", symbol="NVDA")
    memory.record_kade_response("Noted. Waiting for confirmation.", symbol="NVDA")
    memory.add_structured_note("Plan linked", symbol="NVDA", linked_plan_id="p1")
    memory.record_user_intent("What about TSLA?", symbol="TSLA")

    nvda_items = memory.recall_for_symbol("NVDA", limit=5)

    assert len(nvda_items) == 3
    assert all(item.symbol in {"NVDA", None} for item in nvda_items)


def test_plan_tracker_create_update_and_cleanup() -> None:
    tracker = SessionPlanTracker(BRAIN_CONFIG)
    plan = tracker.create_plan(
        symbol="NVDA",
        direction="short",
        trigger_condition="VWAP break",
        target_exit_idea="scale into flush",
        max_hold_minutes=20,
        invalidation_concept="VWAP reclaim",
    )

    tracker.update_status(plan.plan_id, "triggered")
    tracker.update_status(plan.plan_id, "active")
    tracker.update_status(plan.plan_id, "exited")

    assert tracker.plans[plan.plan_id].status == "exited"

    tracker.plans[plan.plan_id].updated_at = utc_now() - timedelta(minutes=30)
    removed = tracker.cleanup_expired()
    assert plan.plan_id in removed


def test_reasoning_generates_deterministic_stance_and_summary() -> None:
    memory = ConversationMemory(BRAIN_CONFIG)
    tracker = SessionPlanTracker(BRAIN_CONFIG)
    plan = tracker.create_plan(
        symbol="NVDA",
        direction="long",
        trigger_condition="Hold above VWAP",
        target_exit_idea="trend extension",
        max_hold_minutes=30,
        invalidation_concept="lose VWAP",
    )
    memory.record_user_intent("Can I take NVDA calls?", symbol="NVDA")

    state = TickerState(
        symbol="NVDA",
        trend="bullish",
        momentum="strong_up",
        qqq_confirmation="confirmed_breadth_aligned",
        regime="trend",
        trap_risk="low",
    )
    engine = AdvisorReasoningEngine(BRAIN_CONFIG)
    output = engine.build_advice(
        symbol="NVDA",
        ticker_state=state,
        radar_context={"score": 80},
        breadth_context={"bias": "risk_on"},
        active_plans=tracker.active_plans(),
        memory=memory,
        options_plan={"target_contracts": 2},
    )

    assert output.stance == "strong"
    assert "Setup looks strong" in output.summary
    assert output.linked_plan_id == plan.plan_id


def test_reasoning_with_real_context_labels_adds_caution() -> None:
    intel = MarketContextIntelligence(MARKET_CONTEXT_CONFIG)
    states = {
        "QQQ": TickerState(symbol="QQQ", trend="bullish", momentum="up_bias"),
        "SPY": TickerState(symbol="SPY", trend="bullish", momentum="up_bias"),
        "NVDA": TickerState(symbol="NVDA", trend="bullish", momentum="up_bias"),
        "MSFT": TickerState(symbol="MSFT", trend="bearish", momentum="down_bias"),
    }
    breadth = intel.breadth_snapshot(states)
    qqq_confirmation = intel.qqq_confirmation_with_breadth("mixed", breadth.bias)

    state = TickerState(
        symbol="NVDA",
        trend="neutral",
        momentum="mixed",
        qqq_confirmation=qqq_confirmation,
        regime="range",
        trap_risk="moderate",
    )
    output = AdvisorReasoningEngine(BRAIN_CONFIG).build_advice(
        symbol="NVDA",
        ticker_state=state,
        radar_context={"score": 35},
        breadth_context={"bias": breadth.bias},
        active_plans=[],
        memory=ConversationMemory(BRAIN_CONFIG),
        options_plan=None,
    )

    assert breadth.bias == "mixed"
    assert qqq_confirmation == "mixed_breadth"
    assert output.stance == "pass"
    assert any("Breadth is mixed" in reason for reason in output.cautionary_reasons)


def test_style_profile_scaffolding_applies_preferences() -> None:
    manager = StyleProfileManager(BRAIN_CONFIG)
    assert manager.response_guidance()["profile_name"] == "petra"

    manager.active_profile.verbosity = "concise"
    styled = manager.apply_scaffold("Confidence is moderate. Wait for volume.")
    assert styled == "Confidence is moderate"
