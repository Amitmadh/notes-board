from typing import Annotated

import psycopg  # noqa: TC002
from fastapi import Depends, HTTPException
from psycopg.rows import class_row

from notes_board.auth import get_current_active_user
from notes_board.db import get_db
from notes_board.schemas import BoardAccess, UserInDB


def get_accessible_board(
    board_id: int,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> BoardAccess:
    with db.cursor(row_factory=class_row(BoardAccess)) as cur:
        board = cur.execute(
            "SELECT id FROM boards WHERE id = %s AND owner_id = %s",
            (board_id, current_user.id),
        ).fetchone()
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return board
