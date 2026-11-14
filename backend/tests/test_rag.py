"""Unit tests for RAG helper functions (citation cleaning, history formatting, greeting filter)."""
from app.services.rag import (
    _build_history_block,
    _clean_dangling_citations,
    _is_conversational,
)


def test_build_history_block_strips_old_assistant_citations():
    history = [
        {"role": "user", "content": "What is the attendance policy?"},
        {
            "role": "assistant",
            "content": "Students must maintain 75% attendance [1] according to regulations [2].",
        },
        {"role": "user", "content": "Is there any exception?"},
    ]
    block = _build_history_block(history)

    assert "[1]" not in block
    assert "[2]" not in block
    assert "Students must maintain 75% attendance according to regulations." in block
    assert "User: What is the attendance policy?" in block
    assert "User: Is there any exception?" in block


def test_clean_dangling_citations():
    # Only 2 passages retrieved
    max_valid = 2

    # Passage [1] is valid, [5] and [9] are dangling
    raw = "The minimum CGPA is 6.0 [1]. Applications must be submitted by Monday [5] or Tuesday [9]."
    cleaned = _clean_dangling_citations(raw, max_valid=max_valid)

    assert "[1]" in cleaned
    assert "[5]" not in cleaned
    assert "[9]" not in cleaned
    assert cleaned == "The minimum CGPA is 6.0 [1]. Applications must be submitted by Monday or Tuesday."


def test_conversational_filter_strictness():
    # Pure conversational queries
    assert _is_conversational("hi") is True
    assert _is_conversational("Hello!") is True
    assert _is_conversational("Good morning.") is True
    assert _is_conversational("who are you?") is True
    assert _is_conversational("thank you so much") is True
    assert _is_conversational("my name is Alice") is True

    # Queries that start with greetings or introductions but contain real questions
    assert _is_conversational("Hi, what is the leave policy?") is False
    assert _is_conversational("I am a new student, what is the fee deadline?") is False
    assert _is_conversational("Hello, where is the library located?") is False
    assert _is_conversational("what is the grading scale?") is False

