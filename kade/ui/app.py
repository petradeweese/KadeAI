from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path

from kade.ui.api import OperatorBackend
from kade.ui.routes import OperatorRequestHandler


def create_server(host: str = "127.0.0.1", port: int = 8765, llm_enabled: bool = True) -> ThreadingHTTPServer:
    backend = OperatorBackend(llm_enabled=llm_enabled)
    root = Path(__file__).resolve().parents[2]

    handler_cls = type("OperatorUIHandler", (OperatorRequestHandler,), {"backend": backend, "project_root": root})
    return ThreadingHTTPServer((host, port), handler_cls)


def main() -> None:
    server = create_server()
    host, port = server.server_address
    print(f"Kade Operator UI running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
