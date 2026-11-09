from contextlib import suppress
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
from notes_board.rooms import Peer, Room, room_for
from notes_board.schemas import (
    AddNode,
    Answer,
    ClientMessage,
    DeleteNode,
    LiveUpdate,
    Node,
    NodeChange,
    SelectNode,
    SocketAuth,
    UpdateNode,
    UserInDB,
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


def sign_in(pool: ConnectionPool, board_id: int, message: str) -> UserInDB:
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
    return user


def saved_nodes(pool: ConnectionPool, board_id: int) -> list[dict[str, Any]]:
    with pool.connection() as db:
        rows = db.execute(
            "SELECT data FROM board_nodes WHERE board_id = %s", (board_id,)
        ).fetchall()
    return [data for (data,) in rows]


def answer_change(
    pool: ConnectionPool, board_id: int, user_id: int, change: NodeChange
) -> Answer:
    try:
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
    except Rejected as err:
        return Answer(reply={"type": "error", "code": err.code, "detail": err.detail})
    return Answer(
        reply={"type": "ack"},
        change=change.model_dump(),
        members=frozenset(member for (member,) in members),
    )


def invalid_reply(err: ValidationError) -> dict[str, Any]:
    detail = err.errors(include_url=False, include_context=False, include_input=False)
    return {"type": "error", "code": "invalid", "detail": detail}


async def close_removed(room: Room, members: frozenset[int]) -> None:
    for socket, peer in list(room.sockets.items()):
        if peer.user_id not in members:
            del room.sockets[socket]
            with suppress(WebSocketDisconnect):
                await socket.close(NO_ACCESS, "Board not found")


# send live updates and selections to the others without saveing or answering
async def relay(
    room: Room, sender: WebSocket, peer: Peer, message: LiveUpdate | SelectNode
) -> None:
    peer.shown = True
    match message:
        case LiveUpdate():
            await room.send_to_others(sender, {**message.model_dump(), "peer": peer.id})
        case SelectNode(id=node_id):
            peer.selected = node_id
            await room.send_to_others(sender, {"type": "select", **peer.selection()})


# The first message signs in, every message after it is a ClientMessage.
@router.websocket("/boards/{board_id}/ws")
async def board_socket(websocket: WebSocket, board_id: int) -> None:
    pool: ConnectionPool = websocket.app.state.pool
    await websocket.accept()
    try:
        message = await websocket.receive_text()
        user = await run_in_threadpool(sign_in, pool, board_id, message)
        peer = Peer(user.id, user.username)
        async with room_for(board_id, websocket, peer) as room:
            # no change is saved between reading the board and joining the room
            async with room.lock:
                nodes = await run_in_threadpool(saved_nodes, pool, board_id)
                await websocket.send_json(
                    {"type": "ready", "nodes": nodes, "selections": room.selections()}
                )
                room.sockets[websocket] = peer
            while True:
                message = await websocket.receive_text()
                async with room.lock:
                    if websocket not in room.sockets:
                        return
                    try:
                        change = ClientMessage.validate_json(message)
                    except ValidationError as err:
                        await websocket.send_json(invalid_reply(err))
                        continue
                    if isinstance(change, LiveUpdate | SelectNode):
                        await relay(room, websocket, peer, change)
                        continue
                    answer = await run_in_threadpool(
                        answer_change, pool, board_id, user.id, change
                    )
                    await websocket.send_json(answer.reply)
                    if answer.change is not None:
                        await close_removed(room, answer.members)
                        await room.send_to_others(websocket, answer.change)
    except WebSocketDisconnect:
        pass
