import uuid  # noqa: TC003
from typing import Annotated

import psycopg  # noqa: TC002
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile

from notes_board.access import get_accessible_board
from notes_board.db import get_db
from notes_board.schemas import BoardAccess, Image

router = APIRouter(prefix="/api", tags=["images"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024


def image_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return None


@router.post("/boards/{board_id}/images", status_code=201)
def upload_image(
    board: Annotated[BoardAccess, Depends(get_accessible_board)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
    file: UploadFile,
) -> Image:
    data = file.file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Images can be at most 10 MB")
    content_type = image_type(data)
    if content_type is None:
        raise HTTPException(
            status_code=415, detail="Only PNG, JPEG and GIF images are supported"
        )
    row = db.execute(
        "INSERT INTO images (board_id, content_type, data) VALUES (%s, %s, %s)"
        " RETURNING id",
        (board.id, content_type, data),
    ).fetchone()
    assert row is not None
    db.commit()
    return Image(url=f"/api/images/{row[0]}")


@router.get("/images/{image_id}")
def get_image(
    image_id: uuid.UUID,
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> Response:
    row = db.execute(
        "SELECT content_type, data FROM images WHERE id = %s", (image_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    content_type, data = row
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
