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


NOTE = {"id": "note-1", "type": "rectangle", "x": 10, "y": 20}


def notes_url(board_id):
    return f"/api/boards/{board_id}/nodes"


def saved_notes(client, board_id, headers):
    return client.get(f"/api/boards/{board_id}", headers=headers).json()["nodes"]


def test_new_board_has_no_notes_yet(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    response = client.get(f"/api/boards/{board_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Ideas"
    assert response.json()["nodes"] == []


def test_added_note_comes_back(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    response = client.post(notes_url(board_id), json=NOTE, headers=auth_headers)
    assert response.status_code == 201
    assert saved_notes(client, board_id, auth_headers) == [NOTE]


@pytest.mark.parametrize(
    "note", [{"type": "rectangle"}, {"id": "", "type": "rectangle"}, {"id": "note-1"}]
)
def test_note_needs_an_id_and_type(client, auth_headers, note):
    board_id = new_board_id(client, auth_headers)
    response = client.post(notes_url(board_id), json=note, headers=auth_headers)
    assert response.status_code == 422


def test_note_ids_are_unique_on_a_board(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    client.post(notes_url(board_id), json=NOTE, headers=auth_headers)
    response = client.post(notes_url(board_id), json=NOTE, headers=auth_headers)
    assert response.status_code == 409


# Like two people changing the same note, neither seeing the other's change.
def test_changes_to_different_fields_are_both_kept(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    client.post(notes_url(board_id), json=NOTE, headers=auth_headers)
    url = f"{notes_url(board_id)}/{NOTE['id']}"
    moved = client.patch(url, json={"x": 100, "y": 200}, headers=auth_headers)
    assert moved.status_code == 204
    client.patch(url, json={"fill": "#cd2435"}, headers=auth_headers)

    expected = {**NOTE, "x": 100, "y": 200, "fill": "#cd2435"}
    assert saved_notes(client, board_id, auth_headers) == [expected]


def test_a_notes_id_cant_change(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    client.post(notes_url(board_id), json=NOTE, headers=auth_headers)
    url = f"{notes_url(board_id)}/{NOTE['id']}"
    response = client.patch(url, json={"id": "note-2"}, headers=auth_headers)
    assert response.status_code == 422


def test_a_deleted_note_stays_deleted(client, auth_headers):
    board_id = new_board_id(client, auth_headers)
    client.post(notes_url(board_id), json=NOTE, headers=auth_headers)
    url = f"{notes_url(board_id)}/{NOTE['id']}"

    assert client.delete(url, headers=auth_headers).status_code == 204
    assert client.delete(url, headers=auth_headers).status_code == 204
    # Someone who still sees the note moves it.
    assert client.patch(url, json={"x": 1}, headers=auth_headers).status_code == 409
    assert saved_notes(client, board_id, auth_headers) == []


def test_other_users_boards_are_not_found(client, register, login, auth_headers):
    board_id = new_board_id(client, auth_headers)
    client.post(notes_url(board_id), json=NOTE, headers=auth_headers)
    someone_else = login(register().json()["username"])
    url = f"{notes_url(board_id)}/{NOTE['id']}"

    responses = [
        client.get(f"/api/boards/{board_id}", headers=someone_else),
        client.post(notes_url(board_id), json=NOTE, headers=someone_else),
        client.patch(url, json={"x": 1}, headers=someone_else),
        client.delete(url, headers=someone_else),
    ]
    assert [response.status_code for response in responses] == [404] * 4
    assert saved_notes(client, board_id, auth_headers) == [NOTE]
