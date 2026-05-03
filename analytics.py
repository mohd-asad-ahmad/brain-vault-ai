"""Premium analytics dashboard: readiness, heatmaps, distributions (Phase 5)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from modules.database import get_connection
from modules.subjects import chapters_per_subject, difficulty_distribution
from modules.utils import DIFFICULTY_LABELS, DIFFICULTY_VALUES, MATERIAL_TYPE_LABELS


def compute_readiness_score() -> tuple[int, dict[str, Any]]:
    """
    Heuristic 0–100 score from coverage, difficulty balance, materials, recent activity.
    """
    with get_connection() as conn:
        n_ch = conn.execute("SELECT COUNT(*) AS c FROM chapters").fetchone()["c"]
        n_red = conn.execute(
            "SELECT COUNT(*) AS c FROM chapters WHERE difficulty_rating = 'red'"
        ).fetchone()["c"]
        n_green = conn.execute(
            "SELECT COUNT(*) AS c FROM chapters WHERE difficulty_rating = 'green'"
        ).fetchone()["c"]
        n_yellow = conn.execute(
            "SELECT COUNT(*) AS c FROM chapters WHERE difficulty_rating = 'yellow'"
        ).fetchone()["c"]
        n_mat = conn.execute("SELECT COUNT(*) AS c FROM materials").fetchone()["c"]
        since = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        n_chat = conn.execute(
            "SELECT COUNT(*) AS c FROM chat_history WHERE datetime(created_at) >= datetime(?)",
            (since,),
        ).fetchone()["c"]
        n_up = conn.execute(
            "SELECT COUNT(*) AS c FROM materials WHERE datetime(upload_date) >= datetime(?)",
            (since,),
        ).fetchone()["c"]
        n_sess = conn.execute(
            "SELECT COUNT(*) AS c FROM study_sessions WHERE datetime(created_at) >= datetime(?)",
            (since,),
        ).fetchone()["c"]

    base = 38
    balance = 0
    if n_ch:
        balance += min(22, int(22 * (n_green / max(n_ch, 1))))
        balance -= min(18, int(n_red * 2.2))
        balance += min(8, int(8 * (n_yellow / max(n_ch, 1))))
    mats = min(18, n_mat * 1.8)
    pulse = min(22, (n_chat + n_up) * 2 + n_sess * 3)

    score = int(base + balance + mats + pulse)
    score = max(0, min(100, score))
    detail = {
        "chapters": n_ch,
        "green": n_green,
        "red": n_red,
        "yellow": n_yellow,
        "materials": n_mat,
        "recent_ai_chats": n_chat,
        "recent_uploads": n_up,
        "recent_sessions": n_sess,
    }
    return score, detail


def subject_performance_rows() -> list[dict[str, Any]]:
    """Per-subject 0–100 style score for bar chart."""
    with get_connection() as conn:
        subs = conn.execute("SELECT id, name FROM subjects").fetchall()
        rows = []
        for s in subs:
            sid = int(s["id"])
            ch = conn.execute(
                "SELECT COUNT(*) AS c FROM chapters WHERE subject_id = ?",
                (sid,),
            ).fetchone()["c"]
            if ch == 0:
                score = 40
            else:
                g = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM chapters
                    WHERE subject_id = ? AND difficulty_rating = 'green'
                    """,
                    (sid,),
                ).fetchone()["c"]
                r = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM chapters
                    WHERE subject_id = ? AND difficulty_rating = 'red'
                    """,
                    (sid,),
                ).fetchone()["c"]
                m = conn.execute(
                    "SELECT COUNT(*) AS c FROM materials WHERE subject_id = ?",
                    (sid,),
                ).fetchone()["c"]
                score = 48 + min(30, int(30 * (g / ch))) - min(20, r * 4) + min(12, m * 2)
                score = max(0, min(100, score))
            rows.append({"Subject": s["name"], "Score": score})
    rows.sort(key=lambda x: x["Score"], reverse=True)
    return rows


def activity_last_days(days: int = 42) -> pd.DataFrame:
    """Daily activity counts for heatmap / bar."""
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    frames: list[pd.DataFrame] = []
    with get_connection() as conn:
        for label, sql in (
            (
                "chat",
                "SELECT date(created_at) AS d, COUNT(*) AS n FROM chat_history GROUP BY d",
            ),
            (
                "upload",
                "SELECT date(upload_date) AS d, COUNT(*) AS n FROM materials GROUP BY d",
            ),
            (
                "session",
                "SELECT date(created_at) AS d, COUNT(*) AS n FROM study_sessions GROUP BY d",
            ),
            (
                "feed",
                "SELECT date(created_at) AS d, COUNT(*) AS n FROM activity_events GROUP BY d",
            ),
        ):
            df = pd.read_sql_query(sql, conn)
            if not df.empty:
                df["layer"] = label
                frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["date", "count"])
    all_days = pd.concat(frames, ignore_index=True)
    all_days = all_days[all_days["d"] >= start]
    agg = all_days.groupby("d", as_index=False)["n"].sum()
    agg.rename(columns={"d": "date", "n": "count"}, inplace=True)
    return agg


def top_topics_from_chat(top_n: int = 12) -> list[tuple[str, int]]:
    stop = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "what",
        "how",
        "why",
        "in",
        "and",
        "or",
        "to",
        "of",
        "for",
        "with",
        "my",
        "me",
        "we",
        "i",
        "you",
        "it",
        "this",
        "that",
        "from",
        "on",
        "be",
        "as",
        "can",
        "do",
        "does",
        "explain",
        "about",
    }
    words: list[str] = []
    with get_connection() as conn:
        for r in conn.execute("SELECT user_question FROM chat_history"):
            q = (r["user_question"] or "").lower()
            for w in re.findall(r"[a-zA-Z]{4,}", q):
                if w not in stop:
                    words.append(w)
    cnt = Counter(words)
    return cnt.most_common(top_n)


def material_type_breakdown() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT material_type, COUNT(*) AS c
            FROM materials
            GROUP BY material_type
            """
        ).fetchall()
    return [
        {"type": MATERIAL_TYPE_LABELS.get(r["material_type"], r["material_type"]), "count": r["c"]}
        for r in rows
    ]


