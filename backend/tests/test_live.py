import threading
import time
from base64 import b64decode, b64encode

import pytest
from pycrdt import Doc, Text

from notes_board.db import get_connection
from notes_board.routers.nodes import edit_text

NOTE = {
    "id": "note-1",
    "type": "rectangle",
    "x": 10,
    "y": 20,
    "width": 30,
    "height": 40,
}
OTHER_NOTE = {"id": "note-2", "type": "circle", "radius": 5}
TEXT_NOTE = {"id": "note-3", "type": "text", "text": "note"}


# What a browser sends when its user types into a note that says first_text: a Yjs
# update on top of the state every client builds from the note's first text.
def typed(first_text, index, added_text):
    first = Doc(client_id=0)
    first.get("text", type=Text).insert(0, first_text)
    doc = Doc()
    doc.apply_update(first.get_update())
    before = doc.get_state()
    doc.get("text", type=Text).insert(index, added_text)
    return b64encode(doc.get_update(before)).decode()


def added(node):
    return {"type": "add_node", "node": node}


# The message without its sender's peer id, which tests can't know in advance.
def without_peer(message):
    assert isinstance(message.pop("peer"), int)
    return message


@pytest.fixture
def board_id(client, auth_headers):
    response = client.post("/api/boards", json={"name": "Live"}, headers=auth_headers)
    return response.json()["id"]


def test_signing_in_sends_the_saved_notes(auth_headers, open_board, board_id):
    with open_board(board_id, auth_headers) as board:
        assert board.nodes == []
        board.add(NOTE)
    with open_board(board_id, auth_headers) as board:
        assert board.nodes == [NOTE]


def test_changes_are_sent_to_the_boards_other_sockets(
    auth_headers, open_board, board_id
):
    with (
        open_board(board_id, auth_headers) as mine,
        open_board(board_id, auth_headers) as theirs,
    ):
        mine.add(NOTE)
        mine.update(NOTE["id"], {"x": 50})
        mine.delete(NOTE["id"])

        assert theirs.next_change() == added(NOTE)
        assert theirs.next_change() == {
            "type": "update_node",
            "id": NOTE["id"],
            "changes": {"x": 50},
        }
        assert theirs.next_change() == {"type": "delete_node", "id": NOTE["id"]}


def test_a_change_isnt_sent_back_to_its_sender(auth_headers, open_board, board_id):
    with (
        open_board(board_id, auth_headers) as mine,
        open_board(board_id, auth_headers) as theirs,
    ):
        mine.add(NOTE)
        theirs.add(OTHER_NOTE)
        assert mine.next_change() == added(OTHER_NOTE)


def test_rejected_changes_arent_sent(auth_headers, open_board, board_id):
    with (
        open_board(board_id, auth_headers) as mine,
        open_board(board_id, auth_headers) as theirs,
    ):
        assert mine.update("missing", {"x": 1})["code"] == "gone"
        mine.add(NOTE)
        assert theirs.next_change() == added(NOTE)


def test_other_boards_dont_get_the_changes(client, auth_headers, open_board, board_id):
    response = client.post("/api/boards", json={"name": "Other"}, headers=auth_headers)
    other_board_id = response.json()["id"]
    with (
        open_board(board_id, auth_headers) as here,
        open_board(other_board_id, auth_headers) as there,
        open_board(other_board_id, auth_headers) as also_there,
    ):
        here.add(NOTE)
        also_there.add(OTHER_NOTE)
        assert there.next_change() == added(OTHER_NOTE)


def test_live_updates_are_sent_on_but_not_saved(auth_headers, open_board, board_id):
    with (
        open_board(board_id, auth_headers) as mine,
        open_board(board_id, auth_headers) as theirs,
    ):
        mine.add(NOTE)
        mine.live(NOTE["id"], {"x": 50})
        assert theirs.next_change() == added(NOTE)
        assert without_peer(theirs.next_change()) == {
            "type": "live_update",
            "id": NOTE["id"],
            "changes": {"x": 50},
        }
    with open_board(board_id, auth_headers) as board:
        assert board.nodes == [NOTE]


def test_live_updates_and_selections_get_no_answer(auth_headers, open_board, board_id):
    with (
        open_board(board_id, auth_headers) as mine,
        open_board(board_id, auth_headers) as theirs,
    ):
        mine.live(NOTE["id"], {"x": 50})
        mine.select(NOTE["id"])
        theirs.add(OTHER_NOTE)
        assert mine.next_change() == added(OTHER_NOTE)


