from __future__ import annotations

from kade.integrations.diagnostics import ProviderDiagnostics
from kade.integrations.providers import build_market_data_provider, resolve_runtime_provider_routes
from kade.main import bootstrap_config
from kade.market.intelligence.service import MarketIntelligenceService
from kade.runtime.bootstrap import print_runtime_summary
from kade.runtime.configuration import apply_runtime_env_overrides


def test_hybrid_provider_config_defaults_load_cleanly() -> None:
    cfg = bootstrap_config()
    providers = cfg["execution.yaml"]["providers"]
    routes = resolve_runtime_provider_routes(providers)

    assert routes["runtime_market_loop_provider"] == "mock"
    assert routes["historical_data_provider"] == "alpaca"
    assert routes["market_intelligence_provider"] == "alpaca"
    assert routes["options_runtime_provider"] == "mock"


def test_runtime_loop_uses_mock_while_history_uses_alpaca_route() -> None:
    runtime_cfg = {
        "runtime_market_loop_provider": "mock",
        "historical_data_provider": "alpaca",
        "market_data_backends": {
            "alpaca": {"enabled": True, "api_key": "k", "secret_key": "s", "mock_on_unavailable": True}
        },
    }

    loop_provider = build_market_data_provider(runtime_cfg, route_key="runtime_market_loop_provider")
    history_provider = build_market_data_provider(runtime_cfg, route_key="historical_data_provider")

    assert loop_provider.provider_name == "mock_alpaca"
    assert history_provider.provider_name == "alpaca"


def test_market_intelligence_route_stays_alpaca_while_runtime_is_mock() -> None:
    routes = resolve_runtime_provider_routes(
        {
            "runtime_market_loop_provider": "mock",
            "market_intelligence_provider": "alpaca",
        }
    )

    service = MarketIntelligenceService(
        {
            "sources": {"clock": False, "calendar": False, "news": False, "movers": False, "earnings": False},
            "alpaca": {"enabled": True, "api_key": "key", "secret_key": "secret"},
        }
    )

    assert routes["runtime_market_loop_provider"] == "mock"
    assert routes["market_intelligence_provider"] == "alpaca"
    assert service.source.health_snapshot(active=True).provider_name == "alpaca"


def test_runtime_summary_prints_hybrid_routing_diagnostics(capsys) -> None:
    print_runtime_summary(
        dashboard_state={"card_count": 1, "radar": {"queue": []}, "plans": {"active": []}, "memory": {"recent": []}, "advisor": {"by_symbol": {}}},
        session_state={"day_key": "2026-01-01", "trades_today": 0},
        history_payload={"radar": [], "advisor": [], "execution": []},
        provider_routes={
            "runtime_market_loop_provider": "mock",
            "historical_data_provider": "alpaca",
            "market_intelligence_provider": "alpaca",
            "options_runtime_provider": "mock",
        },
    )

    output = capsys.readouterr().out
    assert "runtime market loop provider = mock" in output
    assert "historical data provider = alpaca" in output
    assert "market intelligence provider = alpaca" in output
    assert "options runtime provider = mock" in output


def test_env_overrides_support_hybrid_provider_routing() -> None:
    cfg = apply_runtime_env_overrides(
        {"execution.yaml": {"providers": {}}},
        {
            "KADE_RUNTIME_MARKET_LOOP_PROVIDER": "mock",
            "KADE_HISTORICAL_DATA_PROVIDER": "alpaca",
            "KADE_MARKET_INTELLIGENCE_PROVIDER": "alpaca",
            "KADE_OPTIONS_RUNTIME_PROVIDER": "mock",
        },
    )

    providers = cfg["execution.yaml"]["providers"]
    assert providers["runtime_market_loop_provider"] == "mock"
    assert providers["historical_data_provider"] == "alpaca"
    assert providers["market_intelligence_provider"] == "alpaca"
    assert providers["options_runtime_provider"] == "mock"


def test_diagnostics_shape_includes_hybrid_boundaries() -> None:
    report = ProviderDiagnostics().evaluate(
        {
            "runtime_market_loop": build_market_data_provider({"runtime_market_loop_provider": "mock"}, route_key="runtime_market_loop_provider").health_snapshot(active=True),
            "historical_data": build_market_data_provider({"historical_data_provider": "mock"}, route_key="historical_data_provider").health_snapshot(active=True),
        }
    )

    assert "runtime_market_loop" in report["providers"]
    assert "historical_data" in report["providers"]
    assert report["ready"] is True
