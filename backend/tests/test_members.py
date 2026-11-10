import uuid
from typing import NamedTuple

import psycopg
import pytest
from fastapi import WebSocketDisconnect

from notes_board.db import get_connection
from notes_board.routers.nodes import NO_ACCESS

NOTE = {"id": "note-1", "type": "rectangle", "x": 10, "y": 20}
ACK = {"type": "ack"}


class User(NamedTuple):
    name: str
    headers: dict[str, str]


@pytest.fixture
def new_user(register, login):
    def new_user():
        name = register().json()["username"]
        return User(name, login(name))

    return new_user


@pytest.fixture
def alice(new_user):
    return new_user()


@pytest.fixture
def bob(new_user):
    return new_user()


# Alice's board.
@pytest.fixture
def board_id(client, alice):
    response = client.post(
        "/api/boards", json={"name": "Shared"}, headers=alice.headers
    )
    return response.json()["id"]


def members_url(board_id):
    return f"/api/boards/{board_id}/members"


def share(client, board_id, by, username):
    body = {"username": username}
    return client.post(members_url(board_id), json=body, headers=by.headers)


def test_shared_board_is_listed_with_its_owner(client, alice, bob, board_id):
    response = share(client, board_id, alice, bob.name)
    assert response.status_code == 201
    assert response.json()["username"] == bob.name

    boards = client.get("/api/boards", headers=bob.headers).json()
    assert boards == [{"id": board_id, "name": "Shared", "owner": alice.name}]


def test_members_can_edit_the_board(client, open_board, alice, bob, board_id):
    share(client, board_id, alice, bob.name)

    with (
        open_board(board_id, bob.headers) as bobs_board,
        open_board(board_id, alice.headers) as alices_board,
    ):
        assert bobs_board.add(NOTE) == ACK
        assert alices_board.update(NOTE["id"], {"x": 50}) == ACK
    board = client.get(f"/api/boards/{board_id}", headers=bob.headers).json()
    assert board["nodes"] == [{**NOTE, "x": 50}]

    picture = ("picture", b"\x89PNG\r\n\x1a\n", "image/png")
    upload = client.post(
        f"/api/boards/{board_id}/images", files={"file": picture}, headers=bob.headers
    )
    assert upload.status_code == 201


def test_members_are_listed(client, alice, bob, board_id):
    share(client, board_id, alice, bob.name)
    response = client.get(members_url(board_id), headers=bob.headers)
    assert response.json() == [{"username": bob.name, "full_name": None}]


def test_only_the_owner_can_share(client, new_user, alice, bob, board_id):
    share(client, board_id, alice, bob.name)
    carol = new_user()
    assert share(client, board_id, bob, carol.name).status_code == 403


def test_sharing_needs_someone_new(client, alice, bob, board_id):
    unknown = f"missing_{uuid.uuid4().hex}"
    assert share(client, board_id, alice, unknown).status_code == 404
    assert share(client, board_id, alice, alice.name).status_code == 409
    share(client, board_id, alice, bob.name)
    assert share(client, board_id, alice, bob.name).status_code == 409


def test_removed_members_lose_access(client, alice, bob, board_id):
    share(client, board_id, alice, bob.name)
    url = f"{members_url(board_id)}/{bob.name}"

    assert client.delete(url, headers=alice.headers).status_code == 204
    board = client.get(f"/api/boards/{board_id}", headers=bob.headers)
    assert board.status_code == 404
    assert client.get("/api/boards", headers=bob.headers).json() == []
    assert client.delete(url, headers=alice.headers).status_code == 404


# Bob still has the board open when he's removed.
def test_removed_members_cant_keep_editing(client, open_board, alice, bob, board_id):
    share(client, board_id, alice, bob.name)

    with open_board(board_id, bob.headers) as board:
        assert board.add(NOTE) == ACK
        client.delete(f"{members_url(board_id)}/{bob.name}", headers=alice.headers)
        with pytest.raises(WebSocketDisconnect) as closed:
            board.update(NOTE["id"], {"x": 50})
    assert closed.value.code == NO_ACCESS
    board = client.get(f"/api/boards/{board_id}", headers=alice.headers).json()
    assert board["nodes"] == [NOTE]


# Bob is watching the board when he's removed.
def test_removed_members_stop_getting_changes(client, open_board, alice, bob, board_id):
    share(client, board_id, alice, bob.name)

    with (
        open_board(board_id, alice.headers) as alices_board,
        open_board(board_id, bob.headers) as bobs_board,
    ):
        client.delete(f"{members_url(board_id)}/{bob.name}", headers=alice.headers)
        assert alices_board.add(NOTE) == ACK
        with pytest.raises(WebSocketDisconnect) as closed:
            bobs_board.next_change()
    assert closed.value.code == NO_ACCESS


def test_members_can_leave_but_not_remove_others(
    client, new_user, alice, bob, board_id
):
    carol = new_user()
    share(client, board_id, alice, bob.name)
    share(client, board_id, alice, carol.name)

    remove_carol = client.delete(
        f"{members_url(board_id)}/{carol.name}", headers=bob.headers
    )
    assert remove_carol.status_code == 403
    leave = client.delete(f"{members_url(board_id)}/{bob.name}", headers=bob.headers)
    assert leave.status_code == 204
    board = client.get(f"/api/boards/{board_id}", headers=bob.headers)
    assert board.status_code == 404


def test_the_owner_cant_leave(client, alice, board_id):
    url = f"{members_url(board_id)}/{alice.name}"
    assert client.delete(url, headers=alice.headers).status_code == 409
    board = client.get(f"/api/boards/{board_id}", headers=alice.headers)
    assert board.status_code == 200


def test_the_owner_can_delete_the_board(client, open_board, alice, bob, board_id):
    share(client, board_id, alice, bob.name)
    with open_board(board_id, alice.headers) as board:
        assert board.add(NOTE) == ACK
    response = client.delete(f"/api/boards/{board_id}", headers=alice.headers)
    assert response.status_code == 204
    for user in (alice, bob):
        board = client.get(f"/api/boards/{board_id}", headers=user.headers)
        assert board.status_code == 404
        assert client.get("/api/boards", headers=user.headers).json() == []


def test_only_the_owner_can_delete_the_board(client, new_user, alice, bob, board_id):
    share(client, board_id, alice, bob.name)
    url = f"/api/boards/{board_id}"
    assert client.delete(url, headers=bob.headers).status_code == 403
    assert client.delete(url, headers=new_user().headers).status_code == 404
    assert client.get(url, headers=alice.headers).status_code == 200


def test_a_board_has_only_one_owner(bob, board_id):
    with pytest.raises(psycopg.errors.UniqueViolation), get_connection() as conn:
        conn.execute(
            "INSERT INTO board_members (board_id, user_id, role)"
            " SELECT %s, id, 'owner' FROM users WHERE username = %s",
            (board_id, bob.name),
        )
