"""Shared constants and small helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

# Difficulty stored in DB; labels for UI
DIFFICULTY_VALUES: tuple[str, ...] = ("red", "yellow", "green")
DIFFICULTY_LABELS: dict[str, str] = {
    "red": "Weak",
    "yellow": "Average",
    "green": "Easy / Strong",
}

# Study materials (Phase 2)
MATERIAL_TYPES: tuple[str, ...] = ("notes", "pyq", "assignment", "reference")
MATERIAL_TYPE_LABELS: dict[str, str] = {
    "notes": "Notes",
    "pyq": "PYQ (Previous Year Questions)",
    "assignment": "Assignment",
    "reference": "Reference Material",
}

ALLOWED_UPLOAD_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".txt", ".docx"})

# --- Phase 3: Ollama & RAG (override via environment variables) ---
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
# Chat model (user-facing)
OLLAMA_MODEL: str = os.environ.get("BRAIN_VAULT_OLLAMA_MODEL", "gemma:2b")
# Embeddings model — pull with: ollama pull nomic-embed-text
OLLAMA_EMBED_MODEL: str = os.environ.get("BRAIN_VAULT_EMBED_MODEL", "nomic-embed-text")

SUGGESTED_CHAT_MODELS: tuple[str, ...] = ("gemma:2b", "gemma:7b", "mistral:7b")

# Chunking (character-based; token-aware approx via modest sizes)
RAG_CHUNK_SIZE: int = int(os.environ.get("BRAIN_VAULT_CHUNK_SIZE", "1400"))
RAG_CHUNK_OVERLAP: int = int(os.environ.get("BRAIN_VAULT_CHUNK_OVERLAP", "220"))
RAG_TOP_K: int = int(os.environ.get("BRAIN_VAULT_TOP_K", "6"))

# Phase 5 — polish / motivation
ACADEMIC_QUOTES: tuple[str, ...] = (
    "Progress beats perfection — one chapter today moves the needle.",
    "Spaced repetition beats cramming: revisit weak topics before they fade.",
    "PYQs are forecasts, not guarantees — but they show how examiners think.",
    "Teach the concept in simple words — if you can, you understand.",
    "Sleep is part of the syllabus.",
)


def project_root() -> Path:
    """Directory containing app.py (parent of modules/)."""
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    root = project_root() / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def uploads_dir() -> Path:
    """Root folder for uploaded study files; created on demand."""
    root = project_root() / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def vector_db_dir() -> Path:
    """ChromaDB persistence directory."""
    root = project_root() / "vector_db"
    root.mkdir(parents=True, exist_ok=True)
    return root


def models_dir() -> Path:
    """Reserved for local model artifacts / future use."""
    root = project_root() / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def sanitize_path_segment(name: str, fallback: str = "subject") -> str:
    """Safe single path segment for subject folders / filenames (cross-platform)."""
    raw = (name or "").strip()
    raw = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw)
    raw = raw.strip(" .")
    if not raw:
        return fallback
    return raw[:120]


def format_bytes(num: int) -> str:
    """Human-readable file size."""
    n = float(max(num, 0))
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{int(num)} B"


def tags_from_filename(filename: str) -> str | None:
    """
    Lightweight auto-tagging for RAG metadata (Phase 3): e.g. sql_notes.pdf → SQL.
    Returns comma-separated tags or None.
    """
    stem = Path(filename).stem.lower()
    stem = re.sub(r"[^a-z0-9]+", " ", stem).strip()
    if not stem:
        return None
    # Prefer first meaningful token (often topic shorthand)
    parts = [p for p in stem.split() if len(p) > 1]
    if not parts:
        return None
    tag = parts[0].upper() if len(parts[0]) <= 5 else parts[0].title()
    return tag
