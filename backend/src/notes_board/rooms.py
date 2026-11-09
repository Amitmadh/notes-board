import asyncio
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from fastapi import WebSocket


# A board's open sockets, with their users' ids. Whatever sends to them holds
# the lock, so every socket gets the board's changes in the order they're saved.
class Room:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.sockets: dict[WebSocket, int] = {}
        self.handlers = 0


rooms: dict[int, Room] = {}


@contextmanager
def room_for(board_id: int, socket: WebSocket) -> Generator[Room]:
    room = rooms.setdefault(board_id, Room())
    room.handlers += 1
    try:
        yield room
    finally:
        room.sockets.pop(socket, None)
        room.handlers -= 1
        if room.handlers == 0:
            del rooms[board_id]
