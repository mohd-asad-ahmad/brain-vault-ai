"""Smart reminders: CRUD, snooze, exam-aware hints (Phase 5)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from modules.database import get_connection


def list_reminders(status: str | None = None) -> list[sqlite3.Row]:
    with get_connection() as conn:
        if status:
            return list(
                conn.execute(
                    """
                    SELECT r.*, s.name AS subject_name
                    FROM reminders r
                    LEFT JOIN subjects s ON s.id = r.subject_id
                    WHERE r.status = ?
                    ORDER BY
                      CASE WHEN r.due_date IS NULL THEN 1 ELSE 0 END,
                      datetime(r.due_date) ASC,
                      r.id DESC
                    """,
                    (status,),
                )
            )
        return list(
            conn.execute(
                """
                SELECT r.*, s.name AS subject_name
                FROM reminders r
                LEFT JOIN subjects s ON s.id = r.subject_id
                ORDER BY
                  CASE WHEN r.status = 'active' THEN 0 ELSE 1 END,
                  datetime(r.due_date) ASC,
                  r.id DESC
                """
            )
        )


def add_reminder(
    title: str,
    body: str | None = None,
    subject_id: int | None = None,
    due_date: str | None = None,
    source: str = "user",
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO reminders (title, body, subject_id, due_date, source, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            """,
            (title.strip(), body, subject_id, due_date, source),
        )
        return int(cur.lastrowid)


def update_reminder_status(rid: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE reminders SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, rid),
        )


def snooze_reminder(rid: int, days: int = 1) -> None:
    until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE reminders
            SET status = 'snoozed', snooze_until = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (until, rid),
        )


def activate_if_snooze_expired() -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE reminders
            SET status = 'active', snooze_until = NULL, updated_at = datetime('now')
            WHERE status = 'snoozed' AND snooze_until IS NOT NULL
              AND datetime(snooze_until) <= datetime(?)
            """,
            (now,),
        )


def sync_smart_reminders() -> int:
    """
    Insert/update lightweight smart reminders (weak chapters, stale subjects, exams).
    Returns count of new rows inserted.
    """
    activate_if_snooze_expired()
    added = 0
    with get_connection() as conn:
        for row in conn.execute(
            """
            SELECT s.id, s.name,
                   (SELECT MAX(datetime(m.upload_date)) FROM materials m WHERE m.subject_id = s.id) AS last_up,
                   (SELECT MAX(datetime(h.created_at)) FROM chat_history h WHERE h.subject_id = s.id) AS last_chat
            FROM subjects s
            """
        ):
            sid = int(row["id"])
            name = row["name"]
            last_ts = row["last_up"] or row["last_chat"]
            if last_ts:
                try:
                    last_d = datetime.strptime(last_ts[:19], "%Y-%m-%d %H:%M:%S")
                    if datetime.now() - last_d > timedelta(days=8):
                        title = f"{name}: no activity in 8+ days — open your vault"
                        if not _exists_similar(conn, title):
                            conn.execute(
                                """
                                INSERT INTO reminders (title, body, subject_id, source, status)
                                VALUES (?, ?, ?, 'smart', 'active')
                                """,
                                (
                                    title,
                                    "Skim notes or ask the AI one question today.",
                                    sid,
                                ),
                            )
                            added += 1
                except Exception:
                    pass

        for ch in conn.execute(
            """
            SELECT s.name AS sub, c.chapter_name, c.subject_id
            FROM chapters c
            JOIN subjects s ON s.id = c.subject_id
            WHERE c.difficulty_rating = 'red'
            """
        ):
            title = f"Revise weak area: {ch['chapter_name']} ({ch['sub']})"
            if not _exists_similar(conn, title):
                conn.execute(
                    """
                    INSERT INTO reminders (title, body, subject_id, source, status)
                    VALUES (?, ?, ?, 'smart', 'active')
                    """,
                    (
                        title,
                        "You marked this chapter red. Short revision wins.",
                        int(ch["subject_id"]),
                    ),
                )
                added += 1

        for row in conn.execute(
            """
            SELECT s.id, s.name, COUNT(m.id) AS pyq
            FROM subjects s
            LEFT JOIN materials m ON m.subject_id = s.id AND m.material_type = 'pyq'
            GROUP BY s.id
            HAVING pyq > 0
            """
        ):
            title = f"PYQ practice available for {row['name']}"
            if not _exists_similar(conn, title):
                conn.execute(
                    """
                    INSERT INTO reminders (title, body, subject_id, source, status)
                    VALUES (?, ?, ?, 'smart', 'active')
                    """,
                    (
                        title,
                        "Try timed attempts using your uploaded PYQs.",
                        int(row["id"]),
                    ),
                )
                added += 1

    return added


def _exists_similar(conn: sqlite3.Connection, title_prefix: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM reminders WHERE title = ? AND status = 'active' LIMIT 1",
        (title_prefix,),
    ).fetchone()
    if row:
        return True
    like = title_prefix[:48] + "%"
    row = conn.execute(
        "SELECT 1 FROM reminders WHERE title LIKE ? LIMIT 1",
        (like,),
    ).fetchone()
    return row is not None


def set_exam_date(subject_id: int, exam_date: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO exam_dates (subject_id, exam_date)
            VALUES (?, ?)
            ON CONFLICT(subject_id) DO UPDATE SET exam_date = excluded.exam_date
            """,
            (subject_id, exam_date),
        )


def get_exam_dates() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return list(
            conn.execute(
                """
                SELECT e.subject_id, e.exam_date, s.name AS subject_name
                FROM exam_dates e
                JOIN subjects s ON s.id = e.subject_id
                ORDER BY e.exam_date
                """
            )
        )
