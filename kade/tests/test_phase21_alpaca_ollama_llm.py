from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kade.dashboard.app import create_app_status
from kade.integrations.health import ProviderHealth
from kade.integrations.llm import MockLLMProvider, OllamaLLMProvider
from kade.main import bootstrap_config
from kade.runtime.alpaca_smoke import AlpacaSmokeTester
from kade.runtime.configuration import apply_runtime_env_overrides
from kade.runtime.interaction import InteractionRuntimeState
from kade.runtime.narrative import NarrativeSummaryService
from kade.tests.test_phase8_interaction import _interaction


class _FakeMarketData:
    provider_name = "alpaca"

    def get_latest_quote(self, symbol: str):
        raise NotImplementedError

    def get_latest_trade(self, symbol: str):
        raise NotImplementedError

    def get_bars(self, symbol: str, timeframe: str, limit: int = 200):
        raise NotImplementedError

    def get_historical_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime):
        class _Bar:
            def __init__(self, ts: datetime) -> None:
                self.timestamp = ts

        return [_Bar(start + timedelta(minutes=1)), _Bar(end)]

    def health_snapshot(self, active: bool) -> ProviderHealth:
        return ProviderHealth("market_data", "alpaca", "ready", active, {})


class _FakeIntelligenceSource:
    enabled = True
    available = True

    def market_clock(self) -> dict[str, object]:
        return {"is_open": False, "next_open": "2026-01-01T14:30:00+00:00", "next_close": "2026-01-01T21:00:00+00:00"}

    def market_calendar(self, start_date: str, end_date: str) -> list[dict[str, object]]:
        return [{"date": start_date}, {"date": end_date}]

    def news(self, symbols: list[str], limit: int) -> list[dict[str, object]]:
        return [{"headline": f"{symbols[0]} headline"}]

    def screener_movers(self) -> dict[str, list[dict[str, object]]]:
        return {"gainers": [{"symbol": "NVDA"}], "losers": [], "most_actives": [{"symbol": "SPY"}]}


