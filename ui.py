"""Reusable Streamlit UI: navigation, headers, theme (Phase 5 polish)."""

from __future__ import annotations

import streamlit as st

from modules.database import get_setting
from modules.utils import ACADEMIC_QUOTES


NAV_PAGES = (
    "Dashboard",
    "Manage Subjects",
    "Manage Chapters",
    "Study Materials",
    "AI Study Assistant",
    "Exam Intelligence",
    "Productivity Hub",
    "Analytics",
    "Settings",
)


def apply_theme() -> None:
    """Apply dark preference from app_settings (placeholder-quality CSS)."""
    theme = get_setting("theme", "light") or "light"
    if theme == "dark":
        st.markdown(
            """
<style>
    .stApp { background-color: #0e1117; color: #e6edf3; }
    .stMarkdown, .stCaption, label { color: #e6edf3 !important; }
    div[data-testid="stMetric"] { background-color: #161b22; padding: 12px; border-radius: 8px; }
    section[data-testid="stSidebar"] { background-color: #161b22; }
</style>
            """,
            unsafe_allow_html=True,
        )


def daily_quote() -> str:
    """Deterministic-ish quote per day (session-stable)."""
    from datetime import datetime

    i = int(datetime.now().strftime("%j")) % len(ACADEMIC_QUOTES)
    return ACADEMIC_QUOTES[i]


def render_sidebar() -> str:
    """Draw app branding and return selected page name."""
    st.sidebar.markdown("## 🧠 Brain Vault AI")
    st.sidebar.caption("Your local study operating system")
    st.sidebar.divider()
    page = st.sidebar.radio(
        "Navigation",
        NAV_PAGES,
        label_visibility="collapsed",
    )
    st.sidebar.divider()
    st.sidebar.markdown(
        "<small>SQLite · Chroma · Ollama — runs offline</small>",
        unsafe_allow_html=True,
    )
    return page


def page_header(
    title: str,
    subtitle: str | None = None,
    icon: str | None = "📚",
) -> None:
    prefix = f"{icon} " if icon else ""
    st.markdown(f"### {prefix}{title}")
    if subtitle:
        st.caption(subtitle)
    st.divider()


def empty_state(title: str, hint: str) -> None:
    st.info(f"**{title}** — {hint}")
