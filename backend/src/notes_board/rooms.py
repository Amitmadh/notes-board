import asyncio
import itertools
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import WebSocketDisconnect

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi import WebSocket

peer_ids = itertools.count(1)


# a signed-in socket
@dataclass
class Peer:
    user_id: int
    username: str
    id: int = field(default_factory=lambda: next(peer_ids))
    selected: str | None = None
    shown: bool = False

    def selection(self) -> dict[str, Any]:
        return {"peer": self.id, "username": self.username, "id": self.selected}


# A board's open sockets.
class Room:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.sockets: dict[WebSocket, Peer] = {}
        self.handlers = 0

    def selections(self) -> list[dict[str, Any]]:
        return [
            peer.selection()
            for peer in self.sockets.values()
            if peer.selected is not None
        ]

    async def send_to_others(self, sender: WebSocket, message: dict[str, Any]) -> None:
        for socket in list(self.sockets):
            if socket is sender:
                continue
            try:
                await socket.send_json(message)
            except WebSocketDisconnect:
                self.sockets.pop(socket, None)


rooms: dict[int, Room] = {}


@asynccontextmanager
async def room_for(
    board_id: int, socket: WebSocket, peer: Peer
) -> AsyncGenerator[Room]:
    room = rooms.setdefault(board_id, Room())
    room.handlers += 1
    try:
        yield room
    finally:
        try:
            async with room.lock:
                room.sockets.pop(socket, None)
                if peer.shown:
                    await room.send_to_others(socket, {"type": "left", "peer": peer.id})
        finally:
            room.handlers -= 1
            if room.handlers == 0:
                del rooms[board_id]
