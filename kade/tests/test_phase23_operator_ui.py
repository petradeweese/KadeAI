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
    assert "AI Assistant" in body
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
    assert trade_layout.panel_priority_map["trade_idea"] == 1
    assert trade_layout.panel_priority_map["visual_explainability"] == 4
    assert "timeline" in trade_layout.collapsed_panels
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
