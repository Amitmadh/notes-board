from typing import Annotated

import psycopg  # noqa: TC002
from fastapi import APIRouter, Depends
from psycopg.rows import class_row

from notes_board.auth import get_current_active_user
from notes_board.db import get_db
from notes_board.schemas import Board, BoardCreate, UserInDB

router = APIRouter(prefix="/api", tags=["boards"])


@router.get("/boards")
def user_boards(
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> list[Board]:
    with db.cursor(row_factory=class_row(Board)) as cur:
        return cur.execute(
            "SELECT id, name FROM boards WHERE owner_id = %s ORDER BY id",
            (current_user.id,),
        ).fetchall()


@router.post("/boards", status_code=201)
def add_board(
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
    body: BoardCreate,
) -> Board:
    with db.cursor(row_factory=class_row(Board)) as cur:
        board = cur.execute(
            "INSERT INTO boards (owner_id, name) VALUES (%s, %s) RETURNING id, name",
            (current_user.id, body.name),
        ).fetchone()
    db.commit()
    assert board is not None
    return board
