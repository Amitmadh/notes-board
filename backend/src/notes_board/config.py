# Limits and timings the app runs with, kept here so they're easy to find and tune.

import datetime

# Boards
MAX_NODES = 2000  # items on one board
MAX_NOTE_TEXT = 10000  # characters in one text note

# Images
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# a board is saved only after a new image is placed on it, so images this new
# are kept even when their board doesn't show them yet.
IMAGE_GRACE_PERIOD = datetime.timedelta(days=1)
IMAGE_CLEANUP_INTERVAL_SECONDS = 60 * 60

# Sign-in
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30
