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
from notes_board.rooms import Room, room_for
from notes_board.schemas import (
    AddNode,
    Answer,
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


def saved_nodes(pool: ConnectionPool, board_id: int) -> list[dict[str, Any]]:
    with pool.connection() as db:
        rows = db.execute(
            "SELECT data FROM board_nodes WHERE board_id = %s", (board_id,)
        ).fetchall()
    return [data for (data,) in rows]


def answer_change(
    pool: ConnectionPool, board_id: int, user_id: int, message: str
) -> Answer:
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
            members = db.execute(
                "SELECT user_id FROM board_members WHERE board_id = %s", (board_id,)
            ).fetchall()
            db.commit()
    except ValidationError as err:
        detail = err.errors(
            include_url=False, include_context=False, include_input=False
        )
        return Answer(reply={"type": "error", "code": "invalid", "detail": detail})
    except Rejected as err:
        return Answer(reply={"type": "error", "code": err.code, "detail": err.detail})
    return Answer(
        reply={"type": "ack"},
        change=change.model_dump(),
        members=frozenset(member for (member,) in members),
    )


# Sockets of users removed from the board are closed instead.
async def send_to_others(room: Room, sender: WebSocket, answer: Answer) -> None:
    for socket, user_id in list(room.sockets.items()):
        if socket is sender:
            continue
        try:
            if user_id in answer.members:
                await socket.send_json(answer.change)
            else:
                del room.sockets[socket]
                await socket.close(NO_ACCESS, "Board not found")
        except WebSocketDisconnect:
            room.sockets.pop(socket, None)


# The first message signs in, every message after it is a change.
@router.websocket("/boards/{board_id}/ws")
async def board_socket(websocket: WebSocket, board_id: int) -> None:
    pool: ConnectionPool = websocket.app.state.pool
    await websocket.accept()
    try:
        message = await websocket.receive_text()
        user_id = await run_in_threadpool(sign_in, pool, board_id, message)
        with room_for(board_id, websocket) as room:
            # no change is saved between reading the board and joining the room
            async with room.lock:
                nodes = await run_in_threadpool(saved_nodes, pool, board_id)
                await websocket.send_json({"type": "ready", "nodes": nodes})
                room.sockets[websocket] = user_id
            while True:
                message = await websocket.receive_text()
                async with room.lock:
                    if websocket not in room.sockets:
                        return
                    answer = await run_in_threadpool(
                        answer_change, pool, board_id, user_id, message
                    )
                    await websocket.send_json(answer.reply)
                    if answer.change is not None:
                        await send_to_others(room, websocket, answer)
    except WebSocketDisconnect:
        pass
