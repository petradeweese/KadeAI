
import yaml

from kade.integrations.stt import WhisperSTTProvider
from kade.integrations.tts import KokoroTTSProvider
from kade.integrations.wakeword import PorcupineWakeWordDetector
from kade.runtime.interaction import InteractionOrchestrator, InteractionRuntimeState
from kade.voice.formatter import SpokenResponseFormatter
from kade.voice.models import VoiceSessionState
from kade.voice.orchestrator import VoiceOrchestrator
from kade.voice.router import VoiceCommandRouter
from kade.utils.time import utc_now


def _interaction() -> InteractionOrchestrator:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    voice = VoiceOrchestrator(
        wakeword_detector=PorcupineWakeWordDetector({"keyword": "Kade", "enabled": False}),
        router=VoiceCommandRouter(
            handlers={
                "switch_mode": lambda mode: {"mode": mode, "summary": mode},
                "done_for_day": lambda: {"summary": "done"},
                "emergency_shutdown": lambda: {"summary": "shutdown"},
                "radar": lambda: {"summary": "radar"},
                "status": lambda: {"summary": "status"},
                "market_overview": lambda: {"summary": "market"},
                "memory_watchlist": lambda: {"watching": ["NVDA"]},
                "symbol_status": lambda symbol: {"summary": symbol},
                "symbol_opinion": lambda symbol: {"summary": symbol},
                "fallback": lambda mode, transcript: {"summary": transcript},
            }
        ),
        formatter=SpokenResponseFormatter(),
        tts_provider=KokoroTTSProvider({"mock_synthesis": True, "artifact_dir": ".kade_storage/test_tts"}),
        state=VoiceSessionState(wake_word="Kade"),
        enable_tts=False,
    )
    return InteractionOrchestrator(
        voice_orchestrator=voice,
        stt_provider=WhisperSTTProvider({"enabled": False, "runtime_mode": "deterministic_text"}),
        state=state,
    )


def test_provider_health_reported_in_dashboard_payload() -> None:
    interaction = _interaction()
    interaction.submit_text_command("status", now=utc_now())
    payload = interaction.dashboard_payload()

    assert payload["provider_health"]["wakeword"]["state"] == "disabled"
    assert payload["provider_health"]["stt"]["state"] == "mock"
    assert payload["provider_health"]["tts"]["state"] == "mock"


def test_text_panel_response_is_structured_with_debug() -> None:
    interaction = _interaction()
    result = interaction.submit_text_panel_command({"command": "what do you think about NVDA", "include_debug": True})

    assert result["intent"] == "symbol_opinion"
    assert "formatted_response" in result
    assert "provider_mode" in result
    assert "debug" in result


def test_replay_debug_returns_recent_records() -> None:
    interaction = _interaction()
    interaction.submit_text_command("status", now=utc_now())
    interaction.submit_text_command("radar", now=utc_now())

    replay_payload = interaction.replay_recent_commands(2)
    assert replay_payload["debug"]["returned"] == 2
    assert replay_payload["replay"][0]["intent"] == "status"


def test_whisper_porcupine_kokoro_readiness_metadata() -> None:
    whisper = WhisperSTTProvider({"enabled": False, "runtime_mode": "deterministic_text", "supports_realtime_audio": False})
    porcupine = PorcupineWakeWordDetector({"enabled": True, "access_key": ""})
    kokoro = KokoroTTSProvider({"mock_synthesis": True, "output_mode": "artifact_uri", "artifact_dir": ".kade_storage/test_tts_meta"})

    assert whisper.health_snapshot(active=False).state == "mock"
    assert porcupine.health_snapshot(active=False).state == "degraded"
    out = kokoro.synthesize("hello")
    assert out.metadata["output_mode"] == "artifact_uri"
    assert "artifact_path" in out.metadata


def test_text_first_defaults_preserved_in_config() -> None:
    cfg = yaml.safe_load(open("kade/config/voice.yaml", "r", encoding="utf-8"))
    voice = cfg["voice"]

    assert voice["runtime_mode"] == "text_first"
    assert voice["voice_runtime_enabled"] is False
    assert voice["text_command_input_enabled"] is True


def test_text_panel_handles_malformed_payloads_and_missing_handlers() -> None:
    interaction = _interaction()

    empty = interaction.submit_text_panel_command({})
    malformed = interaction.submit_text_panel_command({"command": "target_move symbol=NVDA dtes=a,b,1"})

    assert empty["intent"] == "invalid"
    assert "raw_result" in empty
    assert malformed["intent"] == "target_move_scenario_unavailable"
    assert "raw_result" in malformed


def test_repeated_requests_update_latest_state_without_cross_panel_leakage() -> None:
    interaction = _interaction()
    interaction.trade_plan_handler = lambda payload: {"plan_id": payload.get("plan_id", "p1"), "symbol": "NVDA", "status": "watching", "risk_posture": "watch_only"}
    interaction.trade_review_handler = lambda payload: {"latest_review": {"plan_id": payload.get("plan_id", "p1"), "symbol": "NVDA", "summary": "ok"}, "metrics_summary": {"review_count": 1}}

    interaction.submit_trade_plan_request({"plan_id": "p1", "symbol": "NVDA"})
    interaction.submit_trade_plan_request({"plan_id": "p2", "symbol": "AAPL"})
    interaction.submit_trade_review_request({"plan_id": "p1"})

    payload = interaction.dashboard_payload()
    assert payload["trade_plan"]["plan_id"] == "p2"
    assert payload["trade_review"]["latest_review"]["plan_id"] == "p1"
