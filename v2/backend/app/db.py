"""SQLite access + numbered SQL migrations (no ORM, no extra deps)."""
from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def connect(path: Path | None = None) -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            config.ensure_dirs()
            p = path or config.DB_PATH
            _conn = sqlite3.connect(str(p), check_same_thread=False, isolation_level=None)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA foreign_keys = ON")
            _conn.execute("PRAGMA journal_mode = WAL")
            _conn.execute("PRAGMA busy_timeout = 5000")
            migrate(_conn)
        return _conn


def close() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


@contextmanager
def tx():
    """Serialised write transaction."""
    conn = connect()
    with _lock:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def query(sql: str, params=()) -> list[sqlite3.Row]:
    conn = connect()
    with _lock:
        return conn.execute(sql, params).fetchall()


def one(sql: str, params=()) -> sqlite3.Row | None:
    rows = query(sql, params)
    return rows[0] if rows else None


_MIG_RE = re.compile(r"^(\d{3})_.*\.sql$")


def migrate(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> list[int]:
    """Apply every NNN_*.sql in order whose number is > current schema_version."""
    mdir = migrations_dir or config.MIGRATIONS_DIR
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    current = row["v"] if row and row["v"] is not None else 0
    applied: list[int] = []
    for f in sorted(mdir.glob("*.sql")):
        m = _MIG_RE.match(f.name)
        if not m:
            continue
        n = int(m.group(1))
        if n <= current:
            continue
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (n,))
        applied.append(n)
    return applied
