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


def new_board_id(client, headers):
    response = client.post("/api/boards", json={"name": "Ideas"}, headers=headers)
    return response.json()["id"]


def test_new_board_has_no_content_yet(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    response = client.get(f"/api/boards/{board_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"id": board_id, "name": "Ideas", "content": None}


def test_saved_content_comes_back(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    content = {
        "background": "#f4f5f7",
        "nodes": [{"type": "rectangle", "x": 10, "y": 20, "width": 30, "height": 40}],
    }
    url = f"/api/boards/{board_id}/content"
    assert client.put(url, json=content, headers=auth_headers).status_code == 204

    response = client.get(f"/api/boards/{board_id}", headers=auth_headers)
    assert response.json()["content"] == content


def test_content_must_look_like_a_canvas(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    url = f"/api/boards/{board_id}/content"
    response = client.put(url, json={"nodes": "not a list"}, headers=auth_headers)
    assert response.status_code == 422


def test_other_users_boards_are_not_found(client, register, login, auth_headers):
    board_id = new_board_id(client, auth_headers)
    someone_else = login(register().json()["username"])

    response = client.get(f"/api/boards/{board_id}", headers=someone_else)
    assert response.status_code == 404
    url = f"/api/boards/{board_id}/content"
    content = {"background": None, "nodes": []}
    assert client.put(url, json=content, headers=someone_else).status_code == 404
