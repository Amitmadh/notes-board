import datetime
import logging
import threading  # noqa: TC003

import psycopg  # noqa: TC002
from psycopg_pool import ConnectionPool  # noqa: TC002

logger = logging.getLogger(__name__)

# A board is saved only after a new image is placed on it, so images this new
# are kept even when their board doesn't show them yet.
GRACE_PERIOD = datetime.timedelta(days=1)
INTERVAL_SECONDS = 60 * 60


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
        (GRACE_PERIOD,),
    )
    conn.commit()
    return cur.rowcount


def clean_up_hourly(pool: ConnectionPool, stop: threading.Event) -> None:
    while not stop.wait(INTERVAL_SECONDS):
        try:
            with pool.connection() as conn:
                delete_leftover_images(conn)
        except Exception:
            logger.exception("Couldn't delete leftover images")
