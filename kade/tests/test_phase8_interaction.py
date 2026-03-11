from datetime import datetime

from kade.execution.lifecycle import ExecutionLifecycle
from kade.integrations.providers import build_stt_provider, build_tts_provider, build_wakeword_provider
from kade.integrations.stt import MockSTTProvider, WhisperSTTProvider
from kade.integrations.wakeword import MockWakeWordDetector, PorcupineWakeWordDetector
from kade.runtime.interaction import InteractionOrchestrator, InteractionRuntimeState
from kade.voice.formatter import SpokenResponseFormatter
from kade.voice.models import VoiceSessionState
from kade.voice.orchestrator import VoiceOrchestrator
from kade.voice.router import VoiceCommandRouter


def _handlers() -> dict:
    return {
        "switch_mode": lambda mode: {"mode": mode, "summary": f"Mode {mode}"},
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


def _interaction(state: InteractionRuntimeState) -> InteractionOrchestrator:
    voice = VoiceOrchestrator(
        wakeword_detector=build_wakeword_provider({"wakeword_provider": "mock", "wake_word": "Kade"}),
        router=VoiceCommandRouter(handlers=_handlers()),
        formatter=SpokenResponseFormatter(),
        tts_provider=build_tts_provider({"tts_provider": "kokoro", "kokoro": {"voice": "Puck", "mock_synthesis": True}}),
        state=VoiceSessionState(wake_word="Kade"),
        enable_tts=state.tts_enabled,
    )
    return InteractionOrchestrator(voice_orchestrator=voice, stt_provider=MockSTTProvider(), state=state)


def test_text_first_routing_is_default_path() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    result = _interaction(state).submit_text_command("status", now=datetime.utcnow())

    assert result["intent"] == "status"
    assert result["tts"]["provider"] == "disabled"


def test_voice_disabled_feature_flags_block_voice_processing() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )

    assert _interaction(state).process_voice_sample("Kade status") is None


def test_provider_boundaries_select_mock_or_real_backends() -> None:
    mock_cfg = {"wakeword_provider": "mock", "stt_provider": "mock", "tts_provider": "kokoro"}
    real_cfg = {
        "wakeword_provider": "porcupine",
        "stt_provider": "whisper",
        "wakeword_backends": {"porcupine": {"keyword": "Kade", "enabled": False}},
        "stt_backends": {"whisper": {"model": "tiny.en", "enabled": False}},
    }

    assert isinstance(build_wakeword_provider(mock_cfg), MockWakeWordDetector)
    assert isinstance(build_stt_provider(mock_cfg), MockSTTProvider)
    assert isinstance(build_wakeword_provider(real_cfg), PorcupineWakeWordDetector)
    assert isinstance(build_stt_provider(real_cfg), WhisperSTTProvider)


def test_execution_lifecycle_transitions_are_deterministic() -> None:
    lifecycle = ExecutionLifecycle()

    assert lifecycle.transition("confirmed", "user confirmed")
    assert lifecycle.transition("submitted", "sent to broker")
    assert lifecycle.transition("partially_filled", "partial")
    assert lifecycle.transition("filled", "completed")
    assert lifecycle.state == "filled"
    assert lifecycle.transition("cancelled", "should fail") is False


def test_dashboard_payload_tracks_typed_command_and_latest_result() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    interaction = _interaction(state)
    interaction.submit_text_command("what was i watching", now=datetime.utcnow())
    payload = interaction.dashboard_payload()

    assert payload["current_typed_command"] == "what was i watching"
    assert payload["latest_command_result"]["intent"] == "memory_watchlist"
    assert payload["runtime_mode"] == "text_first"