def test_env_backed_alpaca_config_loading(monkeypatch) -> None:
    monkeypatch.setenv("APCA_API_KEY_ID", "env-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "env-secret")
    monkeypatch.setenv("KADE_ALPACA_MARKET_DATA_ENABLED", "true")
    monkeypatch.setenv("KADE_ALPACA_OPTIONS_ENABLED", "true")
    monkeypatch.setenv("KADE_ALPACA_OPTIONS_SUPPORTED", "true")
    monkeypatch.setenv("KADE_ALPACA_MARKET_INTELLIGENCE_ENABLED", "true")

    cfg = bootstrap_config()

    assert cfg["execution.yaml"]["providers"]["market_data_backends"]["alpaca"]["api_key"] == "env-key"
    assert cfg["execution.yaml"]["providers"]["options_data_backends"]["alpaca"]["secret_key"] == "env-secret"
    assert cfg["execution.yaml"]["providers"]["options_data_backends"]["alpaca"]["supported"] is True
    assert cfg["market_intelligence.yaml"]["market_intelligence"]["alpaca"]["enabled"] is True


def test_ollama_provider_falls_back_when_unavailable(monkeypatch) -> None:
    provider = OllamaLLMProvider({"enabled": True, "host": "http://localhost:11434", "model": "llama3.1", "timeout_seconds": 1})
    monkeypatch.setattr(provider, "_request_json", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")))

    health = provider.health_snapshot(active=True)
    generation = provider.generate("test prompt")

    assert health.state == "degraded"
    assert generation.success is False
    assert generation.error == "offline"


def test_mock_llm_provider_is_deterministic() -> None:
    provider = MockLLMProvider({"enabled": True, "model": "mock-narrative"})
    first = provider.generate("Summarize this payload.")
    second = provider.generate("Summarize this payload.")

    assert first.content == second.content
    assert provider.health_snapshot(active=True).state == "mock"


def test_narrative_summary_generation_preserves_deterministic_core() -> None:
    service = NarrativeSummaryService(MockLLMProvider({"enabled": True}), {"narrative_summaries_enabled": True, "allow_trade_logic_override": False})
    payload = {
        "summary": {"headline": "Market posture is mixed."},
        "market_posture": {"posture_label": "mixed"},
        "watchlist_priorities": [{"symbol": "NVDA"}],
    }

    summary = service.summarize("premarket_gameplan", payload)

    assert summary["llm_used"] is True
    assert summary["core_payload_preserved"] is True
    assert summary["allow_trade_logic_override"] is False
    assert "Posture mixed" in summary["deterministic_text"]
    assert payload["market_posture"]["posture_label"] == "mixed"


def test_operator_payload_includes_llm_and_alpaca_sections() -> None:
    payload = create_app_status(
        voice_payload={
            "provider_selection": {"llm": "mock", "market_intelligence": "alpaca"},
            "provider_diagnostics": {
                "providers": {
                    "llm": {"state": "mock", "active": True, "metadata": {"model": "mock-narrative"}},
                    "market_intelligence": {"state": "ready", "active": True, "metadata": {"enabled": True}},
                }
            },
            "llm": {
                "latest_summary": {"summary_type": "market_intelligence", "narrative_text": "Narrative", "llm_used": True},
                "summaries": {"market_intelligence": {"summary_type": "market_intelligence", "narrative_text": "Narrative", "llm_used": True}},
                "narrative_summaries_enabled": True,
                "allow_trade_logic_override": False,
            },
        },
        market_intelligence_payload={"regime": {"regime_label": "trend"}},
        alpaca_smoke_test_payload={"state": "ready", "summary": {"passed": 5, "failed": 0}},
    )

    assert payload["operator_console"]["llm"]["latest_summary"]["summary_type"] == "market_intelligence"
    assert payload["operator_console"]["market_intelligence"]["narrative_summary"]["llm_used"] is True
    assert payload["operator_console"]["alpaca"]["smoke_test"]["state"] == "ready"


def test_runtime_ingests_llm_summary_without_replacing_structured_payload() -> None:
    state = InteractionRuntimeState(
        runtime_mode="text_first",
        voice_runtime_enabled=False,
        text_command_input_enabled=True,
        wakeword_enabled=False,
        stt_enabled=False,
        tts_enabled=False,
    )
    interaction = _interaction(state)
    interaction.ingest_llm_summary(
        {
            "summary_type": "strategy_intelligence",
            "narrative_text": "Narrative summary",
            "deterministic_text": "Deterministic summary",
            "provider_name": "mock",
            "source": "mock",
            "llm_used": True,
        }
    )

    payload = interaction.dashboard_payload()
    event_types = [event["event_type"] for event in interaction.timeline.snapshot()["events"]]

    assert payload["llm"]["latest_summary"]["summary_type"] == "strategy_intelligence"
    assert payload["llm"]["latest_summary"]["deterministic_text"] == "Deterministic summary"
    assert "llm_summary_generated" in event_types


def test_alpaca_smoke_test_returns_structured_diagnostics() -> None:
    tester = AlpacaSmokeTester(_FakeMarketData(), _FakeIntelligenceSource())

    result = tester.run("SPY")

    assert result["state"] == "ready"
    assert result["checks"]["historical_bars_1m"]["count"] == 2
    assert result["checks"]["news"]["count"] == 1
    assert result["summary"]["passed"] == 5


def test_apply_runtime_env_overrides_handles_ollama_and_llm_provider() -> None:
    cfg = apply_runtime_env_overrides(
        {"llm.yaml": {"llm": {"provider": "mock", "providers": {"ollama": {"enabled": False, "host": "http://localhost:11434"}}}}},
        {"KADE_LLM_PROVIDER": "ollama", "KADE_OLLAMA_ENABLED": "true", "KADE_OLLAMA_MODEL": "llama3.1"},
    )

    assert cfg["llm.yaml"]["llm"]["provider"] == "ollama"
    assert cfg["llm.yaml"]["llm"]["providers"]["ollama"]["enabled"] is True
    assert cfg["llm.yaml"]["llm"]["providers"]["ollama"]["model"] == "llama3.1"
