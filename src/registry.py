"""Register (SQLite) som håller reda på vilka filer som hittats/processats.

Varje fil identifieras av (source_path, content_hash). Om samma fil dyker
upp igen med samma hash och redan är markerad 'done' hoppas den över,
vilket gör pipelinen säker att köra om (idempotent).
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    output_path TEXT,
    error_message TEXT,
    discovered_at TEXT NOT NULL,
    processed_at TEXT,
    UNIQUE(source_path, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
"""


def hash_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 av filinnehållet, används för att avgöra om en fil ändrats."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


class Registry:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Registry":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def already_processed(self, source_path: Path, content_hash: str) -> bool:
        cur = self._conn.execute(
            "SELECT status FROM files WHERE source_path = ? AND content_hash = ?",
            (str(source_path), content_hash),
        )
        row = cur.fetchone()
        return bool(row) and row["status"] == "done"

    def mark_pending(self, source_path: Path, content_hash: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """INSERT INTO files (source_path, content_hash, status, discovered_at)
               VALUES (?, ?, 'pending', ?)
               ON CONFLICT(source_path, content_hash)
               DO UPDATE SET status='pending'""",
            (str(source_path), content_hash, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def mark_done(self, source_path: Path, content_hash: str, output_path: Path) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """UPDATE files SET status='done', output_path=?, processed_at=?, error_message=NULL
               WHERE source_path=? AND content_hash=?""",
            (str(output_path), now, str(source_path), content_hash),
        )
        self._conn.commit()

    def mark_error(self, source_path: Path, content_hash: str, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """UPDATE files SET status='error', error_message=?, processed_at=?
               WHERE source_path=? AND content_hash=?""",
            (error, now, str(source_path), content_hash),
        )
        self._conn.commit()

    def counts(self) -> dict[str, int]:
        cur = self._conn.execute("SELECT status, COUNT(*) c FROM files GROUP BY status")
        return {row["status"]: row["c"] for row in cur.fetchall()}

    def list_by_status(self, status: str) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM files WHERE status=? ORDER BY discovered_at", (status,)
        )
        return cur.fetchall()

    def all_files(self) -> list[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM files ORDER BY discovered_at")
        return cur.fetchall()