def test_selections_are_sent_with_the_username(
    client, auth_headers, open_board, board_id
):
    username = client.get("/api/users/me/", headers=auth_headers).json()["username"]
    with (
        open_board(board_id, auth_headers) as mine,
        open_board(board_id, auth_headers) as theirs,
    ):
        mine.select(NOTE["id"])
        assert without_peer(theirs.next_change()) == {
            "type": "select",
            "username": username,
            "id": NOTE["id"],
        }
        with open_board(board_id, auth_headers) as later:
            assert [without_peer(selection) for selection in later.selections] == [
                {"username": username, "id": NOTE["id"]}
            ]

        mine.select(None)
        assert theirs.next_change()["id"] is None
        with open_board(board_id, auth_headers) as later:
            assert later.selections == []


def test_others_hear_when_a_selecting_socket_leaves(auth_headers, open_board, board_id):
    with open_board(board_id, auth_headers) as theirs:
        with open_board(board_id, auth_headers) as mine:
            mine.select(NOTE["id"])
            peer = theirs.next_change()["peer"]
        assert theirs.next_change() == {"type": "left", "peer": peer}


def test_invalid_live_updates_are_rejected(auth_headers, open_board, board_id):
    with open_board(board_id, auth_headers) as board:
        reply = board.send({"type": "live_update", "id": NOTE["id"]})
        assert reply["code"] == "invalid"


def test_text_typed_at_the_same_time_merges(auth_headers, open_board, board_id):
    with (
        open_board(board_id, auth_headers) as mine,
        open_board(board_id, auth_headers) as theirs,
    ):
        mine.add(TEXT_NOTE)
        # each typed without having seen the other's edit
        my_edit = typed("note", 0, "my ")
        their_edit = typed("note", 4, " theirs")
        assert mine.edit_text(TEXT_NOTE["id"], my_edit) == {"type": "ack"}
        assert theirs.edit_text(TEXT_NOTE["id"], their_edit) == {"type": "ack"}

        assert theirs.next_change() == added(TEXT_NOTE)
        assert theirs.next_change() == {
            "type": "edit_text",
            "id": TEXT_NOTE["id"],
            "update": my_edit,
        }
    with open_board(board_id, auth_headers) as board:
        (note,) = board.nodes
        assert note["text"] == "my note theirs"


# Two servers merge into one note at once, as if both held its board.
def test_merges_into_one_note_wait_for_each_other(auth_headers, open_board, board_id):
    with open_board(board_id, auth_headers) as board:
        board.add(TEXT_NOTE)

    def their_server():
        with get_connection() as db:
            update = b64decode(typed("note", 4, " theirs"))
            edit_text(db, board_id, TEXT_NOTE["id"], update)

    other_server = threading.Thread(target=their_server)
    with get_connection() as db:
        update = b64decode(typed("note", 0, "my "))
        edit_text(db, board_id, TEXT_NOTE["id"], update)
        other_server.start()
        time.sleep(0.2)  # their merge starts before mine is saved
    other_server.join()
    with open_board(board_id, auth_headers) as board:
        assert board.nodes[0]["text"] == "my note theirs"


def test_a_text_edit_sent_twice_is_applied_once(auth_headers, open_board, board_id):
    with open_board(board_id, auth_headers) as board:
        board.add(TEXT_NOTE)
        edit = typed("note", 4, "s")
        board.edit_text(TEXT_NOTE["id"], edit)
        board.edit_text(TEXT_NOTE["id"], edit)
    with open_board(board_id, auth_headers) as board:
        assert board.nodes[0]["text"] == "notes"


def test_text_edits_need_a_text_note(auth_headers, open_board, board_id):
    with open_board(board_id, auth_headers) as board:
        board.add(NOTE)
        for node_id in (NOTE["id"], "no-such-note"):
            reply = board.edit_text(node_id, typed("", 0, "hello"))
            assert reply["code"] == "gone"
    with open_board(board_id, auth_headers) as board:
        assert board.nodes == [NOTE]


@pytest.mark.parametrize("update", ["not base64!", b64encode(b"not yjs").decode()])
def test_invalid_text_edits_are_rejected(auth_headers, open_board, board_id, update):
    with open_board(board_id, auth_headers) as board:
        board.add(TEXT_NOTE)
        assert board.edit_text(TEXT_NOTE["id"], update)["code"] == "invalid"
    with open_board(board_id, auth_headers) as board:
        assert board.nodes == [TEXT_NOTE]


def test_a_note_holds_a_limited_text(auth_headers, open_board, board_id, monkeypatch):
    monkeypatch.setattr("notes_board.routers.nodes.MAX_NOTE_TEXT", 6)
    with open_board(board_id, auth_headers) as board:
        board.add(TEXT_NOTE)
        assert board.edit_text(TEXT_NOTE["id"], typed("note", 4, "s!")) == {
            "type": "ack"
        }
        # typed by someone who hasn't seen that edit: "a notes!" is too long
        assert (
            board.edit_text(TEXT_NOTE["id"], typed("note", 0, "a "))["code"] == "full"
        )
    with open_board(board_id, auth_headers) as board:
        assert board.nodes[0]["text"] == "notes!"
