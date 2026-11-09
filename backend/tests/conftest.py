import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from notes_board.app import app
from notes_board.db import get_connection

PASSWORD = "pw12345"


# A signed-in board socket. Each change returns the server's answer to it.
class BoardSocket:
    def __init__(self, socket):
        self.socket = socket

    def send(self, message):
        self.socket.send_json(message)
        return self.socket.receive_json()

    def add(self, node):
        return self.send({"type": "add_node", "node": node})

    def update(self, node_id, changes):
        return self.send({"type": "update_node", "id": node_id, "changes": changes})

    def delete(self, node_id):
        return self.send({"type": "delete_node", "id": node_id})


@pytest.fixture
def client():
    # https, so the client keeps the Secure refresh cookie and sends it back.
    # The with runs the app's startup, which opens the connection pool.
    with TestClient(app, base_url="https://testserver") as client:
        yield client


# Registers users with fresh names, and deletes them and their boards afterwards.
@pytest.fixture
def register(client):
    names = []

    def register(**fields):
        name = f"test_{uuid.uuid4().hex[:8]}"
        names.append(name)
        body = {"username": name, "password": PASSWORD, **fields}
        return client.post("/api/register", json=body)

    yield register

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM boards WHERE id IN (SELECT board_id FROM board_members"
            " JOIN users ON users.id = board_members.user_id"
            " WHERE board_members.role = 'owner' AND users.username = ANY(%s))",
            (names,),
        )
        conn.execute("DELETE FROM users WHERE username = ANY(%s)", (names,))


# Logs a user in and returns the headers that authorize their requests.
@pytest.fixture
def login(client):
    def login(username):
        response = client.post(
            "/api/login", data={"username": username, "password": PASSWORD}
        )
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return login


@pytest.fixture
def auth_headers(register, login):
    return login(register().json()["username"])


# Opens a board's socket and signs in with the token, like the board page does.
@pytest.fixture
def connect(client):
    @contextmanager
    def connect(board_id, token):
        with client.websocket_connect(f"/api/boards/{board_id}/ws") as socket:
            socket.send_json({"type": "auth", "token": token})
            yield socket

    return connect


# Opens a board's socket for the user the headers authorize.
@pytest.fixture
def open_board(connect):
    @contextmanager
    def open_board(board_id, headers):
        token = headers["Authorization"].removeprefix("Bearer ")
        with connect(board_id, token) as socket:
            assert socket.receive_json() == {"type": "ready"}
            yield BoardSocket(socket)

    return open_board
