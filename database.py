"""SQLite connection, schema, and first-run initialization."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from modules.utils import data_dir

DEFAULT_DB_NAME = "second_brain.db"


def db_path() -> Path:
    return data_dir() / DEFAULT_DB_NAME


@contextmanager
def get_connection():
    path = db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if missing; seed sample subjects when DB is new."""
    with get_connection() as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                chapter_name TEXT NOT NULL,
                difficulty_rating TEXT NOT NULL CHECK (
                    difficulty_rating IN ('red', 'yellow', 'green')
                ),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chapters_subject
                ON chapters(subject_id);

            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                chapter_id INTEGER,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                material_type TEXT NOT NULL CHECK (
                    material_type IN ('notes', 'pyq', 'assignment', 'reference')
                ),
                upload_date TEXT NOT NULL DEFAULT (datetime('now')),
                extracted_text TEXT,
                tags TEXT,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE SET NULL,
                UNIQUE (subject_id, file_name)
            );

            CREATE INDEX IF NOT EXISTS idx_materials_subject
                ON materials(subject_id);
            CREATE INDEX IF NOT EXISTS idx_materials_type
                ON materials(material_type);
            CREATE INDEX IF NOT EXISTS idx_materials_chapter
                ON materials(chapter_id);

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                chapter_id INTEGER,
                user_question TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chat_subject
                ON chat_history(subject_id);

            CREATE TABLE IF NOT EXISTS vector_status (
                material_id INTEGER PRIMARY KEY,
                indexed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_vector_indexed
                ON vector_status(indexed);

            CREATE TABLE IF NOT EXISTS study_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER,
                duration_minutes INTEGER NOT NULL CHECK (duration_minutes >= 0),
                note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_created
                ON study_sessions(created_at);

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','done','snoozed','dismissed')),
                due_date TEXT,
                snooze_until TEXT,
                subject_id INTEGER,
                source TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_reminders_status
                ON reminders(status);

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                subject_id INTEGER,
                message TEXT,
                meta TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_activity_created
                ON activity_events(created_at);

            CREATE TABLE IF NOT EXISTS exam_dates (
                subject_id INTEGER PRIMARY KEY,
                exam_date TEXT NOT NULL,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS manual_focus_hours (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                hours REAL NOT NULL CHECK (hours >= 0 AND hours <= 24),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (day)
            );
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO vector_status (material_id, indexed)
            SELECT m.id, 0 FROM materials m
            WHERE NOT EXISTS (
                SELECT 1 FROM vector_status v WHERE v.material_id = m.id
            )
            """
        )
        cur = conn.execute("SELECT COUNT(*) AS c FROM subjects")
        if cur.fetchone()["c"] == 0:
            _seed_default_subjects(conn)


def _seed_default_subjects(conn: sqlite3.Connection) -> None:
    samples = ("DBMS", "OS", "Python", "AI")
    conn.executemany(
        "INSERT INTO subjects (name) VALUES (?)",
        [(n,) for n in samples],
    )


def get_setting(key: str, default: str | None = None) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return row["value"]
    return default


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def reset_all_app_data() -> None:
    """Destructive: clears user-generated data and re-seeds sample subjects."""
    with get_connection() as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = OFF;
            DELETE FROM chat_history;
            DELETE FROM activity_events;
            DELETE FROM vector_status;
            DELETE FROM materials;
            DELETE FROM reminders;
            DELETE FROM study_sessions;
            DELETE FROM manual_focus_hours;
            DELETE FROM exam_dates;
            DELETE FROM chapters;
            DELETE FROM subjects;
            DELETE FROM app_settings;
            PRAGMA foreign_keys = ON;
            """
        )
        cur = conn.execute("SELECT COUNT(*) AS c FROM subjects")
        if cur.fetchone()["c"] == 0:
            _seed_default_subjects(conn)


if __name__ == "__main__":
    init_db()
    print(f"Database ready at: {db_path()}")
