import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from notes_board.cleanup import clean_up_hourly
from notes_board.db import create_pool
from notes_board.models import create_tables
from notes_board.routers import auth, boards, images, nodes


@asynccontextmanager
async def lifespan(app: FastAPI):
    with create_pool() as pool:
        with pool.connection() as conn:
            create_tables(conn)
        app.state.pool = pool
        stop = threading.Event()
        cleanup = threading.Thread(
            target=clean_up_hourly, args=(pool, stop), daemon=True
        )
        cleanup.start()
        yield
        stop.set()
        cleanup.join()


app = FastAPI(
    title="notes-board",
    description="collaborative board of notes",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(boards.router)
app.include_router(images.router)
app.include_router(nodes.router)
