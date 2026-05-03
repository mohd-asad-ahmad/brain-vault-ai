"""
Brain Vault AI — full stack student OS (Phases 1–5).

Run: streamlit run app.py  (or: python -m streamlit run app.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Ensure project root is on path when running as `streamlit run app.py`
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modules.ai_chat import (
    ask_brain_vault_stream,
    list_chat_history,
    ollama_available,
    save_chat,
)
from modules.analytics import render_premium_analytics
from modules.database import (
    get_connection,
    get_setting,
    init_db,
    reset_all_app_data,
    set_setting,
)
from modules.productivity import (
    add_study_session,
    compute_streak_days,
    engagement_snapshot,
    export_bundle,
    get_manual_hours_today,
    sessions_this_week,
    set_manual_hours_today,
)
from modules.rag_engine import count_pending, index_all_pending, rebuild_vector_store
from modules.reminders import (
    add_reminder,
    get_exam_dates,
    list_reminders,
    set_exam_date,
    snooze_reminder,
    sync_smart_reminders,
    update_reminder_status,
)
from modules.timeline import bucket_timeline_for_ui, fetch_timeline_merged, search_vault
from modules.subjects import (
    SubjectError,
    add_chapter,
    add_subject,
    dashboard_stats,
    delete_chapter,
    delete_subject,
    list_chapters_by_subject,
    list_subjects,
)
from modules.summarizer import (
    SUMMARY_STYLE_PROMPTS,
    find_important_topics,
    generate_summary,
    weak_portion_coach,
)
from modules.uploader import (
    UploadError,
    delete_material,
    file_size_on_disk,
    get_material,
    list_chapters_for_filters,
    list_chapters_for_subject,
    list_materials,
    materials_insights,
    process_upload,
)
from modules.ui import apply_theme, daily_quote, page_header, render_sidebar
from modules.utils import (
    DIFFICULTY_LABELS,
    DIFFICULTY_VALUES,
    MATERIAL_TYPE_LABELS,
    MATERIAL_TYPES,
    OLLAMA_MODEL,
    SUGGESTED_CHAT_MODELS,
    format_bytes,
)


def _init_session_state() -> None:
    if "db_ready" not in st.session_state:
        init_db()
        st.session_state.db_ready = True
    for key in (
        "confirm_delete_subject_id",
        "confirm_delete_chapter_id",
        "confirm_delete_material_id",
        "material_detail_id",
    ):
        if key not in st.session_state:
            st.session_state[key] = None
    if "flash_message" not in st.session_state:
        st.session_state.flash_message = None
    if "ai_auto_index" not in st.session_state:
        st.session_state.ai_auto_index = False
    if "ai_last_indexed" not in st.session_state:
        st.session_state.ai_last_indexed = 0


def _show_flash() -> None:
    msg = st.session_state.pop("flash_message", None)
    if msg:
        st.success(msg)


def _flash(msg: str) -> None:
    st.session_state.flash_message = msg


def _page_dashboard() -> None:
    page_header("Dashboard", "Your at-a-glance study map", icon="🏠")
    st.caption(f"💡 _{daily_quote()}_")
    stats = dashboard_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total subjects", stats["total_subjects"])
    with c2:
        st.metric("Total chapters", stats["total_chapters"])
    with c3:
        st.metric("Weak topics", stats["weak"], help="Red difficulty")
    with c4:
        st.metric("Medium topics", stats["medium"], help="Yellow difficulty")
    with c5:
        st.metric("Strong topics", stats["strong"], help="Green difficulty")

    st.markdown("---")
    st.info(
        "Add subjects and chapters from the sidebar. Difficulty colors track "
        "where to focus revision. Upload materials under **Study Materials**."
    )


def _page_subjects() -> None:
    page_header("Manage subjects", "Create, list, and remove subjects")

    with st.container():
        st.markdown("##### Add subject")
        with st.form("add_subject_form", clear_on_submit=True):
            name = st.text_input("Subject name", placeholder="e.g. DBMS")
            submitted = st.form_submit_button("Add subject", type="primary")
            if submitted:
                try:
                    add_subject(name)
                    _flash(f"Added subject “{name.strip()}”.")
                    st.rerun()
                except SubjectError as e:
                    st.error(str(e))

    st.markdown("##### Existing subjects")
    subjects = list_subjects()
    if not subjects:
        st.warning("No subjects yet. Add one above.")
        return

    for row in subjects:
        sid = row["id"]
        cols = st.columns([4, 1])
        with cols[0]:
            st.write(f"**{row['name']}**")
        with cols[1]:
            if st.button("Delete", key=f"del_sub_{sid}", type="secondary"):
                st.session_state.confirm_delete_subject_id = sid
                st.rerun()

        if st.session_state.confirm_delete_subject_id == sid:
            st.warning(
                f"Delete subject **{row['name']}** and all its chapters? "
                "This cannot be undone."
            )
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Yes, delete", key=f"yes_sub_{sid}", type="primary"):
                    delete_subject(sid)
                    st.session_state.confirm_delete_subject_id = None
                    _flash("Subject removed.")
                    st.rerun()
            with b2:
                if st.button("Cancel", key=f"no_sub_{sid}"):
                    st.session_state.confirm_delete_subject_id = None
                    st.rerun()


def _page_chapters() -> None:
    page_header("Manage chapters", "Link chapters to subjects and set difficulty")

    subjects = list_subjects()
    if not subjects:
        st.warning("Add at least one subject first.")
        return

    subject_options = {s["name"]: s["id"] for s in subjects}

    with st.container():
        st.markdown("##### Add chapter")
        with st.form("add_chapter_form", clear_on_submit=True):
            sub_label = st.selectbox("Subject", list(subject_options.keys()))
            ch_name = st.text_input("Chapter name", placeholder="e.g. Normalization")
            diff = st.selectbox(
                "Difficulty",
                options=list(DIFFICULTY_VALUES),
                format_func=lambda x: f"{DIFFICULTY_LABELS[x]} ({x})",
            )
            submitted = st.form_submit_button("Add chapter", type="primary")
            if submitted:
                try:
                    sid = subject_options[sub_label]
                    add_chapter(sid, ch_name, diff)
                    _flash(
                        f"Added “{ch_name.strip()}” to {sub_label} "
                        f"({DIFFICULTY_LABELS[diff]})."
                    )
                    st.rerun()
                except SubjectError as e:
                    st.error(str(e))

    st.markdown("##### Chapters by subject")
    rows = list_chapters_by_subject()
    if not rows:
        st.info("No chapters yet.")
        return

    current_subject = None
    for r in rows:
        if r["subject_name"] != current_subject:
            current_subject = r["subject_name"]
            st.markdown(f"**{current_subject}**")
        label = DIFFICULTY_LABELS.get(r["difficulty_rating"], r["difficulty_rating"])
        cid = r["id"]
        cols = st.columns([4, 2, 1])
        with cols[0]:
            st.write(r["chapter_name"])
        with cols[1]:
            st.caption(f"{label} · {r['difficulty_rating']}")
        with cols[2]:
            if st.button("Delete", key=f"del_ch_{cid}", type="secondary"):
                st.session_state.confirm_delete_chapter_id = cid
                st.rerun()

        if st.session_state.confirm_delete_chapter_id == cid:
            st.warning(
                f"Delete chapter **{r['chapter_name']}** from **{r['subject_name']}**?"
            )
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Yes, delete", key=f"yes_ch_{cid}", type="primary"):
                    delete_chapter(cid)
                    st.session_state.confirm_delete_chapter_id = None
                    _flash("Chapter removed.")
                    st.rerun()
            with b2:
                if st.button("Cancel", key=f"no_ch_{cid}"):
                    st.session_state.confirm_delete_chapter_id = None
                    st.rerun()


def _page_study_materials() -> None:
    page_header(
        "Study materials",
        "Upload, organize, and filter PDF, TXT, and DOCX files by subject",
    )

    ins = materials_insights()
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total uploaded files", ins["total_files"])
    with m2:
        st.metric("Notes", ins["notes"])
    with m3:
        st.metric("PYQ", ins["pyq"])
    with m4:
        st.metric("Subjects with materials", ins["subjects_with_materials"])

    st.markdown("---")

    subjects = list_subjects()
    if not subjects:
        st.warning("Add a subject first, then upload materials.")
        return

    tab_up, tab_lib = st.tabs(["Upload material", "Material library"])

    with tab_up:
        with st.container():
            st.markdown("##### Upload material")
            with st.form("material_upload_form", clear_on_submit=True):
                sub_names = [s["name"] for s in subjects]
                pick_sub = st.selectbox("Subject *", sub_names)
                sid = next(s["id"] for s in subjects if s["name"] == pick_sub)

                ch_rows = list_chapters_for_subject(sid)
                chapter_choice = st.selectbox(
                    "Chapter (optional)",
                    options=["— No chapter —"]
                    + [c["chapter_name"] for c in ch_rows],
                )
                chapter_id = None
                if chapter_choice != "— No chapter —":
                    chapter_id = next(
                        c["id"] for c in ch_rows if c["chapter_name"] == chapter_choice
                    )

                mtype = st.selectbox(
                    "Material type",
                    options=list(MATERIAL_TYPES),
                    format_func=lambda x: MATERIAL_TYPE_LABELS[x],
                )
                uploaded = st.file_uploader(
                    "File (PDF, TXT, DOCX)",
                    type=["pdf", "txt", "docx"],
                )
                submitted = st.form_submit_button("Upload material", type="primary")

                if submitted:
                    if not uploaded:
                        st.error("Please choose a file to upload.")
                    else:
                        try:
                            data = uploaded.getvalue()
                            mid = process_upload(
                                subject_id=sid,
                                subject_name=pick_sub,
                                chapter_id=chapter_id,
                                original_filename=uploaded.name,
                                file_bytes=data,
                                material_type=mtype,
                            )
                            _flash(
                                f"Uploaded “{uploaded.name}” as "
                                f"{MATERIAL_TYPE_LABELS[mtype]} (id {mid})."
                            )
                            st.rerun()
                        except UploadError as e:
                            st.error(str(e))

    with tab_lib:
        st.markdown("##### Smart filters")
        f1, f2, f3 = st.columns(3)
        with f1:
            sub_filter = st.selectbox(
                "Subject",
                options=["All subjects"]
                + [s["name"] for s in subjects],
                key="mat_filter_sub",
            )
        sub_id_filter = None
        if sub_filter != "All subjects":
            sub_id_filter = next(s["id"] for s in subjects if s["name"] == sub_filter)

        all_ch_meta = list_chapters_for_filters()
        if sub_id_filter is not None:
            ch_options_meta = [c for c in all_ch_meta if c["subject_id"] == sub_id_filter]
        else:
            ch_options_meta = list(all_ch_meta)

        ch_labels = ["All chapters", "No chapter assigned"] + [
            f'{c["subject_name"]} — {c["chapter_name"]}' for c in ch_options_meta
        ]
        with f2:
            type_filter = st.selectbox(
                "Material type",
                options=["All types"] + list(MATERIAL_TYPES),
                format_func=lambda x: "All types"
                if x == "All types"
                else MATERIAL_TYPE_LABELS[x],
                key="mat_filter_type",
            )
        with f3:
            ch_pick = st.selectbox(
                "Chapter",
                options=ch_labels,
                key=f"mat_filter_ch_{sub_filter}",
            )

        mt = None if type_filter == "All types" else type_filter
        only_no_ch = False
        ch_id_f = None
        if ch_pick == "All chapters":
            only_no_ch = False
            ch_id_f = None
        elif ch_pick == "No chapter assigned":
            only_no_ch = True
            ch_id_f = None
        else:
            only_no_ch = False
            idx = ch_labels.index(ch_pick) - 2
            if 0 <= idx < len(ch_options_meta):
                ch_id_f = ch_options_meta[idx]["id"]

        rows = list_materials(
            subject_id=sub_id_filter,
            material_type=mt,
            chapter_id=ch_id_f,
            only_without_chapter=only_no_ch,
        )

        st.markdown("##### Material library")
        if not rows:
            st.info("No files match these filters.")
        else:
            table_rows = []
            for r in rows:
                sz = file_size_on_disk(r["file_path"])
                table_rows.append(
                    {
                        "id": r["id"],
                        "Subject": r["subject_name"],
                        "Chapter": r["chapter_name"] or "—",
                        "File": r["file_name"],
                        "Type": MATERIAL_TYPE_LABELS.get(
                            r["material_type"], r["material_type"]
                        ),
                        "Uploaded": r["upload_date"][:19]
                        if r["upload_date"]
                        else "",
                        "Size": format_bytes(sz) if sz is not None else "—",
                        "Tags": r["tags"] or "—",
                    }
                )
            df = pd.DataFrame(table_rows)
            show_df = df.drop(columns=["id"]) if "id" in df.columns else df
            st.dataframe(show_df, use_container_width=True, hide_index=True)

            st.markdown("##### Actions")
            ids = [r["id"] for r in rows]
            pick = st.selectbox(
                "Select a file",
                options=ids,
                format_func=lambda i: next(
                    (x["file_name"] for x in rows if x["id"] == i), str(i)
                ),
                key="mat_pick_action",
            )

            a1, a2, a3 = st.columns([1, 1, 2])
            with a1:
                if st.button("View details", type="secondary"):
                    st.session_state.material_detail_id = pick
                    st.rerun()
            with a2:
                if st.button("Delete", type="secondary"):
                    st.session_state.confirm_delete_material_id = pick
                    st.rerun()

            det_id = st.session_state.material_detail_id
            if det_id is not None:
                row = get_material(det_id)
                if not row:
                    st.warning("That file is no longer in the library.")
                    if st.button("Dismiss", key="dismiss_mat_gone"):
                        st.session_state.material_detail_id = None
                        st.rerun()
                else:
                    with st.expander("File details", expanded=True):
                        p = _ROOT / row["file_path"]
                        sz = file_size_on_disk(row["file_path"])
                        st.write(f"**Subject:** {row['subject_name']}")
                        st.write(
                            "**Chapter:** "
                            f"{row['chapter_name'] or '—'}"
                        )
                        tlab = MATERIAL_TYPE_LABELS.get(
                            row["material_type"], row["material_type"]
                        )
                        st.write(f"**Type:** {tlab}")
                        st.write(f"**Stored path:** `{row['file_path']}`")
                        if sz is not None:
                            st.write(f"**Size:** {format_bytes(sz)}")
                        st.write(f"**Uploaded:** {row['upload_date']}")
                        st.write(f"**Auto tags:** {row['tags'] or '—'}")
                        text = row["extracted_text"] or ""
                        preview = text[:12000]
                        st.markdown("**Extracted text (preview, RAG-ready)**")
                        st.text_area(
                            "extracted",
                            preview + ("…" if len(text) > len(preview) else ""),
                            height=220,
                            disabled=True,
                            label_visibility="collapsed",
                            key=f"ext_preview_{det_id}",
                        )
                        if p.is_file():
                            st.download_button(
                                label=f"Download {row['file_name']}",
                                data=p.read_bytes(),
                                file_name=row["file_name"],
                                mime="application/octet-stream",
                                key=f"dl_mat_{det_id}",
                            )
                    if st.button("Close details", key="close_mat_det"):
                        st.session_state.material_detail_id = None
                        st.rerun()

            cid_del = st.session_state.confirm_delete_material_id
            if cid_del is not None:
                rdel = get_material(cid_del)
                if rdel:
                    st.warning(
                        f"Delete **{rdel['file_name']}** from **{rdel['subject_name']}**? "
                        "The file will be removed from disk."
                    )
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("Yes, delete", key="yes_mat_del", type="primary"):
                            try:
                                delete_material(cid_del)
                                st.session_state.confirm_delete_material_id = None
                                st.session_state.material_detail_id = None
                                _flash("Material deleted.")
                                st.rerun()
                            except UploadError as e:
                                st.error(str(e))
                    with b2:
                        if st.button("Cancel", key="no_mat_del"):
                            st.session_state.confirm_delete_material_id = None
                            st.rerun()


def _count_text_materials() -> int:
    with get_connection() as conn:
        return int(
            conn.execute(
                """
                SELECT COUNT(*) AS c FROM materials
                WHERE extracted_text IS NOT NULL
                  AND TRIM(extracted_text) != ''
                """
            ).fetchone()["c"]
        )


def _page_ai_study() -> None:
    page_header(
        "AI Study Assistant",
        "Retrieval from your vault + local Ollama — private and exam-oriented",
    )
    st.caption(
        f"Default chat model: **{OLLAMA_MODEL}** (env `BRAIN_VAULT_OLLAMA_MODEL`). "
        f"Embeddings: pull **`nomic-embed-text`** with `ollama pull nomic-embed-text`."
    )

    if not ollama_available():
        st.error(
            "Ollama is not running. Please start Ollama locally, then refresh this page."
        )
        st.info("Install from https://ollama.com — then e.g. `ollama pull gemma:2b`")
        return

    n_text = _count_text_materials()
    if n_text == 0:
        st.warning("Upload study materials first (PDF / TXT / DOCX) with extractable text.")
        return

    pending = count_pending()
    c0, c1, c2, c3 = st.columns(4)
    with c0:
        st.metric("Materials with text", n_text)
    with c1:
        st.metric("Pending index", pending)
    with c2:
        st.metric("Last batch indexed", st.session_state.ai_last_indexed)
    with c3:
        st.session_state.ai_auto_index = st.toggle(
            "Auto-index on open",
            value=st.session_state.ai_auto_index,
            help="When on, pending uploads are embedded when you open this page.",
        )

    if st.session_state.ai_auto_index and pending > 0:
        with st.spinner("Auto-indexing pending materials…"):
            stats = index_all_pending()
            st.session_state.ai_last_indexed = int(stats.get("indexed", 0))
        st.success(
            f"Indexed **{stats['indexed']}** file(s) · {stats['seconds']}s"
        )
        st.rerun()

    with st.expander("Build Brain Vault knowledge base", expanded=(pending > 0 and not st.session_state.ai_auto_index)):
        st.markdown(
            "Chunks + vectors live in **`vector_db/`** (ChromaDB). "
            "Index after uploads so Ask / Summary use your notes."
        )
        if st.button("Index pending materials now", type="primary", key="btn_kb"):
            log = st.empty()

            def _cb(msg: str) -> None:
                log.caption(msg)

            with st.spinner("Indexing…"):
                stats = index_all_pending(progress_cb=_cb)
            st.session_state.ai_last_indexed = int(stats.get("indexed", 0))
            st.success(
                f"Indexed **{stats['indexed']}** · skipped **{stats['skipped']}** · "
                f"{stats['seconds']}s"
            )
            st.rerun()

    subjects = list_subjects()
    if not subjects:
        st.warning("Add a subject first.")
        return
    sub_map = {s["name"]: s["id"] for s in subjects}
    m_opts = list(sub_map.keys())

    st.markdown("##### Model")
    col_m1, col_m2 = st.columns(2)
    _saved = get_setting("ollama_model", OLLAMA_MODEL) or OLLAMA_MODEL
    with col_m1:
        _models = list(SUGGESTED_CHAT_MODELS)
        _idx = _models.index(_saved) if _saved in _models else 0
        pick_model = st.selectbox(
            "Chat model",
            options=_models,
            index=_idx,
            key="ai_chat_model_pick",
        )
    with col_m2:
        custom_model = st.text_input(
            "Custom Ollama model name",
            placeholder="e.g. llama3 :2b:8b-instruct-q4_K_M",
            key="ai_custom_model",
        )
    model_use = (custom_model or "").strip() or pick_model

    tab_a, tab_b, tab_c, tab_d = st.tabs(
        [
            "Ask Brain Vault",
            "Smart Summarizer",
            "Important Topics Finder",
            "Weak Portion Coach",
        ]
    )

    # --- Tab 1: RAG Q&A ---
    with tab_a:
        sname = st.selectbox("Subject", m_opts, key="ask_sub")
        sid = sub_map[sname]
        chs = list_chapters_for_subject(sid)
        ch_names = ["— None —"] + [c["chapter_name"] for c in chs]
        ch_choice = st.selectbox("Chapter (optional)", ch_names, key="ask_ch")
        cid = None
        if ch_choice != "— No filter —":
            cid = next(c["id"] for c in chs if c["chapter_name"] == ch_choice)
        q = st.text_area(
            "Your question",
            height=160,
            placeholder="Explain normalization simply · What are key topics in Unit 3? · PYQ focus areas?",
        )
        ask = st.button("Ask AI", type="primary", key="btn_ask_ai")

        if ask and (not q or not q.strip()):
            st.warning("Enter a question.")
        elif ask and q.strip():
            pieces: list[str] = []
            with st.chat_message("assistant"):
                box = st.empty()
                for chunk in ask_brain_vault_stream(
                    q.strip(), sid, cid, model=model_use
                ):
                    pieces.append(chunk)
                    box.markdown("".join(pieces))
            full_text = "".join(pieces)
            save_chat(sid, cid, q.strip(), full_text)
            b1, b2 = st.columns(2)
            with b1:
                st.download_button(
                    "Download answer (.txt)",
                    data=full_text,
                    file_name="brain_vault_answer.txt",
                    mime="text/plain",
                    key="dl_ask_txt",
                )

        with st.expander("Recent chat history (this subject)"):
            hist = list_chat_history(subject_id=sid, limit=15)
            if not hist:
                st.caption("No saved turns yet.")
            else:
                for h in hist:
                    with st.container():
                        st.markdown(f"**Q:** {h['user_question']}")
                        st.markdown(f"**A:** {h['ai_response']}")
                        st.caption(h["created_at"])
                        st.divider()

    # --- Tab 2: Summarizer ---
    with tab_b:
        sname_b = st.selectbox("Subject", m_opts, key="sum_sub")
        sid_b = sub_map[sname_b]
        chs_b = list_chapters_for_subject(sid_b)
        ch_names_b = ["— Whole subject —"] + [c["chapter_name"] for c in chs_b]
        ch_choice_b = st.selectbox("Chapter (optional)", ch_names_b, key="sum_ch")
        cid_b = None
        if ch_choice_b != "— Whole subject —":
            cid_b = next(c["id"] for c in chs_b if c["chapter_name"] == ch_choice_b)
        style_labels = {
            "short": "Short Summary",
            "exam": "Exam Revision Notes",
            "bullets": "Bullet Points",
            "easy": "Easy Language",
            "detailed": "Detailed Notes",
        }
        style_key = st.selectbox(
            "Summary style",
            options=list(SUMMARY_STYLE_PROMPTS.keys()),
            format_func=lambda k: style_labels.get(k, k),
            key="sum_style",
        )
        if st.button("Generate summary", type="primary", key="btn_sum"):
            with st.spinner("Reading your vault and summarizing…"):
                out = generate_summary(
                    sid_b, cid_b, style_key, sname_b, model=model_use
                )
            try:
                from modules.timeline import log_activity

                log_activity(
                    "summary",
                    sid_b,
                    message=f"Style: {style_key}",
                )
            except Exception:
                pass
            st.markdown(out)
            st.download_button(
                "Download summary (.md)",
                data=out,
                file_name="brain_vault_summary.md",
                mime="text/markdown",
                key="dl_sum_md",
            )

    # --- Tab 3: Important topics ---
    with tab_c:
        sname_c = st.selectbox("Subject", m_opts, key="top_sub")
        sid_c = sub_map[sname_c]
        chs_c = list_chapters_for_subject(sid_c)
        ch_names_c = ["— Whole subject —"] + [c["chapter_name"] for c in chs_c]
        ch_choice_c = st.selectbox("Chapter (optional)", ch_names_c, key="top_ch")
        cid_c = None
        if ch_choice_c != "— Whole subject —":
            cid_c = next(c["id"] for c in chs_c if c["chapter_name"] == ch_choice_c)
        if st.button("Find important topics", type="primary", key="btn_top"):
            with st.spinner("Analyzing notes & PYQs…"):
                out = find_important_topics(sid_c, cid_c, sname_c, model=model_use)
            st.markdown(out)

    # --- Tab 4: Weak coach ---
    with tab_d:
        sname_d = st.selectbox("Subject", m_opts, key="weak_sub")
        sid_d = sub_map[sname_d]
        if st.button("Coach my weak areas", type="primary", key="btn_weak"):
            with st.spinner("Building your revision plan…"):
                out = weak_portion_coach(sid_d, sname_d, model=model_use)
            st.markdown(out)


def _page_analytics() -> None:
    page_header(
        "Analytics",
        "Premium insights across difficulty, activity, materials, and readiness",
        icon="📊",
    )
    render_premium_analytics()


def _page_exam_intelligence() -> None:
    page_header(
        "Exam Intelligence",
        "PYQs, countdowns, planners, and calm-before-exam tools",
        icon="🎯",
    )
    subjects = list_subjects()
    if not subjects:
        st.warning("Add subjects under **Manage Subjects** first.")
        return
    sub_map = {s["name"]: s["id"] for s in subjects}
    t1, t2, t3, t4 = st.tabs(
        ["Exam overview", "PYQ practice", "Revision planner", "Panic mode"],
    )

    with t1:
        st.markdown("##### Exam dates")
        c1, c2 = st.columns(2)
        with c1:
            pick = st.selectbox("Subject", list(sub_map.keys()), key="exam_sub_pick")
        sid = sub_map[pick]
        with c2:
            d = st.date_input("Exam date", key="exam_date_pick")
        if st.button("Save exam date", key="save_exam_date"):
            set_exam_date(sid, d.isoformat())
            _flash(f"Saved exam date for **{pick}**.")
            st.rerun()
        st.markdown("##### Upcoming")
        rows = get_exam_dates()
        if not rows:
            st.caption("No exam dates set.")
        else:
            for r in rows:
                st.write(f"**{r['subject_name']}** · `{r['exam_date'][:10]}`")

    with t2:
        st.markdown("##### Previous-year style materials")
        mt = list_materials(material_type="pyq")
        if not mt:
            st.info("Upload files tagged **PYQ** under Study Materials.")
        else:
            for r in mt[:40]:
                st.markdown(f"- **{r['subject_name']}** · `{r['file_name']}`")

    with t3:
        st.markdown("##### 2 / 4 / 8 marker prompts (draft)")
        sub = st.selectbox("Subject context", list(sub_map.keys()), key="rev_planner_sub")
        st.markdown(
            f"- **2 markers:** List four defining traits of a core concept in **{sub}**.\n"
            f"- **4 markers:** Compare two approaches with examples from your notes.\n"
            f"- **8 markers:** Structured mini-essay with intro, two sections, conclusion."
        )
        weak = list_chapters_by_subject()
        red_list = [x for x in weak if x["subject_name"] == sub and x["difficulty_rating"] == "red"]
        if red_list:
            st.markdown("**Weak chapters to prioritize:**")
            for x in red_list:
                st.markdown(f"- {x['chapter_name']}")
        else:
            st.caption("Mark weak chapters on the Chapters page for a sharper plan.")

    with t4:
        st.markdown("##### Panic mode — steady checklist")
        st.success(
            "Breathe. Read one weak headline · skim one PYQ pattern · answer one AI question."
        )
        if st.button("I logged a micro-session", key="panic_micro"):
            add_study_session(None, 15, note="panic_mode_micro")
            _flash("Nice — 15 min logged. You've got this.")
            st.rerun()


def _page_productivity_hub() -> None:
    page_header(
        "Productivity Hub",
        "Timeline, focus, reminders, and exports",
        icon="⚡",
    )
    sync_smart_reminders()
    tab_tl, tab_ft, tab_rm, tab_ex = st.tabs(
        ["Study timeline", "Focus tracker", "Reminders", "Export center"],
    )

    with tab_tl:
        ev = fetch_timeline_merged(80)
        buckets = bucket_timeline_for_ui(ev)
        if not ev:
            st.info("Your timeline fills as you upload, ask AI, and log sessions.")
        else:

            def _card(entries: list[dict]) -> None:
                for e in entries[:25]:
                    with st.container():
                        st.markdown(f"{e['icon']} **{e['title']}**")
                        if e.get("detail"):
                            st.caption(e["detail"])
                        st.caption(e.get("ts", "")[:19])
                        st.divider()

            st.markdown("##### Today")
            _card(buckets["today"])
            st.markdown("##### This week")
            _card(buckets["week"])
            with st.expander("Earlier"):
                _card(buckets["earlier"])

    with tab_ft:
        snap = engagement_snapshot()
        st.markdown("##### Engagement snapshot")
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Sessions this week", sessions_this_week())
        with m2:
            st.metric("🔥 Streak (days)", compute_streak_days())
        with m3:
            st.metric("Manual hours today", f"{get_manual_hours_today():.1f} h")

        sc = snap.get("scores") or {}
        if sc:
            df = pd.DataFrame(
                [{"Subject": k, "Engagement": v} for k, v in sc.items()]
            )
            fig = px.bar(
                df,
                x="Subject",
                y="Engagement",
                color="Engagement",
                color_continuous_scale="Blues",
            )
            fig.update_layout(height=360, margin=dict(t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Most studied (signal)", snap.get("most") or "—")
        with c2:
            st.metric("Least touched", snap.get("least") or "—")
        st.caption(
            f"Weakest subject (by red chapters): **{snap.get('weakest_subj') or '—'}** · "
            f"Strongest (by green): **{snap.get('strongest_subj') or '—'}**"
        )
        st.markdown("##### Log focus")
        with st.form("log_session_form"):
            subs = list_subjects()
            labels = ["General"] + [s["name"] for s in subs]
            pick = st.selectbox("Subject", labels)
            sid = None
            if pick != "General":
                sid = next(s["id"] for s in subs if s["name"] == pick)
            mins = st.number_input("Minutes", min_value=5, max_value=300, value=25, step=5)
            if st.form_submit_button("Log session"):
                add_study_session(sid, int(mins))
                _flash("Session saved.")
                st.rerun()
        hrs = st.slider("Hours studied today (manual)", 0.0, 12.0, get_manual_hours_today(), 0.25)
        if st.button("Update hours today", key="btn_hours"):
            set_manual_hours_today(hrs)
            _flash("Hours updated.")
            st.rerun()
        with st.expander("Pomodoro (placeholder)"):
            st.caption("Use a 25/5 cycle: 25 min focus, 5 min break. Timer UI can plug in here.")

    with tab_rm:
        st.markdown("##### Smart reminders")
        n = sync_smart_reminders()
        if n:
            st.success(f"Generated **{n}** new nudges. Refine or dismiss below.")
        open_rem = [
            r
            for r in list_reminders()
            if r["status"] in ("active", "snoozed")
        ]
        if not open_rem:
            st.caption("No active reminders. Add your own or mark chapters weak for smart nudges.")
        for r in open_rem:
            with st.expander(f"🔔 {r['title'][:80]}"):
                st.write(r["body"] or "")
                b1, b2, b3, b4 = st.columns(4)
                with b1:
                    if st.button("Done", key=f"rd_{r['id']}_ok"):
                        update_reminder_status(int(r["id"]), "done")
                        st.rerun()
                with b2:
                    if st.button("Snooze", key=f"rd_{r['id']}_sn"):
                        snooze_reminder(int(r["id"]), 1)
                        st.rerun()
                with b3:
                    if st.button("Dismiss", key=f"rd_{r['id']}_di"):
                        update_reminder_status(int(r["id"]), "dismissed")
                        st.rerun()
        with st.form("add_rem"):
            title = st.text_input("New reminder")
            body = st.text_area("Details")
            if st.form_submit_button("Add reminder"):
                if title.strip():
                    add_reminder(title.strip(), body or None)
                    _flash("Reminder added.")
                    st.rerun()

    with tab_ex:
        st.markdown("##### Export Center")
        bundle = export_bundle()
        for i, (fname, content) in enumerate(bundle.items()):
            ext = fname.split(".")[-1]
            mime = (
                "text/plain"
                if ext == "txt"
                else "text/csv"
                if ext == "csv"
                else "application/json"
            )
            st.download_button(
                f"Download {fname}",
                data=content,
                file_name=fname,
                mime=mime,
                key=f"dl_ex_{i}_{ext}",
            )


def _page_settings() -> None:
    page_header("Settings", "Model, data hygiene, and vault-wide search", icon="⚙️")
    c1, c2 = st.columns(2)
    with c1:
        cur_m = get_setting("ollama_model", OLLAMA_MODEL) or OLLAMA_MODEL
        _sm = list(SUGGESTED_CHAT_MODELS)
        pick = st.selectbox(
            "Preferred Ollama chat model",
            _sm,
            index=_sm.index(cur_m) if cur_m in _sm else 0,
            key="settings_model",
        )
        custom = st.text_input("Custom model name (optional)", key="settings_custom_model")
        if st.button("Save model preference", key="save_model_pref"):
            set_setting("ollama_model", (custom or "").strip() or pick)
            _flash("Model preference saved.")
            st.rerun()
    with c2:
        theme = st.selectbox(
            "Theme",
            ["light", "dark"],
            index=1 if (get_setting("theme", "light") == "dark") else 0,
            key="settings_theme",
        )
        if st.button("Save theme", key="save_theme"):
            set_setting("theme", theme)
            _flash("Theme saved — refresh if styles look stale.")
            st.rerun()
        st.caption("Dark mode is a lightweight stylesheet overlay.")

    st.markdown("##### Search entire Brain Vault")
    q = st.text_input("Search materials & chat", placeholder="e.g. normalization, deadlock…")
    if q.strip():
        res = search_vault(q.strip())
        st.markdown("**Materials**")
        if not res["materials"]:
            st.caption("No material hits.")
        else:
            for r in res["materials"][:15]:
                st.markdown(f"- **{r['subject_name']}** · `{r['file_name']}` · _{r['snippet'][:120]}…_")
        st.markdown("**Chat questions**")
        if not res["chat"]:
            st.caption("No chat hits.")
        else:
            for r in res["chat"][:15]:
                st.markdown(f"- **{r['subject_name']}** · {r['user_question'][:200]}…")

    st.markdown("##### Data & maintenance")
    if st.button("Clear chat history only", key="clr_chat"):
        with get_connection() as conn:
            conn.execute("DELETE FROM chat_history")
        _flash("Chat history cleared.")
        st.rerun()
    if st.button("Rebuild vector database (Chroma)", key="rebuild_v"):
        rebuild_vector_store()
        _flash("Vector store cleared — re-index from **AI Study Assistant**.")
        st.rerun()
    st.warning(
        "Reset removes subjects, chapters, materials, sessions, reminders, and activity. "
        "Sample subjects are re-seeded."
    )
    confirm = st.text_input('Type RESET to confirm total reset', key="reset_confirm")
    if st.button("Reset ALL Brain Vault data", key="reset_all"):
        if confirm.strip().upper() == "RESET":
            reset_all_app_data()
            _flash("All data reset. Fresh sample subjects loaded.")
            st.rerun()
        else:
            st.error("Type RESET to confirm.")


def main() -> None:
    st.set_page_config(
        page_title="Brain Vault AI",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_session_state()
    apply_theme()

    page = render_sidebar()
    _show_flash()

    if page == "Dashboard":
        _page_dashboard()
    elif page == "Manage Subjects":
        _page_subjects()
    elif page == "Manage Chapters":
        _page_chapters()
    elif page == "Study Materials":
        _page_study_materials()
    elif page == "AI Study Assistant":
        _page_ai_study()
    elif page == "Exam Intelligence":
        _page_exam_intelligence()
    elif page == "Productivity Hub":
        _page_productivity_hub()
    elif page == "Analytics":
        _page_analytics()
    elif page == "Settings":
        _page_settings()


if __name__ == "__main__":
    main()
