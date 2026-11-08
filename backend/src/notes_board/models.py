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
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS board_members (
    board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor')),
    PRIMARY KEY (board_id, user_id)
);

CREATE INDEX IF NOT EXISTS board_members_user_id_idx ON board_members (user_id);

CREATE UNIQUE INDEX IF NOT EXISTS board_members_owner_idx
    ON board_members (board_id) WHERE role = 'owner';

CREATE TABLE IF NOT EXISTS board_nodes (
    board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    data JSONB NOT NULL,
    PRIMARY KEY (board_id, node_id)
);

CREATE TABLE IF NOT EXISTS images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    content_type TEXT NOT NULL,
    data BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS images_board_id_idx ON images (board_id);
"""


def create_tables(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()
