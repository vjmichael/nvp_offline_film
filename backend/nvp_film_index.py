"""NVP-DATA-01: durable project-scoped index for film source and derived artifacts.

This is the *foundation*, not yet the full Digital Take capture/renderer/editor.
It stores immutable JSON source revisions and binary blobs, maintains typed
revision-level dependency edges and computes bounded downstream invalidation.

An object can have a newer revision without rewriting old approved takes.
The special "take" kind is strictly single-commit per stable take identity.

No model, network, GPU, Blender worker or Lu dependency is required.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from backend.nvp_production_scene import compact, digest
from backend.nvp_studio import Studio, now

IDENT = re.compile(r"[a-zA-Z][a-zA-Z0-9_.:-]{0,79}\Z")
PROJECT = re.compile(r"[a-f0-9]{32}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
KINDS = frozenset({
    "world", "scene", "actor", "asset", "style", "performance",
    "camera", "dialogue", "audio", "lighting", "prop",
    "take", "presentation", "edit", "master", "temporal"
})
EDGE_ROLES = frozenset({
    "world", "scene", "actor", "asset", "style", "performance",
    "camera", "dialogue", "audio", "lighting", "prop",
    "source_take", "render_job", "presentation", "timeline", "temporal",
})
MAX_JSON_BYTES = 1024 * 1024
MAX_BLOB_BYTES = 32 * 1024 * 1024
MAX_DEPENDENCIES = 128


def _id(value, what):
    if type(value) is not str or not IDENT.fullmatch(value):
        raise ValueError("Invalid " + what)
    return value


def _sha(value):
    if type(value) is not str or not SHA.fullmatch(value):
        raise ValueError("Invalid lowercase SHA-256")
    return value


def _require_pid(value):
    if type(value) is not str or not PROJECT.fullmatch(value):
        raise ValueError("Invalid film project identity")
    return value


def _deps(dependencies, source_id):
    if type(dependencies) is not list or len(dependencies) > MAX_DEPENDENCIES:
        raise ValueError("Expected bounded list of typed revision dependencies")
    seen = set()
    approved = []
    for dep in dependencies:
        if type(dep) is not dict or set(dep) != {"object_id", "revision", "role"}:
            raise ValueError("Dependency needs object_id, revision and role")
        oid = _id(dep["object_id"], "dependency object ID")
        rev = dep["revision"]
        role = dep["role"]
        if type(rev) is not int or rev < 1 or role not in EDGE_ROLES:
            raise ValueError("Invalid dependency revision or edge role")
        if oid == source_id:
            raise ValueError("Do not create revision self-dependencies; use parent revisions")
        key = (oid, rev, role)
        if key in seen:
            raise ValueError("Repeated dependency edge")
        seen.add(key)
        approved.append({"object_id": oid, "revision": rev, "role": role})
    return sorted(approved, key=lambda x: (x["object_id"], x["revision"], x["role"]))


class FilmIndex:
    """SQLite transaction index; SHA-addressed payloads live on disk, not in VRAM.

    This class does NOT grant director approval or authorize workers. The host
    must authenticate user actions. Existing project IDs from Studio are used
    as the sole namespace; actors/assets never leak across film projects.
    """

    def __init__(self, studio: Studio, blob_root: str | Path | None = None):
        self.studio = studio
        self.blob_root = Path(blob_root if blob_root is not None
                              else studio.db_path.parent / (studio.db_path.stem + "_film_blobs"))
        self.blob_root.mkdir(parents=True, exist_ok=True)
        self.blob_root = self.blob_root.resolve()
        with self.studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS film_blob_refs (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                media_type TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(project_id, sha256))""")
            db.execute("""CREATE TABLE IF NOT EXISTS film_objects (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                object_id TEXT NOT NULL, kind TEXT NOT NULL,
                head_revision INTEGER NOT NULL CHECK(head_revision >= 1),
                PRIMARY KEY(project_id, object_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS film_object_revisions (
                project_id TEXT NOT NULL, object_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision >= 1),
                document_sha TEXT NOT NULL,
                parent_revision INTEGER, committed_at TEXT NOT NULL,
                PRIMARY KEY(project_id, object_id, revision),
                FOREIGN KEY(project_id, object_id)
                    REFERENCES film_objects(project_id, object_id) ON DELETE CASCADE,
                FOREIGN KEY(project_id, document_sha)
                    REFERENCES film_blob_refs(project_id, sha256),
                CHECK(parent_revision IS NULL OR parent_revision < revision))""")
            db.execute("""CREATE TABLE IF NOT EXISTS film_dependencies (
                project_id TEXT NOT NULL,
                source_id TEXT NOT NULL, source_revision INTEGER NOT NULL,
                target_id TEXT NOT NULL, target_revision INTEGER NOT NULL,
                role TEXT NOT NULL,
                PRIMARY KEY(project_id, source_id, source_revision,
                            target_id, target_revision, role),
                FOREIGN KEY(project_id, source_id, source_revision)
                    REFERENCES film_object_revisions(project_id, object_id, revision)
                    ON DELETE CASCADE,
                FOREIGN KEY(project_id, target_id, target_revision)
                    REFERENCES film_object_revisions(project_id, object_id, revision))""")
            db.execute("""CREATE INDEX IF NOT EXISTS film_dependencies_reverse
                ON film_dependencies(project_id, target_id, target_revision)""")

    def _project(self, db, project_id):
        _require_pid(project_id)
        if db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
            raise KeyError("Film project not found")
        return project_id

    def _blob_path(self, project_id, sha):
        _require_pid(project_id)
        _sha(sha)
        parent = self.blob_root / project_id / sha[:2]
        # Never follow a manipulated symlink out of the project's blob directory.
        parent.mkdir(parents=True, exist_ok=True)
        resolved = parent.resolve()
        if not resolved.is_relative_to(self.blob_root / project_id):
            raise RuntimeError("Film blob directory escaped its project root")
        return resolved / sha

    def put_blob(self, project_id, value: bytes, media_type="application/octet-stream"):
        """Atomically publish bytes by SHA without overwriting an existing blob.

        A failed DB insert can leave an unindexed, harmless orphan disk blob,
        which a future approved garbage collector can remove. It cannot become
        an indexed film artifact merely by being present on disk.
        """
        if type(value) is not bytes or len(value) > MAX_BLOB_BYTES:
            raise ValueError("Film blob must be bytes, <=32 MiB per indexed chunk")
        if (type(media_type) is not str or not 1 <= len(media_type) <= 100 or
            any(c in media_type for c in "\r\n\x00")):
            raise ValueError("Invalid media type")
        sha = hashlib.sha256(value).hexdigest()
        with self.studio._connection() as db:
            self._project(db, project_id)
        path = self._blob_path(project_id, sha)
        if path.is_symlink():
            raise RuntimeError("Refusing symlinked content-addressed media")
        if path.exists():
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                raise RuntimeError("Previously stored film asset bytes were corrupted")
        else:
            fd, temp_name = tempfile.mkstemp(prefix=".unpublished-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as out:
                    out.write(value)
                    out.flush()
                    os.fsync(out.fileno())
                # Atomic no-clobber creation. Another writer may publish the same
                # digest first; validate that content rather than overwrite it.
                try:
                    os.link(temp_name, path)
                except FileExistsError:
                    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                        raise RuntimeError("Concurrent blob publication changed content")
            finally:
                Path(temp_name).unlink(missing_ok=True)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._project(db, project_id)
            existing = db.execute("""SELECT size_bytes,media_type FROM film_blob_refs
                          WHERE project_id=? AND sha256=?""", (project_id, sha)).fetchone()
            if existing is not None:
                if existing["size_bytes"] != len(value) or existing["media_type"] != media_type:
                    raise RuntimeError("Existing film blob metadata conflicts with new registration")
            else:
                db.execute("""INSERT INTO film_blob_refs
                          (project_id,sha256,size_bytes,media_type,created_at)
                          VALUES(?,?,?,?,?)""", (project_id, sha, len(value), media_type, now()))
        return sha

    def get_blob(self, project_id, sha):
        _require_pid(project_id)
        _sha(sha)
        with self.studio._connection() as db:
            self._project(db, project_id)
            record = db.execute("""SELECT size_bytes FROM film_blob_refs
                WHERE project_id=? AND sha256=?""", (project_id, sha)).fetchone()
        if record is None:
            raise KeyError("Film blob does not belong to this project")
        path = self._blob_path(project_id, sha)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Film blob missing or replaced by a symlink")
        data = path.read_bytes()
        if len(data) != record["size_bytes"] or hashlib.sha256(data).hexdigest() != sha:
            raise RuntimeError("Film blob integrity check failed")
        return data

    def put_media_file(self, project_id, source_path, media_type="video/mp4",
                       *, max_bytes=2 * 1024 * 1024 * 1024):
        """Stream and atomically register a larger media file, without RAM loading.

        This is an immutable source/video artifact, not a mutable render temp.
        Never exposes an arbitrary uploaded path as an asset until bytes have
        been copied, hashed, and bound to a project-scoped DB registration.
        """
        if media_type not in ("video/mp4", "video/quicktime", "audio/wav",
                               "audio/mpeg", "audio/flac", "audio/ogg",
                               "image/x-exr", "application/octet-stream"):
            raise ValueError("Unsupported indexed media type")
        if type(max_bytes) is not int or max_bytes < 1 or max_bytes > 2*1024**3:
            raise ValueError("Invalid media budget")
        path = Path(source_path)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Media source missing or symlinked")
        _require_pid(project_id)
        with self.studio._connection() as db:
            self._project(db, project_id)
        # Stage under a project-controlled directory before publishing by SHA.
        stage_dir = (self.blob_root / project_id / ".staging").resolve()
        if not stage_dir.is_relative_to(self.blob_root / project_id):
            raise RuntimeError("Media staging path escaped the film root")
        stage_dir.mkdir(parents=True, exist_ok=True)
        if stage_dir.is_symlink():
            raise RuntimeError("Media staging directory is symlinked")
        fd, tmp = tempfile.mkstemp(prefix=".media-", dir=stage_dir)
        size = 0
        h = hashlib.sha256()
        try:
            with os.fdopen(fd,"wb") as out, path.open("rb") as inp:
                while chunk := inp.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Media exceeds maximum indexed file budget")
                    h.update(chunk)
                    out.write(chunk)
                if not size:
                    raise ValueError("Empty media file cannot be indexed")
                out.flush()
                os.fsync(out.fileno())
            sha = h.hexdigest()
            target = self._blob_path(project_id, sha)
            if target.is_symlink():
                raise RuntimeError("Refusing symlinked indexed media")
            try:
                os.link(tmp, target)
            except FileExistsError:
                if target.is_symlink() or not target.is_file():
                    raise RuntimeError("Existing indexed media path is unsafe")
                self._verify_file_bytes(target, sha, size)
            with self.studio._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                self._project(db, project_id)
                row = db.execute("""SELECT size_bytes,media_type FROM film_blob_refs
                    WHERE project_id=? AND sha256=?""",(project_id,sha)).fetchone()
                if row is None:
                    db.execute("""INSERT INTO film_blob_refs
                        (project_id,sha256,size_bytes,media_type,created_at)
                        VALUES(?,?,?,?,?)""",(project_id,sha,size,media_type,now()))
                elif row["size_bytes"]!=size or row["media_type"]!=media_type:
                    raise RuntimeError("Conflicting media registration metadata")
            return {"sha256":sha,"size_bytes":size,"media_type":media_type}
        finally:
            Path(tmp).unlink(missing_ok=True)

    @staticmethod
    def _verify_file_bytes(path, sha, expected_size):
        h=hashlib.sha256()
        size=0
        with Path(path).open("rb") as src:
            while chunk := src.read(1024*1024):
                size += len(chunk)
                if size > expected_size:
                    raise RuntimeError("Indexed media grew after storage")
                h.update(chunk)
        if size!=expected_size or h.hexdigest()!=sha:
            raise RuntimeError("Indexed media SHA-256 integrity failure")
        return size

    def verify_media_file(self, project_id, sha, media_type=None):
        """Independently rehash stored bytes after restart without reading RAM."""
        _require_pid(project_id)
        _sha(sha)
        with self.studio._connection() as db:
            self._project(db,project_id)
            row=db.execute("""SELECT size_bytes,media_type FROM film_blob_refs
                WHERE project_id=? AND sha256=?""",(project_id,sha)).fetchone()
        if row is None:
            raise KeyError("Media not registered to the specified film")
        if media_type is not None and row["media_type"]!=media_type:
            raise RuntimeError("Indexed media type mismatch")
        path=self._blob_path(project_id,sha)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Indexed media file missing or symlinked")
        self._verify_file_bytes(path,sha,row["size_bytes"])
        return {"sha256":sha,"size_bytes":row["size_bytes"],
                "media_type":row["media_type"],"path":str(path)}

    def put_json(self, project_id, document):
        if type(document) not in (dict, list):
            raise ValueError("Film manifest must be structured JSON")
        encoded = compact(document).encode("utf-8")
        if len(encoded) > MAX_JSON_BYTES:
            raise ValueError("Film manifest exceeds one MiB; store large media separately")
        return self.put_blob(project_id, encoded, "application/vnd.nvp.manifest+json")

    def _read_revision(self, db, project_id, object_id, revision):
        return db.execute("""SELECT r.document_sha,r.parent_revision,r.committed_at,o.kind
             FROM film_object_revisions r JOIN film_objects o
             ON o.project_id=r.project_id AND o.object_id=r.object_id
             WHERE r.project_id=? AND r.object_id=? AND r.revision=?""",
             (project_id, object_id, revision)).fetchone()

    def register_revision(self, project_id, object_id, kind, data, *,
                          expected_revision=0, dependencies=None, precommit_guard=None):
        """Publish an immutable source/derived revision; old revisions survive.

        A frozen take ID accepts exactly one commit; a changed performance or
        camera must use a different take ID. Dependency IDs are version-bound.
        """
        _require_pid(project_id)
        _id(object_id, "film object ID")
        if kind not in KINDS:
            raise ValueError("Unknown authoritative or derived film object kind")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected revision must be a nonnegative integer")
        if type(data) is not dict or not data:
            raise ValueError("Film object data must be a nonempty structured object")
        if precommit_guard is not None and not callable(precommit_guard):
            raise ValueError("Precommit validation must be trusted in-process code")
        edges = _deps(dependencies if dependencies is not None else [], object_id)
        manifest = {"format": "nvp.film.revision.v1", "object_id": object_id,
                    "kind": kind, "data": data, "dependencies": edges}
        sha = self.put_json(project_id, manifest)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._project(db, project_id)
            existing = db.execute("""SELECT kind,head_revision FROM film_objects
                 WHERE project_id=? AND object_id=?""", (project_id, object_id)).fetchone()
            head = existing["head_revision"] if existing else 0
            if existing and existing["kind"] != kind:
                raise RuntimeError("An object cannot change its identity or kind")
            if head != expected_revision:
                raise RuntimeError("Film object revision conflict; reload before committing")
            # A source is immutable while present, but may be explicitly
            # retired or purged. The lifecycle table is optional for older
            # installations; check it inside the SAME SQLite write lease
            # that publishes a FilmIndex revision. IDs of deleted sources
            # cannot be reused; a retired source cannot acquire new users.
            retention=db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='nvp_film_source_retirements'""").fetchone()
            if retention is not None:
                blocked=db.execute("""SELECT 1 FROM nvp_film_source_retirements
                    WHERE project_id=? AND object_id=? AND state!='RESTORED'""",
                    (project_id,object_id)).fetchone()
                if blocked is not None:
                    raise RuntimeError("Film object identity was retired or purged")
                for dep in edges:
                    blocked=db.execute("""SELECT 1 FROM nvp_film_source_retirements
                        WHERE project_id=? AND object_id=? AND state!='RESTORED'""",
                        (project_id,dep["object_id"])).fetchone()
                    if blocked is not None:
                        raise RuntimeError("Cannot publish a new dependency on retired film source")
            if kind == "take" and existing:
                raise RuntimeError("A frozen digital take cannot be revised in-place")
            for dep in edges:
                if self._read_revision(db, project_id, dep["object_id"], dep["revision"]) is None:
                    raise KeyError("Dependency revision not present in this film")
            # A capture guard validates its *live approved source* inside this
            # same BEGIN IMMEDIATE write transaction. Reopening source through
            # other WAL readers is safe; their writes cannot change data here.
            # The guard is a trusted internal callable, never model output.
            if precommit_guard is not None:
                precommit_guard(db)
            revision = head + 1
            if existing is None:
                db.execute("""INSERT INTO film_objects(project_id,object_id,kind,head_revision)
                           VALUES(?,?,?,?)""", (project_id, object_id, kind, revision))
            else:
                db.execute("""UPDATE film_objects SET head_revision=?
                           WHERE project_id=? AND object_id=? AND head_revision=?""",
                           (revision, project_id, object_id, head))
            db.execute("""INSERT INTO film_object_revisions
                       (project_id,object_id,revision,document_sha,parent_revision,committed_at)
                       VALUES(?,?,?,?,?,?)""",
                       (project_id, object_id, revision, sha,
                        head if head else None, now()))
            for dep in edges:
                db.execute("""INSERT INTO film_dependencies
                       (project_id,source_id,source_revision,target_id,target_revision,role)
                       VALUES(?,?,?,?,?,?)""",
                       (project_id, object_id, revision, dep["object_id"],
                        dep["revision"], dep["role"]))
        return {"project_id": project_id, "object_id": object_id,
                "kind": kind, "revision": revision, "document_sha256": sha,
                "parent_revision": head or None,
                "dependencies": edges}

    def read_revision(self, project_id, object_id, revision=None):
        _require_pid(project_id)
        _id(object_id, "film object ID")
        with self.studio._connection() as db:
            self._project(db, project_id)
            if revision is None:
                head = db.execute("""SELECT head_revision FROM film_objects
                    WHERE project_id=? AND object_id=?""",
                    (project_id, object_id)).fetchone()
                if head is None:
                    raise KeyError("Film object not found")
                revision = head["head_revision"]
            if type(revision) is not int or revision < 1:
                raise ValueError("Invalid film revision number")
            row = self._read_revision(db, project_id, object_id, revision)
            if row is None:
                raise KeyError("Exact film revision not found")
            recorded = [dict(x) for x in db.execute("""SELECT
                  target_id AS object_id,target_revision AS revision,role
                  FROM film_dependencies WHERE project_id=? AND
                  source_id=? AND source_revision=?
                  ORDER BY target_id,target_revision,role""",
                  (project_id, object_id, revision))]
        raw = self.get_blob(project_id, row["document_sha"])
        doc = json.loads(raw)
        if (type(doc) is not dict or doc.get("format") != "nvp.film.revision.v1" or
            doc.get("object_id") != object_id or doc.get("kind") != row["kind"] or
            doc.get("dependencies") != recorded or digest(doc) != row["document_sha"]):
            raise RuntimeError("Film revision database and immutable source bytes disagree")
        return {"project_id": project_id, "object_id": object_id, "revision": revision,
                "parent_revision": row["parent_revision"],
                "document_sha256": row["document_sha"], "committed_at": row["committed_at"],
                **doc}

    def history(self, project_id, object_id):
        _require_pid(project_id)
        _id(object_id, "film object ID")
        with self.studio._connection() as db:
            self._project(db, project_id)
            rows = db.execute("""SELECT revision,document_sha,parent_revision,committed_at
                FROM film_object_revisions WHERE project_id=? AND object_id=?
                ORDER BY revision""", (project_id, object_id)).fetchall()
        return [dict(row) for row in rows]

    def list_objects(self, project_id, *, kind=None, include_retired=False):
        """List available original objects; old retired sources stay addressable
        by exact revision for historical cut custody, not new selection."""
        _require_pid(project_id)
        if kind is not None and kind not in KINDS:
            raise ValueError("Unrecognized film object type")
        if type(include_retired) is not bool:
            raise ValueError("include_retired must be an explicit boolean")
        with self.studio._connection() as db:
            self._project(db, project_id)
            lifecycle=db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='nvp_film_source_retirements'""").fetchone()
            if lifecycle is not None and not include_retired:
                rows=db.execute("""SELECT f.object_id,f.kind,f.head_revision
                    FROM film_objects f LEFT JOIN nvp_film_source_retirements r
                    ON r.project_id=f.project_id AND r.object_id=f.object_id
                    WHERE f.project_id=? AND (? IS NULL OR f.kind=?)
                      AND (r.state IS NULL OR r.state='RESTORED')
                    ORDER BY f.kind,f.object_id""",(project_id,kind,kind)).fetchall()
            else:
                rows=db.execute("""SELECT object_id,kind,head_revision
                    FROM film_objects WHERE project_id=? AND
                    (? IS NULL OR kind=?) ORDER BY kind,object_id""",
                    (project_id,kind,kind)).fetchall()
        return [dict(row) for row in rows]

    def direct_dependents(self, project_id, object_id, revision):
        _require_pid(project_id)
        _id(object_id, "source object ID")
        if type(revision) is not int or revision < 1:
            raise ValueError("Invalid source revision")
        with self.studio._connection() as db:
            self._project(db, project_id)
            if self._read_revision(db, project_id, object_id, revision) is None:
                raise KeyError("Source revision not present")
            direct = [dict(x) for x in db.execute("""SELECT DISTINCT source_id AS object_id,
                   source_revision AS revision FROM film_dependencies
                   WHERE project_id=? AND target_id=? AND target_revision=?
                   ORDER BY source_id,source_revision""",
                   (project_id, object_id, revision))]
            # Studio-scale clip references are normalized into an indexed table
            # rather than capped at the 128 FilmIndex JSON dependency edges.
            # The trusted bound-edit publisher inserts these rows in the SAME
            # FilmIndex commit transaction. Older databases need not have it.
            exists = db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                   AND name='scale_editorial_source_bindings'""").fetchone()
            if exists:
                indexed = db.execute("""SELECT DISTINCT b.edit_id AS object_id,
                       b.revision AS revision
                    FROM scale_editorial_source_bindings b
                    JOIN film_object_revisions r
                      ON r.project_id=b.project_id
                      AND r.object_id=b.edit_id AND r.revision=b.revision
                    WHERE b.project_id=? AND b.source_id=? AND b.source_revision=?
                      AND b.source_document_sha256=?
                    ORDER BY b.edit_id,b.revision""",
                    (project_id, object_id, revision,
                     self._read_revision(db, project_id, object_id, revision)["document_sha"]))
                direct.extend(dict(x) for x in indexed)
            # Authored actions are sparse time events, not rendered frames.
            # Their source revisions are indexed independently of FilmIndex's
            # legacy bounded direct dependency JSON list.
            temporal_table = db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='nvp_temporal_events'""").fetchone()
            if temporal_table:
                authored = db.execute("""SELECT DISTINCT e.timeline_id AS object_id,
                    e.revision AS revision
                    FROM nvp_temporal_events e
                    JOIN film_object_revisions r
                      ON r.project_id=e.project_id
                     AND r.object_id=e.timeline_id AND r.revision=e.revision
                    WHERE e.project_id=? AND e.source_id=?
                      AND e.source_revision=? AND e.source_document_sha256=?
                    ORDER BY e.timeline_id,e.revision""",
                    (project_id,object_id,revision,
                     self._read_revision(db,project_id,object_id,revision)["document_sha"]))
                direct.extend(dict(x) for x in authored)
            unique = {(r["object_id"], r["revision"]) for r in direct}
            return [{"object_id": oid, "revision": rev}
                    for oid, rev in sorted(unique)]

    def impact(self, project_id, object_id, revision):
        """Return transitive *indexed* consumers of an old source revision.

        This reports impacted recorded versions, not a promise that a video
        model can regenerate an individual frame or that all connections
        to legacy unindexed producer outputs have already been migrated.
        """
        pending = [(object_id, revision)]
        visited = {(object_id, revision)}
        result = []
        while pending:
            source, rev = pending.pop(0)
            for consumer in self.direct_dependents(project_id, source, rev):
                key = (consumer["object_id"], consumer["revision"])
                if key not in visited:
                    visited.add(key)
                    result.append(consumer)
                    pending.append(key)
        return result
