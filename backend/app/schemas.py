from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.models import DocStatus, Role
from app.security import MAX_PASSWORD_BYTES


class RegisterIn(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError("Password must be at most 72 bytes")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: Role
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RoleUpdate(BaseModel):
    role: Role


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    size_bytes: int
    page_count: int
    status: DocStatus
    error: str | None
    uploaded_by: int
    created_at: datetime


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_index: int
    page_number: int
    text: str


# ---------------------------------------------------------------------------
# Chat schemas
# ---------------------------------------------------------------------------


class AskIn(BaseModel):
    """Request body for submitting a question."""

    question: str
    session_id: int | None = None

    @field_validator("question")
    @classmethod
    def check_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question must not be empty")
        if len(v) > 2000:
            raise ValueError("Question must be at most 2000 characters")
        return v


class CitationOut(BaseModel):
    """A single source citation returned alongside an answer."""

    document_id: int
    filename: str
    page_number: int
    chunk_index: int
    excerpt: str


class AskOut(BaseModel):
    """Response from the /chat/ask endpoint."""

    answer: str
    citations: list[CitationOut]
    session_id: int
    chunks_retrieved: int


class SessionOut(BaseModel):
    """Summary of a chat session (for listing)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    """A single chat message with optional citations."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    citations: list | None = None
    created_at: datetime


class SessionDetailOut(BaseModel):
    """Full chat session including message history."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    messages: list[MessageOut]


class SessionTitleUpdate(BaseModel):
    """Request body for updating a session title."""

    title: str

    @field_validator("title")
    @classmethod
    def check_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title must not be empty")
        if len(v) > 255:
            raise ValueError("Title must be at most 255 characters")
        return v

