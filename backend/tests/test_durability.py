import json
import socket
import subprocess
import sys
import time
from base64 import b64encode
from contextlib import contextmanager

import pytest
from pycrdt import Doc, Text
from websockets.sync.client import connect

ACK = {"type": "ack"}
TEXT_NOTE = {"id": "text", "type": "text", "text": ""}
TYPED = "nothing acknowledged is lost"


# Runs the app in a process of its own, so the test can kill it.
@contextmanager
def server():
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "notes_board.app:app", "--port", str(port)]
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                socket.create_connection(("127.0.0.1", port)).close()
                break
            except OSError:
                assert time.monotonic() < deadline, "the server didn't start"
                time.sleep(0.1)
        yield process, f"ws://127.0.0.1:{port}"
    finally:
        process.kill()
        process.wait()


@contextmanager
def open_board(url, board_id, token):
    with connect(f"{url}/api/boards/{board_id}/ws") as board:
        board.send(json.dumps({"type": "auth", "token": token}))
        yield board, json.loads(board.recv())["nodes"]


def save(board, change):
    board.send(json.dumps(change))
    return json.loads(board.recv())


@pytest.fixture
def board_id(client, auth_headers):
    response = client.post("/api/boards", json={"name": "Crash"}, headers=auth_headers)
    return response.json()["id"]


# Adds and moves notes and types into one, and kills the server the moment its
# last ack arrives: after a restart, every acknowledged change is there.
def test_acknowledged_changes_survive_a_crash(auth_headers, board_id):
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    doc = Doc()
    text = doc.get("text", type=Text)
    notes = {}
    with server() as (process, url), open_board(url, board_id, token) as (board, _):
        assert save(board, {"type": "add_node", "node": TEXT_NOTE}) == ACK
        for i, char in enumerate(TYPED):
            note = {"id": f"note-{i}", "type": "rectangle", "width": 10, "height": 10}
            assert save(board, {"type": "add_node", "node": note}) == ACK
            moved = {"x": i, "y": i}
            update = {"type": "update_node", "id": note["id"], "changes": moved}
            assert save(board, update) == ACK
            notes[note["id"]] = note | moved
            before = doc.get_state()
            text.insert(len(text), char)
            typed = b64encode(doc.get_update(before)).decode()
            edit = {"type": "edit_text", "id": "text", "update": typed}
            assert save(board, edit) == ACK
        process.kill()

    with server() as (_, url), open_board(url, board_id, token) as (_, nodes):
        saved = {node["id"]: node for node in nodes}
    assert saved.pop("text")["text"] == TYPED
    assert saved == notes
