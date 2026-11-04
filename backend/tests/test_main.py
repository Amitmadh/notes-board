from fastapi.testclient import TestClient

from notes_board.app import app

client = TestClient(app)


def test_boards_need_login():
    response = client.get("/api/boards")
    assert response.status_code == 401
