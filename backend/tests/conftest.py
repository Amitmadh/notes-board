import os
import uuid
from contextlib import contextmanager

import psycopg
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from psycopg import sql

# Tests run on a database of their own, so they never touch the boards you use.
# DB_NAME changes before the app reads it.
load_dotenv()
os.environ["DB_NAME"] += "_test"

from notes_board.app import app  # noqa: E402
from notes_board.db import CONNINFO, get_connection  # noqa: E402

PASSWORD = "test-password"


# Makes the test database afresh for each run. The app adds its tables when it
# starts.
@pytest.fixture(scope="session", autouse=True)
def database():
    name = sql.Identifier(os.environ["DB_NAME"])
    with psycopg.connect(CONNINFO, dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(name))


# A signed-in board socket, with the notes and selections it got on signing in.
# Each change returns the server's answer to it, and others' changes wait in
# self.changes.
class BoardSocket:
    def __init__(self, socket, nodes, selections):
        self.socket = socket
        self.nodes = nodes
        self.selections = selections
        self.changes = []

    def send(self, message):
        self.socket.send_json(message)
        while (reply := self.socket.receive_json())["type"] not in ("ack", "error"):
            self.changes.append(reply)
        return reply

    def next_change(self):
        return self.changes.pop(0) if self.changes else self.socket.receive_json()

    def add(self, node):
        return self.send({"type": "add_node", "node": node})

    def update(self, node_id, changes):
        return self.send({"type": "update_node", "id": node_id, "changes": changes})

    def delete(self, node_id):
        return self.send({"type": "delete_node", "id": node_id})

    def edit_text(self, node_id, update):
        return self.send({"type": "edit_text", "id": node_id, "update": update})

    # Live updates and selections get no answer.
    def live(self, node_id, changes):
        self.socket.send_json(
            {"type": "live_update", "id": node_id, "changes": changes}
        )

    def select(self, node_id):
        self.socket.send_json({"type": "select", "id": node_id})


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
        body = {"username": name, "password": PASSWORD, **fields}
        names.append(body["username"].strip())
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
            ready = socket.receive_json()
            assert ready["type"] == "ready"
            yield BoardSocket(socket, ready["nodes"], ready["selections"])

    return open_board
