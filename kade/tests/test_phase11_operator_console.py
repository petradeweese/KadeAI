from datetime import datetime, timezone

from kade.dashboard.app import create_app_status
from kade.runtime.interaction import InteractionOrchestrator, InteractionRuntimeState
from kade.runtime.replay import ReplayRuntime
from kade.runtime.timeline import RuntimeTimeline
from kade.tests.test_phase8_interaction import _interaction


def _state() -> InteractionRuntimeState:
    return InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
        command_history_limit=3,
        execution_history_limit=3,
        radar_top_signals_limit=5,
    )


def test_command_panel_history_and_replay() -> None:
    interaction = _interaction(_state())
    now = datetime.now(timezone.utc)
    interaction.submit_text_command("status", now=now)
    interaction.submit_text_command("radar", now=now)

    history = interaction.command_history_viewer()
    assert history["count"] == 2
    assert history["history"][-1]["command"] == "radar"

    last = interaction.replay_last_command()
    assert last is not None
    assert last["command"] == "radar"


def test_timeline_event_creation() -> None:
    timeline = RuntimeTimeline(retention=2)
    timeline.add_event("command_received", "2026-01-01T00:00:00+00:00", {"command": "status"})
    timeline.add_event("intent_routed", "2026-01-01T00:00:01+00:00", {"intent": "status"})
    timeline.add_event("advisor_response", "2026-01-01T00:00:02+00:00", {"text": "ok"})

    snap = timeline.snapshot()
    assert len(snap["events"]) == 2
    assert snap["events"][0]["event_type"] == "intent_routed"


def test_replay_viewer_supports_index_session_and_export(tmp_path) -> None:
    replay = ReplayRuntime(retention_limit=5)
    replay.add_record("status", {"intent": "status", "spoken_text": "ok", "tts": {"provider": "disabled"}}, "text", datetime.now(timezone.utc))

    by_index = replay.replay_command(0)
    assert by_index is not None
    assert by_index["intent"] == "status"
    assert len(replay.replay_session()) == 1

    exported = replay.export_replay_log(str(tmp_path / "replay.json"))
    assert (tmp_path / "replay.json").exists()
    assert exported.endswith("replay.json")


def test_provider_diagnostics_and_operator_console_panels() -> None:
    voice_payload = {
        "runtime_mode": "text_first",
        "command_input_mode": "text_panel",
        "provider_selection": {"market_data": "mock_alpaca", "options_data": "mock_chain", "stt": "mock_stt", "tts": "kokoro", "wakeword": "mock_wakeword"},
        "provider_diagnostics": {
            "providers": {
                "market_data": {"state": "degraded", "active": True, "metadata": {"reason": "missing credentials"}},
                "options_data": {"state": "ready", "active": True, "metadata": {}},
                "stt": {"state": "mock", "active": False, "metadata": {"mode": "deterministic_text"}},
                "tts": {"state": "mock", "active": False, "metadata": {"voice": "Puck"}},
                "wakeword": {"state": "ready", "active": False, "metadata": {}},
            }
        },
        "latest_radar_signals": [{"symbol": "NVDA", "setup": "trend_continuation", "confidence": 0.8, "timestamp": "2026-01-01T00:00:00+00:00"}],
        "execution_monitor": {"lifecycle_history": [{"symbol": "NVDA", "status": "partially_filled", "lifecycle_state": "partially_filled", "contracts": 2, "fill_price": 2.12, "timestamp": "2026-01-01T00:00:01+00:00"}]},
        "timeline": {"retention": 200, "events": [{"event_type": "command_received", "timestamp": "2026-01-01T00:00:00+00:00", "payload": {}}]},
        "trade_idea_opinion": {"symbol": "NVDA", "stance": "agree", "target_plausibility": "possible_but_stretched"},
    }
    payload = create_app_status(voice_payload=voice_payload, session_payload={"trades_today": 1})
    operator = payload["operator_console"]

    assert operator["providers"]["market_data_provider"]["state"] == "degraded"
    assert operator["radar"]["top_signals"][0]["symbol"] == "NVDA"
    assert operator["execution"]["latest_lifecycle"][0]["symbol"] == "NVDA"
    assert operator["trade_idea_opinion"]["symbol"] == "NVDA"


def test_radar_and_execution_monitor_payload_structure() -> None:
    interaction: InteractionOrchestrator = _interaction(_state())
    interaction.ingest_radar_signals(
        [{"symbol": "NVDA", "setup": "breakout", "confidence": 0.9, "timeframe": "5m", "notes": "vwap reclaim", "timestamp": "2026-01-01T00:00:00+00:00", "supporting_indicators": ["vwap", "rvol"]}]
    )
    interaction.ingest_execution_events(
        [{"symbol": "NVDA", "option_symbol": "NVDA-C-100", "status": "staged", "lifecycle_state": "confirmed", "contracts": 2, "filled_contracts": 0, "avg_fill_price": None, "timestamp": "2026-01-01T00:00:01+00:00"}]
    )

    payload = interaction.dashboard_payload()
    assert payload["latest_radar_signals"][0]["supporting_indicators"] == ["vwap", "rvol"]
    assert payload["execution_monitor"]["lifecycle_history"][0]["option_symbol"] == "NVDA-C-100"
