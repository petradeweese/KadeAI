from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from kade.ui.api import OperatorBackend


class OperatorRequestHandler(BaseHTTPRequestHandler):
    backend: OperatorBackend
    project_root: Path

    def _json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return dict(json.loads(raw.decode("utf-8") or "{}"))
        except json.JSONDecodeError:
            return {}

    def _serve_static(self, path: str) -> None:
        static_path = self.project_root / "kade" / "ui" / "static" / path
        if not static_path.exists() or not static_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = static_path.read_bytes()
        mime = "text/plain"
        if path.endswith(".css"):
            mime = "text/css"
        elif path.endswith(".js"):
            mime = "application/javascript"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/dashboard"}:
            template = (self.project_root / "kade" / "ui" / "templates" / "index.html").read_text(encoding="utf-8")
            self._html(template)
            return
        if parsed.path == "/api/dashboard":
            self._json(self.backend.dashboard())
            return
        if parsed.path == "/api/history":
            self._json(self.backend.history())
            return
        if parsed.path == "/api/chart":
            query = parse_qs(parsed.query)
            symbol = str((query.get("symbol") or [""])[0] or "").strip() or None
            timeframe = str((query.get("timeframe") or [""])[0] or "").strip() or None
            self._json(self.backend.chart_data(symbol=symbol, timeframe=timeframe))
            return
        if parsed.path.startswith("/static/"):
            self._serve_static(parsed.path.replace("/static/", "", 1))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        body = self._read_json()
        if parsed.path == "/api/command":
            command = str(body.get("command", "")).strip()
            if not command:
                self._json({"ok": False, "error": "command_required"}, status=400)
                return
            self._json(self.backend.command(command))
            return
        if parsed.path == "/api/chat":
            message = str(body.get("message", "")).strip()
            if not message:
                self._json({"ok": False, "error": "message_required"}, status=400)
                return
            self._json(self.backend.chat(message))
            return
        self.send_error(HTTPStatus.NOT_FOUND)
