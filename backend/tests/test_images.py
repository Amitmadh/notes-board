import base64
import uuid

import pytest

from notes_board.cleanup import delete_leftover_images
from notes_board.db import get_connection

# A 1x1 pixel PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

# The server only looks at how a file starts, so the start is enough here.
FORMATS = [
    (PNG, "image/png"),
    (b"\xff\xd8\xff\xe0", "image/jpeg"),
    (b"GIF89a", "image/gif"),
]


@pytest.fixture
def board_id(client, auth_headers):
    response = client.post("/api/boards", json={"name": "Ideas"}, headers=auth_headers)
    return response.json()["id"]


def upload(client, board_id, data, headers):
    file = ("picture", data, "application/octet-stream")
    return client.post(
        f"/api/boards/{board_id}/images", files={"file": file}, headers=headers
    )


def test_uploading_needs_login(client, board_id):
    assert upload(client, board_id, PNG, headers={}).status_code == 401


@pytest.mark.parametrize(("data", "content_type"), FORMATS)
def test_uploaded_image_comes_back(client, auth_headers, board_id, data, content_type):
    response = upload(client, board_id, data, auth_headers)
    assert response.status_code == 201

    # Without the access token, like an <img> would load it.
    image = client.get(response.json()["url"])
    assert image.status_code == 200
    assert image.content == data
    assert image.headers["content-type"] == content_type
    assert image.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in image.headers["cache-control"]


@pytest.mark.parametrize("data", [b"<script>alert(1)</script>", b"<svg></svg>", b""])
def test_only_images_are_accepted(client, auth_headers, board_id, data):
    assert upload(client, board_id, data, auth_headers).status_code == 415


def test_images_are_at_most_10_mb(client, auth_headers, board_id):
    too_big = PNG + bytes(10 * 1024 * 1024)
    assert upload(client, board_id, too_big, auth_headers).status_code == 413


def test_other_users_boards_are_not_found(client, register, login, board_id):
    someone_else = login(register().json()["username"])
    assert upload(client, board_id, PNG, someone_else).status_code == 404


def test_unknown_images_are_not_found(client):
    assert client.get(f"/api/images/{uuid.uuid4()}").status_code == 404


def save_nodes(client, board_id, headers, nodes):
    content = {"background": None, "nodes": nodes}
    client.put(f"/api/boards/{board_id}/content", json=content, headers=headers)


# Runs the cleanup as if the image had been uploaded two days ago.
def clean_up_two_days_later(url):
    with get_connection() as conn:
        conn.execute(
            "UPDATE images SET created_at = created_at - interval '2 days'"
            " WHERE id = %s",
            (url.removeprefix("/api/images/"),),
        )
        delete_leftover_images(conn)


def test_cleanup_deletes_images_taken_off_their_board(client, auth_headers, board_id):
    url = upload(client, board_id, PNG, auth_headers).json()["url"]
    save_nodes(client, board_id, auth_headers, [{"type": "image", "src": url}])
    save_nodes(client, board_id, auth_headers, [])

    clean_up_two_days_later(url)
    assert client.get(url).status_code == 404


def test_cleanup_keeps_images_on_their_board(client, auth_headers, board_id):
    url = upload(client, board_id, PNG, auth_headers).json()["url"]
    save_nodes(client, board_id, auth_headers, [{"type": "image", "src": url}])

    clean_up_two_days_later(url)
    assert client.get(url).status_code == 200


def test_cleanup_keeps_new_images(client, auth_headers, board_id):
    # Uploaded, but the board isn't saved with it yet.
    url = upload(client, board_id, PNG, auth_headers).json()["url"]

    with get_connection() as conn:
        delete_leftover_images(conn)
    assert client.get(url).status_code == 200
