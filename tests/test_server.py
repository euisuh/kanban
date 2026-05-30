from __future__ import annotations

import base64
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
    def log_message(self, fmt: str, *args: object) -> None:
        return


def _clear_creds() -> tuple[str | None, str | None]:
    return (
        os.environ.pop("KANBAN_CREDENTIAL", None),
        os.environ.pop("KANBAN_CREDENTIALS", None),
    )


def _restore_creds(single: str | None, multi: str | None) -> None:
    if single is not None:
        os.environ["KANBAN_CREDENTIAL"] = single
    if multi is not None:
        os.environ["KANBAN_CREDENTIALS"] = multi


def _png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def request(port: int, method: str, path: str, body: dict[str, Any] | None = None, auth: str | None = None) -> tuple[int, Any]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers: dict[str, str] = {}
    if body is not None:
        headers["content-type"] = "application/json"
    if auth is not None:
        headers["authorization"] = auth
    conn.request(method, path, body=payload, headers=headers)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    try:
        parsed = json.loads(data.decode("utf-8")) if data else None
    except json.JSONDecodeError:
        parsed = data.decode("utf-8")
    return res.status, parsed


def _start(tmp_path: Path) -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    HandlerForTest.data_root = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), HandlerForTest)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    port = server.server_address[1]
    return server, thread, port


