from typing import Annotated

import psycopg  # noqa: TC002
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import class_row

from notes_board.access import get_accessible_board
from notes_board.auth import get_current_active_user
from notes_board.db import get_db
from notes_board.schemas import Board, BoardAccess, BoardCreate, BoardInDB, UserInDB

router = APIRouter(prefix="/api", tags=["boards"])


@router.get("/boards")
def user_boards(
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> list[Board]:
    with db.cursor(row_factory=class_row(Board)) as cur:
        return cur.execute(
            "SELECT boards.id, boards.name, owners.username AS owner"
            " FROM board_members AS mine"
            " JOIN boards ON boards.id = mine.board_id"
            " JOIN board_members AS ownership USING (board_id)"
            " JOIN users AS owners ON owners.id = ownership.user_id"
            " WHERE mine.user_id = %s AND ownership.role = 'owner'"
            " ORDER BY boards.id",
            (current_user.id,),
        ).fetchall()


@router.post("/boards", status_code=201)
def add_board(
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
    body: BoardCreate,
) -> Board:
    row = db.execute(
        "INSERT INTO boards (name) VALUES (%s) RETURNING id", (body.name,)
    ).fetchone()
    assert row is not None
    db.execute(
        "INSERT INTO board_members (board_id, user_id, role) VALUES (%s, %s, 'owner')",
        (row[0], current_user.id),
    )
    db.commit()
    return Board(id=row[0], name=body.name, owner=current_user.username)


@router.get("/boards/{board_id}")
def get_board(
    access: Annotated[BoardAccess, Depends(get_accessible_board)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> BoardInDB:
    with db.cursor(row_factory=class_row(Board)) as cur:
        board = cur.execute(
            "SELECT boards.id, boards.name, users.username AS owner"
            " FROM boards"
            " JOIN board_members ON board_members.board_id = boards.id"
            " AND board_members.role = 'owner'"
            " JOIN users ON users.id = board_members.user_id"
            " WHERE boards.id = %s",
            (access.id,),
        ).fetchone()
    assert board is not None
    rows = db.execute(
        "SELECT data FROM board_nodes WHERE board_id = %s", (access.id,)
    ).fetchall()
    return BoardInDB(**board.model_dump(), nodes=[data for (data,) in rows])


@router.delete("/boards/{board_id}", status_code=204)
def delete_board(
    access: Annotated[BoardAccess, Depends(get_accessible_board)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> None:
    if access.role != "owner":
        raise HTTPException(
            status_code=403, detail="Only the owner can delete this board"
        )
    db.execute("DELETE FROM boards WHERE id = %s", (access.id,))
    db.commit()
