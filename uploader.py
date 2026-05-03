"""Study material uploads: filesystem layout, text extraction, SQLite records."""

from __future__ import annotations

import sqlite3
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

from modules.database import get_connection
from modules.utils import (
    MATERIAL_TYPES,
    project_root,
    sanitize_path_segment,
    tags_from_filename,
    uploads_dir,
)


class UploadError(Exception):
    """User-facing upload / validation errors."""


def _ensure_extension(name: str) -> str:
    suf = Path(name).suffix.lower()
    if suf not in (".pdf", ".txt", ".docx"):
        raise UploadError("Only PDF, TXT, and DOCX files are supported.")
    return suf


def subject_upload_folder(subject_name: str) -> Path:
    """uploads/<subject_name>/ with sanitized segment."""
    seg = sanitize_path_segment(subject_name)
    folder = uploads_dir() / seg
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def unique_target_path(folder: Path, base_name: str) -> Path:
    """Avoid overwriting: file.pdf, file_1.pdf, ..."""
    path = folder / base_name
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    n = 1
    while True:
        candidate = folder / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def extract_text_from_file(file_path: Path, extension: str) -> str:
    """Extract plain text for RAG / preview (Phase 3)."""
    ext = extension.lower()
    if ext == ".txt":
        data = file_path.read_bytes()
        for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise UploadError("PDF support requires pypdf.") from e
        reader = PdfReader(str(file_path))
        parts: list[str] = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n\n".join(parts).strip()

    if ext == ".docx":
        try:
            from docx import Document
        except ImportError as e:
            raise UploadError("DOCX support requires python-docx.") from e
        document = Document(str(file_path))
        return "\n".join(p.text for p in document.paragraphs if p.text).strip()

    raise UploadError(f"Unsupported extension: {ext}")


