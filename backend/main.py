# Starts the app, in Docker and locally. Pass --reload to restart on code changes.

import sys

import uvicorn

from notes_board.config import MAX_MESSAGE_BYTES

if __name__ == "__main__":
    uvicorn.run(
        "notes_board.app:app",
        host="0.0.0.0",
        port=8000,
        reload="--reload" in sys.argv[1:],
        ws_max_size=MAX_MESSAGE_BYTES,
    )
