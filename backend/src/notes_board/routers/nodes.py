from typing import Annotated, Any

import psycopg  # noqa: TC002
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import args_row
from psycopg.types.json import Jsonb

from notes_board.access import get_accessible_board
from notes_board.db import get_db
from notes_board.schemas import BoardAccess, Node  # noqa: TC001

router = APIRouter(prefix="/api", tags=["nodes"])


@router.post("/boards/{board_id}/nodes", status_code=201)
def add_node(
    board: Annotated[BoardAccess, Depends(get_accessible_board)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
    body: Node,
) -> Node:
    with db.cursor(row_factory=args_row(Node.model_validate)) as cur:
        node = cur.execute(
            "INSERT INTO board_nodes (board_id, node_id, data) VALUES (%s, %s, %s)"
            " ON CONFLICT DO NOTHING RETURNING data",
            (board.id, body.id, Jsonb(body.model_dump())),
        ).fetchone()
    db.commit()
    if node is None:
        raise HTTPException(
            status_code=409, detail="A note with this id already exists"
        )
    return node


@router.patch("/boards/{board_id}/nodes/{node_id}", status_code=204)
def update_node(
    node_id: str,
    board: Annotated[BoardAccess, Depends(get_accessible_board)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
    body: dict[str, Any],
) -> None:
    if "id" in body:
        raise HTTPException(status_code=422, detail="A note's id can't change")
    updated = db.execute(
        "UPDATE board_nodes SET data = data || %s WHERE board_id = %s AND node_id = %s",
        (Jsonb(body), board.id, node_id),
    ).rowcount
    db.commit()
    if updated == 0:
        raise HTTPException(status_code=409, detail="This note was deleted")


@router.delete("/boards/{board_id}/nodes/{node_id}", status_code=204)
def delete_node(
    node_id: str,
    board: Annotated[BoardAccess, Depends(get_accessible_board)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> None:
    db.execute(
        "DELETE FROM board_nodes WHERE board_id = %s AND node_id = %s",
        (board.id, node_id),
    )
    db.commit()
