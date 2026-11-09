import pytest

NOTE = {"id": "note-1", "type": "rectangle", "x": 10, "y": 20}
OTHER_NOTE = {"id": "note-2", "type": "circle", "radius": 5}


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
