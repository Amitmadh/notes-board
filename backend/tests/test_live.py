import pytest

NOTE = {"id": "note-1", "type": "rectangle", "x": 10, "y": 20}
OTHER_NOTE = {"id": "note-2", "type": "circle", "radius": 5}


def added(node):
    return {"type": "add_node", "node": node}


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
