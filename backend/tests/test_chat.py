"""Tests for retrieval, RAG, and chat endpoints.

Runs against a throwaway database (ragdb_chat_test) created and dropped by the test
itself, using the server from DATABASE_URL. The Gemini calls are fully mocked.
"""
import hashlib
import os
import pytest

_db_url_env = os.environ.get("DATABASE_URL")
if not _db_url_env or "postgresql" not in _db_url_env:
    pytest.skip(
        "PostgreSQL DATABASE_URL not set in environment (requires live PostgreSQL + pgvector). "
        "Run inside container via: docker compose exec backend pytest",
        allow_module_level=True,
    )

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import app.db as app_db
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import DocStatus, Document, DocumentChunk
from app.services import embeddings
from app.services import rag as rag_service
from tests.pdf_utils import make_pdf

# ---------------------------------------------------------------------------
# Fake embedding: deterministic, dimension-correct
# ---------------------------------------------------------------------------

FIXED_VECTOR = embeddings.normalize([1.0] + [0.0] * (settings.embedding_dim - 1))


def fake_embed_docs(texts):
    return [FIXED_VECTOR for _ in texts]


def fake_embed_query(text):
    return FIXED_VECTOR


embeddings.embed_documents = fake_embed_docs
embeddings.embed_query = fake_embed_query


# ---------------------------------------------------------------------------
# Fake LLM generation
# ---------------------------------------------------------------------------

FAKE_ANSWER = "According to the document, students must maintain 75% attendance [1]."


