from datetime import datetime, timedelta

from kade.integrations.stt.mock import MockSTTProvider
from kade.integrations.tts.kokoro import KokoroTTSProvider
from kade.integrations.wakeword.mock import MockWakeWordDetector
from kade.voice.formatter import SpokenResponseFormatter
from kade.voice.models import Transcript, VoiceSessionState, WakeWordEvent
from kade.voice.orchestrator import VoiceOrchestrator
from kade.voice.router import VoiceCommandRouter


def _build_handlers() -> dict:
    return {
        "switch_mode": lambda mode: {"mode": mode},
        "done_for_day": lambda: {"summary": "Done-for-day."},
        "emergency_shutdown": lambda: {"summary": "Emergency."},
        "radar": lambda: {"top_symbol": "NVDA", "summary": "Momentum setup."},
        "status": lambda: {"summary": "System stable."},
        "market_overview": lambda: {"summary": "Market mixed."},
        "memory_watchlist": lambda: {"watching": ["NVDA", "TSLA"]},
        "symbol_status": lambda symbol: {"summary": f"{symbol} bullish."},
        "symbol_opinion": lambda symbol: {"summary": f"{symbol} looks constructive."},
        "fallback": lambda mode, transcript: {"summary": f"Unhandled {transcript}"},
    }


def test_voice_session_state_transitions_and_cooldown() -> None:
    state = VoiceSessionState(cooldown_ms=1000, command_window_ms=2000)
    now = datetime.utcnow()

    assert state.can_accept_wake(now)
    state.open_command_window(now)
    assert state.command_window_active(now + timedelta(milliseconds=1500))

    state.close_command_window(now)
    assert state.wake_state == "passive_listening"
    assert not state.can_accept_wake(now)
    assert state.can_accept_wake(now + timedelta(milliseconds=1200))


def test_router_mode_switch_and_shutdown_commands() -> None:
    router = VoiceCommandRouter(handlers=_build_handlers())

    mode_cmd = router.route("Kade enter analyst mode", "advisor")
    done_cmd = router.route("Kade I'm done for the day", "advisor")
    shutdown_cmd = router.route("Kade emergency shutdown", "advisor")

    assert mode_cmd.mode_after == "analyst"
    assert done_cmd.intent == "done_for_day"
    assert shutdown_cmd.intent == "emergency_shutdown"


def test_spoken_formatter_modes() -> None:
    formatter = SpokenResponseFormatter()
    router = VoiceCommandRouter(handlers=_build_handlers())
    routed = router.route("Kade radar", "advisor")

    advisor = formatter.format(routed, "advisor")
    analyst = formatter.format(routed, "analyst")
    quiet = formatter.format(routed, "quiet")

    assert "Radar top setup" in advisor.text
    assert "Monitoring for confirmation" in analyst.text
    assert quiet.text.count(".") == 1


def test_kokoro_provider_returns_puck_metadata() -> None:
    provider = KokoroTTSProvider({"voice": "Puck", "mock_synthesis": True, "model": "kokoro-v1"})

    output = provider.synthesize("Test response")

    assert output.provider == "kokoro"
    assert output.voice == "Puck"
    assert output.audio_uri and output.audio_uri.startswith("mock://kokoro/puck/")
    assert output.metadata["model"] == "kokoro-v1"


def test_orchestrator_transcript_to_spoken_response_flow() -> None:
    state = VoiceSessionState(wake_word="Kade", current_mode="advisor", command_window_ms=3000)
    orchestrator = VoiceOrchestrator(
        wakeword_detector=MockWakeWordDetector("Kade"),
        router=VoiceCommandRouter(handlers=_build_handlers()),
        formatter=SpokenResponseFormatter(),
        tts_provider=KokoroTTSProvider({"voice": "Puck", "mock_synthesis": True}),
        state=state,
    )
    now = datetime.utcnow()

    opened = orchestrator.handle_wake_event(WakeWordEvent(wake_word="Kade", detected_at=now, source="developer"))
    transcript = Transcript(text="Kade status", received_at=now, provider="mock")
    result = orchestrator.process_transcript(transcript, now=now + timedelta(milliseconds=100))

    assert opened
    assert result is not None
    assert result["intent"] == "status"
    assert result["tts"]["voice"] == "Puck"
    assert state.last_transcript == "Kade status"
    assert state.last_spoken_response is not None


def test_mock_stt_provider_is_deterministic_for_developer_inputs() -> None:
    provider = MockSTTProvider(seeded_transcripts=["Kade radar"])

    seeded = provider.transcribe("ignored")
    manual = provider.developer_transcript("Kade status")

    assert seeded.text == "Kade radar"
    assert manual.metadata["source"] == "developer"
