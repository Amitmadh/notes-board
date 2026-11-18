from typing import Annotated, Any, Literal

from pydantic import (
    Base64Bytes,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    SecretStr,
    StringConstraints,
    TypeAdapter,
)

from notes_board.config import (
    MAX_NOTE_TEXT,
    MAX_USERNAME_LENGTH,
    MIN_PASSWORD_LENGTH,
    MIN_USERNAME_LENGTH,
)


class Token(BaseModel):
    access_token: str
    token_type: str


class User(BaseModel):
    username: str
    full_name: str | None = None
    disabled: bool


class UserCreate(BaseModel):
    username: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=MIN_USERNAME_LENGTH,
            max_length=MAX_USERNAME_LENGTH,
        ),
    ]
    full_name: Annotated[str, StringConstraints(max_length=100)] | None = None
    password: Annotated[SecretStr, Field(min_length=MIN_PASSWORD_LENGTH)]


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


ShortStr = Annotated[str, StringConstraints(max_length=100)]


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    x: FiniteFloat = 0
    y: FiniteFloat = 0
    rotation: FiniteFloat = 0
    scaleX: FiniteFloat = 1
    scaleY: FiniteFloat = 1
    opacity: FiniteFloat = 1
    visible: bool = True
    layer: FiniteFloat = 0
    selectable: bool = False
    draggable: bool = False
    resizable: bool = False


class ShapeNode(Node):
    fill: ShortStr | None = "black"
    stroke: ShortStr | None = None
    strokeWidth: FiniteFloat = 1


class BoxNode(ShapeNode):
    type: Literal[
        "rectangle", "triangle", "diamond", "hexagon", "star", "arrow", "cursor"
    ]
    width: FiniteFloat
    height: FiniteFloat


class CircleNode(ShapeNode):
    type: Literal["circle"]
    radius: FiniteFloat


class TextNode(Node):
    type: Literal["text"]
    text: Annotated[str, StringConstraints(max_length=MAX_NOTE_TEXT)]
    width: FiniteFloat | None = None
    fontSize: FiniteFloat = 14
    fontFamily: ShortStr = "sans-serif"
    fontWeight: ShortStr | FiniteFloat = "normal"
    fontStyle: Literal["normal", "italic"] = "normal"
    fill: ShortStr = "black"
    stroke: ShortStr | None = None
    strokeWidth: FiniteFloat = 1
    lineHeight: FiniteFloat = 1
    align: Literal["left", "center", "right"] = "left"
    baseline: Literal[
        "alphabetic", "bottom", "hanging", "ideographic", "middle", "top"
    ] = "alphabetic"
    direction: Literal["ltr", "rtl"] = "ltr"
    padding: FiniteFloat = 0
    background: ShortStr | None = None
    cornerRadius: FiniteFloat = 0
    writable: bool = False


class ImageNode(Node):
    type: Literal["image"]
    # the url of an image uploaded to the board
    src: Annotated[
        str,
        StringConstraints(
            pattern=r"^/api/images/[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$"
        ),
    ]
    width: FiniteFloat
    height: FiniteFloat


AnyNode = Annotated[
    BoxNode | CircleNode | TextNode | ImageNode, Field(discriminator="type")
]
ValidNode = TypeAdapter(AnyNode)


# The first message on a board's socket.
class SocketAuth(BaseModel):
    type: Literal["auth"]
    token: str


class AddNode(BaseModel):
    type: Literal["add_node"]
    node: AnyNode


class UpdateNode(BaseModel):
    type: Literal["update_node"]
    id: str
    changes: dict[str, Any]


class DeleteNode(BaseModel):
    type: Literal["delete_node"]
    id: str


class EditText(BaseModel):
    type: Literal["edit_text"]
    id: str
    update: Base64Bytes


NodeChange = AddNode | UpdateNode | DeleteNode | EditText


class LiveUpdate(BaseModel):
    type: Literal["live_update"]
    id: str
    changes: dict[str, Any]


class SelectNode(BaseModel):
    type: Literal["select"]
    id: str | None


ClientMessage = TypeAdapter(
    Annotated[NodeChange | LiveUpdate | SelectNode, Field(discriminator="type")]
)


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