def material_exists(subject_id: int, stored_file_name: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM materials
            WHERE subject_id = ? AND file_name = ?
            LIMIT 1
            """,
            (subject_id, stored_file_name),
        ).fetchone()
        return row is not None


def list_chapters_for_subject(subject_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return list(
            conn.execute(
                """
                SELECT id, chapter_name FROM chapters
                WHERE subject_id = ?
                ORDER BY chapter_name COLLATE NOCASE
                """,
                (subject_id,),
            )
        )


def list_chapters_for_filters() -> list[sqlite3.Row]:
    """All chapters with subject labels for filter dropdowns."""
    with get_connection() as conn:
        return list(
            conn.execute(
                """
                SELECT c.id, c.subject_id, c.chapter_name, s.name AS subject_name
                FROM chapters c
                JOIN subjects s ON s.id = c.subject_id
                ORDER BY s.name COLLATE NOCASE, c.chapter_name COLLATE NOCASE
                """
            )
        )


def insert_material(
    subject_id: int,
    chapter_id: int | None,
    stored_file_name: str,
    relative_file_path: str,
    material_type: str,
    extracted_text: str | None,
    tags: str | None,
) -> int:
    if material_type not in MATERIAL_TYPES:
        raise UploadError("Invalid material type.")
    try:
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO materials (
                    subject_id, chapter_id, file_name, file_path,
                    material_type, extracted_text, tags
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    subject_id,
                    chapter_id,
                    stored_file_name,
                    relative_file_path,
                    material_type,
                    extracted_text,
                    tags,
                ),
            )
            mid = int(cur.lastrowid)
            conn.execute(
                """
                INSERT OR REPLACE INTO vector_status (material_id, indexed, updated_at)
                VALUES (?, 0, datetime('now'))
                """,
                (mid,),
            )
            return mid
    except sqlite3.IntegrityError as e:
        raise UploadError(
            "A file with this name already exists for this subject."
        ) from e


def list_materials(
    subject_id: int | None = None,
    material_type: str | None = None,
    chapter_id: int | None = None,
    only_without_chapter: bool = False,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if subject_id is not None:
        clauses.append("m.subject_id = ?")
        params.append(subject_id)
    if material_type:
        clauses.append("m.material_type = ?")
        params.append(material_type)
    if only_without_chapter:
        clauses.append("m.chapter_id IS NULL")
    elif chapter_id is not None:
        clauses.append("m.chapter_id = ?")
        params.append(chapter_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT m.id, m.subject_id, m.chapter_id, m.file_name, m.file_path,
               m.material_type, m.upload_date, m.extracted_text, m.tags,
               s.name AS subject_name,
               c.chapter_name AS chapter_name
        FROM materials m
        JOIN subjects s ON s.id = m.subject_id
        LEFT JOIN chapters c ON c.id = m.chapter_id
        {where}
        ORDER BY m.upload_date DESC, m.file_name COLLATE NOCASE
    """
    with get_connection() as conn:
        return list(conn.execute(sql, params))


def get_material(material_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT m.id, m.subject_id, m.chapter_id, m.file_name, m.file_path,
                   m.material_type, m.upload_date, m.extracted_text, m.tags,
                   s.name AS subject_name,
                   c.chapter_name AS chapter_name
            FROM materials m
            JOIN subjects s ON s.id = m.subject_id
            LEFT JOIN chapters c ON c.id = m.chapter_id
            WHERE m.id = ?
            """,
            (material_id,),
        ).fetchone()


def delete_material(material_id: int) -> None:
    row = get_material(material_id)
    if not row:
        raise UploadError("Material not found.")
    try:
        from modules.rag_engine import remove_material_from_index

        remove_material_from_index(material_id)
    except Exception:
        pass
    abs_path = (project_root() / row["file_path"]).resolve()
    with get_connection() as conn:
        conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    try:
        if abs_path.is_file():
            abs_path.unlink()
    except OSError:
        # File missing — DB row still removed
        pass


def materials_insights() -> dict[str, Any]:
    with get_connection() as conn:
        total_files = conn.execute(
            "SELECT COUNT(*) AS c FROM materials"
        ).fetchone()["c"]
        notes = conn.execute(
            "SELECT COUNT(*) AS c FROM materials WHERE material_type = 'notes'"
        ).fetchone()["c"]
        pyq = conn.execute(
            "SELECT COUNT(*) AS c FROM materials WHERE material_type = 'pyq'"
        ).fetchone()["c"]
        subjects_with_mats = conn.execute(
            """
            SELECT COUNT(DISTINCT subject_id) AS c FROM materials
            """
        ).fetchone()["c"]
    return {
        "total_files": total_files,
        "notes": notes,
        "pyq": pyq,
        "subjects_with_materials": subjects_with_mats,
    }


def save_stream_to_subject_folder(
    subject_name: str,
    original_filename: str,
    stream: BinaryIO,
) -> tuple[str, Path, int]:
    """
    Write bytes under uploads/<subject>/ with a safe filename.
    Returns (stored_file_name, absolute_path, size_bytes).
    """
    ext = _ensure_extension(original_filename)
    base = Path(original_filename).name
    stem = sanitize_path_segment(Path(base).stem, fallback="file")
    safe_name = f"{stem}{ext}"
    folder = subject_upload_folder(subject_name)
    dest = unique_target_path(folder, safe_name)
    data = stream.read()
    size = len(data)
    dest.write_bytes(data)
    return dest.name, dest.resolve(), size


def process_upload(
    subject_id: int,
    subject_name: str,
    chapter_id: int | None,
    original_filename: str,
    file_bytes: bytes,
    material_type: str,
) -> int:
    """Full pipeline: save file, extract text, insert DB."""
    ext = _ensure_extension(original_filename)
    stem = sanitize_path_segment(Path(original_filename).stem, fallback="file")
    candidate_name = f"{stem}{ext}"
    if material_exists(subject_id, candidate_name):
        raise UploadError(
            "Duplicate: a file with this name already exists for this subject "
            "(rename the file or delete the existing record)."
        )

    stream = BytesIO(file_bytes)
    stored_name, abs_path, _size = save_stream_to_subject_folder(
        subject_name, original_filename, stream
    )
    root = project_root()
    try:
        relative = abs_path.relative_to(root).as_posix()
    except ValueError:
        relative = str(abs_path)

    ext = Path(stored_name).suffix.lower()
    try:
        extracted = extract_text_from_file(abs_path, ext) or None
    except Exception as e:
        try:
            abs_path.unlink()
        except OSError:
            pass
        if isinstance(e, UploadError):
            raise
        raise UploadError(f"Could not read file content: {e}") from e

    tag_str = tags_from_filename(stored_name)
    mid = insert_material(
        subject_id=subject_id,
        chapter_id=chapter_id,
        stored_file_name=stored_name,
        relative_file_path=relative,
        material_type=material_type,
        extracted_text=extracted,
        tags=tag_str,
    )
    try:
        from modules.timeline import log_activity

        log_activity(
            "material_upload",
            subject_id,
            message=f"{stored_name} ({material_type})",
        )
    except Exception:
        pass
    return mid


def file_size_on_disk(relative_path: str) -> int | None:
    p = (project_root() / relative_path).resolve()
    if p.is_file():
        return p.stat().st_size
    return None
