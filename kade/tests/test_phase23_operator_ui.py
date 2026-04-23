from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

from kade.chat.parser import ChatIntentParser
from kade.ui.api import OperatorBackend
from kade.ui.app import create_server
from kade.ui.workspace import build_workspace_layout, intent_to_workspace_mode, parse_symbol_from_command


def test_ui_server_startup_wiring_and_page_render() -> None:
    server = create_server(host="127.0.0.1", port=0, llm_enabled=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    conn = HTTPConnection(host, port, timeout=3)
    conn.request("GET", "/")
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    server.shutdown()
    server.server_close()

    assert resp.status == 200
    assert "Kade Operator Console" in body
    assert "Kade Assistant" in body
    assert "workspace-mode" in body


def test_dashboard_command_chat_and_history_endpoints() -> None:
    server = create_server(host="127.0.0.1", port=0, llm_enabled=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=3)

    conn.request("GET", "/api/dashboard")
    dashboard = json.loads(conn.getresponse().read().decode("utf-8"))
    assert dashboard["status"] == "running"
    assert dashboard["ui_state"]["active_workspace_mode"] == "overview"

    conn.request("POST", "/api/command", body=json.dumps({"command": "trade_plan symbol=NVDA"}), headers={"Content-Type": "application/json"})
    command_payload = json.loads(conn.getresponse().read().decode("utf-8"))
    assert command_payload["ok"] is True
    assert command_payload["result"]["intent"] == "trade_plan"
    assert command_payload["layout_state"]["active_workspace_mode"] == "trade"
    assert command_payload["layout_state"]["active_symbol"] == "NVDA"

    conn.request("POST", "/api/chat", body=json.dumps({"message": "Show NVDA visually."}), headers={"Content-Type": "application/json"})
    chat_payload = json.loads(conn.getresponse().read().decode("utf-8"))
    assert chat_payload["ok"] is True
    assert chat_payload["interpreted_action"]["intent"] == "visual_explain"
    assert chat_payload["layout_state"]["active_workspace_mode"] == "trade"
    assert chat_payload["layout_state"]["active_symbol"] == "NVDA"

    conn.request("GET", "/api/history")
    history = json.loads(conn.getresponse().read().decode("utf-8"))
    assert len(history["items"]) >= 2

    conn.close()
    server.shutdown()
    server.server_close()


def test_intent_to_workspace_mapping_and_prioritization() -> None:
    assert intent_to_workspace_mode("premarket_gameplan") == "market"
    assert intent_to_workspace_mode("trade_idea") == "trade"
    assert intent_to_workspace_mode("trade_plan_check") == "tracking"
    assert intent_to_workspace_mode("trade_review") == "review"
    assert intent_to_workspace_mode("strategy_analysis") == "analysis"
    assert intent_to_workspace_mode("unknown") == "overview"

    trade_layout = build_workspace_layout("trade", active_symbol="NVDA")
    assert trade_layout.panel_priority_map["visual_explainability"] == 1
    assert trade_layout.panel_priority_map["trade_idea"] == 2
    assert "market_intelligence" in trade_layout.collapsed_panels
    assert "trade_plan" in trade_layout.highlighted_panels


def test_explicit_command_passthrough_parser_fallback_and_symbol_parse() -> None:
    parser = ChatIntentParser()
    parsed = parser.parse("trade_idea symbol=NVDA direction=put")
    assert parsed.intent == "explicit_command"
    assert parsed.payload["command"].startswith("trade_idea")

    fallback = parser.parse("nonsense words with no known intent")
    assert fallback.intent == "status"
    assert fallback.source == "fallback"

    assert parse_symbol_from_command("trade_plan symbol=NVDA direction=put") == "NVDA"
    assert parse_symbol_from_command("status") is None


def test_sparse_payload_and_collapsible_debug_markup_present() -> None:
    backend = OperatorBackend(llm_enabled=False)
    result = backend.chat("what's the market doing this morning?")
    assert result["diagnostics"]["fallback_used"] is False
    assert result["layout_state"]["active_workspace_mode"] == "market"
    dashboard = result["dashboard"]
    assert "operator_console" in dashboard
    assert "collapsed_panels" in dashboard["ui_state"]

    with open("kade/ui/templates/index.html", encoding="utf-8") as handle:
        html = handle.read()
    with open("kade/ui/static/app.js", encoding="utf-8") as handle:
        js = handle.read()

    assert "<details" in html
    assert "applyLayoutState" in js


def test_llm_intent_parse_cannot_override_trade_logic_fields() -> None:
    class _LLM:
        def generate(self, *args, **kwargs):
            from kade.integrations.llm.base import LLMGeneration

            return LLMGeneration(
                provider_name="mock",
                model="x",
                success=True,
                content='{"intent":"trade_idea","symbol":"NVDA","direction":"put","trigger":"invented"}',
                finish_reason="stop",
            )

    backend = OperatorBackend(llm_enabled=False)
    from kade.chat.service import ChatService

    chat = ChatService(backend._runtime, llm_provider=_LLM(), llm_enabled=True)
    interpreted = chat._interpret("Should I consider a put on NVDA within an hour?")
    assert interpreted.intent == "trade_idea"
    assert interpreted.payload == {"symbol": "NVDA", "direction": "put"}


def test_trade_prompt_extracts_symbol_direction_and_horizon() -> None:
    parser = ChatIntentParser()
    parsed = parser.parse("Should I consider a put on NVDA within an hour?")

    assert parsed.intent == "trade_idea"
    assert parsed.payload["symbol"] == "NVDA"
    assert parsed.payload["direction"] == "put"
    assert parsed.payload["horizon_minutes"] == 60


def test_backend_propagates_active_symbol_direction_and_horizon() -> None:
    backend = OperatorBackend(llm_enabled=False)
    result = backend.chat("Should I consider a put on NVDA within an hour?")

    assert result["layout_state"]["active_workspace_mode"] == "trade"
    assert result["layout_state"]["active_symbol"] == "NVDA"
    assert result["layout_state"]["active_direction"] == "put"
    assert result["layout_state"]["active_horizon"] == 60


def test_trade_mode_collapses_secondary_panels_by_default() -> None:
    trade_layout = build_workspace_layout("trade", active_symbol="NVDA")

    for key in ("market_intelligence", "premarket_gameplan", "radar", "movers", "execution_monitor", "timeline", "provider_diagnostics"):
        assert key in trade_layout.collapsed_panels


def test_ui_template_includes_secondary_collapsible_section() -> None:
    with open("kade/ui/templates/index.html", encoding="utf-8") as handle:
        html = handle.read()

    assert "Secondary Panels" in html
    assert "active-direction" in html
    assert "market-context-card" in html
    assert "market-pill" in html




def test_chart_endpoint_and_timeframe_switching_shape() -> None:
    server = create_server(host="127.0.0.1", port=0, llm_enabled=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=3)

    conn.request("GET", "/api/chart?symbol=NVDA&timeframe=1m")
    payload_1m = json.loads(conn.getresponse().read().decode("utf-8"))
    assert payload_1m["symbol"] == "NVDA"
    assert payload_1m["timeframe"] == "1m"
    assert isinstance(payload_1m["bars"], list)
    assert isinstance(payload_1m["overlays"], list)

    conn.request("GET", "/api/chart?symbol=NVDA&timeframe=15m")
    payload_15m = json.loads(conn.getresponse().read().decode("utf-8"))
    assert payload_15m["timeframe"] == "15m"
    assert payload_15m["meta"]["provider"] in {"mock_alpaca", "alpaca"}

    conn.close()
    server.shutdown()
    server.server_close()


def test_visual_explainability_panel_has_polished_sparse_fallback() -> None:
    with open("kade/ui/static/app.js", encoding="utf-8") as handle:
        js = handle.read()

    assert "Chart data unavailable for" in js
    assert "deterministic levels visible and update timing confidence when real bars resume." in js
    assert "tf-btn" in js
    assert "chart-empty" in js


def test_parser_handles_trade_idea_exit_phrasing_and_stopwords() -> None:
    parser = ChatIntentParser()
    parsed = parser.parse("what do you think about a put on NVDA exit of 182.80")

    assert parsed.intent == "trade_idea"
    assert parsed.payload["symbol"] == "NVDA"
    assert parsed.payload["direction"] == "put"
    assert parsed.payload["target"] == 182.8


def test_parser_ignores_greeting_and_filler_words_for_symbol_extraction() -> None:
    parser = ChatIntentParser()
    parsed = parser.parse("hello hi hey kade what do you think about a put on NVDA")

    assert parsed.payload["symbol"] == "NVDA"


def test_parser_keeps_explicit_command_mode_intact() -> None:
    parser = ChatIntentParser()
    parsed = parser.parse("trade_idea symbol=NVDA direction=put target=182.80")

    assert parsed.intent == "explicit_command"


def test_deterministic_trade_idea_reply_is_not_mock_placeholder() -> None:
    backend = OperatorBackend(llm_enabled=False)
    result = backend.chat("what do you think about a put on NVDA exit of 182.80")

    assert "Mock narrative summary" not in result["reply"]
    assert "NVDA" in result["reply"]
    assert "182.80" in result["reply"]


def test_trade_idea_fallback_reply_is_direction_aware() -> None:
    backend = OperatorBackend(llm_enabled=False)

    put_reply = backend.chat("what do you think about a put on NVDA exit of 182.80")["reply"].lower()
    call_reply = backend.chat("what do you think about a call on NVDA exit of 205")["reply"].lower()

    assert "downside" in put_reply
    assert "upside" in call_reply
    assert "conditional setup" in put_reply


def test_chat_transcript_intent_metadata_is_deemphasized_in_auxiliary_meta() -> None:
    with open("kade/ui/static/app.js", encoding="utf-8") as handle:
        js = handle.read()
    with open("kade/ui/templates/index.html", encoding="utf-8") as handle:
        html = handle.read()

    assert "chat-meta" in html
    assert "Action:" not in js
    assert "addMessage('kade', data.reply" in js


def test_chart_summary_reasoning_reflects_overlay_levels() -> None:
    backend = OperatorBackend(llm_enabled=False)
    backend.chat("what do you think about a put on NVDA exit of 182.80")
    backend.command("trade_plan symbol=NVDA")

    class _Provider:
        provider_name = "alpaca"

        def health_snapshot(self, active: bool):
            class _Health:
                state = "ready"

            return _Health()

        def get_bars(self, symbol: str, timeframe: str, limit: int = 180):
            return [
                {"timestamp": "2026-01-01T14:30:00+00:00", "open": 182.1, "high": 183.2, "low": 181.8, "close": 182.9, "volume": 12345},
                {"timestamp": "2026-01-01T14:35:00+00:00", "open": 182.9, "high": 183.4, "low": 182.5, "close": 183.1, "volume": 11321},
            ]

    backend._historical_provider = _Provider()
    chart = backend.chart_data(symbol="NVDA", timeframe="5m")
    reasoning = str(chart["summary"]["reasoning"])
    overlay_types = {item["type"] for item in chart["overlays"]}

    assert "target around" in reasoning
    assert "invalidation near" in reasoning
    assert {"entry", "invalidation", "target", "vwap"}.issubset(overlay_types)




def test_chart_endpoint_reports_real_provider_unavailable_without_synthetic_fallback() -> None:
    backend = OperatorBackend(llm_enabled=False)

    payload = backend.chart_data(symbol="NVDA", timeframe="5m")

    assert payload["meta"]["provider"] == "alpaca"
    assert payload["meta"]["is_mock_provider"] is False
    assert payload["fallback"]["available"] is False
    assert payload["fallback"]["reason"] in {"provider_unavailable", "bars_unavailable"}
    assert payload["bars"] == []

def test_provider_runtime_config_loads_top_level_provider_block() -> None:
    backend = OperatorBackend(llm_enabled=False)
    cfg = backend._load_provider_runtime_config()

    assert cfg["historical_data_provider"] == "alpaca"
    assert "market_data_backends" in cfg


def test_provider_runtime_config_applies_alpaca_env_credentials(monkeypatch) -> None:
    monkeypatch.setenv("APCA_API_KEY_ID", "env-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "env-secret")

    backend = OperatorBackend(llm_enabled=False)
    cfg = backend._load_provider_runtime_config()
    alpaca_cfg = dict(dict(cfg.get("market_data_backends", {})).get("alpaca", {}))

    assert alpaca_cfg["api_key"] == "env-key"
    assert alpaca_cfg["secret_key"] == "env-secret"

    provider = backend._historical_provider
    assert provider.provider_name == "alpaca"
    assert provider.api_key == "env-key"
    assert provider.secret_key == "env-secret"
    assert provider.client.config.api_key == "env-key"
    assert provider.client.config.secret_key == "env-secret"


def test_chart_endpoint_normalizes_alpaca_shorthand_fields() -> None:
    backend = OperatorBackend(llm_enabled=False)

    class _Provider:
        provider_name = "alpaca"

        def get_bars(self, symbol: str, timeframe: str, limit: int = 180):
            return [
                {"t": "2026-01-01T14:30:00+00:00", "o": 100.1, "h": 101.2, "l": 99.8, "c": 100.9, "v": 12345},
                {"t": "2026-01-01T14:35:00+00:00", "o": 100.9, "h": 101.5, "l": 100.4, "c": 101.1, "v": 11321},
            ]

    backend._historical_provider = _Provider()
    payload = backend.chart_data(symbol="NVDA", timeframe="5m")

    assert payload["bars"]
    first = payload["bars"][0]
    assert set(["timestamp", "open", "high", "low", "close"]).issubset(first.keys())
    assert not any(key in first for key in ["t", "o", "h", "l", "c"])


def test_dashboard_visual_chart_bars_are_non_empty_when_provider_has_data() -> None:
    backend = OperatorBackend(llm_enabled=False)

    class _Provider:
        provider_name = "alpaca"

        def health_snapshot(self, active: bool):
            class _Health:
                state = "ready"

            return _Health()

        def get_bars(self, symbol: str, timeframe: str, limit: int = 180):
            return [
                {"timestamp": "2026-01-01T14:30:00+00:00", "open": 182.1, "high": 183.2, "low": 181.8, "close": 182.9, "volume": 12345},
                {"timestamp": "2026-01-01T14:35:00+00:00", "open": 182.9, "high": 183.4, "low": 182.5, "close": 183.1, "volume": 11321},
            ]

    backend._historical_provider = _Provider()
    dashboard = backend.dashboard()
    visual = dashboard["operator_console"]["visual_explainability"]
    bars = visual["charts"][0]["bars"]

    assert isinstance(bars, list)
    assert len(bars) > 0
    assert visual["fallback"]["available"] is True

def test_trade_followup_question_stays_in_active_trade_context() -> None:
    backend = OperatorBackend(llm_enabled=False)

    first = backend.chat("what do you think about a put on NVDA exit of 182.00")
    assert first["interpreted_action"]["intent"] == "trade_idea"
    assert first["layout_state"]["active_workspace_mode"] == "trade"

    followup = backend.chat("if it went under 182.5 would 181.50 be reasonable")

    assert followup["interpreted_action"]["intent"] == "trade_followup"
    assert followup["layout_state"]["active_workspace_mode"] == "trade"
    assert followup["interpreted_action"]["payload"]["symbol"] == "NVDA"
    assert followup["interpreted_action"]["payload"]["direction"] == "put"
    assert followup["command_response"]["intent"] == "trade_idea_opinion"
    assert "workstation is currently functioning" not in followup["reply"].lower()

def test_trade_followup_context_does_not_override_explicit_system_status_question() -> None:
    parser = ChatIntentParser()
    parsed = parser.parse(
        "what's the system status right now",
        conversation_context={"mode": "trade", "active_symbol": "NVDA", "active_direction": "put"},
    )

    assert parsed.intent == "status"
