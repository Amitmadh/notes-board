import psycopg  # noqa: TC002

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT,
    disabled BOOLEAN NOT NULL DEFAULT FALSE,
    hashed_password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS boards (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL
);
"""


def create_tables(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()
