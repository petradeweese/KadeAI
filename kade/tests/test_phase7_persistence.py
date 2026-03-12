from datetime import datetime, timedelta

from kade.brain.memory import ConversationMemory
from kade.brain.plans import SessionPlanTracker
from kade.storage import ExecutionStore, MemoryStore, PlanStore, RadarStore, SessionStore, rollover_session
from kade.utils.time import utc_now, utc_now_iso

BRAIN_CONFIG = {
    "memory": {
        "recent_intents_limit": 2,
        "recent_responses_limit": 2,
        "structured_notes_limit": 2,
    },
    "plans": {"expiration_minutes": 100},
}


def test_memory_persistence_roundtrip(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    memory = ConversationMemory(BRAIN_CONFIG)
    memory.record_user_intent("watch NVDA", symbol="NVDA")
    memory.record_kade_response("copy", symbol="NVDA")
    memory.add_structured_note("note", symbol="NVDA", linked_plan_id="p1")

    store.save_memory(memory.snapshot(limit=20))

    restored = ConversationMemory(BRAIN_CONFIG)
    restored.restore(store.load_memory())
    snap = restored.snapshot(limit=10)

    assert len(snap["intents"]) == 1
    assert len(snap["responses"]) == 1
    assert snap["notes"][0]["metadata"]["linked_plan_id"] == "p1"


def test_plan_persistence_roundtrip(tmp_path) -> None:
    store = PlanStore(tmp_path)
    tracker = SessionPlanTracker(BRAIN_CONFIG)
    plan = tracker.create_plan("NVDA", "long", "trigger", "exit", 10, "invalidate")
    tracker.update_status(plan.plan_id, "triggered", reason="radar")
    tracker.add_note(plan.plan_id, "still valid")
    store.save_plans(tracker.persistence_payload())

    restored = SessionPlanTracker(BRAIN_CONFIG)
    restored.restore(store.load_plans())

    assert restored.plans[plan.plan_id].status == "triggered"
    assert restored.plans[plan.plan_id].notes[-1] == "still valid"
    assert restored.snapshot()["events"][0]["reason"] == "radar"


def test_history_store_retains_and_loads(tmp_path) -> None:
    radar_store = RadarStore(tmp_path)
    execution_store = ExecutionStore(tmp_path)

    radar_events = [{"event_type": "heads_up", "symbol": "NVDA", "timestamp": utc_now_iso()}]
    execution_events = [{"event_type": "paper_order_request", "symbol": "NVDA", "timestamp": utc_now_iso()}]
    radar_store.save_events(radar_events)
    execution_store.save_events(execution_events)

    assert radar_store.load_events()[0]["event_type"] == "heads_up"
    assert execution_store.load_events()[0]["event_type"] == "paper_order_request"


def test_session_rollover_resets_daily_state() -> None:
    payload = {
        "day_key": (utc_now().date() - timedelta(days=1)).isoformat(),
        "trades_today": 4,
        "daily_realized_pnl": 100.0,
        "done_for_day": True,
        "recent_voice_events": [{"intent": "status"}],
    }
    rolled = rollover_session(payload, now=utc_now())

    assert rolled["trades_today"] == 0
    assert rolled["daily_realized_pnl"] == 0.0
    assert rolled["done_for_day"] is False
    assert rolled["recent_voice_events"] == []


def test_bounded_behavior_after_reload(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    payload = {
        "intents": [
            {"item_id": "i1", "item_type": "user_intent", "symbol": "A", "content": "1", "created_at": "2024-01-01T00:00:00", "metadata": {}},
            {"item_id": "i2", "item_type": "user_intent", "symbol": "B", "content": "2", "created_at": "2024-01-01T00:00:01", "metadata": {}},
            {"item_id": "i3", "item_type": "user_intent", "symbol": "C", "content": "3", "created_at": "2024-01-01T00:00:02", "metadata": {}},
        ],
        "responses": [],
        "notes": [],
    }
    store.save_memory(payload)

    restored = ConversationMemory(BRAIN_CONFIG)
    restored.restore(store.load_memory())

    assert [item.item_id for item in restored.recent_intents] == ["i2", "i3"]


def test_missing_files_are_graceful(tmp_path) -> None:
    assert MemoryStore(tmp_path).load_memory() == {"intents": [], "responses": [], "notes": []}
    assert PlanStore(tmp_path).load_plans() == {"plans": [], "events": []}
    assert RadarStore(tmp_path).load_events() == []
    assert ExecutionStore(tmp_path).load_events() == []
    session = SessionStore(tmp_path).load_session()
    assert session["trades_today"] == 0

from kade.runtime.persistence import RuntimePersistence


def test_runtime_persistence_bounded_history_after_reload(tmp_path) -> None:
    persistence = RuntimePersistence.from_config({"root_dir": str(tmp_path), "history": {"advisor_limit": 2}}, logger=None)
    session = {"advisor_history": [{"i": 1}, {"i": 2}, {"i": 3}]}

    bounded = persistence.persist_advisor_history(session["advisor_history"], session)

    assert len(bounded) == 2
    assert session["advisor_history"] == [{"i": 2}, {"i": 3}]


def test_runtime_persistence_compat_with_empty_or_partial_session(tmp_path) -> None:
    persistence = RuntimePersistence.from_config({"root_dir": str(tmp_path), "session": {}}, logger=None)
    session = {}

    persistence.retain_recent_commands(session)
    persistence.retain_recent_voice_events(session)
    persistence.retain_provider_health_history(session)

    assert session["recent_command_history"] == []
    assert session["recent_voice_events"] == []
    assert session["provider_health_history"] == []