def _stop(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    HandlerForTest.data_root = None
    server.shutdown()
    thread.join(timeout=2)


def test_card_api_lifecycle(tmp_path: Path) -> None:
    saved = _clear_creds()
    server, thread, port = _start(tmp_path)
    try:
        status, board = request(port, "GET", "/api/board")
        assert status == 200
        assert board["columns"][0]["id"] == "backlog"

        status, card = request(
            port, "POST", "/api/cards",
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
        _restore_creds(*saved)
        _stop(server, thread)


def test_basic_auth_gate(tmp_path: Path) -> None:
    os.environ["KANBAN_CREDENTIAL"] = "kanban:secret"
    server, thread, port = _start(tmp_path)
    try:
        status, body = request(port, "GET", "/api/board")
        assert status == 401
        assert body == "Authentication required\n"

        auth = "Basic " + base64.b64encode(b"kanban:secret").decode()
        status, data = request(port, "GET", "/api/board", auth=auth)
        assert status == 200
        assert data["columns"][0]["id"] == "backlog"
    finally:
        os.environ.pop("KANBAN_CREDENTIAL", None)
        _stop(server, thread)


def test_single_credential_uses_legacy_data_file(tmp_path: Path) -> None:
    os.environ["KANBAN_CREDENTIAL"] = "kanban:secret"
    legacy_board = {
        "settings": {"background": {"type": "none", "value": "", "fit": "cover"}},
        "columns": [{"id": "backlog", "title": "Backlog", "accent": "#7c8a99"}],
        "cards": [
            {
                "id": "existing",
                "title": "Existing deploy board",
                "notes": "",
                "project": "",
                "priority": 4,
                "column": "backlog",
                "sortIndex": 0,
                "createdAt": 1,
                "updatedAt": 1,
            }
        ],
    }
    (tmp_path / "board.json").write_text(json.dumps(legacy_board), encoding="utf-8")
    server, thread, port = _start(tmp_path)
    auth = "Basic " + base64.b64encode(b"kanban:secret").decode()
    try:
        status, board = request(port, "GET", "/api/board", auth=auth)
        assert status == 200
        assert board["cards"][0]["title"] == "Existing deploy board"
        assert not (tmp_path / "kanban" / "board.json").exists()
    finally:
        os.environ.pop("KANBAN_CREDENTIAL", None)
        _stop(server, thread)


def test_per_user_boards_isolated(tmp_path: Path) -> None:
    os.environ["KANBAN_CREDENTIALS"] = "alice:pass1,bob:pass2"
    server, thread, port = _start(tmp_path)
    alice_auth = "Basic " + base64.b64encode(b"alice:pass1").decode()
    bob_auth = "Basic " + base64.b64encode(b"bob:pass2").decode()
    try:
        status, card = request(
            port, "POST", "/api/cards",
            {"title": "Alice task", "notes": "", "column": "backlog"},
            auth=alice_auth,
        )
        assert status == 201

        status, bob_board = request(port, "GET", "/api/board", auth=bob_auth)
        assert status == 200
        assert not any(c["title"] == "Alice task" for c in bob_board["cards"])

        status, alice_board = request(port, "GET", "/api/board", auth=alice_auth)
        assert status == 200
        assert any(c["title"] == "Alice task" for c in alice_board["cards"])

        status, _ = request(port, "GET", "/api/board")
        assert status == 401
    finally:
        os.environ.pop("KANBAN_CREDENTIALS", None)
        _stop(server, thread)


def test_patch_board_settings(tmp_path: Path) -> None:
    saved = _clear_creds()
    server, thread, port = _start(tmp_path)
    try:
        status, body = request(
            port, "PATCH", "/api/board/settings",
            {"background": {"type": "url", "value": "https://example.com/bg.jpg", "fit": "cover"}},
        )
        assert status == 200
        assert body["background"]["type"] == "url"
        assert body["background"]["value"] == "https://example.com/bg.jpg"
    finally:
        _restore_creds(*saved)
        _stop(server, thread)


def test_card_api_accepts_project_and_priority(tmp_path: Path) -> None:
    saved = _clear_creds()
    server, thread, port = _start(tmp_path)
    try:
        status, card = request(
            port, "POST", "/api/cards",
            {"title": "Ship", "notes": "", "column": "backlog", "project": "Infra", "priority": 2},
        )
        assert status == 201
        assert card["project"] == "Infra"
        assert card["priority"] == 2
    finally:
        _restore_creds(*saved)
        _stop(server, thread)


def test_card_api_rejects_string_priority(tmp_path: Path) -> None:
    saved = _clear_creds()
    server, thread, port = _start(tmp_path)
    try:
        status, body = request(
            port, "POST", "/api/cards",
            {"title": "Ship", "notes": "", "column": "backlog", "priority": "2"},
        )
        assert status == 400
        assert body["error"] == "Priority must be 1–4"
    finally:
        _restore_creds(*saved)
        _stop(server, thread)


def test_patch_board_settings_rejects_unsafe_url(tmp_path: Path) -> None:
    saved = _clear_creds()
    server, thread, port = _start(tmp_path)
    try:
        status, body = request(
            port, "PATCH", "/api/board/settings",
            {"background": {"type": "url", "value": "javascript:alert(1)", "fit": "cover"}},
        )
        assert status == 400
        assert body["error"] == "background.value must be http(s), /uploads/<hex>.<ext>, or a preset id"
    finally:
        _restore_creds(*saved)
        _stop(server, thread)


def test_upload_valid_image(tmp_path: Path) -> None:
    saved = _clear_creds()
    server, thread, port = _start(tmp_path)
    try:
        png_bytes = _png_bytes()
        boundary = b"testboundary"
        body = (
            b"--testboundary\r\n"
            b'Content-Disposition: form-data; name="file"; filename="test.png"\r\n'
            b"Content-Type: image/png\r\n"
            b"\r\n" + png_bytes + b"\r\n"
            b"--testboundary--\r\n"
        )
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request(
            "POST", "/api/upload", body=body,
            headers={
                "Content-Type": "multipart/form-data; boundary=testboundary",
                "Content-Length": str(len(body)),
            },
        )
        res = conn.getresponse()
        data = json.loads(res.read().decode())
        conn.close()
        assert res.status == 201
        assert data["path"].startswith("/uploads/")
        assert data["path"].endswith(".png")
    finally:
        _restore_creds(*saved)
        _stop(server, thread)


def test_upload_uses_configured_uploads_dir_and_serves_file(tmp_path: Path) -> None:
    saved = _clear_creds()
    previous_uploads = os.environ.get("KANBAN_UPLOADS")
    uploads = tmp_path / "data" / "uploads"
    os.environ["KANBAN_UPLOADS"] = str(uploads)
    server, thread, port = _start(tmp_path)
    try:
        png_bytes = _png_bytes()
        body = (
            b"--testboundary\r\n"
            b'Content-Disposition: form-data; name="file"; filename="test.png"\r\n'
            b"Content-Type: image/png\r\n"
            b"\r\n" + png_bytes + b"\r\n"
            b"--testboundary--\r\n"
        )
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request(
            "POST", "/api/upload", body=body,
            headers={
                "Content-Type": "multipart/form-data; boundary=testboundary",
                "Content-Length": str(len(body)),
            },
        )
        res = conn.getresponse()
        data = json.loads(res.read().decode())
        conn.close()

        assert res.status == 201
        filename = Path(data["path"]).name
        assert (uploads / filename).read_bytes() == png_bytes

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", data["path"])
        res = conn.getresponse()
        served = res.read()
        conn.close()

        assert res.status == 200
        assert served == png_bytes
    finally:
        if previous_uploads is None:
            os.environ.pop("KANBAN_UPLOADS", None)
        else:
            os.environ["KANBAN_UPLOADS"] = previous_uploads
        _restore_creds(*saved)
        _stop(server, thread)


def test_upload_rejects_non_image(tmp_path: Path) -> None:
    saved = _clear_creds()
    server, thread, port = _start(tmp_path)
    try:
        body = (
            b"--testboundary\r\n"
            b'Content-Disposition: form-data; name="file"; filename="evil.html"\r\n'
            b"Content-Type: text/html\r\n"
            b"\r\n<script>alert(1)</script>\r\n"
            b"--testboundary--\r\n"
        )
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request(
            "POST", "/api/upload", body=body,
            headers={
                "Content-Type": "multipart/form-data; boundary=testboundary",
                "Content-Length": str(len(body)),
            },
        )
        res = conn.getresponse()
        res.read()
        conn.close()
        assert res.status == 400
    finally:
        _restore_creds(*saved)
        _stop(server, thread)


def test_head_requires_basic_auth(tmp_path: Path) -> None:
    os.environ["KANBAN_CREDENTIAL"] = "kanban:secret"
    server, thread, port = _start(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("HEAD", "/")
        res = conn.getresponse()
        res.read()
        conn.close()
        assert res.status == 401

        auth = "Basic " + base64.b64encode(b"kanban:secret").decode()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("HEAD", "/", headers={"authorization": auth})
        res = conn.getresponse()
        res.read()
        conn.close()
        assert res.status == 200
    finally:
        os.environ.pop("KANBAN_CREDENTIAL", None)
        _stop(server, thread)


def test_malformed_credentials_fail_closed(tmp_path: Path) -> None:
    os.environ["KANBAN_CREDENTIALS"] = "no-colon-here,also-bad"
    server, thread, port = _start(tmp_path)
    try:
        status, _ = request(port, "GET", "/api/board")
        assert status == 401
    finally:
        os.environ.pop("KANBAN_CREDENTIALS", None)
        _stop(server, thread)


def test_invalid_username_characters_rejected(tmp_path: Path) -> None:
    os.environ["KANBAN_CREDENTIALS"] = "../evil:pass,valid:pass2"
    server, thread, port = _start(tmp_path)
    try:
        # ../evil should be rejected at parse time; only valid:pass2 is accepted
        bad_auth = "Basic " + base64.b64encode(b"../evil:pass").decode()
        status, _ = request(port, "GET", "/api/board", auth=bad_auth)
        assert status == 401

        good_auth = "Basic " + base64.b64encode(b"valid:pass2").decode()
        status, _ = request(port, "GET", "/api/board", auth=good_auth)
        assert status == 200
    finally:
        os.environ.pop("KANBAN_CREDENTIALS", None)
        _stop(server, thread)
