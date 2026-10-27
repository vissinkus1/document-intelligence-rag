"""Step 3 tests: upload, ingestion, listing, deletion.

Runs against a throwaway database (ragdb_test) created and dropped by the test
itself, using the server from DATABASE_URL. Only the Gemini call is faked.

    docker compose exec backend python -m tests.test_documents
"""
import hashlib
import os

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

# --- point the app at a throwaway DB BEFORE importing it ---------------------
_base = make_url(os.environ["DATABASE_URL"])
TEST_DB = "ragdb_test"
_admin = create_engine(_base.set(database="postgres"), isolation_level="AUTOCOMMIT")
with _admin.connect() as c:
    c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
    c.execute(text(f"CREATE DATABASE {TEST_DB}"))
os.environ["DATABASE_URL"] = _base.set(database=TEST_DB).render_as_string(hide_password=False)
os.environ["UPLOAD_DIR"] = "/tmp/rag_test_uploads"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DocStatus, Document, DocumentChunk  # noqa: E402
from app.services import embeddings  # noqa: E402
from app.services.ingestion import recover_stuck_documents  # noqa: E402
from tests.pdf_utils import make_pdf  # noqa: E402


def fake_embed(texts):
    out = []
    for t in texts:
        h = hashlib.sha256(t.encode()).digest()
        out.append(embeddings.normalize([(h[i % 32] - 128) / 128 for i in range(settings.embedding_dim)]))
    return out


embeddings.embed_documents = fake_embed  # ingestion looks this up at call time


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def upload(c, tok, files):
    return c.post("/documents", files=[("files", f) for f in files], headers=auth(tok))


