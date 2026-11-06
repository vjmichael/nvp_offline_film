"""SCALE-02: project-scoped external source-media references.

This is a trusted native-host ingestion helper, not a model/web API.
It never copies or decodes camera originals, and does not claim that files
on external volumes are immutable. Exact bytes must be reverified before use.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from backend.nvp_studio import Studio, now
from backend.nvp_film_index import _id, _require_pid

CHUNK_BYTES = 4 * 1024 * 1024
MAX_I64 = 2**63 - 1


def _read_and_hash(path):
    """Hash in bounded memory; reject changed or symlinked source."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Source media unavailable or symlinked")
    # Never follow a symlink substituted between the path check and open.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        with os.fdopen(fd, "rb", closefd=False) as stream:
            initial = os.fstat(fd)
            if not os.path.isfile(path) or initial.st_size < 1 or initial.st_size > MAX_I64:
                raise RuntimeError("Invalid media size or unavailable source")
            digest = hashlib.sha256()
            total = 0
            while block := stream.read(CHUNK_BYTES):
                digest.update(block)
                total += len(block)
                if total > MAX_I64:
                    raise OverflowError("Source media exceeds signed 64-bit size")
            final = os.fstat(fd)
            if (total != initial.st_size or
                (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns,
                 initial.st_ctime_ns) !=
                (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns,
                 final.st_ctime_ns) or path.is_symlink()):
                raise RuntimeError("Source media changed during ingest")
            return {"sha256": digest.hexdigest(), "size_bytes": total,
                    "device": initial.st_dev, "inode": initial.st_ino,
                    "mtime_ns": initial.st_mtime_ns}
    finally:
        os.close(fd)


class ExternalMediaCatalog:
    """SQLite index of source files; source data stays in original storage.

    The native caller authenticates project membership and verifies consent to
    index this path. This class cannot grant source access or creator approval.
    """
    def __init__(self, studio: Studio):
        if not isinstance(studio, Studio):
            raise TypeError("Trusted Studio instance required")
        self.studio = studio
        with studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS scale_source_media (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                asset_id TEXT NOT NULL,
                media_path TEXT NOT NULL,
                media_type TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
                registered_at TEXT NOT NULL,
                PRIMARY KEY(project_id, asset_id))""")
            db.execute("""CREATE INDEX IF NOT EXISTS scale_source_media_lookup
                ON scale_source_media(project_id, asset_id)""")

    def register(self, project_id, asset_id, source_path, *, media_type):
        _require_pid(project_id)
        _id(asset_id, "source asset")
        if (type(media_type) is not str or
            not 1 <= len(media_type) <= 100 or
            any(ch in media_type for ch in "\r\n\x00")):
            raise ValueError("Invalid media type")
        path = Path(source_path)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("Source path must be absolute and not a symlink")
        fingerprint = _read_and_hash(path)
        with self.studio._connection() as db:
            db.execute("INSERT INTO scale_source_media VALUES (?,?,?,?,?,?,?)",
                       (project_id, asset_id, str(path), media_type,
                        fingerprint["sha256"], fingerprint["size_bytes"], now()))
        return {"asset_id": asset_id, "sha256": fingerprint["sha256"],
                "size_bytes": fingerprint["size_bytes"],
                "custody": "external_source_reference_not_copied",
                "verification": "hashed_at_registration"}

    def list_assets(self, project_id, *, after_id="", limit=100):
        _require_pid(project_id)
        if type(after_id) is not str or type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("Invalid page")
        with self.studio._connection() as db:
            if db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
                raise KeyError("Project not found")
            rows = db.execute("""SELECT asset_id,media_type,size_bytes,sha256
                FROM scale_source_media WHERE project_id=? AND asset_id>?
                ORDER BY asset_id LIMIT ?""", (project_id, after_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def probe(self, project_id, asset_id, *, verify_bytes=False):
        """Metadata probe is fast but NOT proof of current file contents."""
        _require_pid(project_id)
        _id(asset_id, "source asset")
        with self.studio._connection() as db:
            row = db.execute("""SELECT media_path,sha256,size_bytes,media_type
                FROM scale_source_media WHERE project_id=? AND asset_id=?""",
                (project_id, asset_id)).fetchone()
        if row is None:
            raise KeyError("Asset not registered in this project")
        path = Path(row["media_path"])
        if path.is_symlink() or not path.is_file():
            return {"asset_id": asset_id, "status": "OFFLINE", "verified": False}
        if path.stat().st_size != row["size_bytes"]:
            return {"asset_id": asset_id, "status": "CHANGED", "verified": False}
        if not verify_bytes:
            return {"asset_id": asset_id, "status": "PRESENT_UNVERIFIED",
                    "verified": False}
        try:
            fingerprint = _read_and_hash(path)
        except (OSError, RuntimeError):
            return {"asset_id": asset_id, "status": "UNAVAILABLE_OR_CHANGED",
                    "verified": False}
        good = (fingerprint["sha256"] == row["sha256"] and
                fingerprint["size_bytes"] == row["size_bytes"])
        return {"asset_id": asset_id, "status": "VERIFIED" if good else "CHANGED",
                "verified": good}
