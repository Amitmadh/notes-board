from typing import Any

import psycopg  # noqa: TC002
from fastapi import (
    APIRouter,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
)
from fastapi.concurrency import run_in_threadpool
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool  # noqa: TC002
from pydantic import ValidationError

from notes_board.access import find_board_access
from notes_board.auth import user_from_token
from notes_board.schemas import (
    AddNode,
    DeleteNode,
    Node,
    NodeChange,
    SocketAuth,
    UpdateNode,
)

router = APIRouter(prefix="/api", tags=["nodes"])

# close codes the board page acts on
UNAUTHORIZED = 4401
NO_ACCESS = 4404
BAD_REQUEST = 4400


class Rejected(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def add_node(db: psycopg.Connection, board_id: int, node: Node) -> None:
    inserted = db.execute(
        "INSERT INTO board_nodes (board_id, node_id, data) VALUES (%s, %s, %s)"
        " ON CONFLICT DO NOTHING",
        (board_id, node.id, Jsonb(node.model_dump())),
    ).rowcount
    if inserted == 0:
        raise Rejected("exists", "A note with this id already exists")


def update_node(
    db: psycopg.Connection, board_id: int, node_id: str, changes: dict[str, Any]
) -> None:
    if "id" in changes:
        raise Rejected("invalid", "A note's id can't change")
    updated = db.execute(
        "UPDATE board_nodes SET data = data || %s WHERE board_id = %s AND node_id = %s",
        (Jsonb(changes), board_id, node_id),
    ).rowcount
    if updated == 0:
        raise Rejected("gone", "This note was deleted")


def delete_node(db: psycopg.Connection, board_id: int, node_id: str) -> None:
    db.execute(
        "DELETE FROM board_nodes WHERE board_id = %s AND node_id = %s",
        (board_id, node_id),
    )


def sign_in(pool: ConnectionPool, board_id: int, message: str) -> int:
    try:
        token = SocketAuth.model_validate_json(message).token
    except ValidationError as err:
        raise WebSocketException(BAD_REQUEST, "The first message must sign in") from err
    with pool.connection() as db:
        try:
            user = user_from_token(db, token, kind="access")
        except HTTPException as err:
            raise WebSocketException(UNAUTHORIZED, err.detail) from err
        if user.disabled:
            raise WebSocketException(UNAUTHORIZED, "Inactive user")
        if find_board_access(db, board_id, user.id) is None:
            raise WebSocketException(NO_ACCESS, "Board not found")
    return user.id


def answer_change(
    pool: ConnectionPool, board_id: int, user_id: int, message: str
) -> dict[str, Any]:
    try:
        change = NodeChange.validate_json(message)
        with pool.connection() as db:
            if find_board_access(db, board_id, user_id) is None:
                raise WebSocketException(NO_ACCESS, "Board not found")
            match change:
                case AddNode(node=node):
                    add_node(db, board_id, node)
                case UpdateNode(id=node_id, changes=changes):
                    update_node(db, board_id, node_id, changes)
                case DeleteNode(id=node_id):
                    delete_node(db, board_id, node_id)
            db.commit()
    except ValidationError as err:
        detail = err.errors(
            include_url=False, include_context=False, include_input=False
        )
        return {"type": "error", "code": "invalid", "detail": detail}
    except Rejected as err:
        return {"type": "error", "code": err.code, "detail": err.detail}
    return {"type": "ack"}


# The first message signs in, every message after it is a change.
@router.websocket("/boards/{board_id}/ws")
async def board_socket(websocket: WebSocket, board_id: int) -> None:
    pool: ConnectionPool = websocket.app.state.pool
    await websocket.accept()
    try:
        message = await websocket.receive_text()
        user_id = await run_in_threadpool(sign_in, pool, board_id, message)
        await websocket.send_json({"type": "ready"})
        while True:
            message = await websocket.receive_text()
            answer = await run_in_threadpool(
                answer_change, pool, board_id, user_id, message
            )
            await websocket.send_json(answer)
    except WebSocketDisconnect:
        pass
