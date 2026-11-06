"""SCALE-03C.1 — user-facing FFMS2 index upgrade readiness contract.

An .ffindex is disposable; incompatible versions require REINDEXING, not
recovery of project data. This module never reads camera originals and never
deletes previous index files. A GUI may query inspect() without invoking any
source decoder or hashing a multi-terabyte original.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from backend.nvp_film_index import _id, _require_pid, _sha

FORMAT = "nvp.ffms2.cache_compat.v1"
MAX_MARKER_BYTES = 4096

NOTICE = {
    "code": "VIDEO_INDEX_VERSION_CHANGED",
    "title": "Media indexes need updating",
    "message": (
        "NVP's video indexing engine changed. Some saved indexes must be rebuilt "
        "before frame-accurate previews are available. Your original footage, "
        "edits, and film projects are safe."
    ),
    "action": "Rebuild indexes",
    "requires_permission_for_new_read": True,
    "does_not_change_originals": True,
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


class FFMS2IndexMaintenance:
    """Tiny version pointer per immutable source ID, outside removable media."""

    def __init__(self, cache_root, *, engine_version, library_sha256):
        root = Path(cache_root)
        if not root.is_absolute() or root.is_symlink():
            raise ValueError("Trusted absolute NVP index-cache directory required")
        if (type(engine_version) is not int or not 0 <= engine_version <= 2**32 - 1):
            raise ValueError("Invalid FFMS2 engine version")
        _sha(library_sha256)
        self.root = root
        self.version = engine_version
        self.lib_sha = library_sha256

    def _marker(self, project_id, asset_id, source_sha256):
        _require_pid(project_id)
        _id(asset_id, "source ID")
        _sha(source_sha256)
        identity = {
            "project_id": project_id, "asset_id": asset_id,
            "source_sha256": source_sha256,
        }
        key = hashlib.sha256(_canonical(identity)).hexdigest()
        parent = self.root / project_id / "compat"
        return parent / (key + ".json")

    def inspect(self, project_id, asset_id, source_sha256):
        """Return a truthful display state without examining source media."""
        marker = self._marker(project_id, asset_id, source_sha256)
        if marker.is_symlink():
            return {"status": "INDEX_METADATA_UNSAFE", "ready": False}
        if not marker.is_file():
            return {"status": "NOT_INDEXED_OR_LEGACY_CACHE", "ready": False,
                    "notice": None}
        if marker.stat().st_size > MAX_MARKER_BYTES:
            return {"status": "INDEX_METADATA_INVALID", "ready": False}
        try:
            data = json.loads(marker.read_bytes())
        except (OSError, ValueError, UnicodeError):
            return {"status": "INDEX_METADATA_INVALID", "ready": False}
        if (type(data) is not dict or data.get("format") != FORMAT or
            data.get("project_id") != project_id or
            data.get("asset_id") != asset_id or
            data.get("source_sha256") != source_sha256 or
            type(data.get("ffms2_version")) is not int or
            type(data.get("ffms2_library_sha256")) is not str or
            len(data["ffms2_library_sha256"]) != 64):
            return {"status": "INDEX_METADATA_INVALID", "ready": False}
        if (data["ffms2_version"] != self.version or
            data["ffms2_library_sha256"] != self.lib_sha):
            return {"status": "REINDEX_REQUIRED", "ready": False,
                    "previous_ffms2_version": data["ffms2_version"],
                    "current_ffms2_version": self.version,
                    "notice": dict(NOTICE)}
        # A matching marker is only evidence of last completed indexing.
        # The actual .ffindex and original must be verified before decode.
        return {"status": "INDEX_VERSION_MATCH_UNVERIFIED", "ready": False,
                "notice": None}

    def mark_index_verified(self, project_id, asset_id, source_sha256):
        """Record version only AFTER successful native index verification.

        Previous binary-version cache files remain intact; this atomically
        changes a small pointer. Native TaskLedger authorization remains
        necessary for any actual indexing or media read.
        """
        target = self._marker(project_id, asset_id, source_sha256)
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent.is_symlink() or not parent.resolve().is_relative_to(self.root.resolve()):
            raise RuntimeError("FFMS2 cache compatibility path escaped root")
        if target.is_symlink():
            raise RuntimeError("FFMS2 compatibility marker is unsafe")
        record = {
            "format": FORMAT, "project_id": project_id, "asset_id": asset_id,
            "source_sha256": source_sha256, "ffms2_version": self.version,
            "ffms2_library_sha256": self.lib_sha,
        }
        fd, tmp = tempfile.mkstemp(prefix=".compat-", dir=parent)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(_canonical(record))
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, target)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return {"status": "INDEX_VERSION_RECORDED", "originals_modified": False}
