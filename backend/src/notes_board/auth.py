import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import jwt

# FastAPI reads dependency type hints at runtime, so this can't be a type-only import.
import psycopg  # noqa: TC002
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from psycopg.rows import class_row
from psycopg_pool import ConnectionPool  # noqa: TC002
from pwdlib import PasswordHash

from notes_board.config import ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
from notes_board.db import get_db
from notes_board.schemas import Token, UserInDB

load_dotenv()

ALGORITHM = "HS256"
REFRESH_COOKIE_PATH = "/api/refresh"
SECRET_KEY = os.environ["SECRET_KEY"]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")


def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def get_user(db: psycopg.Connection, username: str) -> UserInDB | None:
    with db.cursor(row_factory=class_row(UserInDB)) as cur:
        return cur.execute(
            "SELECT id, username, full_name, disabled, hashed_password"
            " FROM users WHERE username = %s",
            (username,),
        ).fetchone()


# Checks the token and that it was made for this use, so a refresh token
# can't be sent as an access token or the other way round.
def user_from_token(
    db: psycopg.Connection, token: str, kind: Literal["access", "refresh"]
) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("kind") != kind:
            raise credentials_exception
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError as err:
        raise credentials_exception from err
    user = get_user(db, username=username)
    if not user:
        raise credentials_exception
    return user


# A plain def, so FastAPI runs it in a worker thread and the blocking query
# doesn't hold up other requests.
def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> UserInDB:
    return user_from_token(db, token, kind="access")


async def get_current_active_user(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> UserInDB:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def find_user(pool: ConnectionPool, username: str) -> UserInDB | None:
    with pool.connection() as db:
        return get_user(db, username)


async def authenticate_user(
    request: Request, username: str, password: str
) -> UserInDB | None:
    user = await run_in_threadpool(find_user, request.app.state.pool, username)
    # Takes as long as a real check, so timing doesn't reveal which usernames exist.
    hashed_password = user.hashed_password if user else DUMMY_HASH
    async with request.app.state.hashing:
        matches = await run_in_threadpool(verify_password, password, hashed_password)
    return user if matches else None


def create_token(
    data: dict, expires_delta: timedelta, kind: Literal["access", "refresh"]
):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.now(UTC) + expires_delta, "kind": kind})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# Sets a new refresh cookie and returns a new access token.
def issue_tokens(response: Response, username: str) -> Token:
    refresh_token_expires = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = create_token(
        data={"sub": username}, expires_delta=refresh_token_expires, kind="refresh"
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="strict",
        secure=True,
        max_age=int(refresh_token_expires.total_seconds()),
        path=REFRESH_COOKIE_PATH,
    )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_token(
        data={"sub": username}, expires_delta=access_token_expires, kind="access"
    )
    return Token(access_token=access_token, token_type="bearer")
