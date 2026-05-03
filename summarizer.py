"""
Summaries, exam topic mining, and weak-area coaching using Ollama (Phase 3).
"""

from __future__ import annotations

from typing import Any

import ollama

from modules.rag_engine import load_subject_material_blob, retrieve_context
from modules.subjects import list_chapters_by_difficulty
from modules.utils import OLLAMA_HOST, OLLAMA_MODEL


SUMMARY_STYLE_PROMPTS: dict[str, str] = {
    "short": "Produce a **short summary** (roughly 10–15 lines). Keep only essentials.",
    "exam": "Produce **exam revision notes**: formulas/steps, traps to avoid, 1-line recap per major idea.",
    "bullets": "Use **mostly bullet points**. Keep bullets tight and scannable.",
    "easy": "Use **very easy language** (assume a tired student). Short sentences, analogies welcome.",
    "detailed": "Produce **detailed notes**: structured sections, examples if present in sources.",
}


def _chat_simple(system: str, user: str, model: str | None = None) -> str:
    client = ollama.Client(host=OLLAMA_HOST)
    m = model or OLLAMA_MODEL
    resp = client.chat(
        model=m,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    msg = resp.get("message") or {}
    return (msg.get("content") or "").strip()


def generate_summary(
    subject_id: int,
    chapter_id: int | None,
    style_key: str,
    subject_name: str,
    model: str | None = None,
) -> str:
    style = SUMMARY_STYLE_PROMPTS.get(style_key, SUMMARY_STYLE_PROMPTS["short"])
    blob = load_subject_material_blob(subject_id, chapter_id)
    if not blob.strip():
        return "No extracted text found for this selection. Upload materials and index the knowledge base."
    system = (
        "You are Brain Vault AI. Summarize study materials for exam preparation.\n"
        "Stay faithful to the sources; do not invent facts or exam questions.\n"
        f"{style}"
    )
    scope = (
        f"Subject: {subject_name}\n"
        + (
            f"Focus chapter filter: yes (materials tagged to this chapter + general notes).\n"
            if chapter_id is not None
            else "Scope: whole subject.\n"
        )
    )
    user = f"{scope}\n--- MATERIAL START ---\n{blob[:85000]}\n--- MATERIAL END ---"
    return _chat_simple(system, user, model=model)


def find_important_topics(
    subject_id: int,
    chapter_id: int | None,
    subject_name: str,
    model: str | None = None,
) -> str:
    blob = load_subject_material_blob(subject_id, chapter_id)
    extra_ctx, _ = retrieve_context(
        "important topics exams PYQs likely questions",
        subject_id,
        chapter_id,
        top_k=8,
    )
    if not blob.strip() and not extra_ctx.strip():
        return "No study text available. Upload notes or PYQs first, then index."
    system = (
        "You are Brain Vault AI. Identify important exam topics from the student's materials.\n"
        "Pay special attention to **PYQ / assignment** style repetition when present.\n"
        "Output sections:\n"
        "## High-impact topics\n"
        "## Likely exam angles\n"
        "## Focus-first study order (today)\n"
        "Use bullets; keep it actionable."
    )
    user = (
        f"Subject: {subject_name}\n\n"
        f"### Retrieved snippets (semantic)\n{extra_ctx[:12000]}\n\n"
        f"### Full-text bundle (truncated)\n{blob[:65000]}"
    )
    return _chat_simple(system, user, model=model)


def weak_portion_coach(
    subject_id: int,
    subject_name: str,
    model: str | None = None,
) -> str:
    weak = list_chapters_by_difficulty(subject_id, "red")
    if not weak:
        return (
            "No **red (weak)** chapters are marked for this subject yet. "
            "Mark difficulty under **Manage Chapters**, then return here."
        )
    names = ", ".join(r["chapter_name"] for r in weak)
    focus_blob = load_subject_material_blob(subject_id, None, max_chars=60000)
    weak_queries = " ".join(r["chapter_name"] for r in weak[:12])
    rag_hint, _ = retrieve_context(
        f"Revision plan for weak topics: {weak_queries}",
        subject_id,
        None,
        top_k=10,
    )
    system = (
        "You are Brain Vault AI — a supportive coach.\n"
        "The student marked these chapters as weak (red). Build a practical revision plan:\n"
        "- Priority weak areas (why they matter)\n"
        "- Suggested order for today (30–90 minutes)\n"
        "- Two micro-tasks per weak chapter\n"
        "- Quick wins vs deeper fixes\n"
        "Keep tone encouraging; no shaming."
    )
    user = (
        f"Subject: {subject_name}\n"
        f"**Weak chapters (red):** {names}\n\n"
        f"### Context snippets\n{rag_hint[:14000]}\n\n"
        f"### Notes bundle (truncated)\n{focus_blob[:50000]}"
    )
    return _chat_simple(system, user, model=model)
