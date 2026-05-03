"""
ChromaDB + Ollama embeddings RAG layer for Brain Vault AI (Phase 3).

Stores chunk embeddings with metadata (subject, chapter, material type, file).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import chromadb

from modules.database import get_connection
from modules.utils import (
    OLLAMA_EMBED_MODEL,
    OLLAMA_HOST,
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
    RAG_TOP_K,
    vector_db_dir,
)


COLLECTION_NAME = "brain_vault_rag"


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed texts with Ollama (sequential; modest corpus sizes)."""
    import ollama

    client = ollama.Client(host=OLLAMA_HOST)
    out: list[list[float]] = []
    for t in texts:
        resp = client.embeddings(model=OLLAMA_EMBED_MODEL, prompt=t)
        out.append(resp["embedding"])
    return out


def embed_one(text: str) -> list[float]:
    return embed_batch([text])[0]


def get_collection():
    """Persistent Chroma collection (embeddings supplied explicitly)."""
    client = chromadb.PersistentClient(path=str(vector_db_dir()))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    """
    Character-based chunking with overlap; prefers paragraph boundaries.
    Token-efficient for LLMs (moderate sizes).
    """
    cs = chunk_size or RAG_CHUNK_SIZE
    ov = overlap or RAG_CHUNK_OVERLAP
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + cs, n)
        piece = text[start:end]
        if end < n:
            boundary = piece.rfind("\n\n")
            if boundary > cs // 3:
                end = start + boundary + 2
                piece = text[start:end]
        piece = piece.strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(0, end - ov)
    return chunks


def _meta_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def remove_material_from_index(material_id: int) -> None:
    """Remove all vectors for a material."""
    col = get_collection()
    try:
        col.delete(where={"material_id": _meta_str(material_id)})
    except Exception:
        pass
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE vector_status SET indexed = 0, updated_at = datetime('now')
            WHERE material_id = ?
            """,
            (material_id,),
        )


def index_material(
    material_id: int,
    progress_cb: Callable[[str], None] | None = None,
) -> bool:
    """
    Encode one material’s extracted_text into Chroma. Returns False if skipped.
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT m.id, m.subject_id, m.chapter_id, m.file_name, m.material_type,
                   m.extracted_text, s.name AS subject_name,
                   c.chapter_name AS chapter_name
            FROM materials m
            JOIN subjects s ON s.id = m.subject_id
            LEFT JOIN chapters c ON c.id = m.chapter_id
            WHERE m.id = ?
            """,
            (material_id,),
        ).fetchone()
    if not row:
        return False
    text = (row["extracted_text"] or "").strip()
    if not text:
        if progress_cb:
            progress_cb(f"Skipping material {material_id}: no extracted text.")
        with get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO vector_status (material_id, indexed, updated_at)
                VALUES (?, 0, datetime('now'))
                """,
                (material_id,),
            )
        return False

    col = get_collection()
    try:
        col.delete(where={"material_id": _meta_str(material_id)})
    except Exception:
        pass

    chunks = chunk_text(text)
    if progress_cb:
        progress_cb(f"Material {material_id}: {len(chunks)} chunk(s).")

    subject_id = int(row["subject_id"])
    ch_id = row["chapter_id"]
    chapter_key = str(ch_id) if ch_id is not None else "-1"

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str]] = []
    for i, ch in enumerate(chunks):
        cid = f"m{material_id}_c{i}"
        ids.append(cid)
        documents.append(ch)
        metadatas.append(
            {
                "material_id": _meta_str(material_id),
                "subject_id": _meta_str(subject_id),
                "chapter_id": chapter_key,
                "material_type": _meta_str(row["material_type"]),
                "file_name": _meta_str(row["file_name"]),
                "subject_name": _meta_str(row["subject_name"]),
                "chapter_name": _meta_str(row["chapter_name"] or ""),
            }
        )

    if not ids:
        return False

    embs = embed_batch(documents)

    batch = 64
    for i in range(0, len(ids), batch):
        col.add(
            ids=ids[i : i + batch],
            embeddings=embs[i : i + batch],
            documents=documents[i : i + batch],
            metadatas=metadatas[i : i + batch],
        )

    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO vector_status (material_id, indexed, updated_at)
            VALUES (?, 1, datetime('now'))
            """,
            (material_id,),
        )
    return True


def list_pending_material_ids() -> list[int]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT m.id FROM materials m
            LEFT JOIN vector_status v ON v.material_id = m.id
            WHERE (v.indexed IS NULL OR v.indexed = 0)
              AND m.extracted_text IS NOT NULL
              AND TRIM(m.extracted_text) != ''
            """
        ).fetchall()
    return [int(r["id"]) for r in rows]