try:
    with TestClient(app) as c:
        assert settings.upload_dir == "/tmp/rag_test_uploads"
        c.post("/auth/register", json={"email": "admin@t.com", "password": "password123"})
        c.post("/auth/register", json={"email": "emp@t.com", "password": "password123"})
        at = c.post("/auth/login", data={"username": "admin@t.com", "password": "password123"}).json()["access_token"]
        mt = c.post("/auth/login", data={"username": "emp@t.com", "password": "password123"}).json()["access_token"]

        # --- access control & validation ---
        pdf = make_pdf(["hello"])
        assert upload(c, mt, [("a.pdf", pdf, "application/pdf")]).status_code == 403
        assert c.post("/documents", files=[("files", ("a.pdf", pdf))]).status_code == 401
        assert upload(c, at, [("a.txt", b"hi", "text/plain")]).status_code == 400
        assert upload(c, at, [("fake.pdf", b"not really a pdf", "application/pdf")]).status_code == 400
        assert upload(c, at, [("empty.pdf", b"", "application/pdf")]).status_code == 400
        old = settings.max_upload_mb
        settings.max_upload_mb = 1
        assert upload(c, at, [("big.pdf", b"%PDF-" + b"x" * (1024 * 1024 + 10), "application/pdf")]).status_code == 413
        settings.max_upload_mb = old
        # one bad file in a batch -> nothing saved
        r = upload(c, at, [("ok.pdf", pdf, "application/pdf"), ("bad.txt", b"x", "text/plain")])
        assert r.status_code == 400
        assert c.get("/documents", headers=auth(at)).json() == []
        print("access control + validation OK (403/401/400/413, batch is all-or-nothing)")

        # --- happy path: 3 pages, page 2 holds a unique marker ---
        p1 = "Leave policy. " * 150          # long enough to need several chunks
        p2 = "The reimbursement process requires form ZX-9981 signed by a manager. " * 20
        p3 = "Short final page about the dress code."
        big = make_pdf([p1, p2, p3])
        r = upload(c, at, [("HR_Policy.pdf", big, "application/pdf")])
        assert r.status_code == 202, r.text
        doc = r.json()[0]
        assert doc["filename"] == "HR_Policy.pdf" and doc["status"] == "uploaded"
        doc_id = doc["id"]

        got = c.get(f"/documents/{doc_id}", headers=auth(mt)).json()   # member may read
        assert got["status"] == "indexed", got
        assert got["page_count"] == 3 and got["error"] is None
        with SessionLocal() as db:
            chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
                                .order_by(DocumentChunk.chunk_index)).all()
            assert len(chunks) >= 4, len(chunks)
            assert [ch.chunk_index for ch in chunks] == list(range(len(chunks)))
            assert {ch.page_number for ch in chunks} == {1, 2, 3}
            assert all(len(ch.embedding) == 768 for ch in chunks)
            marker = [ch for ch in chunks if "ZX-9981" in ch.text]
            assert marker and all(ch.page_number == 2 for ch in marker), "citation page wrong"
            assert all(len(ch.text) <= settings.chunk_size + 50 for ch in chunks)
            # pgvector similarity search really works against stored vectors
            q = fake_embed([marker[0].text])[0]
            best = db.scalars(select(DocumentChunk).order_by(DocumentChunk.embedding.cosine_distance(q)).limit(1)).one()
            assert best.id == marker[0].id
            path = db.get(Document, doc_id).file_path
            assert os.path.exists(path)
        print(f"ingestion OK: {len(chunks)} chunks, pages {{1,2,3}}, 768-dim vectors, "
              "marker on page 2 cited correctly, cosine search finds it")

        # --- multi-file upload ---
        r = upload(c, at, [("A.pdf", make_pdf(["alpha text " * 30]), "application/pdf"),
                           ("B.pdf", make_pdf(["beta text " * 30]), "application/pdf")])
        assert r.status_code == 202 and len(r.json()) == 2
        lst = c.get("/documents", headers=auth(mt)).json()
        assert [d["status"] for d in lst] == ["indexed"] * 3
        assert lst[0]["id"] > lst[-1]["id"]  # newest first
        print("multi-file upload + listing OK")

        # --- failure modes surface as status=failed with a message ---
        r = upload(c, at, [("scan.pdf", make_pdf(["", ""]), "application/pdf")])
        d = c.get(f"/documents/{r.json()[0]['id']}", headers=auth(at)).json()
        assert d["status"] == "failed" and "scanned" in d["error"], d
        print("scanned/blank PDF -> failed with clear message")

        def boom(texts):
            raise RuntimeError("GEMINI_API_KEY is not set in .env")
        embeddings.embed_documents = boom
        r = upload(c, at, [("x.pdf", make_pdf(["some text " * 20]), "application/pdf")])
        did = r.json()[0]["id"]
        d = c.get(f"/documents/{did}", headers=auth(at)).json()
        assert d["status"] == "failed" and "GEMINI_API_KEY" in d["error"], d
        with SessionLocal() as db:
            assert db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == did)) == 0
        embeddings.embed_documents = fake_embed
        print("embedding failure -> failed, error stored, zero partial chunks")

        # --- chunks endpoint ---
        assert c.get(f"/documents/{doc_id}/chunks", headers=auth(mt)).status_code == 403
        ch = c.get(f"/documents/{doc_id}/chunks?limit=2", headers=auth(at)).json()
        assert len(ch) == 2 and ch[0]["chunk_index"] == 0 and "embedding" not in ch[0]
        assert c.get("/documents/9999/chunks", headers=auth(at)).status_code == 404
        print("chunks endpoint: admin only, no embeddings leaked")

        # --- restart recovery ---
        with SessionLocal() as db:
            stuck = Document(filename="stuck.pdf", file_path="/nope", uploaded_by=1, status=DocStatus.processing)
            db.add(stuck); db.commit(); sid = stuck.id
        recover_stuck_documents()
        d = c.get(f"/documents/{sid}", headers=auth(at)).json()
        assert d["status"] == "failed" and "restart" in d["error"]
        print("restart recovery: stuck 'processing' doc marked failed")

        # --- delete ---
        assert c.delete(f"/documents/{doc_id}", headers=auth(mt)).status_code == 403
        assert c.delete(f"/documents/{doc_id}", headers=auth(at)).status_code == 204
        assert c.delete(f"/documents/{doc_id}", headers=auth(at)).status_code == 404
        assert not os.path.exists(path), "file left on disk"
        with SessionLocal() as db:
            assert db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc_id)) == 0
        assert c.get(f"/documents/{doc_id}", headers=auth(at)).status_code == 404
        print("delete OK: member blocked, file removed from disk, chunks cascaded away")

        # --- embedding utils ---
        import math
        v = embeddings.normalize([3.0, 4.0]); assert abs(math.hypot(*v) - 1) < 1e-9
        assert embeddings.normalize([0.0, 0.0]) == [0.0, 0.0]
        print("normalize OK")

    print("\nALL STEP 3 TESTS PASSED")
finally:
    from app.db import engine
    engine.dispose()
    with _admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
