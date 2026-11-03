from fastapi import FastAPI

from notes_board.db import get_connection
from notes_board.models import create_tables
from notes_board.routers import auth

with get_connection() as conn:
    create_tables(conn)

app = FastAPI(
    title="notes-board",
    description="collaborative board of notes",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.include_router(auth.router)