def count_pending() -> int:
    return len(list_pending_material_ids())


def index_all_pending(
    progress_cb: Callable[[str], None] | None = None,
) -> dict[str, int | float]:
    """Index every material that has text but is not marked indexed."""
    mids = list_pending_material_ids()
    done = 0
    skipped = 0
    t0 = time.time()
    for mid in mids:
        ok = index_material(mid, progress_cb=progress_cb)
        if ok:
            done += 1
        else:
            skipped += 1
    return {
        "total_candidates": len(mids),
        "indexed": done,
        "skipped": skipped,
        "seconds": round(time.time() - t0, 2),
    }


def _chapter_where_clause(subject_id: int, chapter_id: int | None) -> dict[str, Any]:
    """Chroma `where` filter: subject + optional chapter (includes unassigned)."""
    if chapter_id is None:
        return {"subject_id": _meta_str(subject_id)}
    return {
        "$and": [
            {"subject_id": _meta_str(subject_id)},
            {
                "$or": [
                    {"chapter_id": _meta_str(chapter_id)},
                    {"chapter_id": "-1"},
                ]
            },
        ]
    }


def retrieve_context(
    question: str,
    subject_id: int,
    chapter_id: int | None = None,
    top_k: int | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Return concatenated context string + raw matches for UI citations.
    """
    k = top_k or RAG_TOP_K
    col = get_collection()
    where = _chapter_where_clause(subject_id, chapter_id)
    q_emb = embed_one(question)
    try:
        res = col.query(
            query_embeddings=[q_emb],
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return "", []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    parts: list[str] = []
    raw: list[dict[str, Any]] = []
    for i, doc in enumerate(docs or []):
        meta = metas[i] if i < len(metas) else {}
        d = dists[i] if i < len(dists) else None
        fname = (meta or {}).get("file_name", "?")
        parts.append(f"[Source: {fname}]\n{doc}")
        raw.append({"file_name": fname, "distance": d, "snippet": (doc or "")[:400]})
    ctx = "\n\n---\n\n".join(parts) if parts else ""
    return ctx, raw


def load_subject_material_blob(
    subject_id: int,
    chapter_id: int | None = None,
    max_chars: int = 90000,
) -> str:
    """
    Pull concatenated extracted_text from SQLite for summarization / topic mining.
    When chapter_id is set, include that chapter plus unassigned materials.
    """
    if chapter_id is None:
        where_sql = "m.subject_id = ? AND m.extracted_text IS NOT NULL"
        params: list[Any] = [subject_id]
    else:
        where_sql = """
            m.subject_id = ?
            AND m.extracted_text IS NOT NULL
            AND (m.chapter_id = ? OR m.chapter_id IS NULL)
        """
        params = [subject_id, chapter_id]

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT m.file_name, m.material_type, m.extracted_text
            FROM materials m
            WHERE {where_sql}
            ORDER BY m.material_type, m.file_name
            """,
            tuple(params),
        ).fetchall()

    buf: list[str] = []
    used = 0
    for r in rows:
        block = (
            f"\n\n### File: {r['file_name']} ({r['material_type']})\n"
            f"{r['extracted_text'] or ''}"
        )
        if used + len(block) > max_chars:
            remain = max_chars - used
            if remain > 0:
                buf.append(block[:remain])
            break
        buf.append(block)
        used += len(block)
    return "".join(buf).strip()


def rebuild_vector_store() -> None:
    """Delete Chroma collection and mark all materials as not indexed (re-run indexing after)."""
    client = chromadb.PersistentClient(path=str(vector_db_dir()))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    with get_connection() as conn:
        conn.execute(
            "UPDATE vector_status SET indexed = 0, updated_at = datetime('now')"
        )
