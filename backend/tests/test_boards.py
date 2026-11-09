from datetime import timedelta

import pytest
from fastapi import WebSocketDisconnect

from notes_board.auth import create_token
from notes_board.routers.nodes import BAD_REQUEST, NO_ACCESS, UNAUTHORIZED


def test_boards_need_login(client):
    assert client.get("/api/boards").status_code == 401
    assert client.post("/api/boards", json={"name": "Ideas"}).status_code == 401


def test_create_board_trims_the_name(client, auth_headers):
    response = client.post(
        "/api/boards", json={"name": "  Ideas  "}, headers=auth_headers
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Ideas"


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": "   "}])
def test_create_board_needs_a_name(client, auth_headers, body):
    response = client.post("/api/boards", json=body, headers=auth_headers)
    assert response.status_code == 422


def test_boards_are_listed_in_creation_order(client, auth_headers):
    assert client.get("/api/boards", headers=auth_headers).json() == []
    created = [
        client.post("/api/boards", json={"name": name}, headers=auth_headers).json()
        for name in ("First", "Second")
    ]
    response = client.get("/api/boards", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == created


def test_users_only_see_their_own_boards(client, register, login, auth_headers):
    client.post("/api/boards", json={"name": "Private"}, headers=auth_headers)
    someone_else = login(register().json()["username"])
    assert client.get("/api/boards", headers=someone_else).json() == []


def new_board_id(client, headers):
    response = client.post("/api/boards", json={"name": "Ideas"}, headers=headers)
    return response.json()["id"]


NOTE = {"id": "note-1", "type": "rectangle", "x": 10, "y": 20}
ACK = {"type": "ack"}


def saved_notes(client, board_id, headers):
    return client.get(f"/api/boards/{board_id}", headers=headers).json()["nodes"]


def closed_with(socket):
    with pytest.raises(WebSocketDisconnect) as closed:
        socket.receive_json()
    return closed.value.code


def test_new_board_has_no_notes_yet(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    response = client.get(f"/api/boards/{board_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Ideas"
    assert response.json()["nodes"] == []


def test_added_note_comes_back(client, auth_headers, open_board):
    board_id = new_board_id(client, auth_headers)
    with open_board(board_id, auth_headers) as board:
        assert board.add(NOTE) == ACK
    assert saved_notes(client, board_id, auth_headers) == [NOTE]


@pytest.mark.parametrize(
    "note", [{"type": "rectangle"}, {"id": "", "type": "rectangle"}, {"id": "note-1"}]
)
def test_note_needs_an_id_and_type(client, auth_headers, open_board, note):
    board_id = new_board_id(client, auth_headers)
    with open_board(board_id, auth_headers) as board:
        assert board.add(note)["code"] == "invalid"


def test_a_rejected_change_leaves_the_socket_open(client, auth_headers, open_board):
    board_id = new_board_id(client, auth_headers)
    with open_board(board_id, auth_headers) as board:
        answer = board.send({"type": "rename_node", "id": NOTE["id"]})
        assert answer["code"] == "invalid"
        assert board.add(NOTE) == ACK


def test_note_ids_are_unique_on_a_board(client, auth_headers, open_board):
    board_id = new_board_id(client, auth_headers)
    with open_board(board_id, auth_headers) as board:
        board.add(NOTE)
        assert board.add(NOTE)["code"] == "exists"


# Like two people changing the same note, neither seeing the other's change.
def test_changes_to_different_fields_are_both_kept(client, auth_headers, open_board):
    board_id = new_board_id(client, auth_headers)
    with (
        open_board(board_id, auth_headers) as first,
        open_board(board_id, auth_headers) as second,
    ):
        first.add(NOTE)
        assert first.update(NOTE["id"], {"x": 100, "y": 200}) == ACK
        assert second.update(NOTE["id"], {"fill": "#cd2435"}) == ACK

    expected = {**NOTE, "x": 100, "y": 200, "fill": "#cd2435"}
    assert saved_notes(client, board_id, auth_headers) == [expected]


def test_a_notes_id_cant_change(client, auth_headers, open_board):
    board_id = new_board_id(client, auth_headers)
    with open_board(board_id, auth_headers) as board:
        board.add(NOTE)
        assert board.update(NOTE["id"], {"id": "note-2"})["code"] == "invalid"
    assert saved_notes(client, board_id, auth_headers) == [NOTE]


def test_a_deleted_note_stays_deleted(client, auth_headers, open_board):
    board_id = new_board_id(client, auth_headers)
    with open_board(board_id, auth_headers) as board:
        board.add(NOTE)
        assert board.delete(NOTE["id"]) == ACK
        assert board.delete(NOTE["id"]) == ACK
        # Someone who still sees the note moves it.
        assert board.update(NOTE["id"], {"x": 1})["code"] == "gone"
    assert saved_notes(client, board_id, auth_headers) == []


def test_other_users_boards_are_not_found(
    client, register, login, auth_headers, connect, open_board
):
    board_id = new_board_id(client, auth_headers)
    with open_board(board_id, auth_headers) as board:
        board.add(NOTE)
    someone_else = login(register().json()["username"])
    token = someone_else["Authorization"].removeprefix("Bearer ")

    response = client.get(f"/api/boards/{board_id}", headers=someone_else)
    assert response.status_code == 404
    with connect(board_id, token) as socket:
        assert closed_with(socket) == NO_ACCESS
    assert saved_notes(client, board_id, auth_headers) == [NOTE]


def test_unknown_boards_are_not_found(connect, auth_headers):
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    with connect(0, token) as socket:
        assert closed_with(socket) == NO_ACCESS


def test_the_socket_needs_a_valid_token(client, auth_headers, connect):
    board_id = new_board_id(client, auth_headers)
    with connect(board_id, "not-a-token") as socket:
        assert closed_with(socket) == UNAUTHORIZED


# The board page gets a new token and connects again when it sees this.
def test_the_socket_turns_down_expired_tokens(client, register, login, connect):
    name = register().json()["username"]
    board_id = new_board_id(client, login(name))
    token = create_token({"sub": name}, timedelta(minutes=-1), kind="access")
    with connect(board_id, token) as socket:
        assert closed_with(socket) == UNAUTHORIZED


def test_the_first_message_must_sign_in(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    with client.websocket_connect(f"/api/boards/{board_id}/ws") as socket:
        socket.send_json({"type": "add_node", "node": NOTE})
        assert closed_with(socket) == BAD_REQUEST
    assert saved_notes(client, board_id, auth_headers) == []
