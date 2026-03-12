from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

from kade.chat.models import InterpretedAction
from kade.chat.parser import ChatIntentParser
from kade.chat.router import ChatActionRouter
from kade.ui.api import OperatorBackend
from kade.ui.app import create_server


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


def test_dashboard_command_chat_and_history_endpoints() -> None:
    server = create_server(host="127.0.0.1", port=0, llm_enabled=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=3)

    conn.request("GET", "/api/dashboard")
    dashboard = json.loads(conn.getresponse().read().decode("utf-8"))
    assert dashboard["status"] == "running"
    assert "operator_console" in dashboard

    conn.request("POST", "/api/command", body=json.dumps({"command": "status"}), headers={"Content-Type": "application/json"})
    command_payload = json.loads(conn.getresponse().read().decode("utf-8"))
    assert command_payload["ok"] is True
    assert command_payload["result"]["intent"] == "status"

    conn.request("POST", "/api/chat", body=json.dumps({"message": "Show NVDA visually."}), headers={"Content-Type": "application/json"})
    chat_payload = json.loads(conn.getresponse().read().decode("utf-8"))
    assert chat_payload["ok"] is True
    assert chat_payload["interpreted_action"]["intent"] == "visual_explain"
    assert "dashboard" in chat_payload

    conn.request("GET", "/api/history")
    history = json.loads(conn.getresponse().read().decode("utf-8"))
    assert len(history["items"]) >= 2

    conn.close()
    server.shutdown()
    server.server_close()


def test_explicit_command_passthrough_and_parser_fallback() -> None:
    parser = ChatIntentParser()
    parsed = parser.parse("trade_idea symbol=NVDA direction=put")
    assert parsed.intent == "explicit_command"
    assert parsed.payload["command"].startswith("trade_idea")

    fallback = parser.parse("nonsense words with no known intent")
    assert fallback.intent == "status"
    assert fallback.source == "fallback"


def test_sparse_payload_and_collapsible_debug_markup_present() -> None:
    backend = OperatorBackend(llm_enabled=False)
    result = backend.chat("what's the market doing this morning?")
    assert result["diagnostics"]["fallback_used"] is False
    dashboard = result["dashboard"]
    assert "operator_console" in dashboard

    with open("kade/ui/templates/index.html", encoding="utf-8") as handle:
        html = handle.read()
    with open("kade/ui/static/app.js", encoding="utf-8") as handle:
        js = handle.read()

    assert "<details" in html
    assert "Show raw" in js


def test_llm_intent_parse_cannot_override_trade_logic_fields() -> None:
    class _LLM:
        def generate(self, *args, **kwargs):
            from kade.integrations.llm.base import LLMGeneration
            return LLMGeneration(provider_name="mock", model="x", success=True, content="{\"intent\":\"trade_idea\",\"symbol\":\"NVDA\",\"direction\":\"put\",\"trigger\":\"invented\"}", finish_reason="stop")

    backend = OperatorBackend(llm_enabled=False)
    from kade.chat.service import ChatService

    chat = ChatService(backend._runtime, llm_provider=_LLM(), llm_enabled=True)
    interpreted = chat._interpret("Should I consider a put on NVDA within an hour?")
    assert interpreted.intent == "trade_idea"
    assert interpreted.payload == {"symbol": "NVDA", "direction": "put"}
