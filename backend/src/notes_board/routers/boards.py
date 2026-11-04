from typing import Annotated

import psycopg  # noqa: TC002
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from notes_board.auth import get_current_active_user
from notes_board.db import get_db
from notes_board.schemas import Board, BoardContent, BoardCreate, BoardInDB, UserInDB

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


@router.get("/boards/{board_id}")
def get_board(
    board_id: int,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> BoardInDB:
    with db.cursor(row_factory=class_row(BoardInDB)) as cur:
        board = cur.execute(
            "SELECT id, name, content FROM boards WHERE id = %s AND owner_id = %s",
            (board_id, current_user.id),
        ).fetchone()
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


@router.put("/boards/{board_id}/content", status_code=204)
def save_board_content(
    board_id: int,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
    content: BoardContent,
) -> None:
    cur = db.execute(
        "UPDATE boards SET content = %s WHERE id = %s AND owner_id = %s",
        (Jsonb(content.model_dump()), board_id, current_user.id),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Board not found")
    db.commit()
