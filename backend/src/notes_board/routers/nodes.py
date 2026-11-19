import asyncio
from base64 import b64decode, b64encode
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
from pycrdt import Doc, Text
from pydantic import ValidationError

from notes_board.access import find_board_access
from notes_board.auth import user_from_token
from notes_board.config import MAX_NODES, MAX_NOTE_TEXT, SIGN_IN_TIMEOUT_SECONDS
from notes_board.rooms import Peer, Room, room_for, rooms
from notes_board.schemas import (
    AddNode,
    Answer,
    ClientMessage,
    DeleteNode,
    EditText,
    ImageNode,
    LiveUpdate,
    Node,
    NodeChange,
    SelectNode,
    SocketAuth,
    UpdateNode,
    UserInDB,
    ValidNode,
)

router = APIRouter(prefix="/api", tags=["nodes"])

# close codes the board page acts on
UNAUTHORIZED = 4401
NO_ACCESS = 4404
BAD_REQUEST = 4400

# what an update can't change
FIXED_FIELDS = {"id", "type", "src", "text"}


class Rejected(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def add_node(db: psycopg.Connection, board_id: int, node: Node) -> None:
    if isinstance(node, ImageNode):
        image = db.execute(
            "SELECT 1 FROM images WHERE id = %s AND board_id = %s",
            (node.src.removeprefix("/api/images/"), board_id),
        ).fetchone()
        if image is None:
            raise Rejected("invalid", "The image isn't one of this board's")
    inserted = db.execute(
        "INSERT INTO board_nodes (board_id, node_id, data) VALUES (%s, %s, %s)"
        " ON CONFLICT DO NOTHING",
        (board_id, node.id, Jsonb(node.model_dump(exclude_unset=True))),
    ).rowcount
    if inserted == 0:
        raise Rejected("exists", "A note with this id already exists")
    nodes = db.execute(
        "SELECT count(*) FROM board_nodes WHERE board_id = %s", (board_id,)
    ).fetchone()
    assert nodes is not None
    if nodes[0] > MAX_NODES:
        raise Rejected("full", f"A board holds up to {MAX_NODES} nodes")


def set_fields(
    db: psycopg.Connection, board_id: int, node_id: str, fields: dict[str, Any]
) -> None:
    db.execute(
        "UPDATE board_nodes SET data = data || %s WHERE board_id = %s AND node_id = %s",
        (Jsonb(fields), board_id, node_id),
    )


def update_node(
    db: psycopg.Connection, board_id: int, node_id: str, changes: dict[str, Any]
) -> None:
    if fixed := FIXED_FIELDS & changes.keys():
        raise Rejected("invalid", f"An update can't change {', '.join(sorted(fixed))}")
    node = db.execute(
        "SELECT data - 'ytext' FROM board_nodes WHERE board_id = %s AND node_id = %s",
        (board_id, node_id),
    ).fetchone()
    if node is None:
        raise Rejected("gone", "This node was deleted")
    ValidNode.validate_python({**node[0], **changes})
    set_fields(db, board_id, node_id, changes)


def edit_text(
    db: psycopg.Connection, board_id: int, node_id: str, update: bytes
) -> None:
    # locked, so two servers merging into one note take turns
    note = db.execute(
        "SELECT data->>'ytext', data->>'text' FROM board_nodes"
        " WHERE board_id = %s AND node_id = %s AND data->>'type' = 'text'"
        " FOR NO KEY UPDATE",
        (board_id, node_id),
    ).fetchone()
    if note is None:
        raise Rejected("gone", "This note was deleted")
    state, first_text = note
    doc = Doc(client_id=0)
    text = doc.get("text", type=Text)
    try:
        if state is None:
            text += first_text or ""
        else:
            doc.apply_update(b64decode(state))
        doc.apply_update(update)
    except ValueError as err:
        raise Rejected("invalid", "Not a change to a note's text") from err
    merged = str(text)
    if len(merged) > MAX_NOTE_TEXT:
        raise Rejected("full", f"A note holds up to {MAX_NOTE_TEXT} characters")
    state = b64encode(doc.get_update()).decode()
    set_fields(db, board_id, node_id, {"ytext": state, "text": merged})


def delete_node(db: psycopg.Connection, board_id: int, node_id: str) -> None:
    db.execute(
        "DELETE FROM board_nodes WHERE board_id = %s AND node_id = %s",
        (board_id, node_id),
    )


def sign_in(pool: ConnectionPool, message: str) -> UserInDB:
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
    return user


def saved_nodes(
    pool: ConnectionPool, board_id: int, user_id: int
) -> list[dict[str, Any]]:
    with pool.connection() as db:
        if find_board_access(db, board_id, user_id) is None:
            raise WebSocketException(NO_ACCESS, "Board not found")
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
                case EditText(id=node_id, update=update):
                    edit_text(db, board_id, node_id, update)
            members = db.execute(
                "SELECT user_id FROM board_members WHERE board_id = %s", (board_id,)
            ).fetchall()
            db.commit()
    except Rejected as err:
        return Answer(reply={"type": "error", "code": err.code, "detail": err.detail})
    except ValidationError as err:
        return Answer(reply=invalid_reply(err))
    return Answer(
        reply={"type": "ack"},
        change=change.model_dump(mode="json", exclude_unset=True),
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


async def close_sockets(board_id: int, user_id: int | None = None) -> None:
    room = rooms.get(board_id)
    if room is None:
        return
    async with room.lock:
        for socket, peer in list(room.sockets.items()):
            if user_id is None or peer.user_id == user_id:
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
        try:
            message = await asyncio.wait_for(
                websocket.receive_text(), SIGN_IN_TIMEOUT_SECONDS
            )
        except TimeoutError as err:
            raise WebSocketException(
                BAD_REQUEST, f"Sign in within {SIGN_IN_TIMEOUT_SECONDS} seconds"
            ) from err
        user = await run_in_threadpool(sign_in, pool, message)
        peer = Peer(user.id, user.username)
        async with room_for(board_id, websocket, peer) as room:
            # no change is saved between reading the board and joining the room
            async with room.lock:
                nodes = await run_in_threadpool(saved_nodes, pool, board_id, user.id)
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
