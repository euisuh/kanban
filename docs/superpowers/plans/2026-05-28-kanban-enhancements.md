# Kanban UI Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add transparent columns, richer card metadata (project/priority/date), customizable background, smart quick-add parser, and expandable card modal to the self-hosted kanban app.

**Architecture:** Extend `board.json` schema with `project`/`priority` on cards and a top-level `settings` key for background. Add two new HTTP endpoints. All UI is vanilla JS/CSS in the existing static files.

**Tech Stack:** Python stdlib HTTP server, vanilla JS (ES2020), CSS custom properties, pytest

---

## File Map

| File | Change |
|------|--------|
| `app/storage.py` | Add `project`/`priority` to card schema; add `settings` to board schema; add `update_settings` method |
| `app/server.py` | Add `PATCH /api/board/settings` and `POST /api/upload` handlers |
| `app/static/index.html` | Update card template; add modal template; add settings panel |
| `app/static/styles.css` | Column glass; priority badges; modal overlay + transitions; bg image support |
| `app/static/app.js` | Quick-add parser; sort; card expand modal; settings/upload UI |
| `app/static/uploads/.gitkeep` | Create dir, gitkeep |
| `tests/test_storage.py` | Tests for new fields and `update_settings` |
| `tests/test_server.py` | Tests for new endpoints |

---

## Task 1: Branch

- [ ] **Create feature branch**

```bash
git checkout main
git checkout -b feat/kanban-ui-enhancements
```

---

## Task 2: Storage — card fields + settings schema

