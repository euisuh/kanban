from __future__ import annotations

import base64
import json
import mimetypes
import os
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .storage import BoardStore


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"


def store_from_env() -> BoardStore:
    return BoardStore(Path(os.environ.get("KANBAN_DATA", "data/board.json")))


class KanbanHandler(BaseHTTPRequestHandler):
    store = store_from_env()

    def do_HEAD(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/board":
            self._json(HTTPStatus.OK, self.store.load(), send_body=False)
            return

        self._static(parsed.path, send_body=False)

    def do_GET(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/board":
            self._json(HTTPStatus.OK, self.store.load())
            return

        self._static(parsed.path)

    def do_POST(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/cards":
            payload = self._payload()
            card = self.store.create_card(
                str(payload.get("title", "")),
                str(payload.get("notes", "")),
                str(payload.get("column", "backlog")),
            )
            self._json(HTTPStatus.CREATED, card)
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_PATCH(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        prefix = "/api/cards/"
        if parsed.path.startswith(prefix):
            card_id = unquote(parsed.path[len(prefix) :])
            card = self.store.update_card(card_id, self._payload())
            self._json(HTTPStatus.OK, card)
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_DELETE(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        prefix = "/api/cards/"
        if parsed.path.startswith(prefix):
            self.store.delete_card(unquote(parsed.path[len(prefix) :]))
            self._json(HTTPStatus.NO_CONTENT, None)
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def _authorized(self) -> bool:
        credential = os.environ.get("KANBAN_CREDENTIAL", "")
        if not credential:
            return True

        expected = "Basic " + base64.b64encode(credential.encode("utf-8")).decode("ascii")
        actual = self.headers.get("authorization", "")
        if secrets.compare_digest(actual, expected):
            return True

        body = b"Authentication required\n"
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("www-authenticate", 'Basic realm="Kanban"')
        self.send_header("content-type", "text/plain; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def _payload(self) -> dict[str, object]:
        length = int(self.headers.get("content-length", "0") or "0")
        if length <= 0:
            return {}
        try:
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON object required")
        return payload

    def _static(self, path: str, send_body: bool = True) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (STATIC / relative).resolve()
        if STATIC not in target.parents and target != STATIC:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        mime, _ = mimetypes.guess_type(str(target))
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", mime or "application/octet-stream")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _json(self, status: HTTPStatus, body: object | None, send_body: bool = True) -> None:
        self.send_response(status)
        if body is None:
            self.send_header("content-length", "0")
            self.end_headers()
            return
        data = json.dumps(body).encode("utf-8")
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except (ValueError, KeyError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc).strip("'")})


def main() -> None:
    host = os.environ.get("KANBAN_HOST", "127.0.0.1")
    port = int(os.environ.get("KANBAN_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), KanbanHandler)
    print(f"Kanban running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
