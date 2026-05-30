from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any


DEFAULT_COLUMNS = [
    {"id": "backlog", "title": "Backlog",     "accent": "#7c8a99"},
    {"id": "todo",    "title": "To Do",        "accent": "#2b93e0"},
    {"id": "doing",   "title": "In Progress",  "accent": "#e08a2f"},
    {"id": "review",  "title": "In Review",    "accent": "#8a6cd1"},
    {"id": "done",    "title": "Done",         "accent": "#2f9268"},
]

UPLOAD_BACKGROUND_RE = re.compile(r"^/uploads/[0-9a-fA-F]+\.(?:jpg|jpeg|png|webp|gif)$")
PRESET_ID_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


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
                "sortIndex": 0,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
    }


def _priority(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("Priority must be 1–4")
    if value not in (1, 2, 3, 4):
        raise ValueError("Priority must be 1–4")
    return value


def _sort_index(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("sortIndex must be a non-negative integer")
    return value


def _valid_background_value(bg_type: str, value: str) -> bool:
    if bg_type == "none":
        return value == ""
    if bg_type == "upload":
        return UPLOAD_BACKGROUND_RE.fullmatch(value) is not None
    if bg_type == "url":
        from urllib.parse import urlparse
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    if bg_type == "preset":
        return bool(PRESET_ID_RE.fullmatch(value))
    return False


@dataclass
class BoardStore:
    path: Path

    def __post_init__(self) -> None:
        self._lock = RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                board = default_board()
                return self.save(board)

            with self.path.open("r", encoding="utf-8") as handle:
                board = json.load(handle)

            return self._normalized(board)

    def save(self, board: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            board = self._normalized(board)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(board, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                os.replace(tmp_name, self.path)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            return board

    def create_card(self, title: str, notes: str, column: str, project: str = "", priority: int = 4) -> dict[str, Any]:
        title = title.strip()
        notes = notes.strip()
        if not title:
            raise ValueError("Card title is required")
        priority = _priority(priority)

        board = self.load()
        self._require_column(board, column)
        now = int(time.time())
        sort_index = max((card.get("sortIndex", 0) for card in board["cards"] if card["column"] == column), default=-1) + 1
        card = {
            "id": uuid.uuid4().hex,
            "title": title,
            "notes": notes,
            "project": project.strip(),
            "priority": priority,
            "column": column,
            "sortIndex": sort_index,
            "createdAt": now,
            "updatedAt": now,
        }
        board["cards"].append(card)
        self.save(board)
        return card

    def update_card(self, card_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        board = self.load()
        card = self._find_card(board, card_id)

        if "title" in patch:
            title = str(patch["title"]).strip()
            if not title:
                raise ValueError("Card title is required")
            card["title"] = title
        if "notes" in patch:
            card["notes"] = str(patch["notes"]).strip()
        if "project" in patch:
            card["project"] = str(patch["project"]).strip()
        if "priority" in patch:
            card["priority"] = _priority(patch["priority"])
        if "column" in patch:
            column = str(patch["column"])
            self._require_column(board, column)
            card["column"] = column
        if "sortIndex" in patch:
            card["sortIndex"] = _sort_index(patch["sortIndex"])
        card["updatedAt"] = int(time.time())
        self.save(board)
        return card

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        board = self.load()
        settings = board.get("settings") or {}
        if "background" in patch:
            bg = patch["background"]
            if not isinstance(bg, dict):
                raise ValueError("background must be an object")
            bg_type = str(bg.get("type", "none"))
            if bg_type not in ("none", "url", "upload", "preset"):
                raise ValueError("background.type must be none, url, upload, or preset")
            fit = str(bg.get("fit", "cover"))
            if fit not in ("cover", "contain", "center"):
                raise ValueError("background.fit must be cover, contain, or center")
            value = str(bg.get("value", "")).strip()
            if not _valid_background_value(bg_type, value):
                raise ValueError("background.value must be http(s), /uploads/<hex>.<ext>, or a preset id")
            raw_scrim = bg.get("scrim", 30)
            scrim = int(raw_scrim) if isinstance(raw_scrim, (int, float)) and not isinstance(raw_scrim, bool) else 30
            scrim = max(0, min(80, scrim))
            settings["background"] = {
                "type": bg_type,
                "value": value,
                "fit": fit,
                "scrim": scrim,
            }
        board["settings"] = settings
        board = self.save(board)
        return board["settings"]

    def delete_card(self, card_id: str) -> None:
        board = self.load()
        original = len(board["cards"])
        board["cards"] = [card for card in board["cards"] if card["id"] != card_id]
        if len(board["cards"]) == original:
            raise KeyError(card_id)
        self.save(board)

    def _normalized(self, board: dict[str, Any]) -> dict[str, Any]:
        columns = board.get("columns") or DEFAULT_COLUMNS
        column_ids = {column["id"] for column in columns}
        cards = []
        now = int(time.time())
        for index, raw in enumerate(board.get("cards", [])):
            card = {
                "id": str(raw.get("id") or uuid.uuid4().hex),
                "title": str(raw.get("title") or "Untitled").strip() or "Untitled",
                "notes": str(raw.get("notes") or "").strip(),
                "project": str(raw.get("project") or "").strip(),
                "priority": int(raw["priority"]) if raw.get("priority") in (1, 2, 3, 4) else 4,
                "column": str(raw.get("column") or columns[0]["id"]),
                "sortIndex": (
                    raw.get("sortIndex")
                    if isinstance(raw.get("sortIndex"), int) and not isinstance(raw.get("sortIndex"), bool)
                    else index
                ),
                "createdAt": int(raw.get("createdAt") or now),
                "updatedAt": int(raw.get("updatedAt") or now),
            }
            if card["column"] not in column_ids:
                card["column"] = columns[0]["id"]
            cards.append(card)
        bg_raw = (board.get("settings") or {}).get("background") or {}
        bg_type = bg_raw.get("type", "none") if bg_raw.get("type") in ("none", "url", "upload", "preset") else "none"
        fit = bg_raw.get("fit", "cover") if bg_raw.get("fit") in ("cover", "contain", "center") else "cover"
        raw_scrim = bg_raw.get("scrim", 30)
        scrim = int(raw_scrim) if isinstance(raw_scrim, (int, float)) and not isinstance(raw_scrim, bool) else 30
        scrim = max(0, min(80, scrim))
        settings = {"background": {"type": bg_type, "value": str(bg_raw.get("value") or ""), "fit": fit, "scrim": scrim}}
        return {"settings": settings, "columns": columns, "cards": cards}

    def _find_card(self, board: dict[str, Any], card_id: str) -> dict[str, Any]:
        for card in board["cards"]:
            if card["id"] == card_id:
                return card
        raise KeyError(card_id)

    def _require_column(self, board: dict[str, Any], column: str) -> None:
        if column not in {item["id"] for item in board["columns"]}:
            raise ValueError("Unknown column")
