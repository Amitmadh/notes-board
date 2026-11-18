import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import WebSocketDisconnect

from notes_board.auth import verify_password
from notes_board.config import PASSWORDS_HASHED_AT_ONCE
from notes_board.db import get_connection
from notes_board.routers.nodes import UNAUTHORIZED


def test_register_returns_the_user_without_the_password(register):
    response = register(full_name="Test User")
    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Test User"
    assert body["disabled"] is False
    assert "hashed_password" not in body


def test_register_rejects_a_taken_username(client, register):
    name = register().json()["username"]
    response = client.post(
        "/api/register", json={"username": name, "password": "another-password"}
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "fields",
    [
        {"username": "ab"},
        {"username": "  ab  "},
        {"username": "a" * 33},
        {"password": "1234567"},
        {"full_name": "a" * 101},
    ],
)
def test_register_refuses_names_and_passwords_out_of_range(register, fields):
    assert register(**fields).status_code == 422


def test_a_username_is_saved_trimmed(client, register):
    name = f"test_{uuid.uuid4().hex[:8]}"
    response = register(username=f"  {name} ", password="right-password")
    assert response.json()["username"] == name
    # signing in trims it too
    response = client.post(
        "/api/login", data={"username": f" {name}  ", "password": "right-password"}
    )
    assert response.status_code == 200


def test_only_a_few_passwords_are_hashed_at_once(client, register, monkeypatch):
    name = register(password="right-password").json()["username"]
    hashing = most = 0
    lock = threading.Lock()

    def slow_verify(password, hashed_password):
        nonlocal hashing, most
        with lock:
            hashing += 1
            most = max(most, hashing)
        time.sleep(0.05)
        with lock:
            hashing -= 1
        return verify_password(password, hashed_password)

    monkeypatch.setattr("notes_board.auth.verify_password", slow_verify)
    form = {"username": name, "password": "right-password"}
    with ThreadPoolExecutor(8) as threads:
        responses = threads.map(
            lambda _: client.post("/api/login", data=form), range(8)
        )
        assert [response.status_code for response in responses] == [200] * 8
    assert most == PASSWORDS_HASHED_AT_ONCE


def test_login_sets_a_secure_refresh_cookie(client, register):
    name = register(password="right-password").json()["username"]
    response = client.post(
        "/api/login", data={"username": name, "password": "right-password"}
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    cookie = response.headers["set-cookie"].lower()
    for attribute in ("httponly", "secure", "samesite=strict", "path=/api/refresh"):
        assert attribute in cookie


def test_login_does_not_reveal_which_part_is_wrong(client, register):
    name = register(password="right-password").json()["username"]
    wrong_password = client.post(
        "/api/login", data={"username": name, "password": "wrong-password"}
    )
    unknown_user = client.post(
        "/api/login", data={"username": "test_nobody", "password": "right-password"}
    )
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


def test_me_returns_the_signed_in_user(client, register, login):
    name = register().json()["username"]
    response = client.get("/api/users/me/", headers=login(name))
    assert response.status_code == 200
    assert response.json()["username"] == name


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-token"}])
def test_me_needs_a_valid_token(client, headers):
    assert client.get("/api/users/me/", headers=headers).status_code == 401


def test_refresh_gives_a_working_access_token(client, register, login):
    login(register().json()["username"])
    response = client.post("/api/refresh")
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/api/users/me/", headers=headers).status_code == 200


def test_tokens_only_work_for_their_own_purpose(client, register, login):
    headers = login(register().json()["username"])
    access_token = headers["Authorization"].removeprefix("Bearer ")
    refresh_token = client.cookies["refresh_token"]

    # A refresh token can't authorize requests...
    headers = {"Authorization": f"Bearer {refresh_token}"}
    response = client.get("/api/users/me/", headers=headers)
    assert response.status_code == 401

    # ...and an access token can't get new tokens.
    client.cookies.clear()
    headers = {"Cookie": f"refresh_token={access_token}"}
    response = client.post("/api/refresh", headers=headers)
    assert response.status_code == 401
    # Not "Not signed in", so the token really was sent and checked.
    assert response.json()["detail"] == "Could not validate credentials"


def test_logout_ends_the_session(client, register, login):
    login(register().json()["username"])
    assert client.post("/api/logout").status_code == 204
    assert client.post("/api/refresh").status_code == 401


def test_disabled_user_is_locked_out(client, register, login, connect):
    name = register().json()["username"]
    headers = login(name)
    board = client.post("/api/boards", json={"name": "Ideas"}, headers=headers)
    with get_connection() as conn:
        conn.execute("UPDATE users SET disabled = TRUE WHERE username = %s", (name,))

    assert client.get("/api/users/me/", headers=headers).status_code == 400
    assert client.post("/api/refresh").status_code == 403
    token = headers["Authorization"].removeprefix("Bearer ")
    with (
        connect(board.json()["id"], token) as socket,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        socket.receive_json()
    assert closed.value.code == UNAUTHORIZED
