import yaml

from kade.execution.models import OrderRequest
from kade.execution.paper import PaperExecutionEngine
from kade.integrations.diagnostics import ProviderDiagnostics
from kade.integrations.providers import build_market_data_provider, build_options_data_provider
from kade.integrations.stt import WhisperSTTProvider
from kade.integrations.tts import KokoroTTSProvider
from kade.integrations.wakeword import PorcupineWakeWordDetector


def test_market_data_provider_selection_and_fallback() -> None:
    cfg = {
        "market_data_provider": "alpaca",
        "market_data_backends": {"alpaca": {"enabled": True, "api_key": "", "secret_key": "", "mock_on_unavailable": True}},
    }
    provider = build_market_data_provider(cfg)

    assert provider.provider_name == "mock_alpaca"
    bars = provider.get_bars("NVDA", "1m", 3)
    assert len(bars) == 3


def test_options_data_provider_selection_and_fallback() -> None:
    cfg = {
        "options_data_provider": "alpaca",
        "options_data_backends": {"alpaca": {"enabled": True, "supported": False, "mock_on_unavailable": True}},
    }
    provider = build_options_data_provider(cfg)

    assert provider.provider_name == "mock_chain"
    chain = provider.get_option_chain("NVDA", 100.0)
    assert chain


def test_provider_diagnostics_report_all_boundaries() -> None:
    checks = {
        "market_data": build_market_data_provider({}).health_snapshot(active=True),
        "options_data": build_options_data_provider({}).health_snapshot(active=True),
        "stt": WhisperSTTProvider({"enabled": False, "runtime_mode": "deterministic_text"}).health_snapshot(active=False),
        "wakeword": PorcupineWakeWordDetector({"enabled": True, "access_key": ""}).health_snapshot(active=False),
        "tts": KokoroTTSProvider({"mock_synthesis": True}).health_snapshot(active=False),
    }
    report = ProviderDiagnostics(policy="warn_on_degraded").evaluate(checks)

    assert set(report["providers"].keys()) == {"market_data", "options_data", "stt", "wakeword", "tts"}
    assert "wakeword" in report["degraded"]


def test_paper_execution_contains_lifecycle_snapshots() -> None:
    cfg = yaml.safe_load(open("kade/config/execution.yaml", "r", encoding="utf-8"))["execution"]
    engine = PaperExecutionEngine(cfg)
    result = engine.stage_order(
        OrderRequest("NVDA", "NVDA-C-100", 2, "buy", 2.0, "paper", "limit"),
        trades_today=0,
        daily_realized_pnl=0.0,
        confirm=True,
    )

    assert result.status == "partially_filled"
    assert result.lifecycle["state"] == "partially_filled"
    assert result.nudged_limit_price is not None
    assert any(event["to_state"] == "submitted" for event in result.lifecycle["events"])
    assert any(event["to_state"] == "partially_filled" for event in result.lifecycle["events"])


def test_text_first_defaults_preserved() -> None:
    cfg = yaml.safe_load(open("kade/config/voice.yaml", "r", encoding="utf-8"))["voice"]
    assert cfg["runtime_mode"] == "text_first"
    assert cfg["voice_runtime_enabled"] is False
