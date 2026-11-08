from typing import Annotated

import psycopg  # noqa: TC002
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import class_row

from notes_board.access import get_accessible_board
from notes_board.auth import get_current_active_user, get_user
from notes_board.db import get_db
from notes_board.schemas import BoardAccess, Member, MemberCreate, UserInDB

router = APIRouter(prefix="/api", tags=["members"])


@router.get("/boards/{board_id}/members")
def board_members(
    board: Annotated[BoardAccess, Depends(get_accessible_board)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> list[Member]:
    with db.cursor(row_factory=class_row(Member)) as cur:
        return cur.execute(
            "SELECT users.username, users.full_name"
            " FROM board_members JOIN users ON users.id = board_members.user_id"
            " WHERE board_members.board_id = %s AND board_members.role <> 'owner'"
            " ORDER BY users.username",
            (board.id,),
        ).fetchall()


@router.post("/boards/{board_id}/members", status_code=201)
def add_member(
    board: Annotated[BoardAccess, Depends(get_accessible_board)],
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
    body: MemberCreate,
) -> Member:
    if board.role != "owner":
        raise HTTPException(
            status_code=403, detail="Only the owner can share this board"
        )
    user = get_user(db, body.username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=409, detail="You already own this board")
    cur = db.execute(
        "INSERT INTO board_members (board_id, user_id, role)"
        " VALUES (%s, %s, 'editor') ON CONFLICT DO NOTHING",
        (board.id, user.id),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=409, detail="Already shared with this user")
    db.commit()
    return Member(username=user.username, full_name=user.full_name)


# The owner can remove anyone, and members can remove themselves to leave.
@router.delete("/boards/{board_id}/members/{username}", status_code=204)
def remove_member(
    username: str,
    board: Annotated[BoardAccess, Depends(get_accessible_board)],
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> None:
    if board.role != "owner" and username != current_user.username:
        raise HTTPException(status_code=403, detail="Only the owner can remove others")
    if board.role == "owner" and username == current_user.username:
        raise HTTPException(status_code=409, detail="The owner can't leave the board")
    cur = db.execute(
        "DELETE FROM board_members USING users"
        " WHERE board_members.user_id = users.id"
        " AND board_members.board_id = %s AND users.username = %s",
        (board.id, username),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not a member of this board")
    db.commit()
