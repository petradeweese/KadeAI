"""Factory helpers for selecting voice providers from config."""

from __future__ import annotations

from kade.integrations.stt import MockSTTProvider, STTProvider, WhisperSTTProvider
from kade.integrations.tts import KokoroTTSProvider, TTSProvider
from kade.integrations.wakeword import MockWakeWordDetector, PorcupineWakeWordDetector, WakeWordDetector


def _use_mock(provider_name: str, cfg: dict[str, object]) -> bool:
    fallback = str(cfg.get("provider_fallback", "mock"))
    return provider_name == "mock" or fallback == "mock"


def build_wakeword_provider(voice_cfg: dict[str, object]) -> WakeWordDetector:
    provider_name = str(voice_cfg.get("wakeword_provider", "mock"))
    if provider_name == "porcupine" and not _use_mock(provider_name, voice_cfg):
        backends = dict(voice_cfg.get("wakeword_backends", {}))
        return PorcupineWakeWordDetector(dict(backends.get("porcupine", {})))
    if provider_name == "porcupine":
        backends = dict(voice_cfg.get("wakeword_backends", {}))
        return PorcupineWakeWordDetector(dict(backends.get("porcupine", {})))
    return MockWakeWordDetector(wake_word=str(voice_cfg.get("wake_word", "Kade")))


def build_stt_provider(voice_cfg: dict[str, object]) -> STTProvider:
    provider_name = str(voice_cfg.get("stt_provider", "mock"))
    if provider_name == "whisper":
        backends = dict(voice_cfg.get("stt_backends", {}))
        return WhisperSTTProvider(dict(backends.get("whisper", {})))
    return MockSTTProvider()


def build_tts_provider(voice_cfg: dict[str, object]) -> TTSProvider:
    provider_name = str(voice_cfg.get("tts_provider", "kokoro"))
    if provider_name == "kokoro":
        return KokoroTTSProvider(dict(voice_cfg.get("kokoro", {})))
    return KokoroTTSProvider({"voice": "Puck", "mock_synthesis": True})