def render_premium_analytics() -> None:
    """Streamlit premium analytics page body."""
    st.caption("Signals from chapters, materials, AI usage, and sessions — private to your machine.")

    score, detail = compute_readiness_score()
    c0, c1, c2 = st.columns([1, 1, 2])
    with c0:
        st.metric("Predicted readiness", f"{score}/100")
    with c1:
        st.metric("Materials in vault", detail["materials"])
    with c2:
        fig_g = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=score,
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": "Readiness"},
                gauge={
                    "axis": {"range": [None, 100]},
                    "bar": {"color": "#5b8cff"},
                    "steps": [
                        {"range": [0, 40], "color": "#ffcccc"},
                        {"range": [40, 70], "color": "#fff4cc"},
                        {"range": [70, 100], "color": "#ccffdd"},
                    ],
                },
            )
        )
        fig_g.update_layout(height=240, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_g, use_container_width=True)

    with st.expander("How readiness is estimated"):
        st.write(
            "Based on green vs red chapters, material count, and activity in the last **14 days** "
            "(AI questions, uploads, study sessions). Tune by marking chapter difficulty and staying active."
        )

    st.markdown("---")
    st.markdown("##### Subject performance score")
    perf = subject_performance_rows()
    if not perf:
        st.info("Add subjects and chapters to see performance scores.")
    else:
        fig_b = px.bar(perf, x="Subject", y="Score", color="Score", color_continuous_scale="Teal")
        fig_b.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_b, use_container_width=True)

    st.markdown("##### Weak / medium / strong distribution")
    dist = difficulty_distribution()
    label_map = {k: DIFFICULTY_LABELS[k] for k in DIFFICULTY_VALUES}
    counts = {k: 0 for k in DIFFICULTY_VALUES}
    for r in dist:
        counts[r["difficulty_rating"]] = r["cnt"]
    pie_rows = [{"Difficulty": label_map[k], "Count": counts[k]} for k in DIFFICULTY_VALUES]
    if sum(counts.values()) == 0:
        st.caption("No chapters yet.")
    else:
        fig_p = px.pie(
            pie_rows,
            names="Difficulty",
            values="Count",
            hole=0.5,
            color="Difficulty",
            color_discrete_map={
                "Weak": "#e74c3c",
                "Average": "#f1c40f",
                "Easy / Strong": "#2ecc71",
            },
        )
        fig_p.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_p, use_container_width=True)

    st.markdown("##### Activity by day (last 42 days)")
    df = activity_last_days(42)
    if df.empty:
        st.caption("No activity timestamps yet — chat, upload, or log a session.")
    else:
        fig_h = px.bar(
            df,
            x="date",
            y="count",
            color="count",
            color_continuous_scale="Blues",
        )
        fig_h.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_h, use_container_width=True)

    st.markdown("##### Most searched topics (from AI questions)")
    top = top_topics_from_chat(14)
    if not top:
        st.caption("Ask the AI a few questions to populate this chart.")
    else:
        tdf = pd.DataFrame(top, columns=["topic", "count"])
        fig_t = px.bar(tdf, x="topic", y="count", color="count", color_continuous_scale="Purples")
        fig_t.update_layout(height=340, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_t, use_container_width=True)

    st.markdown("##### Material type distribution")
    mt = material_type_breakdown()
    if not mt:
        st.caption("Upload materials to see distribution.")
    else:
        fig_m = px.pie(
            mt,
            names="type",
            values="count",
            hole=0.45,
        )
        fig_m.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_m, use_container_width=True)

    st.markdown("##### Chapters per subject (coverage)")
    per_subj = chapters_per_subject()
    if not per_subj:
        st.caption("No chapters recorded.")
    else:
        df_c = pd.DataFrame(
            [{"Subject": r["subject_name"], "Chapters": r["chapter_count"]} for r in per_subj]
        )
        fig_c = px.bar(
            df_c,
            x="Subject",
            y="Chapters",
            color="Chapters",
            color_continuous_scale="Viridis",
        )
        fig_c.update_layout(height=340, showlegend=False, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_c, use_container_width=True)
