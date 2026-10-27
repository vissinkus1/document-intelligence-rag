"""Gemini embedding wrapper shared by ingestion (documents) and chat (queries)."""
import logging
import math
import time

from google import genai
from google.genai import types

from app.config import settings

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
RETRYABLE_CODES = {429, 500, 503, 504}

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in .env")
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def normalize(vec: list[float]) -> list[float]:
    """Gemini only returns unit-length vectors at 3072 dims. We request 768, so we
    normalize ourselves; otherwise cosine similarity scores are not comparable."""
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def _embed_batch(texts: list[str], task_type: str) -> list[list[float]]:
    client = _get_client()
    delay = 2.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = client.models.embed_content(
                model=settings.embedding_model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=settings.embedding_dim,
                ),
            )
            vectors = [normalize(list(e.values)) for e in result.embeddings]
            if len(vectors) != len(texts):
                raise RuntimeError("Gemini returned a different number of embeddings than inputs")
            return vectors
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code not in RETRYABLE_CODES or attempt == MAX_ATTEMPTS:
                raise
            log.warning("Embedding call failed (%s), retry %d in %.0fs", code, attempt, delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)
    raise RuntimeError("unreachable")


def embed_documents(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    size = settings.embedding_batch_size
    for i in range(0, len(texts), size):
        out.extend(_embed_batch(texts[i : i + size], "RETRIEVAL_DOCUMENT"))
    return out


def embed_query(text: str) -> list[float]:
    return _embed_batch([text], "RETRIEVAL_QUERY")[0]
