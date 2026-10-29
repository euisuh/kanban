from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

import pytest

from app.storage import BoardStore


def test_concurrent_creates_do_not_lose_updates(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    store.load()
    threads = [Thread(target=store.create_card, args=(f"card {i}", "", "backlog")) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    titles = {c["title"] for c in store.load()["cards"]}
    assert {f"card {i}" for i in range(40)} <= titles


def test_concurrent_updates_and_deletes_keep_valid_json(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    ids = [store.create_card(f"c{i}", "", "todo")["id"] for i in range(20)]
    threads = [Thread(target=store.update_card, args=(i, {"priority": 1})) for i in ids[:10]]
    threads += [Thread(target=store.delete_card, args=(i,)) for i in ids[10:]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    board = json.loads((tmp_path / "board.json").read_text())
    remaining = {c["id"]: c for c in board["cards"]}
    assert all(remaining[i]["priority"] == 1 for i in ids[:10])
    assert not set(ids[10:]) & set(remaining)
    assert not list(tmp_path.glob(".board.json.*.tmp"))


def test_corrupt_board_is_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "board.json"
    path.write_text("{not json")
    store = BoardStore(path)
    with pytest.raises(RuntimeError, match="not valid JSON"):
        store.create_card("x", "", "backlog")
    assert path.read_text() == "{not json"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"title": "x" * 201},
        {"title": "ok", "notes": "n" * 10_001},
        {"title": "ok", "project": "p" * 65},
    ],
)
def test_create_card_rejects_oversized_text(tmp_path: Path, kwargs: dict) -> None:
    store = BoardStore(tmp_path / "board.json")
    with pytest.raises(ValueError, match="too long"):
        store.create_card(kwargs["title"], kwargs.get("notes", ""), "backlog", project=kwargs.get("project", ""))


def test_update_card_rejects_non_string_text(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    card = store.create_card("a", "", "backlog")
    for field in ("title", "notes", "project"):
        with pytest.raises(ValueError, match="must be a string"):
            store.update_card(card["id"], {field: None})
        with pytest.raises(ValueError, match="must be a string"):
            store.update_card(card["id"], {field: {"x": 1}})
    assert store.load()["cards"][-1]["title"] == "a"
