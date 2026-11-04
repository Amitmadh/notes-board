import os

import psycopg
from dotenv import load_dotenv
from fastapi import Request  # noqa: TC002
from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

load_dotenv()

CONNINFO = make_conninfo(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
)


def get_connection() -> psycopg.Connection:
    return psycopg.connect(CONNINFO)


def create_pool() -> ConnectionPool:
    return ConnectionPool(CONNINFO, open=False)


def get_db(request: Request):
    pool: ConnectionPool = request.app.state.pool
    with pool.connection() as db:
        yield db
