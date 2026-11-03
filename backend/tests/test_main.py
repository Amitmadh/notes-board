from fastapi.testclient import TestClient

from notes_board.app import app

client = TestClient(app)
