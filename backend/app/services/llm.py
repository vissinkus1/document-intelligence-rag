"""Gemini LLM generation client for RAG answers."""
import logging
import time

from google import genai
from google.genai import types

from app.config import settings

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRYABLE_CODES = {429, 500, 503, 504}

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in .env")
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def generate(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_output_tokens: int = 2048,
) -> str:
    """Generate a text response using the configured Gemini generation model.

    Retries on transient server errors with exponential backoff, matching
    the strategy used in the embedding service.

    Args:
        system_prompt: The system instruction guiding model behaviour.
        user_prompt: The user's question combined with retrieved context.
        temperature: Sampling temperature (lower = more deterministic).
        max_output_tokens: Maximum length of the generated response.

    Returns:
        The model's text response.

    Raises:
        RuntimeError: If GEMINI_API_KEY is missing or the model returns empty.
        Exception: Re-raised after exhausting retries.
    """
    client = _get_client()
    delay = 2.0

    # Build deduplicated model list to try
    models_to_try = [settings.generation_model]
    for fallback in ("gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"):
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    last_error = None
    for model_name in models_to_try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                    ),
                )
                text = response.text
                if not text:
                    raise RuntimeError("Gemini returned an empty response")
                return text
            except Exception as exc:
                last_error = exc
                code = getattr(exc, "code", None)
                if code in (404, 503):
                    log.warning("Model %s returned %s, trying fallback", model_name, code)
                    break  # Break inner loop and try next model
                if code not in RETRYABLE_CODES or attempt == MAX_ATTEMPTS:
                    break
                log.warning(
                    "Generation call failed (%s), retry %d in %.0fs",
                    code,
                    attempt,
                    delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 30)

    if last_error:
        raise last_error
    raise RuntimeError("Generation failed across all models")
