"""JSON-baserat importregister med atomiska skrivningar och engångsmigrering."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def hash_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()

class Registry:
    def __init__(self, db_path):
        original = Path(db_path)
        self.db_path = original.with_suffix(".json")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._locked():
            if not self.db_path.exists():
                legacy = original.with_suffix(".db")
                rows = []
                if legacy.exists():
                    import sqlite3
                    conn = sqlite3.connect(legacy.resolve().as_uri() + "?mode=ro", uri=True)
                    try:
                        conn.row_factory = sqlite3.Row
                        rows = [dict(row) for row in conn.execute("SELECT * FROM files ORDER BY id")]
                    finally:
                        conn.close()
                atomic_json(self.db_path, {"version": 1, "files": rows})
                if legacy.exists() and not legacy.with_suffix(".db.bak").exists():
                    legacy.rename(legacy.with_suffix(".db.bak"))

    @contextmanager
    def _locked(self):
        with open(self.db_path.with_suffix(".lock"), "a+b") as lock:
            lock.seek(0, 2)
            if not lock.tell():
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def all_files(self):
        return json.loads(self.db_path.read_text(encoding="utf-8"))["files"]

    def already_processed(self, source_path, content_hash):
        return any(r["source_path"] == str(source_path) and r["content_hash"] == content_hash
                   and r["status"] == "done" for r in self.all_files())

    def _update(self, source_path, content_hash, **values):
        with self._locked():
            rows = self.all_files()
            row = next((r for r in rows if r["source_path"] == str(source_path)
                        and r["content_hash"] == content_hash), None)
            if row is None:
                row = dict(id=max((r["id"] for r in rows), default=0) + 1,
                           source_path=str(source_path), content_hash=content_hash,
                           discovered_at=datetime.now(timezone.utc).isoformat(),
                           output_path=None, error_message=None, processed_at=None)
                rows.append(row)
            row.update(values)
            atomic_json(self.db_path, {"version": 1, "files": rows})
            return row["id"]

    def mark_pending(self, source_path, content_hash):
        return self._update(source_path, content_hash, status="pending")

    def mark_done(self, source_path, content_hash, output_path):
        self._update(source_path, content_hash, status="done", output_path=str(output_path),
                     error_message=None, processed_at=datetime.now(timezone.utc).isoformat())

    def mark_error(self, source_path, content_hash, error):
        self._update(source_path, content_hash, status="error", error_message=error,
                     processed_at=datetime.now(timezone.utc).isoformat())

    def counts(self):
        from collections import Counter
        return dict(Counter(r["status"] for r in self.all_files()))

    def list_by_status(self, status):
        return sorted((r for r in self.all_files() if r["status"] == status),
                      key=lambda r: r["discovered_at"])
