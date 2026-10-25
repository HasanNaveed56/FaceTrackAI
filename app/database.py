"""SQLite storage: classes, students (with face embedding) and attendance."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "facetrack.db"


@contextmanager
def connection():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _backup_old_schema():
    """Older versions used email + password. If such a database exists, keep it as a backup and start fresh."""
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
    finally:
        conn.close()
    if cols and "staff_code" not in cols:
        backup = DB_PATH.with_name("facetrack.old.db")
        n = 1
        while backup.exists():
            n += 1
            backup = DB_PATH.with_name(f"facetrack.old{n}.db")
        DB_PATH.rename(backup)


def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    _backup_old_schema()
    with connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            photo TEXT NOT NULL,
            embedding BLOB NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            day TEXT NOT NULL DEFAULT (date('now','localtime')),
            marked_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            similarity REAL NOT NULL,
            UNIQUE(student_id, class_id, day)
        );
        CREATE INDEX IF NOT EXISTS idx_att_day ON attendance(day);

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL CHECK(role IN ('employee','hr','admin')),
            name TEXT NOT NULL,
            staff_code TEXT NOT NULL UNIQUE,
            department TEXT NOT NULL DEFAULT '',
            photo TEXT NOT NULL,
            embedding BLOB NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','warned','fired')),
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS work_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            day TEXT NOT NULL,
            check_in TEXT NOT NULL,
            check_out TEXT,
            similarity REAL NOT NULL,
            UNIQUE(user_id, day)
        );
        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            reason TEXT NOT NULL,
            from_day TEXT NOT NULL,
            to_day TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
            decided_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS offs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            department TEXT NOT NULL,
            title TEXT NOT NULL,
            created_by INTEGER REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        """)
