"""Factory helpers for selecting runtime providers from config."""

from __future__ import annotations

from kade.integrations.llm import LLMProvider, MockLLMProvider, OllamaLLMProvider
from kade.integrations.marketdata import AlpacaMarketDataProvider, MarketDataProvider, MockMarketDataProvider
from kade.integrations.options_data import AlpacaOptionsDataProvider, MockOptionsDataProvider, OptionsDataProvider
from kade.integrations.stt import MockSTTProvider, STTProvider, WhisperSTTProvider
from kade.integrations.tts import KokoroTTSProvider, TTSProvider
from kade.integrations.wakeword import MockWakeWordDetector, PorcupineWakeWordDetector, WakeWordDetector


def _use_mock(provider_name: str, cfg: dict[str, object]) -> bool:
    fallback = str(cfg.get("provider_fallback", "mock"))
    return provider_name == "mock" or fallback == "mock"


def resolve_runtime_provider_routes(runtime_cfg: dict[str, object]) -> dict[str, str]:
    """Resolve responsibility-specific provider routing with legacy fallbacks."""

    return {
        "runtime_market_loop_provider": str(runtime_cfg.get("runtime_market_loop_provider", runtime_cfg.get("market_data_provider", "mock"))),
        "historical_data_provider": str(runtime_cfg.get("historical_data_provider", runtime_cfg.get("market_data_provider", "mock"))),
        "market_intelligence_provider": str(runtime_cfg.get("market_intelligence_provider", "alpaca")),
        "options_runtime_provider": str(runtime_cfg.get("options_runtime_provider", runtime_cfg.get("options_data_provider", "mock"))),
    }


def build_market_data_provider(
    runtime_cfg: dict[str, object], route_key: str = "runtime_market_loop_provider", allow_mock_fallback: bool = True
) -> MarketDataProvider:
    routes = resolve_runtime_provider_routes(runtime_cfg)
    provider_name = str(routes.get(route_key, "mock"))
    backends = dict(runtime_cfg.get("market_data_backends", {}))
    if provider_name == "alpaca":
        provider = AlpacaMarketDataProvider(dict(backends.get("alpaca", {})))
        if allow_mock_fallback and provider.health_snapshot(active=True).state != "ready" and provider.mock_on_unavailable:
            return MockMarketDataProvider()
        return provider
    return MockMarketDataProvider()


def build_options_data_provider(runtime_cfg: dict[str, object], route_key: str = "options_runtime_provider") -> OptionsDataProvider:
    routes = resolve_runtime_provider_routes(runtime_cfg)
    provider_name = str(routes.get(route_key, "mock"))
    backends = dict(runtime_cfg.get("options_data_backends", {}))
    if provider_name in {"alpaca", "alpaca_options"}:
        provider = AlpacaOptionsDataProvider(dict(backends.get("alpaca", {})))
        if provider.health_snapshot(active=True).state != "ready" and provider.mock_on_unavailable:
            return MockOptionsDataProvider()
        return provider
    return MockOptionsDataProvider()


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


def build_llm_provider(llm_cfg: dict[str, object]) -> LLMProvider:
    provider_name = str(llm_cfg.get("provider", "mock"))
    providers = dict(llm_cfg.get("providers", {}))
    if provider_name == "ollama":
        return OllamaLLMProvider(dict(providers.get("ollama", {})))
    return MockLLMProvider(dict(providers.get("mock", {})))
