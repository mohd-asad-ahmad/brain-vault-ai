"""Study timeline: unified activity feed + lightweight logging (Phase 5)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from modules.database import get_connection


def log_activity(
    event_type: str,
    subject_id: int | None = None,
    message: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Append a journal row for Productivity Hub timeline."""
    meta_s = json.dumps(meta, ensure_ascii=False) if meta else None
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO activity_events (event_type, subject_id, message, meta)
            VALUES (?, ?, ?, ?)
            """,
            (event_type, subject_id, message, meta_s),
        )


def _iso_day(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        return ts[:10]
    except Exception:
        return ""


def fetch_timeline_merged(limit: int = 120) -> list[dict[str, Any]]:
    """
    Merge explicit activity_events with uploads, AI chats, and study sessions.
    Returns newest-first rows for UI cards.
    """
    rows: list[dict[str, Any]] = []

    with get_connection() as conn:
        for r in conn.execute(
            """
            SELECT id, event_type, subject_id, message, meta, created_at
            FROM activity_events
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (limit,),
        ):
            sid = r["subject_id"]
            sub = ""
            if sid:
                srow = conn.execute(
                    "SELECT name FROM subjects WHERE id = ?", (sid,)
                ).fetchone()
                sub = srow["name"] if srow else ""
            rows.append(
                {
                    "kind": "activity",
                    "ts": r["created_at"],
                    "day": _iso_day(r["created_at"]),
                    "icon": _icon_for(r["event_type"]),
                    "title": _title_for_event(r["event_type"], r["message"], sub),
                    "detail": r["message"] or "",
                    "event_type": r["event_type"],
                }
            )

        for r in conn.execute(
            """
            SELECT h.created_at, h.user_question, s.name AS subject_name
            FROM chat_history h
            JOIN subjects s ON s.id = h.subject_id
            ORDER BY datetime(h.created_at) DESC
            LIMIT ?
            """,
            (limit,),
        ):
            q = (r["user_question"] or "")[:120]
            rows.append(
                {
                    "kind": "ai",
                    "ts": r["created_at"],
                    "day": _iso_day(r["created_at"]),
                    "icon": "🧠",
                    "title": f"Asked AI · **{r['subject_name']}**",
                    "detail": q + ("…" if len(r["user_question"] or "") > 120 else ""),
                    "event_type": "ai_chat",
                }
            )

        for r in conn.execute(
            """
            SELECT ss.created_at, ss.duration_minutes, s.name AS subject_name
            FROM study_sessions ss
            LEFT JOIN subjects s ON s.id = ss.subject_id
            ORDER BY datetime(ss.created_at) DESC
            LIMIT ?
            """,
            (limit,),
        ):
            sub = r["subject_name"] or "General"
            rows.append(
                {
                    "kind": "session",
                    "ts": r["created_at"],
                    "day": _iso_day(r["created_at"]),
                    "icon": "⏱️",
                    "title": f"Study session · **{sub}** · {r['duration_minutes']} min",
                    "detail": "",
                    "event_type": "study_session",
                }
            )

    rows.sort(key=lambda x: x["ts"] or "", reverse=True)
    # De-dupe similar lines same second (upload logged + materials query)
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (row["kind"], row["ts"][:19], row["title"][:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _icon_for(event_type: str) -> str:
    return {
        "material_upload": "📄",
        "ai_question": "🧠",
        "summary": "📝",
        "exam_plan": "📋",
        "subject_open": "📂",
        "settings": "⚙️",
    }.get(event_type, "✨")


def _title_for_event(
    event_type: str, message: str | None, subject_name: str
) -> str:
    sub = f" · **{subject_name}**" if subject_name else ""
    if event_type == "ai_question":
        return f"AI question{sub}"
    if event_type == "summary":
        return f"Summary generated{sub}"
    if event_type == "exam_plan":
        return f"Exam planning{sub}"
    if event_type == "material_upload":
        return (message or "File uploaded") + sub
    return (message or event_type) + sub


def bucket_timeline_for_ui(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Split into Today / This week / Earlier."""
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    buckets = {"today": [], "week": [], "earlier": []}
    for e in events:
        dstr = e.get("day") or ""
        try:
            d = datetime.strptime(dstr, "%Y-%m-%d").date()
        except Exception:
            buckets["earlier"].append(e)
            continue
        if d == today:
            buckets["today"].append(e)
        elif d >= week_ago:
            buckets["week"].append(e)
        else:
            buckets["earlier"].append(e)
    return buckets


def search_vault(query: str, limit: int = 40) -> dict[str, list[sqlite3.Row]]:
    """Bonus: lightweight search across materials text + chat questions."""
    q = f"%{(query or '').strip()}%"
    if q == "%%":
        return {"materials": [], "chat": []}
    with get_connection() as conn:
        mats = list(
            conn.execute(
                """
                SELECT m.id, m.file_name, m.material_type, s.name AS subject_name,
                       substr(m.extracted_text, 1, 240) AS snippet
                FROM materials m
                JOIN subjects s ON s.id = m.subject_id
                WHERE m.extracted_text LIKE ?
                ORDER BY m.upload_date DESC
                LIMIT ?
                """,
                (q, limit),
            )
        )
        chats = list(
            conn.execute(
                """
                SELECT h.user_question, h.created_at, s.name AS subject_name
                FROM chat_history h
                JOIN subjects s ON s.id = h.subject_id
                WHERE h.user_question LIKE ? OR h.ai_response LIKE ?
                ORDER BY h.created_at DESC
                LIMIT ?
                """,
                (q, q, limit),
            )
        )
    return {"materials": mats, "chat": chats}
