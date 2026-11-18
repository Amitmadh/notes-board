import datetime

# Boards
MAX_NODES = 2000
MAX_NOTE_TEXT = 10000  # characters
MAX_MESSAGE_BYTES = 256 * 1024  # per socket message, enforced by uvicorn
SIGN_IN_TIMEOUT_SECONDS = 10  # for a new socket to send its token

# Images
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_BOARD_IMAGE_BYTES = 100 * 1024 * 1024  # all the images of one board
# a board is saved only after a new image is placed on it, so images this new
# are kept even when their board doesn't show them yet.
IMAGE_GRACE_PERIOD = datetime.timedelta(days=1)
IMAGE_CLEANUP_INTERVAL_SECONDS = 60 * 60

# Sign-in
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 32
MIN_PASSWORD_LENGTH = 8
PASSWORDS_HASHED_AT_ONCE = 2  # other sign-ins wait their turn
