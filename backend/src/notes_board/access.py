from typing import Annotated

import psycopg  # noqa: TC002
from fastapi import Depends, HTTPException
from psycopg.rows import class_row

from notes_board.auth import get_current_active_user
from notes_board.db import get_db
from notes_board.schemas import BoardAccess, UserInDB


def find_board_access(
    db: psycopg.Connection, board_id: int, user_id: int
) -> BoardAccess | None:
    with db.cursor(row_factory=class_row(BoardAccess)) as cur:
        return cur.execute(
            "SELECT board_id AS id, role FROM board_members"
            " WHERE board_id = %s AND user_id = %s",
            (board_id, user_id),
        ).fetchone()


def get_accessible_board(
    board_id: int,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> BoardAccess:
    board = find_board_access(db, board_id, current_user.id)
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return board
