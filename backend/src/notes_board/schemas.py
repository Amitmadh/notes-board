from typing import Annotated

from pydantic import BaseModel, SecretStr, StringConstraints


class Token(BaseModel):
    access_token: str
    token_type: str


class User(BaseModel):
    username: str
    full_name: str | None = None
    disabled: bool


class UserCreate(BaseModel):
    username: str
    full_name: str | None = None
    password: SecretStr


class UserInDB(User):
    id: int
    hashed_password: str


class Board(BaseModel):
    id: int
    name: str


class BoardCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
