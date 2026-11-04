import pytest


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
