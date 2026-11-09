from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    TypeAdapter,
)


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
    owner: str


class BoardCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BoardInDB(Board):
    nodes: list[dict[str, Any]]


class BoardAccess(BaseModel):
    id: int
    role: Literal["owner", "editor"]


class Node(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    type: str


# The first message on a board's socket.
class SocketAuth(BaseModel):
    type: Literal["auth"]
    token: str


class AddNode(BaseModel):
    type: Literal["add_node"]
    node: Node


class UpdateNode(BaseModel):
    type: Literal["update_node"]
    id: str
    changes: dict[str, Any]


class DeleteNode(BaseModel):
    type: Literal["delete_node"]
    id: str


NodeChange = TypeAdapter(
    Annotated[AddNode | UpdateNode | DeleteNode, Field(discriminator="type")]
)


# A saved change, with who's still on the board to send it to.
class Answer(BaseModel):
    reply: dict[str, Any]
    change: dict[str, Any] | None = None
    members: frozenset[int] = frozenset()


class Member(BaseModel):
    username: str
    full_name: str | None = None


class MemberCreate(BaseModel):
    username: str


class Image(BaseModel):
    url: str
