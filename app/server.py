from __future__ import annotations

import base64
from email import policy
from email.parser import BytesParser
import json
import mimetypes
import os
import secrets
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .storage import BoardStore


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
UPLOADS = ROOT / "static" / "uploads"
ALLOWED_UPLOAD_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

_MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _is_valid_image_bytes(data: bytes) -> bool:
    if data[:3] == b"\xff\xd8\xff":
        return True  # JPEG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True  # PNG
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True  # GIF
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True  # WEBP
    return False


def _parse_credentials() -> dict[str, str]:
    """Returns {username: password} from KANBAN_CREDENTIALS or KANBAN_CREDENTIAL."""
    raw = os.environ.get("KANBAN_CREDENTIALS", "")
    if raw:
        result: dict[str, str] = {}
        for entry in raw.split(","):
            entry = entry.strip()
            if ":" in entry:
                username, password = entry.split(":", 1)
                result[username.strip()] = password.strip()
        return result
    # backward compat: single credential
    single = os.environ.get("KANBAN_CREDENTIAL", "")
    if single and ":" in single:
        username, password = single.split(":", 1)
        return {username: password}
    return {}


def _parse_multipart(data: bytes, boundary: bytes) -> tuple[bytes, str, str]:
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: multipart/form-data; boundary="
        + boundary
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + data
    )
    if not message.is_multipart():
        return b"", "application/octet-stream", ".bin"

    first_readable_part = None
    for part in message.iter_parts():
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        mime = part.get_content_type().lower()
        parsed = (payload, mime, _MIME_TO_EXT.get(mime, ".bin"))
        if part.get_filename() or part.get_param("name", header="content-disposition") == "file":
            return parsed
        if first_readable_part is None:
            first_readable_part = parsed
    return first_readable_part or (b"", "application/octet-stream", ".bin")


class KanbanHandler(BaseHTTPRequestHandler):
    # Override in tests to control where board files land.
    data_root: Path | None = None

    def _get_store(self, username: str) -> BoardStore:
        if username:
            root = self.__class__.data_root or Path(
                os.environ.get("KANBAN_DATA_ROOT", "data")
            )
            return BoardStore(root / username / "board.json")
        # no-auth fallback — honour legacy KANBAN_DATA
        if self.__class__.data_root is not None:
            return BoardStore(self.__class__.data_root / "board.json")
        return BoardStore(Path(os.environ.get("KANBAN_DATA", "data/board.json")))

    def do_HEAD(self) -> None:
        username = self._authorized()
        if username is None:
            return
        store = self._get_store(username)
        parsed = urlparse(self.path)
        if parsed.path == "/api/board":
            self._json(HTTPStatus.OK, store.load(), send_body=False)
            return
        self._static(parsed.path, send_body=False)

    def do_GET(self) -> None:
        username = self._authorized()
        if username is None:
            return
        store = self._get_store(username)
        parsed = urlparse(self.path)
        if parsed.path == "/api/board":
            self._json(HTTPStatus.OK, store.load())
            return
        self._static(parsed.path)

    def do_POST(self) -> None:
        username = self._authorized()
        if username is None:
            return
        store = self._get_store(username)
        parsed = urlparse(self.path)

        if parsed.path == "/api/cards":
            payload = self._payload()
            priority = payload.get("priority", 4)
            if not isinstance(priority, int) or isinstance(priority, bool):
                raise ValueError("Priority must be 1–4")
            card = store.create_card(
                str(payload.get("title", "")),
                str(payload.get("notes", "")),
                str(payload.get("column", "backlog")),
                project=str(payload.get("project", "")),
                priority=priority,
            )
            self._json(HTTPStatus.CREATED, card)
            return

        if parsed.path == "/api/upload":
            content_type = self.headers.get("content-type", "")
            if not content_type.startswith("multipart/form-data"):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "multipart/form-data required"})
                return
            length = int(self.headers.get("content-length", "0") or "0")
            if length > MAX_UPLOAD_BYTES:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "File too large (max 10 MB)"})
                return
            raw = self.rfile.read(length)
            boundary = None
            for part in content_type.split(";"):
                part = part.strip()
                if part.startswith("boundary="):
                    boundary = part[9:].strip('"')
            if not boundary:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Missing boundary"})
                return
            file_data, mime, ext = _parse_multipart(raw, boundary.encode())
            if not file_data:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Empty or unreadable file"})
                return
            if mime not in ALLOWED_UPLOAD_MIME:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Unsupported image type"})
                return
            if not _is_valid_image_bytes(file_data):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Invalid image file"})
                return
            UPLOADS.mkdir(parents=True, exist_ok=True)
            filename = uuid.uuid4().hex + ext
            (UPLOADS / filename).write_bytes(file_data)
            self._json(HTTPStatus.CREATED, {"path": f"/uploads/{filename}"})
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_PATCH(self) -> None:
        username = self._authorized()
        if username is None:
            return
        store = self._get_store(username)
        parsed = urlparse(self.path)
        prefix = "/api/cards/"
        if parsed.path.startswith(prefix):
            card_id = unquote(parsed.path[len(prefix):])
            card = store.update_card(card_id, self._payload())
            self._json(HTTPStatus.OK, card)
            return

        if parsed.path == "/api/board/settings":
            settings = store.update_settings(self._payload())
            self._json(HTTPStatus.OK, settings)
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_DELETE(self) -> None:
        username = self._authorized()
        if username is None:
            return
        store = self._get_store(username)
        parsed = urlparse(self.path)
        prefix = "/api/cards/"
        if parsed.path.startswith(prefix):
            store.delete_card(unquote(parsed.path[len(prefix):]))
            self._json(HTTPStatus.NO_CONTENT, None)
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def _authorized(self) -> str | None:
        """Returns username (or '' for no-auth mode) on success; sends 401 and returns None on failure."""
        credentials = _parse_credentials()
        if not credentials:
            return ""

        actual = self.headers.get("authorization", "")
        for username, password in credentials.items():
            expected = "Basic " + base64.b64encode(
                f"{username}:{password}".encode("utf-8")
            ).decode("ascii")
            if secrets.compare_digest(actual, expected):
                return username

        body = b"Authentication required\n"
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("www-authenticate", 'Basic realm="Kanban"')
        self.send_header("content-type", "text/plain; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return None

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
        except (ValueError, KeyError, TypeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc).strip("'")})


def main() -> None:
    host = os.environ.get("KANBAN_HOST", "127.0.0.1")
    port = int(os.environ.get("KANBAN_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), KanbanHandler)
    print(f"Kanban running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
