# Runs the backend for the browser tests (frontend/e2e) on a database of its own,
# made afresh for each run: python tests/e2e_server.py PORT
import os
import sys

import psycopg
import uvicorn
from dotenv import load_dotenv
from psycopg import sql

load_dotenv()
os.environ["DB_NAME"] += "_e2e"

from notes_board.db import CONNINFO  # noqa: E402

name = sql.Identifier(os.environ["DB_NAME"])
with psycopg.connect(CONNINFO, dbname="postgres", autocommit=True) as admin:
    admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
    admin.execute(sql.SQL("CREATE DATABASE {}").format(name))

uvicorn.run("notes_board.app:app", port=int(sys.argv[1]), log_level="warning")
