"""Business logic: subjects and chapters."""

from __future__ import annotations

import sqlite3
from typing import Any

from modules.database import get_connection


class SubjectError(Exception):
    """Domain error for subject operations."""


def list_subjects() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return list(
            conn.execute(
                "SELECT id, name, created_at FROM subjects ORDER BY name COLLATE NOCASE"
            )
        )


def add_subject(name: str) -> int:
    name = (name or "").strip()
    if not name:
        raise SubjectError("Subject name cannot be empty.")
    try:
        with get_connection() as conn:
            cur = conn.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
            return int(cur.lastrowid)
    except sqlite3.IntegrityError as e:
        raise SubjectError("A subject with this name already exists.") from e


def delete_subject(subject_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))


def list_chapters_by_subject() -> list[sqlite3.Row]:
    """All chapters with subject name, ordered by subject then chapter."""
    with get_connection() as conn:
        return list(
            conn.execute(
                """
                SELECT c.id, c.subject_id, c.chapter_name, c.difficulty_rating,
                       c.created_at, s.name AS subject_name
                FROM chapters c
                JOIN subjects s ON s.id = c.subject_id
                ORDER BY s.name COLLATE NOCASE, c.chapter_name COLLATE NOCASE
                """
            )
        )


def add_chapter(subject_id: int, chapter_name: str, difficulty_rating: str) -> int:
    chapter_name = (chapter_name or "").strip()
    if not chapter_name:
        raise SubjectError("Chapter name cannot be empty.")
    if difficulty_rating not in ("red", "yellow", "green"):
        raise SubjectError("Invalid difficulty rating.")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO chapters (subject_id, chapter_name, difficulty_rating)
            VALUES (?, ?, ?)
            """,
            (subject_id, chapter_name, difficulty_rating),
        )
        return int(cur.lastrowid)


def delete_chapter(chapter_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))


def list_chapters_by_difficulty(
    subject_id: int, difficulty_rating: str
) -> list[sqlite3.Row]:
    """Chapters for a subject filtered by difficulty (e.g. red = weak)."""
    with get_connection() as conn:
        return list(
            conn.execute(
                """
                SELECT id, chapter_name, difficulty_rating, created_at
                FROM chapters
                WHERE subject_id = ? AND difficulty_rating = ?
                ORDER BY chapter_name COLLATE NOCASE
                """,
                (subject_id, difficulty_rating),
            )
        )


def dashboard_stats() -> dict[str, Any]:
    with get_connection() as conn:
        total_subjects = conn.execute(
            "SELECT COUNT(*) AS c FROM subjects"
        ).fetchone()["c"]
        total_chapters = conn.execute(
            "SELECT COUNT(*) AS c FROM chapters"
        ).fetchone()["c"]
        weak = conn.execute(
            "SELECT COUNT(*) AS c FROM chapters WHERE difficulty_rating = 'red'"
        ).fetchone()["c"]
        medium = conn.execute(
            "SELECT COUNT(*) AS c FROM chapters WHERE difficulty_rating = 'yellow'"
        ).fetchone()["c"]
        strong = conn.execute(
            "SELECT COUNT(*) AS c FROM chapters WHERE difficulty_rating = 'green'"
        ).fetchone()["c"]
    return {
        "total_subjects": total_subjects,
        "total_chapters": total_chapters,
        "weak": weak,
        "medium": medium,
        "strong": strong,
    }


def chapters_per_subject() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return list(
            conn.execute(
                """
                SELECT s.name AS subject_name, COUNT(c.id) AS chapter_count
                FROM subjects s
                LEFT JOIN chapters c ON c.subject_id = s.id
                GROUP BY s.id, s.name
                ORDER BY chapter_count DESC, s.name COLLATE NOCASE
                """
            )
        )


def difficulty_distribution() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return list(
            conn.execute(
                """
                SELECT difficulty_rating, COUNT(*) AS cnt
                FROM chapters
                GROUP BY difficulty_rating
                """
            )
        )


def subject_with_most_chapters() -> sqlite3.Row | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT s.name AS subject_name, COUNT(c.id) AS chapter_count
            FROM subjects s
            LEFT JOIN chapters c ON c.subject_id = s.id
            GROUP BY s.id, s.name
            ORDER BY chapter_count DESC, s.name COLLATE NOCASE
            LIMIT 1
            """
        ).fetchone()
        return row
