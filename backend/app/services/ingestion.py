"""PDF -> pages -> chunks -> embeddings -> pgvector."""
import logging

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import update

from app.config import settings
from app.db import SessionLocal
from app.models import DocStatus, Document, DocumentChunk
from app.services import embeddings

log = logging.getLogger(__name__)


class IngestionError(Exception):
    pass


def extract_pages(path: str) -> list[tuple[int, str]]:
    """Returns [(page_number starting at 1, text)] for EVERY page (text may be empty)."""
    reader = PdfReader(path)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise IngestionError("PDF is password-protected")
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").replace("\x00", "")  # Postgres rejects NUL bytes
        pages.append((i, text.strip()))
    return pages


def chunk_pages(pages: list[tuple[int, str]]) -> list[dict]:
    """Chunks each page separately so every chunk has one exact page number to cite.
    Trade-off: a sentence that runs across a page break is split."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    chunks, idx = [], 0
    for page_number, text in pages:
        if not text:
            continue
        for piece in splitter.split_text(text):
            if piece.strip():
                chunks.append({"chunk_index": idx, "page_number": page_number, "text": piece})
                idx += 1
    return chunks


def ingest_document(doc_id: int, embed_fn=None, session_factory=None) -> None:
    """Runs as a background task, so it opens its own DB session."""
    session_factory = session_factory or SessionLocal
    embed_fn = embed_fn or embeddings.embed_documents

    with session_factory() as db:
        doc = db.get(Document, doc_id)
        if doc is None:
            return
        doc.status = DocStatus.processing
        doc.error = None
        db.commit()
        try:
            pages = extract_pages(doc.file_path)
            chunks = chunk_pages(pages)
            if not chunks:
                raise IngestionError(
                    "No extractable text found. This looks like a scanned/image-only PDF "
                    "(OCR support is planned for a later phase)."
                )
            vectors = embed_fn([c["text"] for c in chunks])
            if len(vectors) != len(chunks):
                raise IngestionError("Embedding count did not match chunk count")

            db.add_all(
                DocumentChunk(document_id=doc_id, embedding=vec, **c)
                for c, vec in zip(chunks, vectors)
            )
            doc.page_count = len(pages)
            doc.status = DocStatus.indexed
            db.commit()
            log.info("Indexed document %s: %d pages, %d chunks", doc_id, len(pages), len(chunks))
        except Exception as exc:
            db.rollback()
            log.exception("Ingestion failed for document %s", doc_id)
            doc = db.get(Document, doc_id)  # may have been deleted meanwhile
            if doc is not None:
                doc.status = DocStatus.failed
                doc.error = str(exc)[:500]
                db.commit()


def recover_stuck_documents() -> None:
    """Background tasks die with the server (and uvicorn --reload restarts often).
    Anything left mid-flight at startup is marked failed so the UI never spins forever."""
    with SessionLocal() as db:
        db.execute(
            update(Document)
            .where(Document.status.in_([DocStatus.uploaded, DocStatus.processing]))
            .values(
                status=DocStatus.failed,
                error="Processing was interrupted by a server restart. Delete and re-upload.",
            )
        )
        db.commit()
