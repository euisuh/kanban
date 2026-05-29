from pathlib import Path

import pytest

from app.storage import BoardStore


def test_store_creates_default_board(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")

    board = store.load()

    assert [column["id"] for column in board["columns"]] == ["backlog", "todo", "doing", "review", "done"]
    assert board["cards"][0]["title"] == "Make the board yours"
    assert (tmp_path / "board.json").exists()


def test_card_lifecycle_persists(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")

    card = store.create_card("Ship it", "Deploy to homeserver", "backlog")
    moved = store.update_card(card["id"], {"column": "doing", "notes": "Docker first"})

    assert moved["column"] == "doing"
    assert BoardStore(tmp_path / "board.json").load()["cards"][-1]["notes"] == "Docker first"

    store.delete_card(card["id"])

    assert card["id"] not in {item["id"] for item in store.load()["cards"]}


def test_rejects_invalid_card(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")

    with pytest.raises(ValueError):
        store.create_card("", "", "backlog")

    with pytest.raises(ValueError):
        store.create_card("Nope", "", "missing")


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
    assert card["sortIndex"] == 1


def test_update_card_project_and_priority(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    card = store.create_card("Task", "", "backlog")
    updated = store.update_card(card["id"], {"project": "Design", "priority": 2, "sortIndex": 0})
    assert updated["project"] == "Design"
    assert updated["priority"] == 2
    assert updated["sortIndex"] == 0


def test_invalid_priority_rejected(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    card = store.create_card("Task", "", "backlog")
    with pytest.raises(ValueError):
        store.update_card(card["id"], {"priority": 5})
    with pytest.raises(ValueError):
        store.update_card(card["id"], {"priority": "1"})


def test_create_card_rejects_invalid_priority(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    with pytest.raises(ValueError):
        store.create_card("Task", "", "backlog", priority=0)
    with pytest.raises(ValueError):
        store.create_card("Task", "", "backlog", priority=99)
    with pytest.raises(ValueError):
        store.create_card("Task", "", "backlog", priority="1")  # type: ignore[arg-type]


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


def test_update_settings_rejects_unsafe_background_urls(tmp_path: Path) -> None:
    store = BoardStore(tmp_path / "board.json")
    store.update_settings({"background": {"type": "upload", "value": "/uploads/abcdef123456.png", "fit": "cover"}})

    with pytest.raises(ValueError):
        store.update_settings({"background": {"type": "url", "value": "javascript:alert(1)", "fit": "cover"}})
    with pytest.raises(ValueError):
        store.update_settings({"background": {"type": "url", "value": "/uploads/abcdef123456.png", "fit": "cover"}})
    with pytest.raises(ValueError):
        store.update_settings({"background": {"type": "upload", "value": "/uploads/not-hex.png", "fit": "cover"}})
