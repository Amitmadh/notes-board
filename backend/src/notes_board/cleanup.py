import logging
import threading  # noqa: TC003

import psycopg  # noqa: TC002
from psycopg_pool import ConnectionPool  # noqa: TC002

from notes_board.config import IMAGE_CLEANUP_INTERVAL_SECONDS, IMAGE_GRACE_PERIOD

logger = logging.getLogger(__name__)


def delete_leftover_images(conn: psycopg.Connection) -> int:
    cur = conn.execute(
        """
        DELETE FROM images
        WHERE created_at < now() - %s
        AND NOT EXISTS (
            SELECT 1 FROM board_nodes
            WHERE board_nodes.board_id = images.board_id
            AND strpos(board_nodes.data::text, images.id::text) > 0
        )
        """,
        (IMAGE_GRACE_PERIOD,),
    )
    conn.commit()
    return cur.rowcount


def clean_up_hourly(pool: ConnectionPool, stop: threading.Event) -> None:
    while not stop.wait(IMAGE_CLEANUP_INTERVAL_SECONDS):
        try:
            with pool.connection() as conn:
                delete_leftover_images(conn)
        except Exception:
            logger.exception("Couldn't delete leftover images")
