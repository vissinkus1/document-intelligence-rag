"""Chat endpoints: ask questions, manage sessions, view history."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import ChatMessage, ChatSession, User
from app.schemas import (
    AskIn,
    AskOut,
    CitationOut,
    MessageOut,
    SessionDetailOut,
    SessionOut,
    SessionTitleUpdate,
)
from app.services import rag

log = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_user_session(session_id: int, user: User, db: Session) -> ChatSession:
    """Fetch a session and verify it belongs to *user*.  Raises 404 / 403."""
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    return session


def _load_history(session: ChatSession, limit: int | None = None) -> list[dict]:
    """Return the most recent messages as ``[{"role": ..., "content": ...}]``."""
    limit = limit or settings.max_history_messages
    messages = sorted(session.messages, key=lambda m: m.id)
    recent = messages[-limit:] if len(messages) > limit else messages
    return [{"role": m.role, "content": m.content} for m in recent]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/ask", response_model=AskOut)
def ask_question(
    body: AskIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a question and receive a grounded, citation-backed answer.

    - If ``session_id`` is provided, the question is appended to that session.
    - If ``session_id`` is omitted, a new session is created automatically.
    - Session ownership is enforced: users can only interact with their own sessions.
    """
    # Resolve or create session
    if body.session_id is not None:
        session = _get_user_session(body.session_id, user, db)
    else:
        session = ChatSession(user_id=user.id, title=body.question[:120])
        db.add(session)
        db.flush()  # assigns session.id

    # Load bounded conversation history for multi-turn
    history = _load_history(session)

    # Run the RAG pipeline
    try:
        result = rag.ask(question=body.question, db=db, history=history)
    except Exception as exc:
        log.exception("RAG pipeline failed for user %s", user.id)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The AI service is temporarily unavailable. Please try again.",
        ) from exc

    # Persist user message
    db.add(ChatMessage(session_id=session.id, role="user", content=body.question))

    # Build citation payload for storage
    citation_payload = [
        {
            "document_id": c.document_id,
            "filename": c.filename,
            "page_number": c.page_number,
            "chunk_index": c.chunk_index,
            "excerpt": c.excerpt,
        }
        for c in result.citations
    ]

    # Persist assistant message
    db.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content=result.answer,
            citations=citation_payload or None,
        )
    )
    db.commit()

    return AskOut(
        answer=result.answer,
        citations=[CitationOut(**c.__dict__) for c in result.citations],
        session_id=session.id,
        chunks_retrieved=result.chunks_retrieved,
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all chat sessions belonging to the authenticated user (newest first)."""
    return (
        db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user.id)
            .order_by(ChatSession.created_at.desc())
        )
        .all()
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
def get_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a session with its full message history (chronological).

    Ownership is enforced: users can only view their own sessions.
    """
    session = _get_user_session(session_id, user, db)
    messages = sorted(session.messages, key=lambda m: m.id)
    return SessionDetailOut(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def update_session_title(
    session_id: int,
    body: SessionTitleUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the title of a chat session."""
    session = _get_user_session(session_id, user, db)
    session.title = body.title
    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a chat session and all its messages (cascade)."""
    session = _get_user_session(session_id, user, db)
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