def fake_generate(system_prompt, user_prompt, **kwargs):
    """Return a deterministic answer with a [1] citation reference."""
    return FAKE_ANSWER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def upload(c, tok, files):
    return c.post("/documents", files=[("files", f) for f in files], headers=auth(tok))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_chat_pipeline():
    _base = make_url(_db_url_env)
    test_db_name = "ragdb_chat_test"
    admin_engine = create_engine(_base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {test_db_name} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {test_db_name}"))

    test_db_url = _base.set(database=test_db_name).render_as_string(hide_password=False)
    test_engine = create_engine(test_db_url, pool_pre_ping=True)
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    with test_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=test_engine)

    import app.services.ingestion as ingestion_mod
    old_engine = app_db.engine
    old_session_local = app_db.SessionLocal
    old_ingest_session = ingestion_mod.SessionLocal
    old_upload_dir = settings.upload_dir

    app_db.engine = test_engine
    app_db.SessionLocal = TestSessionLocal
    ingestion_mod.SessionLocal = TestSessionLocal
    settings.upload_dir = "/tmp/rag_chat_test_uploads"
    os.makedirs(settings.upload_dir, exist_ok=True)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    embeddings.embed_documents = fake_embed_docs
    embeddings.embed_query = fake_embed_query

    try:
        with TestClient(app) as c:
            # --- Setup: create users + upload a document ---
            r_admin = c.post("/auth/register", json={"email": "admin@t.com", "password": "password123"})
            assert r_admin.status_code == 201, r_admin.text
            r_member = c.post("/auth/register", json={"email": "member@t.com", "password": "password123"})
            assert r_member.status_code == 201, r_member.text

            at = c.post("/auth/login", data={"username": "admin@t.com", "password": "password123"}).json()["access_token"]
            mt = c.post("/auth/login", data={"username": "member@t.com", "password": "password123"}).json()["access_token"]

            # Upload and ingest a test PDF
            pdf = make_pdf(["Students must maintain a minimum attendance of 75% in each course."])
            r = upload(c, at, [("attendance.pdf", pdf, "application/pdf")])
            assert r.status_code == 202, r.text
            doc_id = r.json()[0]["id"]

            # Verify document is indexed
            with TestSessionLocal() as db:
                doc = db.get(Document, doc_id)
                assert doc is not None
                assert doc.status == DocStatus.indexed, f"Doc status: {doc.status}, error: {doc.error}"
                chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc_id)).all()
                assert len(chunks) > 0, "No chunks found"

            # ================================================================
            # TEST 1: Retrieval service
            # ================================================================
            from app.services.retrieval import retrieve_chunks

            with TestSessionLocal() as db:
                results = retrieve_chunks(
                    "What is the attendance requirement?",
                    db,
                    embed_fn=fake_embed_query,
                )
                assert len(results) > 0, "Retrieval returned no results"
                assert results[0].filename == "attendance.pdf"
                assert results[0].page_number == 1
                assert results[0].score > 0

            # Empty query
            with TestSessionLocal() as db:
                assert retrieve_chunks("", db, embed_fn=fake_embed_query) == []
                assert retrieve_chunks("   ", db, embed_fn=fake_embed_query) == []

            # ================================================================
            # TEST 2: RAG service (with fake LLM)
            # ================================================================
            with TestSessionLocal() as db:
                result = rag_service.ask(
                    "What is the attendance policy?",
                    db,
                    embed_fn=fake_embed_query,
                    generate_fn=fake_generate,
                )
                assert result.answer == FAKE_ANSWER
                assert len(result.citations) > 0, "No citations extracted"
                assert result.citations[0].filename == "attendance.pdf"
                assert result.citations[0].page_number == 1
                assert result.chunks_retrieved > 0

            # RAG with empty question
            with TestSessionLocal() as db:
                result = rag_service.ask("", db, embed_fn=fake_embed_query, generate_fn=fake_generate)
                assert "provide a question" in result.answer.lower()
                assert result.citations == []

            # ================================================================
            # TEST 3: Citation validation
            # ================================================================
            from app.services.rag import _extract_citation_refs, _validate_citations
            from app.services.retrieval import RetrievedChunk

            refs = _extract_citation_refs("Answer [1] and [2] and [99].")
            assert refs == {1, 2, 99}

            fake_chunks = [
                RetrievedChunk(chunk_id=1, document_id=1, filename="a.pdf", page_number=1, chunk_index=0, text="hello", score=0.9),
                RetrievedChunk(chunk_id=2, document_id=1, filename="a.pdf", page_number=2, chunk_index=1, text="world", score=0.8),
            ]
            citations = _validate_citations(refs, fake_chunks)
            assert len(citations) == 2  # [99] is invalid and should be dropped
            assert citations[0].page_number == 1
            assert citations[1].page_number == 2

            # ================================================================
            # TEST 4: Chat endpoints — ask question (new session)
            # ================================================================

            # Monkey-patch RAG to use fake functions
            original_retrieve = rag_service.retrieve_chunks
            original_generate = rag_service.generate

            import app.services.retrieval as retrieval_mod
            retrieval_mod.embed_query = fake_embed_query
            rag_service.generate = fake_generate

            r = c.post("/chat/ask", json={"question": "What is the attendance requirement?"}, headers=auth(mt))
            assert r.status_code == 200, r.text
            data = r.json()
            assert "answer" in data
            assert "session_id" in data
            assert "citations" in data
            session_id = data["session_id"]

            # ================================================================
            # TEST 5: Chat endpoints — ask follow-up (existing session)
            # ================================================================
            r = c.post(
                "/chat/ask",
                json={"question": "What happens if I fall below it?", "session_id": session_id},
                headers=auth(mt),
            )
            assert r.status_code == 200, r.text
            assert r.json()["session_id"] == session_id

            # ================================================================
            # TEST 6: Chat endpoints — unauthenticated
            # ================================================================
            assert c.post("/chat/ask", json={"question": "test"}).status_code == 401
            assert c.get("/chat/sessions").status_code == 401

            # ================================================================
            # TEST 7: Session listing
            # ================================================================
            r = c.get("/chat/sessions", headers=auth(mt))
            assert r.status_code == 200
            sessions = r.json()
            assert len(sessions) >= 1
            assert any(s["id"] == session_id for s in sessions)

            # Admin should NOT see member's sessions
            r = c.get("/chat/sessions", headers=auth(at))
            assert r.status_code == 200
            admin_sessions = r.json()
            assert not any(s["id"] == session_id for s in admin_sessions)

            # ================================================================
            # TEST 8: Session detail with messages
            # ================================================================
            r = c.get(f"/chat/sessions/{session_id}", headers=auth(mt))
            assert r.status_code == 200
            detail = r.json()
            assert len(detail["messages"]) == 4  # 2 user + 2 assistant
            assert detail["messages"][0]["role"] == "user"
            assert detail["messages"][1]["role"] == "assistant"

            # ================================================================
            # TEST 9: Session ownership enforcement
            # ================================================================
            r = c.get(f"/chat/sessions/{session_id}", headers=auth(at))
            assert r.status_code == 403

            # ================================================================
            # TEST 10: Session title update
            # ================================================================
            r = c.patch(f"/chat/sessions/{session_id}", json={"title": "Attendance Q&A"}, headers=auth(mt))
            assert r.status_code == 200
            assert r.json()["title"] == "Attendance Q&A"

            # ================================================================
            # TEST 11: Delete session
            # ================================================================
            r = c.delete(f"/chat/sessions/{session_id}", headers=auth(mt))
            assert r.status_code == 204
            r = c.get(f"/chat/sessions/{session_id}", headers=auth(mt))
            assert r.status_code == 404

            # ================================================================
            # TEST 12: Empty question validation
            # ================================================================
            r = c.post("/chat/ask", json={"question": ""}, headers=auth(mt))
            assert r.status_code == 422
            r = c.post("/chat/ask", json={"question": "   "}, headers=auth(mt))
            assert r.status_code == 422

            # ================================================================
            # TEST 13: Invalid session ID
            # ================================================================
            r = c.post("/chat/ask", json={"question": "test", "session_id": 99999}, headers=auth(mt))
            assert r.status_code == 404

            # ================================================================
            # TEST 14: Cross-user session access
            # ================================================================
            # Create a session as admin
            r = c.post("/chat/ask", json={"question": "Admin question"}, headers=auth(at))
            admin_session_id = r.json()["session_id"]

            # Member tries to use admin's session
            r = c.post(
                "/chat/ask",
                json={"question": "Hijack attempt", "session_id": admin_session_id},
                headers=auth(mt),
            )
            assert r.status_code == 403

            # Restore original functions
            retrieval_mod.embed_query = embeddings.embed_query
            rag_service.generate = original_generate

    finally:
        app.dependency_overrides.clear()
        app_db.engine = old_engine
        app_db.SessionLocal = old_session_local
        ingestion_mod.SessionLocal = old_ingest_session
        settings.upload_dir = old_upload_dir

        test_engine.dispose()
        with admin_engine.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {test_db_name} WITH (FORCE)"))
        admin_engine.dispose()
