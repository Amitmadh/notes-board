from typing import Annotated

# FastAPI reads dependency type hints at runtime, so these can't be type-only imports.
import psycopg  # noqa: TC002
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm  # noqa: TC002
from psycopg.rows import class_row

from notes_board.auth import (
    REFRESH_COOKIE_PATH,
    authenticate_user,
    get_current_active_user,
    issue_tokens,
    password_hash,
    user_from_token,
)
from notes_board.db import get_db
from notes_board.schemas import Token, User, UserCreate

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login")
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[psycopg.Connection, Depends(get_db)],
    response: Response,
) -> Token:
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return issue_tokens(response, user.username)


@router.post("/refresh")
def refresh(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> Token:
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in"
        )
    user = user_from_token(db, refresh_token, kind="refresh")
    if user.disabled:
        raise HTTPException(status_code=403, detail="Forbidden")
    return issue_tokens(response, user.username)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        samesite="strict",
        secure=True,
        path=REFRESH_COOKIE_PATH,
    )


@router.get("/users/me/")
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    return current_user


@router.post("/register", status_code=201)
def register(
    body: UserCreate,
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> User:
    if db.execute(
        "SELECT 1 FROM users WHERE username = %s", (body.username,)
    ).fetchone():
        raise HTTPException(status_code=409, detail="Username already exists")

    hashed_password = password_hash.hash(body.password.get_secret_value())
    with db.cursor(row_factory=class_row(User)) as cur:
        user = cur.execute(
            "INSERT INTO users (username, full_name, hashed_password)"
            " VALUES (%s, %s, %s) RETURNING *",
            (body.username, body.full_name, hashed_password),
        ).fetchone()
    db.commit()
    assert user is not None

    return user
