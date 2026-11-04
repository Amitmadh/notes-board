import uuid

import pytest
from fastapi.testclient import TestClient

from notes_board.app import app
from notes_board.db import get_connection

PASSWORD = "pw12345"


@pytest.fixture
def client():
    # https, so the client keeps the Secure refresh cookie and sends it back.
    return TestClient(app, base_url="https://testserver")


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
            "DELETE FROM boards WHERE owner_id IN"
            " (SELECT id FROM users WHERE username = ANY(%s))",
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
