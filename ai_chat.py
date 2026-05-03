"""
Ollama chat + RAG orchestration, chat history, and connectivity checks (Phase 3).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import ollama

from modules.database import get_connection
from modules.rag_engine import retrieve_context
from modules.utils import OLLAMA_HOST, OLLAMA_MODEL


SYSTEM_BRAIN_VAULT = """You are **Brain Vault AI**, a patient local tutor for students.

Use ONLY the provided CONTEXT from the user's uploaded materials when giving factual claims.
If context is missing or insufficient, say so honestly and still give general study advice.

Style requirements:
- Clear, exam-oriented explanations
- Prefer structured answers: short intro, numbered steps or bullets where helpful
- Simple language; define jargon briefly
- When helpful, add a tiny “Remember for exams” line at the end

Never invent quotes from sources; attribute ideas to “your notes” generically."""


def ollama_available() -> bool:
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        client.list()
        return True
    except Exception:
        return False


def save_chat(
    subject_id: int,
    chapter_id: int | None,
    user_question: str,
    ai_response: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_history (subject_id, chapter_id, user_question, ai_response)
            VALUES (?, ?, ?, ?)
            """,
            (subject_id, chapter_id, user_question, ai_response),
        )
    try:
        from modules.timeline import log_activity

        log_activity(
            "ai_question",
            subject_id,
            message=(user_question or "")[:400],
        )
    except Exception:
        pass


def list_chat_history(subject_id: int | None = None, limit: int = 40) -> list[Any]:
    with get_connection() as conn:
        if subject_id is None:
            rows = conn.execute(
                """
                SELECT h.id, h.subject_id, h.chapter_id, h.user_question,
                       h.ai_response, h.created_at, s.name AS subject_name
                FROM chat_history h
                JOIN subjects s ON s.id = h.subject_id
                ORDER BY h.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT h.id, h.subject_id, h.chapter_id, h.user_question,
                       h.ai_response, h.created_at, s.name AS subject_name
                FROM chat_history h
                JOIN subjects s ON s.id = h.subject_id
                WHERE h.subject_id = ?
                ORDER BY h.id DESC
                LIMIT ?
                """,
                (subject_id, limit),
            ).fetchall()
    return list(rows)


def build_messages(
    question: str,
    context: str,
) -> list[dict[str, str]]:
    # Truncate context to ~1500 chars to stay within gemma:2b context limit
    ctx = context.strip()
    if len(ctx) > 1500:
        ctx = ctx[:1500] + "\n...(truncated)"
    ctx_block = ctx if ctx else "(No matching passages indexed yet.)"
    user_payload = (
        f"CONTEXT from uploaded materials:\n{ctx_block}\n\n"
        f"Student question:\n{question.strip()}"
    )
    return [
        {"role": "system", "content": SYSTEM_BRAIN_VAULT},
        {"role": "user", "content": user_payload},
    ]


def ask_brain_vault(
    question: str,
    subject_id: int,
    chapter_id: int | None,
    model: str | None = None,
) -> str:
    """Non-streaming answer."""
    ctx, _src = retrieve_context(question, subject_id, chapter_id)
    client = ollama.Client(host=OLLAMA_HOST)
    m = model or OLLAMA_MODEL
    resp = client.chat(
        model=m,
        messages=build_messages(question, ctx),
        options={"num_ctx": 2048, "num_predict": 512},
    )
    return (resp.message.content or "").strip()


def ask_brain_vault_stream(
    question: str,
    subject_id: int,
    chapter_id: int | None,
    model: str | None = None,
) -> Iterator[str]:
    """Token-ish streaming chunks from Ollama."""
    ctx, _src = retrieve_context(question, subject_id, chapter_id)
    client = ollama.Client(host=OLLAMA_HOST)
    m = model or OLLAMA_MODEL
    stream = client.chat(
        model=m,
        messages=build_messages(question, ctx),
        stream=True,
        options={"num_ctx": 2048, "num_predict": 512},
    )
    for chunk in stream:
        piece = chunk.message.content or ""
        if piece:
            yield piece
