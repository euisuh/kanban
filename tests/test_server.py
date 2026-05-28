from __future__ import annotations

import http.client
import json
import os
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
    try:
        parsed = json.loads(data.decode("utf-8")) if data else None
    except json.JSONDecodeError:
        parsed = data.decode("utf-8")
    return res.status, parsed


def test_card_api_lifecycle(tmp_path: Path) -> None:
    prev_cred = os.environ.pop("KANBAN_CREDENTIAL", None)
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
        if prev_cred is not None:
            os.environ["KANBAN_CREDENTIAL"] = prev_cred
        server.shutdown()
        thread.join(timeout=2)


def test_basic_auth_gate(tmp_path: Path) -> None:
    os.environ["KANBAN_CREDENTIAL"] = "kanban:secret"
    HandlerForTest.store = BoardStore(tmp_path / "board.json")
    server = ThreadingHTTPServer(("127.0.0.1", 0), HandlerForTest)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    port = server.server_address[1]

    try:
        status, body = request(port, "GET", "/api/board")
        assert status == 401
        assert body == "Authentication required\n"

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/api/board", headers={"authorization": "Basic a2FuYmFuOnNlY3JldA=="})
        res = conn.getresponse()
        data = json.loads(res.read().decode("utf-8"))
        conn.close()

        assert res.status == 200
        assert data["columns"][0]["id"] == "backlog"
    finally:
        os.environ.pop("KANBAN_CREDENTIAL", None)
        server.shutdown()
        thread.join(timeout=2)


def test_patch_board_settings(tmp_path: Path) -> None:
    prev_cred = os.environ.pop("KANBAN_CREDENTIAL", None)
    HandlerForTest.store = BoardStore(tmp_path / "board.json")
    server = ThreadingHTTPServer(("127.0.0.1", 0), HandlerForTest)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    port = server.server_address[1]
    try:
        status, body = request(
            port, "PATCH", "/api/board/settings",
            {"background": {"type": "url", "value": "https://example.com/bg.jpg", "fit": "cover"}},
        )
        assert status == 200
        assert body["background"]["type"] == "url"
        assert body["background"]["value"] == "https://example.com/bg.jpg"
    finally:
        if prev_cred is not None:
            os.environ["KANBAN_CREDENTIAL"] = prev_cred
        server.shutdown()
        thread.join(timeout=2)


def test_card_api_accepts_project_and_priority(tmp_path: Path) -> None:
    prev_cred = os.environ.pop("KANBAN_CREDENTIAL", None)
    HandlerForTest.store = BoardStore(tmp_path / "board.json")
    server = ThreadingHTTPServer(("127.0.0.1", 0), HandlerForTest)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    port = server.server_address[1]
    try:
        status, card = request(
            port, "POST", "/api/cards",
            {"title": "Ship", "notes": "", "column": "backlog", "project": "Infra", "priority": 2},
        )
        assert status == 201
        assert card["project"] == "Infra"
        assert card["priority"] == 2
    finally:
        if prev_cred is not None:
            os.environ["KANBAN_CREDENTIAL"] = prev_cred
        server.shutdown()
        thread.join(timeout=2)


def test_head_requires_basic_auth(tmp_path: Path) -> None:
    os.environ["KANBAN_CREDENTIAL"] = "kanban:secret"
    HandlerForTest.store = BoardStore(tmp_path / "board.json")
    server = ThreadingHTTPServer(("127.0.0.1", 0), HandlerForTest)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    port = server.server_address[1]

    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("HEAD", "/")
        res = conn.getresponse()
        res.read()
        conn.close()
        assert res.status == 401

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("HEAD", "/", headers={"authorization": "Basic a2FuYmFuOnNlY3JldA=="})
        res = conn.getresponse()
        res.read()
        conn.close()
        assert res.status == 200
    finally:
        os.environ.pop("KANBAN_CREDENTIAL", None)
        server.shutdown()
        thread.join(timeout=2)