**Files:**
- Modify: `app/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Write failing tests**

Add to `tests/test_storage.py`:

```python
def test_card_has_project_and_priority_defaults(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    card = store.create_card("Task", "", "backlog")
    assert card["project"] == ""
    assert card["priority"] == 4


def test_card_create_accepts_project_and_priority(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    card = store.create_card("Task", "", "backlog", project="Auth", priority=1)
    assert card["project"] == "Auth"
    assert card["priority"] == 1


def test_update_card_project_and_priority(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    card = store.create_card("Task", "", "backlog")
    updated = store.update_card(card["id"], {"project": "Design", "priority": 2})
    assert updated["project"] == "Design"
    assert updated["priority"] == 2


def test_invalid_priority_rejected(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    card = store.create_card("Task", "", "backlog")
    with pytest.raises(ValueError):
        store.update_card(card["id"], {"priority": 5})


def test_settings_default(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    board = store.load()
    assert board["settings"]["background"]["type"] == "none"


def test_update_settings(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    settings = store.update_settings({"background": {"type": "url", "value": "https://example.com/bg.jpg", "fit": "cover"}})
    assert settings["background"]["type"] == "url"
    board = store.load()
    assert board["settings"]["background"]["value"] == "https://example.com/bg.jpg"
```

- [ ] **Run tests to confirm they fail**

```bash
pytest tests/test_storage.py -v -k "project or priority or settings"
```

Expected: all 6 new tests FAIL.

- [ ] **Implement in `app/storage.py`**

Replace `default_board`:
```python
def default_board() -> dict[str, Any]:
    now = int(time.time())
    return {
        "settings": {"background": {"type": "none", "value": "", "fit": "cover"}},
        "columns": DEFAULT_COLUMNS,
        "cards": [
            {
                "id": "welcome",
                "title": "Make the board yours",
                "notes": "Add cards, drag them between columns, and keep the JSON file backed up.",
                "project": "",
                "priority": 4,
                "column": "backlog",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
    }
```

Update `create_card` signature and body:
```python
def create_card(self, title: str, notes: str, column: str, project: str = "", priority: int = 4) -> dict[str, Any]:
    title = title.strip()
    notes = notes.strip()
    if not title:
        raise ValueError("Card title is required")

    board = self.load()
    self._require_column(board, column)
    now = int(time.time())
    card = {
        "id": uuid.uuid4().hex,
        "title": title,
        "notes": notes,
        "project": project.strip(),
        "priority": priority,
        "column": column,
        "createdAt": now,
        "updatedAt": now,
    }
    board["cards"].append(card)
    self.save(board)
    return card
```

Update `update_card` to handle new fields (add after existing `if "notes" in patch:` block):
```python
        if "project" in patch:
            card["project"] = str(patch["project"]).strip()
        if "priority" in patch:
            p = int(patch["priority"])
            if p not in (1, 2, 3, 4):
                raise ValueError("Priority must be 1–4")
            card["priority"] = p
```

Add `update_settings` method to `BoardStore`:
```python
    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        board = self.load()
        settings = board.get("settings") or {}
        if "background" in patch:
            bg = patch["background"]
            bg_type = str(bg.get("type", "none"))
            if bg_type not in ("none", "url", "upload"):
                raise ValueError("background.type must be none, url, or upload")
            fit = str(bg.get("fit", "cover"))
            if fit not in ("cover", "contain", "center"):
                raise ValueError("background.fit must be cover, contain, or center")
            settings["background"] = {
                "type": bg_type,
                "value": str(bg.get("value", "")).strip(),
                "fit": fit,
            }
        board["settings"] = settings
        self.save(board)
        return settings
```

Update `_normalized` to carry new fields:

Replace the card normalization block inside `_normalized`:
```python
        for raw in board.get("cards", []):
            card = {
                "id": str(raw.get("id") or uuid.uuid4().hex),
                "title": str(raw.get("title") or "Untitled").strip() or "Untitled",
                "notes": str(raw.get("notes") or "").strip(),
                "project": str(raw.get("project") or "").strip(),
                "priority": int(raw["priority"]) if raw.get("priority") in (1, 2, 3, 4) else 4,
                "column": str(raw.get("column") or columns[0]["id"]),
                "createdAt": int(raw.get("createdAt") or now),
                "updatedAt": int(raw.get("updatedAt") or now),
            }
            if card["column"] not in column_ids:
                card["column"] = columns[0]["id"]
            cards.append(card)
        default_settings = {"background": {"type": "none", "value": "", "fit": "cover"}}
        raw_settings = board.get("settings") or {}
        bg = raw_settings.get("background") or {}
        bg_type = bg.get("type", "none") if bg.get("type") in ("none", "url", "upload") else "none"
        fit = bg.get("fit", "cover") if bg.get("fit") in ("cover", "contain", "center") else "cover"
        settings = {"background": {"type": bg_type, "value": str(bg.get("value") or ""), "fit": fit}}
        return {"settings": settings, "columns": columns, "cards": cards}
```

- [ ] **Run tests to confirm they pass**

```bash
pytest tests/test_storage.py -v
```

Expected: all tests PASS.

- [ ] **Commit**

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: add project/priority fields and settings schema to storage"
```

---

## Task 3: Server — new endpoints

**Files:**
- Modify: `app/server.py`
- Modify: `tests/test_server.py`

- [ ] **Write failing tests**

Add to `tests/test_server.py` (after existing imports, add `import base64`; add these test functions):

```python
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
```

- [ ] **Run tests to confirm they fail**

```bash
pytest tests/test_server.py -v -k "settings or project_and_priority"
```

Expected: both new tests FAIL.

- [ ] **Implement in `app/server.py`**

Add `ALLOWED_UPLOAD_MIME` constant and `UPLOADS` path near the top after `STATIC`:
```python
UPLOADS = ROOT / "static" / "uploads"
ALLOWED_UPLOAD_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
```

Update `do_POST` to add the upload route (add before the final `_json NOT_FOUND`):
```python
        if parsed.path == "/api/upload":
            content_type = self.headers.get("content-type", "")
            if not content_type.startswith("multipart/form-data"):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "multipart/form-data required"})
                return
            length = int(self.headers.get("content-length", "0") or "0")
            raw = self.rfile.read(length)
            # Parse boundary
            boundary = None
            for part in content_type.split(";"):
                part = part.strip()
                if part.startswith("boundary="):
                    boundary = part[9:].strip('"')
            if not boundary:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Missing boundary"})
                return
            file_data, mime, ext = _parse_multipart(raw, boundary.encode())
            if mime not in ALLOWED_UPLOAD_MIME:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Unsupported image type"})
                return
            UPLOADS.mkdir(parents=True, exist_ok=True)
            filename = uuid.uuid4().hex + ext
            (UPLOADS / filename).write_bytes(file_data)
            self._json(HTTPStatus.CREATED, {"path": f"/uploads/{filename}"})
            return
```

Add `do_PATCH` route for `/api/board/settings` (add before the final `_json NOT_FOUND` in `do_PATCH`):
```python
        if parsed.path == "/api/board/settings":
            settings = self.store.update_settings(self._payload())
            self._json(HTTPStatus.OK, settings)
            return
```

Add `_parse_multipart` helper function at module level (before `KanbanHandler`):
```python
def _parse_multipart(data: bytes, boundary: bytes) -> tuple[bytes, str, str]:
    import email.parser
    import email.policy
    delim = b"--" + boundary
    parts = data.split(delim)
    for part in parts[1:]:
        if part.startswith(b"--"):
            continue
        if b"\r\n\r\n" not in part:
            continue
        header_raw, body = part.split(b"\r\n\r\n", 1)
        body = body.rstrip(b"\r\n")
        headers_text = header_raw.decode("utf-8", errors="replace")
        mime = "application/octet-stream"
        ext = ".bin"
        for line in headers_text.splitlines():
            if line.lower().startswith("content-type:"):
                mime = line.split(":", 1)[1].strip().lower()
                ext_map = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                    "image/gif": ".gif",
                }
                ext = ext_map.get(mime, ".bin")
        return body, mime, ext
    return b"", "application/octet-stream", ".bin"
```

Also add `import uuid` at top of `server.py` if not present (it isn't — add it).

Update `do_POST` to pass `project` and `priority` to `create_card`:
```python
        if parsed.path == "/api/cards":
            payload = self._payload()
            card = self.store.create_card(
                str(payload.get("title", "")),
                str(payload.get("notes", "")),
                str(payload.get("column", "backlog")),
                project=str(payload.get("project", "")),
                priority=int(payload.get("priority", 4)),
            )
            self._json(HTTPStatus.CREATED, card)
            return
```

- [ ] **Run tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Commit**

```bash
git add app/server.py tests/test_server.py
git commit -m "feat: add PATCH /api/board/settings and POST /api/upload endpoints"
```

---

## Task 4: Create uploads dir

**Files:**
- Create: `app/static/uploads/.gitkeep`

- [ ] **Create dir and gitkeep**

```bash
mkdir -p app/static/uploads
touch app/static/uploads/.gitkeep
echo "app/static/uploads/*" >> .gitignore
echo "!app/static/uploads/.gitkeep" >> .gitignore
```

- [ ] **Commit**

```bash
git add app/static/uploads/.gitkeep .gitignore
git commit -m "chore: add uploads dir with gitkeep, ignore uploaded files"
```

---

## Task 5: CSS — column glass, priority badges, body bg support

**Files:**
- Modify: `app/static/styles.css`

- [ ] **Replace `app/static/styles.css` in full**

```css
:root {
  color-scheme: light;
  --bg: #f5f1e8;
  --panel: #fffdf8;
  --ink: #1d2428;
  --muted: #687177;
  --line: #ded8cc;
  --shadow: 0 18px 50px rgba(30, 35, 38, 0.08);
  --focus: #2f7d6d;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  min-height: 100vh;
  background-color: var(--bg);
  background-image:
    linear-gradient(120deg, rgba(47, 125, 109, 0.08), transparent 34%);
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  color: var(--ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
}

body.has-bg-image {
  background-image: var(--board-bg-image);
  background-size: var(--board-bg-size, cover);
  background-position: center;
  background-repeat: no-repeat;
}

button, input, textarea { font: inherit; }

.shell {
  width: min(1480px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 28px 0;
}

/* ── Topbar ─────────────────────────────────────── */

.topbar {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(320px, 620px) 44px;
  gap: 20px;
  align-items: end;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--muted);
  font-size: 0.78rem;
  text-transform: uppercase;
}

h1, h2 { margin: 0; }

h1 {
  font-size: clamp(2.2rem, 6vw, 4.8rem);
  line-height: 0.95;
}

/* ── Composer (quick-add) ───────────────────────── */

.composer-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.composer {
  display: grid;
  grid-template-columns: 1fr;
  background: rgba(255, 253, 248, 0.72);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px;
  box-shadow: var(--shadow);
}

.composer input {
  width: 100%;
  border: 0;
  outline: 0;
  color: var(--ink);
  background: transparent;
  min-width: 0;
  height: 40px;
  padding: 0 10px;
  border-radius: 6px;
}

.composer input:focus { background: #f4efe4; }

.composer-preview {
  min-height: 18px;
  padding: 0 4px;
  font-size: 0.78rem;
  color: var(--muted);
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.composer-preview span { opacity: 0.9; }

/* ── Settings button ────────────────────────────── */

.settings-btn {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(255, 253, 248, 0.72);
  color: var(--muted);
  cursor: pointer;
  font-size: 1.1rem;
  box-shadow: var(--shadow);
  transition: background 0.15s;
}

.settings-btn:hover { background: #f4efe4; color: var(--ink); }

/* ── Settings panel ─────────────────────────────── */

.settings-panel {
  display: none;
  margin-bottom: 20px;
  padding: 16px;
  background: rgba(255, 253, 248, 0.88);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
}

.settings-panel.open { display: block; }

.settings-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.settings-tab {
  padding: 5px 14px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--muted);
}

.settings-tab.active {
  background: var(--ink);
  color: white;
  border-color: var(--ink);
}

.settings-pane { display: none; }
.settings-pane.active { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }

.settings-pane label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.82rem;
  color: var(--muted);
}

.settings-pane input[type="text"],
.settings-pane input[type="url"] {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 6px 10px;
  background: white;
  min-width: 260px;
  color: var(--ink);
}

.settings-fit-group {
  display: flex;
  gap: 6px;
}

.fit-btn {
  padding: 5px 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  font-size: 0.82rem;
  color: var(--muted);
}

.fit-btn.active {
  background: var(--focus);
  color: white;
  border-color: var(--focus);
}

.settings-preview {
  width: 80px;
  height: 50px;
  border-radius: 6px;
  border: 1px solid var(--line);
  object-fit: cover;
  display: none;
}

.settings-preview.visible { display: block; }

.settings-apply {
  padding: 7px 18px;
  background: var(--ink);
  color: white;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
}

.settings-apply:hover { opacity: 0.85; }

/* ── Board ──────────────────────────────────────── */

.board {
  display: grid;
  grid-template-columns: repeat(4, minmax(240px, 1fr));
  gap: 14px;
  align-items: start;
}

/* ── Column (glassmorphism) ─────────────────────── */

.column {
  min-width: 0;
  background: rgba(255, 253, 248, 0.45);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 8px;
  box-shadow: var(--shadow);
}

.column-head {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 14px;
  border-bottom: 1px solid rgba(222, 216, 204, 0.5);
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: var(--focus);
}

.column h2 {
  overflow: hidden;
  font-size: 0.92rem;
  font-weight: 720;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.count { color: var(--muted); font-size: 0.82rem; }

.dropzone {
  display: grid;
  gap: 10px;
  min-height: 62vh;
  padding: 12px;
  align-content: start;
}

.dropzone.dragover { background: rgba(47, 125, 109, 0.09); }

/* ── Card ───────────────────────────────────────── */

.card {
  padding: 12px;
  background: rgba(255, 253, 248, 0.82);
  border: 1px solid rgba(104, 113, 119, 0.18);
  border-radius: 8px;
  box-shadow: 0 10px 22px rgba(30, 35, 38, 0.06);
  cursor: pointer;
  position: relative;
  transition: box-shadow 0.15s, transform 0.15s;
}

.card:hover {
  box-shadow: 0 14px 30px rgba(30, 35, 38, 0.12);
  transform: translateY(-1px);
}

.card.dragging { opacity: 0.46; }

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.priority-badge {
  font-size: 0.68rem;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 999px;
  letter-spacing: 0.02em;
}

.priority-1 { background: #fdd; color: #c0392b; }
.priority-2 { background: #fde8d0; color: #c0672b; }
.priority-3 { background: #fdf6c0; color: #9a7d0a; }
.priority-4 { background: #e0e6f0; color: #5a6478; }

.project-chip {
  font-size: 0.72rem;
  color: var(--muted);
  background: rgba(104, 113, 119, 0.1);
  padding: 2px 8px;
  border-radius: 999px;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-title {
  font-weight: 720;
  font-size: 0.9rem;
  margin: 0 0 4px;
  line-height: 1.35;
}

.card-notes {
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 0 0 6px;
}

.card-date {
  font-size: 0.72rem;
  color: var(--muted);
  opacity: 0.7;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
}

.delete {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 0.8rem;
  line-height: 1;
}

.delete:hover { background: #f0e9dc; color: var(--ink); }

/* ── Modal overlay ──────────────────────────────── */

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(29, 36, 40, 0.4);
  display: grid;
  place-items: center;
  z-index: 100;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}

.modal-backdrop.open {
  opacity: 1;
  pointer-events: all;
}

.modal {
  background: var(--panel);
  border-radius: 12px;
  box-shadow: 0 32px 80px rgba(30, 35, 38, 0.22);
  width: min(540px, calc(100vw - 32px));
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  padding: 24px;
  transform: scale(0.92);
  opacity: 0;
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1),
              opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.modal-backdrop.open .modal {
  transform: scale(1);
  opacity: 1;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
}

.modal-header .priority-badge { flex-shrink: 0; }
.modal-header .project-chip { flex: 1; min-width: 0; }

.modal-close {
  margin-left: auto;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 1rem;
}

.modal-close:hover { background: #f0e9dc; color: var(--ink); }

.modal-section {
  margin-bottom: 16px;
}

.modal-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-bottom: 6px;
}

.modal input[type="text"],
.modal textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px 10px;
  background: #faf8f3;
  color: var(--ink);
  outline: 0;
}

.modal input[type="text"]:focus,
.modal textarea:focus { border-color: var(--focus); }

.modal textarea { min-height: 80px; resize: vertical; }

.modal-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 16px;
  align-items: start;
}

.priority-group {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px;
}

.priority-btn {
  padding: 5px 0;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
  text-align: center;
  transition: all 0.1s;
}

.priority-btn.active.p1 { background: #fdd; color: #c0392b; border-color: #f5c6c6; }
.priority-btn.active.p2 { background: #fde8d0; color: #c0672b; border-color: #f5d0a8; }
.priority-btn.active.p3 { background: #fdf6c0; color: #9a7d0a; border-color: #f0e280; }
.priority-btn.active.p4 { background: #e0e6f0; color: #5a6478; border-color: #c8d2e4; }

.modal select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px 10px;
  background: #faf8f3;
  color: var(--ink);
  outline: 0;
  cursor: pointer;
}

.modal-date {
  font-size: 0.78rem;
  color: var(--muted);
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

/* ── Responsive ─────────────────────────────────── */

@media (max-width: 980px) {
  .topbar { grid-template-columns: 1fr 44px; }
  .composer-wrap { grid-column: 1 / -1; }
  .board { grid-template-columns: repeat(2, minmax(220px, 1fr)); }
}

@media (max-width: 620px) {
  .shell { width: min(100vw - 20px, 560px); padding: 18px 0; }
  .board { grid-template-columns: 1fr; }
  .dropzone { min-height: 220px; }
  .modal-row { grid-template-columns: 1fr; }
}
```

- [ ] **Verify** — no syntax errors

```bash
python3 -c "print('CSS check: manual')"
```

(CSS has no automated check — verify visually in Task 9.)

- [ ] **Commit**

```bash
git add app/static/styles.css
git commit -m "style: glassmorphism columns, priority badges, modal overlay, bg image support"
```

---

## Task 6: HTML — update templates, add modal + settings panel

**Files:**
- Modify: `app/static/index.html`

- [ ] **Replace `app/static/index.html` in full**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Kanban</title>
    <link rel="stylesheet" href="/styles.css" />
  </head>
  <body>
    <main class="shell">
      <header class="topbar">
        <div>
          <p class="eyebrow">Self-hosted</p>
          <h1>Kanban</h1>
        </div>
        <div class="composer-wrap">
          <form id="card-form" class="composer">
            <input
              id="quick-add"
              type="text"
              placeholder="New card — e.g. Fix bug @Auth p2 | check token expiry"
              autocomplete="off"
              required
            />
          </form>
          <div class="composer-preview" id="composer-preview" aria-live="polite"></div>
        </div>
        <button class="settings-btn" id="settings-toggle" type="button" aria-label="Board settings">⚙</button>
      </header>

      <div class="settings-panel" id="settings-panel">
        <div class="settings-tabs">
          <button class="settings-tab active" data-tab="upload">Upload</button>
          <button class="settings-tab" data-tab="url">URL</button>
          <button class="settings-tab" data-tab="none">None</button>
        </div>

        <div class="settings-pane active" id="pane-upload">
          <label>
            Image file
            <input type="file" id="bg-file" accept="image/jpeg,image/png,image/webp,image/gif" />
          </label>
          <label>
            Fit
            <div class="settings-fit-group" id="fit-group-upload">
              <button class="fit-btn active" data-fit="cover">Cover</button>
              <button class="fit-btn" data-fit="contain">Contain</button>
              <button class="fit-btn" data-fit="center">Center</button>
            </div>
          </label>
          <img class="settings-preview" id="preview-upload" alt="Preview" />
          <button class="settings-apply" id="apply-upload">Apply</button>
        </div>

        <div class="settings-pane" id="pane-url">
          <label>
            Image URL
            <input type="url" id="bg-url" placeholder="https://example.com/image.jpg" />
          </label>
          <label>
            Fit
            <div class="settings-fit-group" id="fit-group-url">
              <button class="fit-btn active" data-fit="cover">Cover</button>
              <button class="fit-btn" data-fit="contain">Contain</button>
              <button class="fit-btn" data-fit="center">Center</button>
            </div>
          </label>
          <img class="settings-preview" id="preview-url" alt="Preview" />
          <button class="settings-apply" id="apply-url">Apply</button>
        </div>

        <div class="settings-pane" id="pane-none">
          <p style="color:var(--muted);font-size:0.85rem;margin:0">Remove background image and revert to default gradient.</p>
          <button class="settings-apply" id="apply-none">Apply</button>
        </div>
      </div>

      <section id="board" class="board" aria-label="Kanban board"></section>
    </main>

    <!-- Card expand modal -->
    <div class="modal-backdrop" id="modal-backdrop" role="dialog" aria-modal="true" aria-label="Edit card">
      <div class="modal" id="modal">
        <div class="modal-header">
          <span class="priority-badge" id="modal-priority-badge"></span>
          <span class="project-chip" id="modal-project-chip"></span>
          <button class="modal-close" id="modal-close" type="button" aria-label="Close">✕</button>
        </div>

        <div class="modal-section">
          <div class="modal-label">Title</div>
          <input type="text" id="modal-title" />
        </div>

        <div class="modal-row modal-section">
          <div>
            <div class="modal-label">Project</div>
            <input type="text" id="modal-project" placeholder="e.g. Auth" />
          </div>
          <div>
            <div class="modal-label">Priority</div>
            <div class="priority-group">
              <button class="priority-btn p1" data-p="1">p1</button>
              <button class="priority-btn p2" data-p="2">p2</button>
              <button class="priority-btn p3" data-p="3">p3</button>
              <button class="priority-btn p4 active" data-p="4">p4</button>
            </div>
          </div>
          <div>
            <div class="modal-label">Column</div>
            <select id="modal-column"></select>
          </div>
        </div>

        <div class="modal-section">
          <div class="modal-label">Notes</div>
          <textarea id="modal-notes"></textarea>
        </div>

        <div class="modal-date" id="modal-date"></div>
      </div>
    </div>

    <!-- Templates -->
    <template id="column-template">
      <article class="column">
        <header class="column-head">
          <span class="dot"></span>
          <h2></h2>
          <span class="count"></span>
        </header>
        <div class="dropzone"></div>
      </article>
    </template>

    <template id="card-template">
      <article class="card" draggable="true">
        <div class="card-meta">
          <span class="priority-badge"></span>
          <span class="project-chip"></span>
        </div>
        <p class="card-title"></p>
        <p class="card-notes"></p>
        <div class="card-footer">
          <span class="card-date"></span>
          <button class="delete" type="button" aria-label="Delete card">✕</button>
        </div>
      </article>
    </template>

    <script src="/app.js" defer></script>
  </body>
</html>
```

- [ ] **Commit**

```bash
git add app/static/index.html
git commit -m "feat: update HTML templates — card metadata, modal, settings panel"
```

---

## Task 7: JS — replace app.js with full implementation

**Files:**
- Modify: `app/static/app.js`

- [ ] **Replace `app/static/app.js` in full**

```javascript
const boardEl = document.querySelector("#board");
const form = document.querySelector("#card-form");
const quickAddEl = document.querySelector("#quick-add");
const previewEl = document.querySelector("#composer-preview");
const columnTemplate = document.querySelector("#column-template");
const cardTemplate = document.querySelector("#card-template");
const backdrop = document.querySelector("#modal-backdrop");
const modal = document.querySelector("#modal");

let board = { settings: { background: { type: "none", value: "", fit: "cover" } }, columns: [], cards: [] };
let draggedId = null;
let activeCardId = null;

// ── API ────────────────────────────────────────────────────────────

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Quick-add parser ───────────────────────────────────────────────

function parseQuickAdd(raw) {
  let text = raw;
  let notes = "";
  let project = "";
  let priority = 4;

  const pipeIdx = text.indexOf("|");
  if (pipeIdx !== -1) {
    notes = text.slice(pipeIdx + 1).trim();
    text = text.slice(0, pipeIdx).trim();
  }

  text = text.replace(/@(\S+)/g, (_, w) => { project = w; return ""; }).trim();
  text = text.replace(/\bp([1-4])\b/gi, (_, n) => { priority = parseInt(n, 10); return ""; }).trim();
  text = text.replace(/\s{2,}/g, " ").trim();

  return { title: text, notes, project, priority };
}

function updateComposerPreview(raw) {
  if (!raw.trim()) { previewEl.innerHTML = ""; return; }
  const { title, notes, project, priority } = parseQuickAdd(raw);
  const parts = [];
  if (title) parts.push(`<span><strong>${esc(title)}</strong></span>`);
  if (project) parts.push(`<span>@${esc(project)}</span>`);
  parts.push(`<span>p${priority}</span>`);
  if (notes) parts.push(`<span>· ${esc(notes)}</span>`);
  previewEl.innerHTML = parts.join(" ");
}

quickAddEl.addEventListener("input", () => updateComposerPreview(quickAddEl.value));

// ── Sort ───────────────────────────────────────────────────────────

function cardsFor(columnId) {
  return board.cards
    .filter((c) => c.column === columnId)
    .sort((a, b) => a.priority - b.priority || a.createdAt - b.createdAt);
}

// ── Render ─────────────────────────────────────────────────────────

function priorityLabel(p) {
  return ["", "Urgent", "High", "Med", "Low"][p] || "Low";
}

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function render() {
  boardEl.replaceChildren();
  board.columns.forEach((column) => {
    const node = columnTemplate.content.firstElementChild.cloneNode(true);
    const dropzone = node.querySelector(".dropzone");
    const columnCards = cardsFor(column.id);

    node.querySelector(".dot").style.background = column.accent;
    node.querySelector("h2").textContent = column.title;
    node.querySelector(".count").textContent = columnCards.length;
    dropzone.dataset.column = column.id;

    dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", async (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (!draggedId) return;
      await updateCard(draggedId, { column: column.id });
    });

    columnCards.forEach((card) => dropzone.appendChild(renderCard(card)));
    boardEl.appendChild(node);
  });
}

function renderCard(card) {
  const node = cardTemplate.content.firstElementChild.cloneNode(true);
  const badge = node.querySelector(".priority-badge");
  const chip = node.querySelector(".project-chip");
  const titleEl = node.querySelector(".card-title");
  const notesEl = node.querySelector(".card-notes");
  const dateEl = node.querySelector(".card-date");
  const del = node.querySelector(".delete");

  node.dataset.id = card.id;
  badge.textContent = `p${card.priority}`;
  badge.className = `priority-badge priority-${card.priority}`;

  if (card.project) {
    chip.textContent = card.project;
    chip.style.display = "";
  } else {
    chip.style.display = "none";
  }

  titleEl.textContent = card.title;
  notesEl.textContent = card.notes;
  if (!card.notes) notesEl.style.display = "none";
  dateEl.textContent = formatDate(card.createdAt);

  node.addEventListener("dragstart", () => { draggedId = card.id; node.classList.add("dragging"); });
  node.addEventListener("dragend", () => { draggedId = null; node.classList.remove("dragging"); });

  node.addEventListener("click", (e) => {
    if (e.target.closest(".delete")) return;
    openModal(card.id);
  });

  del.addEventListener("click", (e) => { e.stopPropagation(); deleteCard(card.id); });

  return node;
}

// ── CRUD ───────────────────────────────────────────────────────────

async function updateCard(id, patch) {
  const updated = await api(`/api/cards/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  board.cards = board.cards.map((c) => (c.id === id ? updated : c));
  render();
  return updated;
}

async function deleteCard(id) {
  if (activeCardId === id) closeModal();
  await api(`/api/cards/${encodeURIComponent(id)}`, { method: "DELETE" });
  board.cards = board.cards.filter((c) => c.id !== id);
  render();
}

// ── Modal ──────────────────────────────────────────────────────────

function openModal(cardId) {
  const card = board.cards.find((c) => c.id === cardId);
  if (!card) return;
  activeCardId = cardId;

  document.querySelector("#modal-title").value = card.title;
  document.querySelector("#modal-notes").value = card.notes;
  document.querySelector("#modal-project").value = card.project || "";
  document.querySelector("#modal-priority-badge").textContent = `p${card.priority}`;
  document.querySelector("#modal-priority-badge").className = `priority-badge priority-${card.priority}`;
  document.querySelector("#modal-project-chip").textContent = card.project || "";
  document.querySelector("#modal-project-chip").style.display = card.project ? "" : "none";
  document.querySelector("#modal-date").textContent = `Created ${formatDate(card.createdAt)}`;

  // Priority buttons
  document.querySelectorAll(".priority-btn").forEach((btn) => {
    btn.classList.toggle("active", parseInt(btn.dataset.p) === card.priority);
  });

  // Column select
  const sel = document.querySelector("#modal-column");
  sel.innerHTML = board.columns
    .map((col) => `<option value="${esc(col.id)}"${col.id === card.column ? " selected" : ""}>${esc(col.title)}</option>`)
    .join("");

  backdrop.classList.add("open");
  document.querySelector("#modal-title").focus();
}

function closeModal() {
  backdrop.classList.remove("open");
  activeCardId = null;
}

function modalSave(patch) {
  if (!activeCardId) return;
  updateCard(activeCardId, patch);
}

// Modal event wiring
document.querySelector("#modal-close").addEventListener("click", closeModal);
backdrop.addEventListener("click", (e) => { if (e.target === backdrop) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

document.querySelector("#modal-title").addEventListener("blur", (e) => {
  if (e.target.value.trim()) modalSave({ title: e.target.value.trim() });
});

document.querySelector("#modal-notes").addEventListener("blur", (e) => {
  modalSave({ notes: e.target.value });
});

document.querySelector("#modal-project").addEventListener("blur", (e) => {
  modalSave({ project: e.target.value.trim() });
  const chip = document.querySelector("#modal-project-chip");
  chip.textContent = e.target.value.trim();
  chip.style.display = e.target.value.trim() ? "" : "none";
});

document.querySelectorAll(".priority-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const p = parseInt(btn.dataset.p);
    document.querySelectorAll(".priority-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelector("#modal-priority-badge").textContent = `p${p}`;
    document.querySelector("#modal-priority-badge").className = `priority-badge priority-${p}`;
    modalSave({ priority: p });
  });
});

document.querySelector("#modal-column").addEventListener("change", (e) => {
  modalSave({ column: e.target.value });
});

// ── Form submit ────────────────────────────────────────────────────

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const raw = quickAddEl.value.trim();
  if (!raw) return;
  const { title, notes, project, priority } = parseQuickAdd(raw);
  if (!title) return;
  const card = await api("/api/cards", {
    method: "POST",
    body: JSON.stringify({ title, notes, project, priority, column: board.columns[0]?.id || "backlog" }),
  });
  board.cards.push(card);
  quickAddEl.value = "";
  previewEl.innerHTML = "";
  render();
});

quickAddEl.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { quickAddEl.value = ""; previewEl.innerHTML = ""; }
});

// ── Background ─────────────────────────────────────────────────────

function applyBg(settings) {
  const { type, value, fit } = settings.background || {};
  if (type === "none" || !value) {
    document.body.classList.remove("has-bg-image");
    document.body.style.removeProperty("--board-bg-image");
    document.body.style.removeProperty("--board-bg-size");
  } else {
    const sizeMap = { cover: "cover", contain: "contain", center: "auto" };
    document.body.style.setProperty("--board-bg-image", `url("${value}")`);
    document.body.style.setProperty("--board-bg-size", sizeMap[fit] || "cover");
    document.body.classList.add("has-bg-image");
  }
}

// Settings panel toggle
document.querySelector("#settings-toggle").addEventListener("click", () => {
  document.querySelector("#settings-panel").classList.toggle("open");
});

// Tab switching
document.querySelectorAll(".settings-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".settings-tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".settings-pane").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`#pane-${tab.dataset.tab}`).classList.add("active");
  });
});

// Fit buttons (both groups)
document.querySelectorAll(".settings-fit-group").forEach((group) => {
  group.querySelectorAll(".fit-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      group.querySelectorAll(".fit-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
});

function activeFit(groupId) {
  return document.querySelector(`#${groupId} .fit-btn.active`)?.dataset.fit || "cover";
}

// File preview
document.querySelector("#bg-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    const img = document.querySelector("#preview-upload");
    img.src = ev.target.result;
    img.classList.add("visible");
  };
  reader.readAsDataURL(file);
});

// URL preview
document.querySelector("#bg-url").addEventListener("input", (e) => {
  const img = document.querySelector("#preview-url");
  if (e.target.value.startsWith("http")) {
    img.src = e.target.value;
    img.classList.add("visible");
  } else {
    img.classList.remove("visible");
  }
});

// Apply upload
document.querySelector("#apply-upload").addEventListener("click", async () => {
  const file = document.querySelector("#bg-file").files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: fd });
  if (!res.ok) { alert("Upload failed"); return; }
  const { path } = await res.json();
  const fit = activeFit("fit-group-upload");
  const settings = await api("/api/board/settings", {
    method: "PATCH",
    body: JSON.stringify({ background: { type: "upload", value: path, fit } }),
  });
  board.settings = { background: settings.background };
  applyBg(board.settings);
  document.querySelector("#settings-panel").classList.remove("open");
});

// Apply URL
document.querySelector("#apply-url").addEventListener("click", async () => {
  const value = document.querySelector("#bg-url").value.trim();
  if (!value.startsWith("http")) { alert("Enter a valid URL starting with http"); return; }
  const fit = activeFit("fit-group-url");
  const settings = await api("/api/board/settings", {
    method: "PATCH",
    body: JSON.stringify({ background: { type: "url", value, fit } }),
  });
  board.settings = { background: settings.background };
  applyBg(board.settings);
  document.querySelector("#settings-panel").classList.remove("open");
});

// Apply none
document.querySelector("#apply-none").addEventListener("click", async () => {
  const settings = await api("/api/board/settings", {
    method: "PATCH",
    body: JSON.stringify({ background: { type: "none", value: "", fit: "cover" } }),
  });
  board.settings = { background: settings.background };
  applyBg(board.settings);
  document.querySelector("#settings-panel").classList.remove("open");
});

// ── Boot ───────────────────────────────────────────────────────────

async function boot() {
  board = await api("/api/board");
  if (board.settings) applyBg(board.settings);
  render();
}

boot().catch((err) => {
  boardEl.innerHTML = `<p style="color:red;padding:20px">${err.message}</p>`;
});
```

- [ ] **Commit**

```bash
git add app/static/app.js
git commit -m "feat: quick-add parser, card expand modal, background settings, priority sort"
```

---

## Task 8: Run full test suite

- [ ] **Run all tests**

```bash
pytest tests/ -v
```

Expected output: all tests PASS, no failures.

- [ ] **If any test fails**, read the error message, trace it to the relevant task above, fix the specific issue, then re-run.

---

## Task 9: Manual smoke test

- [ ] **Start the server**

```bash
python -m app.server
```

Open `http://127.0.0.1:8080` in a browser.

- [ ] **Verify quick-add parser**
  - Type `Fix login @Auth p1 | check token` — confirm preview shows title/project/priority/notes
  - Press `Enter` — card appears in Backlog with rose `p1` badge and `Auth` chip
  - Type just a title, press `Enter` — card appears with `p4` grey badge, no project chip

- [ ] **Verify card expand modal**
  - Click a card body — modal opens with scale+fade animation
  - Edit title, blur — change persists on close and reopen
  - Change priority — badge updates in header
  - Change column — card moves after close
  - Press `Escape` or click backdrop — modal closes smoothly

- [ ] **Verify column transparency**
  - Columns should show glass effect
  - Set a background image (next step) and confirm columns are transparent over it

- [ ] **Verify background customization**
  - Click ⚙ — settings panel opens
  - Upload a local image — preview shows, Apply sets body background
  - Switch to URL tab, paste an image URL — preview shows, Apply sets background
  - Switch to None tab, Apply — background reverts to gradient
  - Refresh page — background persists (loaded from board.json)

- [ ] **Verify sort**
  - Create cards with different priorities in same column
  - p1 card should appear at top, p4 at bottom

- [ ] **Commit if any fixes were made during smoke test**

```bash
git add -p
git commit -m "fix: smoke test corrections"
```

---

## Task 10: Final commit + push

- [ ] **Verify branch is clean**

```bash
git status
```

Expected: `nothing to commit, working tree clean`

- [ ] **Push branch**

```bash
git push -u origin feat/kanban-ui-enhancements
```
