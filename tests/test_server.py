from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app.server import KanbanHandler
from app.storage import BoardStore


class HandlerForTest(KanbanHandler):
    store: BoardStore

    def log_message(self, fmt: str, *args: object) -> None:
        return


def request(port: int, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"content-type": "application/json"} if body is not None else {}
    conn.request(method, path, body=payload, headers=headers)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    parsed = json.loads(data.decode("utf-8")) if data else None
    return res.status, parsed


def test_card_api_lifecycle(tmp_path: Path) -> None:
    HandlerForTest.store = BoardStore(tmp_path / "board.json")
    server = ThreadingHTTPServer(("127.0.0.1", 0), HandlerForTest)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    port = server.server_address[1]

    try:
        status, board = request(port, "GET", "/api/board")
        assert status == 200
        assert board["columns"][0]["id"] == "backlog"

        status, card = request(
            port,
            "POST",
            "/api/cards",
            {"title": "Deploy", "notes": "homeserver", "column": "backlog"},
        )
        assert status == 201
        assert card["title"] == "Deploy"

        status, moved = request(port, "PATCH", f"/api/cards/{card['id']}", {"column": "doing"})
        assert status == 200
        assert moved["column"] == "doing"

        status, body = request(port, "DELETE", f"/api/cards/{card['id']}")
        assert status == 204
        assert body is None
    finally:
        server.shutdown()
        thread.join(timeout=2)
