"""Study sessions, engagement metrics, streaks, exports (Phase 5)."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from modules.database import get_connection
from modules.subjects import list_chapters_by_difficulty


def add_study_session(
    subject_id: int | None, duration_minutes: int, note: str | None = None
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO study_sessions (subject_id, duration_minutes, note)
            VALUES (?, ?, ?)
            """,
            (subject_id, duration_minutes, note),
        )


def set_manual_hours_today(hours: float) -> None:
    day = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO manual_focus_hours (day, hours, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(day) DO UPDATE SET hours = excluded.hours,
                updated_at = datetime('now')
            """,
            (day, hours),
        )


def get_manual_hours_today() -> float:
    day = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT hours FROM manual_focus_hours WHERE day = ?", (day,)
        ).fetchone()
    return float(row["hours"]) if row else 0.0


def sessions_this_week() -> int:
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM study_sessions WHERE created_at >= ?",
                (since,),
            ).fetchone()["c"]
        )


def engagement_snapshot() -> dict[str, Any]:
    """Most / least touched subjects by combined signals."""
    with get_connection() as conn:
        subs = list(conn.execute("SELECT id, name FROM subjects"))
        scores: dict[int, float] = {int(r["id"]): 0.0 for r in subs}
        for r in conn.execute(
            """
            SELECT subject_id, COUNT(*) AS c FROM chat_history
            GROUP BY subject_id
            """
        ):
            if r["subject_id"]:
                scores[int(r["subject_id"])] += float(r["c"]) * 3
        for r in conn.execute(
            """
            SELECT subject_id, COUNT(*) AS c FROM materials
            GROUP BY subject_id
            """
        ):
            if r["subject_id"]:
                scores[int(r["subject_id"])] += float(r["c"]) * 2
        for r in conn.execute(
            """
            SELECT subject_id, SUM(duration_minutes) AS m FROM study_sessions
            WHERE subject_id IS NOT NULL
            GROUP BY subject_id
            """
        ):
            scores[int(r["subject_id"])] += float(r["m"] or 0) * 0.05

    if not scores:
        return {
            "most": None,
            "least": None,
            "weakest_subj": None,
            "strongest_subj": None,
            "scores": {},
        }

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    most_id, most_v = ranked[0]
    least_id, least_v = ranked[-1]

    weak_subj = None
    strong_subj = None
    max_red = -1
    max_green = -1
    with get_connection() as conn:
        for r in subs:
            sid = int(r["id"])
            rc = conn.execute(
                """
                SELECT COUNT(*) AS c FROM chapters
                WHERE subject_id = ? AND difficulty_rating = 'red'
                """,
                (sid,),
            ).fetchone()["c"]
            gc = conn.execute(
                """
                SELECT COUNT(*) AS c FROM chapters
                WHERE subject_id = ? AND difficulty_rating = 'green'
                """,
                (sid,),
            ).fetchone()["c"]
            if rc > max_red:
                max_red = rc
                weak_subj = r["name"]
            if gc > max_green:
                max_green = gc
                strong_subj = r["name"]

    id_to_name = {int(r["id"]): r["name"] for r in subs}
    return {
        "most": id_to_name.get(most_id),
        "least": id_to_name.get(least_id) if len(ranked) > 1 else None,
        "weakest_subj": weak_subj,
        "strongest_subj": strong_subj,
        "scores": {id_to_name[k]: v for k, v in scores.items()},
    }


def compute_streak_days() -> int:
    """Consecutive days with any vault activity (UTC-ish local via SQLite dates)."""
    with get_connection() as conn:
        days_set = set()
        for q in (
            "SELECT date(created_at) AS d FROM chat_history",
            "SELECT date(created_at) AS d FROM activity_events",
            "SELECT date(upload_date) AS d FROM materials",
            "SELECT date(created_at) AS d FROM study_sessions",
        ):
            for r in conn.execute(q):
                if r["d"]:
                    days_set.add(r["d"])
    if not days_set:
        return 0
    today = datetime.now().date()
    streak = 0
    for i in range(0, 400):
        d = (today - timedelta(days=i)).isoformat()
        if d in days_set:
            streak += 1
        else:
            if i == 0:
                # allow "yesterday" start if no activity today
                continue
            break
    return streak


# --- Export center ---


def _weak_chapter_report() -> str:
    lines: list[str] = ["# Brain Vault — Weak topic report", ""]
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.name AS sub, c.chapter_name, c.difficulty_rating
            FROM chapters c
            JOIN subjects s ON s.id = c.subject_id
            WHERE c.difficulty_rating = 'red'
            ORDER BY s.name, c.chapter_name
            """
        ).fetchall()
    if not rows:
        lines.append("No red (weak) chapters recorded. Mark difficulty under Manage Chapters.")
    else:
        for r in rows:
            lines.append(f"- **{r['sub']}** — {r['chapter_name']}")
    return "\n".join(lines)


def _revision_plan_text() -> str:
    lines: list[str] = ["# Revision planner snapshot", ""]
    with get_connection() as conn:
        subs = conn.execute("SELECT id, name FROM subjects").fetchall()
    for s in subs:
        sid = int(s["id"])
        weak = list_chapters_by_difficulty(sid, "red")
        if not weak:
            continue
        lines.append(f"## {s['name']}")
        for w in weak:
            lines.append(f"1. Revise: **{w['chapter_name']}** (weak)")
        lines.append("")
    if len(lines) <= 2:
        lines.append("No weak chapters found across subjects.")
    return "\n".join(lines)


def export_chat_txt() -> str:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT h.created_at, s.name AS sub, h.user_question, h.ai_response
            FROM chat_history h
            JOIN subjects s ON s.id = h.subject_id
            ORDER BY h.id ASC
            """
        ).fetchall()
    parts = ["# Brain Vault — AI chat export", ""]
    for r in rows:
        parts.append(f"## {r['created_at']} · {r['sub']}")
        parts.append(f"**Q:** {r['user_question']}")
        parts.append(f"**A:** {r['ai_response']}")
        parts.append("")
    return "\n".join(parts) if rows else "No chat history yet."


def export_chat_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["created_at", "subject", "question", "answer"])
    with get_connection() as conn:
        for r in conn.execute(
            """
            SELECT h.created_at, s.name, h.user_question, h.ai_response
            FROM chat_history h
            JOIN subjects s ON s.id = h.subject_id
            ORDER BY h.id ASC
            """
        ):
            w.writerow(
                [r["created_at"], r["name"], r["user_question"], r["ai_response"]]
            )
    return buf.getvalue()


def export_master_json() -> str:
    with get_connection() as conn:
        data = {
            "exported_at": datetime.now().isoformat(),
            "subjects": [dict(r) for r in conn.execute("SELECT * FROM subjects")],
            "chapters": [dict(r) for r in conn.execute("SELECT * FROM chapters")],
            "materials_meta": [
                dict(r)
                for r in conn.execute(
                    "SELECT id, subject_id, file_name, material_type, upload_date FROM materials"
                )
            ],
            "chat": [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT created_at, subject_id, user_question
                    FROM chat_history ORDER BY id ASC
                    """
                )
            ],
        }
    return json.dumps(data, indent=2, ensure_ascii=False)


def export_bundle() -> dict[str, str]:
    return {
        "weak_topics_report.md": _weak_chapter_report(),
        "revision_plan_snapshot.md": _revision_plan_text(),
        "chat_history.txt": export_chat_txt(),
        "chat_history.csv": export_chat_csv(),
        "vault_export.json": export_master_json(),
    }
