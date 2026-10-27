"""Semantic vector retrieval using pgvector cosine distance."""
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DocStatus, Document, DocumentChunk
from app.services.embeddings import embed_query

log = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A document chunk returned by vector similarity search."""

    chunk_id: int
    document_id: int
    filename: str
    page_number: int
    chunk_index: int
    text: str
    score: float  # cosine similarity (1 - cosine_distance)


def retrieve_chunks(
    query: str,
    db: Session,
    top_k: int | None = None,
    score_threshold: float | None = None,
    embed_fn=None,
) -> list[RetrievedChunk]:
    """Retrieve the most relevant document chunks for a query.

    Uses pgvector's ``<=>`` (cosine distance) operator for database-side
    similarity search.  Results are ranked by similarity, with deterministic
    tie-breaking on ``DocumentChunk.id``.

    Args:
        query: The user's natural-language question.
        db: An active SQLAlchemy session.
        top_k: Maximum number of chunks to return (default from settings).
        score_threshold: Minimum cosine similarity to include (default from settings).
        embed_fn: Optional override for the embedding function (testing).

    Returns:
        A list of ``RetrievedChunk`` objects ordered by descending similarity.
    """
    top_k = top_k or settings.retrieval_top_k
    score_threshold = (
        score_threshold if score_threshold is not None else settings.retrieval_score_threshold
    )
    embed_fn = embed_fn or embed_query

    if not query or not query.strip():
        return []

    # 1. Embed the query
    query_embedding = embed_fn(query.strip())

    # 2. Build pgvector cosine-distance query
    distance_expr = DocumentChunk.embedding.cosine_distance(query_embedding)

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.page_number,
            DocumentChunk.chunk_index,
            DocumentChunk.text,
            Document.filename,
            distance_expr.label("distance"),
        )
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(DocumentChunk.embedding.isnot(None))
        .where(Document.status == DocStatus.indexed)
        .order_by(distance_expr, DocumentChunk.id)  # deterministic tie-breaking
        .limit(top_k)
    )

    rows = db.execute(stmt).all()

    # 3. Filter by similarity threshold and build results
    results: list[RetrievedChunk] = []
    for row in rows:
        similarity = 1.0 - row.distance
        if similarity < score_threshold:
            continue
        results.append(
            RetrievedChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                filename=row.filename,
                page_number=row.page_number,
                chunk_index=row.chunk_index,
                text=row.text,
                score=round(similarity, 4),
            )
        )

    log.info(
        "Retrieved %d chunks for query (top_k=%d, threshold=%.2f): %.60s...",
        len(results),
        top_k,
        score_threshold,
        query,
    )
    return results
