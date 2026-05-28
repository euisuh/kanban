from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any


DEFAULT_COLUMNS = [
    {"id": "backlog", "title": "Backlog", "accent": "#7c8a99"},
    {"id": "doing", "title": "Doing", "accent": "#2f7d6d"},
    {"id": "review", "title": "Review", "accent": "#b7791f"},
    {"id": "done", "title": "Done", "accent": "#5762b7"},
]


def default_board() -> dict[str, Any]:
    now = int(time.time())
    return {
        "columns": DEFAULT_COLUMNS,
        "cards": [
            {
                "id": "welcome",
                "title": "Make the board yours",
                "notes": "Add cards, drag them between columns, and keep the JSON file backed up.",
                "column": "backlog",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
    }


@dataclass
class BoardStore:
    path: Path

    def __post_init__(self) -> None:
        self._lock = RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                board = default_board()
                self.save(board)
                return board

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

    def create_card(self, title: str, notes: str, column: str) -> dict[str, Any]:
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
            "column": column,
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
        if "column" in patch:
            column = str(patch["column"])
            self._require_column(board, column)
            card["column"] = column
        card["updatedAt"] = int(time.time())
        self.save(board)
        return card

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
        for raw in board.get("cards", []):
            card = {
                "id": str(raw.get("id") or uuid.uuid4().hex),
                "title": str(raw.get("title") or "Untitled").strip() or "Untitled",
                "notes": str(raw.get("notes") or "").strip(),
                "column": str(raw.get("column") or columns[0]["id"]),
                "createdAt": int(raw.get("createdAt") or now),
                "updatedAt": int(raw.get("updatedAt") or now),
            }
            if card["column"] not in column_ids:
                card["column"] = columns[0]["id"]
            cards.append(card)
        return {"columns": columns, "cards": cards}

    def _find_card(self, board: dict[str, Any], card_id: str) -> dict[str, Any]:
        for card in board["cards"]:
            if card["id"] == card_id:
                return card
        raise KeyError(card_id)

    def _require_column(self, board: dict[str, Any], column: str) -> None:
        if column not in {item["id"] for item in board["columns"]}:
            raise ValueError("Unknown column")
