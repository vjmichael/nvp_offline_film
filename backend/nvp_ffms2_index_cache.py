"""SCALE-03C: immutable FFMS2 cache identities bound to FilmIndex source SHA.

The index files live under NVP-controlled cache storage, NEVER on SD cards or
camera originals. Existing cache files are not trusted without manifest,
hash, FFMS2 library version and native FFMS_IndexBelongsToFile verification.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from backend.nvp_ffms2_native import FFMS2, sha_file
from backend.nvp_film_index import _require_pid, _id, _sha

FORMAT = "nvp.ffms2.source_index.v1"
MAX_INDEX_BYTES = 2 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


class FFMS2SourceIndex:
    """Host/worker-owned local index cache; not media access authorization."""

    def __init__(self, library: FFMS2, root):
        if not isinstance(library, FFMS2):
            raise TypeError("Native FFMS2 C API required")
        root = Path(root)
        if not root.is_absolute() or root.is_symlink():
            raise PermissionError("Native FFMS2 cache needs an absolute trusted root")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root.resolve()
        self.library = library

    def _location(self, project_id, asset_id, source_sha):
        _require_pid(project_id)
        _id(asset_id, "source asset identity")
        _sha(source_sha)
        basis = _canonical({
            "format": FORMAT, "project_id": project_id,
            "asset_id": asset_id, "content_sha256": source_sha,
            "ffms2_version": self.library.version,
            "ffms2_library_sha256": self.library.library_sha256,
        })
        key = hashlib.sha256(basis).hexdigest()
        parent = self.root / project_id / key[:2]
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent.is_symlink() or not parent.resolve().is_relative_to(self.root):
            raise RuntimeError("FFMS2 cache path escaped trusted directory")
        return parent / (key + ".ffindex"), parent / (key + ".json")

    def get_or_create(self, project_id, asset_id, source, source_sha):
        """Reuse or create bounded-memory FFMS2 frame index for an exact source.

        The source is fully rehashed before indexing/reusing. A second full
        hash after building protects against a changed original during index.
        This is deliberately a correctness gate, not yet instant interactive
        access to a multi-terabyte original.
        """
        _require_pid(project_id)
        _id(asset_id, "source ID")
        _sha(source_sha)
        source = Path(source)
        if not source.is_absolute() or source.is_symlink() or not source.is_file():
            raise RuntimeError("FFMS2 media original is offline or unsafe")
        if sha_file(source) != source_sha:
            raise RuntimeError("FFMS2 source differs from immutable FilmIndex bytes")
        index_file, manifest_file = self._location(project_id, asset_id, source_sha)
        if (index_file.exists() or index_file.is_symlink() or
                manifest_file.exists() or manifest_file.is_symlink()):
            if (not index_file.is_file() or index_file.is_symlink() or
                    not manifest_file.is_file() or manifest_file.is_symlink()):
                raise RuntimeError("Incomplete cached native index requires reconciliation")
            if (manifest_file.stat().st_size > MAX_MANIFEST_BYTES or
                index_file.stat().st_size > MAX_INDEX_BYTES):
                raise RuntimeError("Cached FFMS2 index exceeds native budget")
            metadata = json.loads(manifest_file.read_bytes())
            expected = {
                "format": FORMAT, "project_id": project_id, "asset_id": asset_id,
                "source_sha256": source_sha, "ffms2_version": self.library.version,
                "ffms2_library_sha256": self.library.library_sha256,
            }
            if (any(metadata.get(key) != value for key, value in expected.items()) or
                sha_file(index_file) != metadata.get("index_sha256") or
                metadata.get("index_size_bytes") != index_file.stat().st_size):
                raise RuntimeError("Cached FFMS2 index hash/version/source mismatch")
            # ReadIndex + IndexBelongsToFile validated by open_video immediately.
            with self.library.open_video(source, index_file, track=metadata["track"]) as vid:
                if (vid.meta["num_frames"] != metadata["num_frames"] or
                    vid.meta["time_base_num"] != metadata["time_base_num"] or
                    vid.meta["time_base_den"] != metadata["time_base_den"]):
                    raise RuntimeError("FFMS2 cached frame metadata changed")
            return {"status": "VERIFIED_REUSED", "index_path": str(index_file),
                    **metadata}
        # No partial index must become authoritative after a crash. Preserve
        # suspicious stale lock for host reconciliation instead of stealing.
        lock = index_file.with_suffix(".building")
        with lock.open("xb") as lockfile:
            lockfile.write(source_sha.encode("ascii"))
            lockfile.flush()
            os.fsync(lockfile.fileno())
        stage_path = None
        stage_meta = None
        try:
            fd, stage_path = tempfile.mkstemp(prefix=".ffmsindex-", suffix=".tmp",
                                               dir=index_file.parent)
            os.close(fd)
            indexed = self.library.create_index(source, stage_path)
            if sha_file(source) != source_sha:
                raise RuntimeError("Original changed during FFMS2 indexing")
            if (not Path(stage_path).is_file() or
                not 0 < Path(stage_path).stat().st_size <= MAX_INDEX_BYTES):
                raise RuntimeError("FFMS2 generated invalid or oversized index")
            with self.library.open_video(source, stage_path,
                                         track=indexed["track"]) as video:
                if video.meta != indexed:
                    raise RuntimeError("FFMS2 index readback is inconsistent")
            metadata = {
                "format": FORMAT, "project_id": project_id, "asset_id": asset_id,
                "source_sha256": source_sha, "ffms2_version": self.library.version,
                "ffms2_library_sha256": self.library.library_sha256,
                "index_sha256": sha_file(stage_path),
                "index_size_bytes": Path(stage_path).stat().st_size,
                **indexed,
            }
            fd, stage_meta = tempfile.mkstemp(prefix=".ffmsmeta-", suffix=".tmp",
                                                dir=index_file.parent)
            with os.fdopen(fd, "wb") as out:
                out.write(_canonical(metadata))
                out.flush()
                os.fsync(out.fileno())
            if index_file.exists() or manifest_file.exists():
                raise RuntimeError("Concurrent FFMS2 cache publication detected")
            os.replace(stage_path, index_file)
            stage_path = None
            os.replace(stage_meta, manifest_file)
            stage_meta = None
            return {"status": "VERIFIED_CREATED", "index_path": str(index_file),
                    **metadata}
        finally:
            if stage_path is not None:
                Path(stage_path).unlink(missing_ok=True)
            if stage_meta is not None:
                Path(stage_meta).unlink(missing_ok=True)
            # Only clear the lock when a fully registered manifest is present.
            # If publication was interrupted or verification failed, the
            # trusted host must explicitly reconcile the slot.
            if manifest_file.is_file() and index_file.is_file():
                lock.unlink(missing_ok=True)
