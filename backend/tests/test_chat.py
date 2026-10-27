"""Tests for retrieval, RAG, and chat endpoints.

Runs against a throwaway database (ragdb_test) created and dropped by the test
itself, using the server from DATABASE_URL. The Gemini calls are fully mocked.

    docker compose exec backend python -m tests.test_chat
"""
import hashlib
import os

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

# --- point the app at a throwaway DB BEFORE importing it ---------------------
_base = make_url(os.environ["DATABASE_URL"])
TEST_DB = "ragdb_chat_test"
_admin = create_engine(_base.set(database="postgres"), isolation_level="AUTOCOMMIT")
with _admin.connect() as c:
    c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
    c.execute(text(f"CREATE DATABASE {TEST_DB}"))
os.environ["DATABASE_URL"] = _base.set(database=TEST_DB).render_as_string(hide_password=False)
os.environ["UPLOAD_DIR"] = "/tmp/rag_chat_test_uploads"

from dataclasses import dataclass  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DocStatus, Document, DocumentChunk  # noqa: E402
from app.services import embeddings  # noqa: E402
from app.services import rag as rag_service  # noqa: E402
from tests.pdf_utils import make_pdf  # noqa: E402


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

try:
    with TestClient(app) as c:
        # --- Setup: create users + upload a document ---
        c.post("/auth/register", json={"email": "admin@t.com", "password": "password123"})
        c.post("/auth/register", json={"email": "member@t.com", "password": "password123"})
        at = c.post("/auth/login", data={"username": "admin@t.com", "password": "password123"}).json()["access_token"]
        mt = c.post("/auth/login", data={"username": "member@t.com", "password": "password123"}).json()["access_token"]

        # Upload and ingest a test PDF
        pdf = make_pdf(["Students must maintain a minimum attendance of 75% in each course."])
        r = upload(c, at, [("attendance.pdf", pdf, "application/pdf")])
        assert r.status_code == 202, r.text
        doc_id = r.json()[0]["id"]

        # Wait for ingestion (it ran synchronously via background task in test client)
        import time
        time.sleep(1)

        # Verify document is indexed
        with SessionLocal() as db:
            doc = db.get(Document, doc_id)
            assert doc.status == DocStatus.indexed, f"Doc status: {doc.status}, error: {doc.error}"
            chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc_id)).all()
            assert len(chunks) > 0, "No chunks found"
            print(f"✓ Document indexed: {len(chunks)} chunks")

        # ================================================================
        # TEST 1: Retrieval service
        # ================================================================
        from app.services.retrieval import retrieve_chunks

        with SessionLocal() as db:
            results = retrieve_chunks(
                "What is the attendance requirement?",
                db,
                embed_fn=fake_embed_query,
            )
            assert len(results) > 0, "Retrieval returned no results"
            assert results[0].filename == "attendance.pdf"
            assert results[0].page_number == 1
            assert results[0].score > 0
            print(f"✓ Retrieval: {len(results)} chunks, top score={results[0].score}")

        # Empty query
        with SessionLocal() as db:
            assert retrieve_chunks("", db, embed_fn=fake_embed_query) == []
            assert retrieve_chunks("   ", db, embed_fn=fake_embed_query) == []
            print("✓ Retrieval: empty query returns []")

        # ================================================================
        # TEST 2: RAG service (with fake LLM)
        # ================================================================
        with SessionLocal() as db:
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
            print(f"✓ RAG service: answer + {len(result.citations)} citation(s)")

        # RAG with empty question
        with SessionLocal() as db:
            result = rag_service.ask("", db, embed_fn=fake_embed_query, generate_fn=fake_generate)
            assert "provide a question" in result.answer.lower()
            assert result.citations == []
            print("✓ RAG service: empty question handled")

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
        print("✓ Citation validation: invalid refs filtered")

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
        print(f"✓ POST /chat/ask: new session {session_id}, answer received")

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
        print("✓ POST /chat/ask: follow-up in existing session")

        # ================================================================
        # TEST 6: Chat endpoints — unauthenticated
        # ================================================================
        assert c.post("/chat/ask", json={"question": "test"}).status_code == 401
        assert c.get("/chat/sessions").status_code == 401
        print("✓ Chat: unauthenticated → 401")

        # ================================================================
        # TEST 7: Session listing
        # ================================================================
        r = c.get("/chat/sessions", headers=auth(mt))
        assert r.status_code == 200
        sessions = r.json()
        assert len(sessions) >= 1
        assert any(s["id"] == session_id for s in sessions)
        print(f"✓ GET /chat/sessions: {len(sessions)} sessions")

        # Admin should NOT see member's sessions
        r = c.get("/chat/sessions", headers=auth(at))
        assert r.status_code == 200
        admin_sessions = r.json()
        assert not any(s["id"] == session_id for s in admin_sessions)
        print("✓ Session isolation: admin cannot see member's sessions")

        # ================================================================
        # TEST 8: Session detail with messages
        # ================================================================
        r = c.get(f"/chat/sessions/{session_id}", headers=auth(mt))
        assert r.status_code == 200
        detail = r.json()
        assert len(detail["messages"]) == 4  # 2 user + 2 assistant
        assert detail["messages"][0]["role"] == "user"
        assert detail["messages"][1]["role"] == "assistant"
        print(f"✓ GET /chat/sessions/{session_id}: {len(detail['messages'])} messages")

        # ================================================================
        # TEST 9: Session ownership enforcement
        # ================================================================
        r = c.get(f"/chat/sessions/{session_id}", headers=auth(at))
        assert r.status_code == 403
        print("✓ Session ownership: admin denied access to member's session")

        # ================================================================
        # TEST 10: Session title update
        # ================================================================
        r = c.patch(f"/chat/sessions/{session_id}", json={"title": "Attendance Q&A"}, headers=auth(mt))
        assert r.status_code == 200
        assert r.json()["title"] == "Attendance Q&A"
        print("✓ PATCH session title")

        # ================================================================
        # TEST 11: Delete session
        # ================================================================
        r = c.delete(f"/chat/sessions/{session_id}", headers=auth(mt))
        assert r.status_code == 204
        r = c.get(f"/chat/sessions/{session_id}", headers=auth(mt))
        assert r.status_code == 404
        print("✓ DELETE session and cascade")

        # ================================================================
        # TEST 12: Empty question validation
        # ================================================================
        r = c.post("/chat/ask", json={"question": ""}, headers=auth(mt))
        assert r.status_code == 422
        r = c.post("/chat/ask", json={"question": "   "}, headers=auth(mt))
        assert r.status_code == 422
        print("✓ Empty/blank question → 422")

        # ================================================================
        # TEST 13: Invalid session ID
        # ================================================================
        r = c.post("/chat/ask", json={"question": "test", "session_id": 99999}, headers=auth(mt))
        assert r.status_code == 404
        print("✓ Invalid session_id → 404")

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
        print("✓ Cross-user session hijack → 403")

        # Restore original functions
        retrieval_mod.embed_query = embeddings.embed_query
        rag_service.generate = original_generate

        print("\n" + "=" * 60)
        print("ALL CHAT TESTS PASSED ✓")
        print("=" * 60)

finally:
    # Cleanup: drop the test database
    with _admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
    _admin.dispose()
