"""SLATE-05 — bounded, disk-first, crash-recoverable PNG proxy cache.

Only low-fi DERIVATIVES live here. Original FilmIndex bytes, OpenUSD layers,
digital Takes, editor selections and creator approval records are elsewhere.
Entries are SHA-pinned, project-scoped, optionally evicted by LRU. A missing
or tampered cache file is NEVER treated as a valid completed preview.

A preview becomes READY only after the established BlenderWorkerSupervisor
independently verifies its native worker output and required PNG file hash.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import tempfile
import time

from backend.nvp_film_index import _require_pid,_sha
from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file

PNG=b"\x89PNG\r\n\x1a\n"
FORMAT="nvp.slate.lowfi_png_cache.v1"
MAX_IMAGE_BYTES=8*1024*1024
MIN_BYTES=33
STATES=frozenset(("PENDING","READY","FAILED","INTERRUPTED","EVICTED"))


class SlatePreviewCache:
    def __init__(self,root,*,max_disk_bytes=256*1024*1024,max_ready=1024):
        if (type(max_disk_bytes) is not int or not 1024*1024<=max_disk_bytes<=2*1024**3 or
            type(max_ready) is not int or not 1<=max_ready<=8192):
            raise ValueError("Invalid bounded preview cache disk quota")
        self.root=Path(root).resolve()
        if self.root.is_symlink():
            raise RuntimeError("Cache root cannot be a symlink")
        self.root.mkdir(parents=True,exist_ok=True)
        self.max_disk_bytes=max_disk_bytes
        self.max_ready=max_ready
        self.db=self.root/"preview_cache.sqlite3"
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS slate_preview_cache(
                project_id TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                state TEXT NOT NULL,
                job_id TEXT NOT NULL UNIQUE,
                source_sha256 TEXT NOT NULL,
                recipe_sha256 TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                image_sha256 TEXT,
                size_bytes INTEGER,
                last_use_ns INTEGER NOT NULL,
                updated_ns INTEGER NOT NULL,
                PRIMARY KEY(project_id,cache_key),
                CHECK(state IN ('PENDING','READY','FAILED','INTERRUPTED','EVICTED'))
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS slate_preview_cache_lru
                ON slate_preview_cache(state,last_use_ns)""")

    @contextmanager
    def _db(self):
        db=sqlite3.connect(self.db,timeout=15,isolation_level=None)
        try:
            db.row_factory=sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA busy_timeout=15000")
            # An explicit BEGIN IMMEDIATE must COMMIT before releasing this
            # connection. Merely closing a contextmanager-owned connection
            # silently rolls back a newly reserved preview/ready/failure row,
            # making one-use creator approval appear missing or revoked.
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _path(self,project_id,key):
        _require_pid(project_id)
        _sha(key)
        sub=self.root/project_id/key[:2]
        sub.mkdir(parents=True,exist_ok=True)
        resolved=sub.resolve()
        if not resolved.is_relative_to(self.root/project_id):
            raise RuntimeError("Cache path escaped project namespace")
        return resolved/(key+".png")

    @staticmethod
    def _audit_file(path,width,height):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Preview PNG missing or replaced with symlink")
        size=path.stat().st_size
        if not MIN_BYTES<=size<=MAX_IMAGE_BYTES:
            raise RuntimeError("Preview PNG size outside accepted proxy bounds")
        with path.open("rb") as f:
            head=f.read(24)
        if (head[:8]!=PNG or head[12:16]!=b"IHDR" or
            struct.unpack(">II",head[16:24])!=(width,height)):
            raise RuntimeError("Native output is not the expected PNG dimensions")
        return sha_file(path),size

    def lookup(self,project_id,cache_key):
        """Never serve a thumbnail without checking its accepted disk SHA."""
        path=self._path(project_id,cache_key)
        with self._db() as db:
            row=db.execute("""SELECT * FROM slate_preview_cache
                WHERE project_id=? AND cache_key=?""",
                (project_id,cache_key)).fetchone()
        if row is None or row["state"]!="READY":
            return None
        try:
            digest,size=self._audit_file(path,row["width"],row["height"])
            if digest!=row["image_sha256"] or size!=row["size_bytes"]:
                raise RuntimeError("Cached thumbnail changed after independent audit")
        except (OSError,RuntimeError):
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE slate_preview_cache SET state='INTERRUPTED',
                    updated_ns=? WHERE project_id=? AND cache_key=?
                    AND state='READY'""",(time.time_ns(),project_id,cache_key))
            # The cache namespace owns this derivative path. Discard its
            # corrupt bytes (never FilmIndex source bytes), so a fresh,
            # independently verified preview may be published later.
            try:
                if path.is_symlink() or path.is_file():
                    path.unlink()
            except OSError:
                pass
            return None
        with self._db() as db:
            db.execute("""UPDATE slate_preview_cache SET last_use_ns=?
                WHERE project_id=? AND cache_key=? AND state='READY'""",
                (time.time_ns(),project_id,cache_key))
        return {
            "format":FORMAT,"status":"READY",
            "project_id":project_id,"cache_key":cache_key,
            "job_id":row["job_id"],"png_path":str(path),
            "image_sha256":digest,"size_bytes":size,
            "width":row["width"],"height":row["height"],
            "source_data_modified":False,
            "lowfi_proxy_only":True,
            "original_actor_mesh_rendered":False,
            "full_feature_render_approved":False,
        }

    def reserve(self,project_id,key,*,job_id,source_sha256,recipe_sha256,
                width,height):
        _require_pid(project_id)
        for value in (key,source_sha256,recipe_sha256):
            _sha(value)
        if (type(job_id) is not str or not job_id or
            type(width) is not int or type(height) is not int or
            not 64<=width<=1024 or not 64<=height<=1024):
            raise ValueError("Invalid bounded cache reservation")
        existing=self.lookup(project_id,key)
        if existing:
            return {**existing,"status":"CACHE_HIT"}
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT state,job_id FROM slate_preview_cache
                WHERE project_id=? AND cache_key=?""",(project_id,key)).fetchone()
            if row is not None and row["state"]=="PENDING":
                return {"status":"ALREADY_PENDING","job_id":row["job_id"],
                        "cache_key":key,"source_data_modified":False}
            if row is not None:
                # A failed/restarted job gets a NEW worker ID and independent
                # receipt; old preexisting output is not auto-accepted.
                db.execute("""DELETE FROM slate_preview_cache
                    WHERE project_id=? AND cache_key=?""",
                    (project_id,key))
            db.execute("""INSERT INTO slate_preview_cache
                (project_id,cache_key,state,job_id,source_sha256,
                 recipe_sha256,width,height,last_use_ns,updated_ns)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (project_id,key,"PENDING",job_id,source_sha256,
                 recipe_sha256,width,height,time.time_ns(),time.time_ns()))
        return {"status":"PENDING","job_id":job_id,"cache_key":key,
                "source_data_modified":False}

    def _job(self,job_id):
        with self._db() as db:
            row=db.execute("""SELECT * FROM slate_preview_cache
                WHERE job_id=?""",(job_id,)).fetchone()
        if row is None:
            raise KeyError("No pending proxy preview for native worker")
        return row

    def accept_verified(self,supervisor:BlenderWorkerSupervisor,job_id):
        """A worker audit receipt, not the browser, makes a PNG cacheable."""
        if not isinstance(supervisor,BlenderWorkerSupervisor):
            raise TypeError("Established contained native Blender worker required")
        row=self._job(job_id)
        if row["state"]=="READY":
            result=self.lookup(row["project_id"],row["cache_key"])
            if result:
                return result
            raise RuntimeError("Previously verified preview became unavailable")
        if row["state"]!="PENDING":
            raise RuntimeError("Only PENDING preview may become READY")
        proof=supervisor.verify_completed(job_id)
        output=proof["outputs"]
        artifact=output.get("preview.png")
        if artifact is None or artifact["kind"]!="png":
            raise RuntimeError("Native Blender receipt lacks expected PNG")
        source=supervisor.root/job_id/"preview.png"
        digest,size=self._audit_file(source,row["width"],row["height"])
        if digest!=artifact["sha256"] or size!=artifact["bytes"]:
            raise RuntimeError("Worker output differs from independently accepted receipt")
        destination=self._path(row["project_id"],row["cache_key"])
        if destination.is_symlink():
            raise RuntimeError("Cache destination is symlinked")
        fd,temp=tempfile.mkstemp(prefix=".preview-",dir=destination.parent)
        try:
            with os.fdopen(fd,"wb") as dest, source.open("rb") as src:
                shutil.copyfileobj(src,dest,1024*1024)
                dest.flush()
                os.fsync(dest.fileno())
            staged=Path(temp)
            if self._audit_file(staged,row["width"],row["height"])!=(digest,size):
                raise RuntimeError("Staged preview cache copy changed")
            try:
                os.link(temp,destination)
            except FileExistsError:
                if self._audit_file(destination,row["width"],row["height"])!=(
                        digest,size):
                    raise RuntimeError("Existing cache destination conflicts with verified PNG")
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                updated=db.execute("""UPDATE slate_preview_cache
                    SET state='READY',image_sha256=?,size_bytes=?,
                    last_use_ns=?,updated_ns=?
                    WHERE project_id=? AND cache_key=?
                      AND state='PENDING' AND job_id=?""",
                    (digest,size,time.time_ns(),time.time_ns(),
                     row["project_id"],row["cache_key"],job_id))
                if updated.rowcount!=1:
                    raise RuntimeError("Preview job was superseded before publication")
        finally:
            Path(temp).unlink(missing_ok=True)
        self.evict()
        return self.lookup(row["project_id"],row["cache_key"])

    def fail(self,job_id,*,state="FAILED"):
        if state not in ("FAILED","INTERRUPTED"):
            raise ValueError("Cannot set completed preview state through fail")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE slate_preview_cache
                SET state=?,updated_ns=? WHERE job_id=? AND state='PENDING'""",
                (state,time.time_ns(),job_id))

    def recover(self,supervisor:BlenderWorkerSupervisor):
        """No replay. Publish only independently verified SUCCEEDED workers."""
        with self._db() as db:
            pending=[r[0] for r in db.execute(
                "SELECT job_id FROM slate_preview_cache WHERE state='PENDING'")]
        results=[]
        for job_id in pending:
            try:
                result=self.accept_verified(supervisor,job_id)
                results.append({"job_id":job_id,"state":"READY",
                                "cache_key":result["cache_key"]})
            except (KeyError,RuntimeError,ValueError,OSError):
                self.fail(job_id,state="INTERRUPTED")
                results.append({"job_id":job_id,"state":"INTERRUPTED",
                                "output_accepted":False})
        return results

    def evict(self):
        """LRU eviction ONLY for bounded derivative PNGs, never FilmIndex."""
        removed=[]
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            ready=db.execute("""SELECT project_id,cache_key,size_bytes
                FROM slate_preview_cache WHERE state='READY'
                ORDER BY last_use_ns DESC""").fetchall()
            total=sum(r["size_bytes"] for r in ready)
            while ready and (
                    total>self.max_disk_bytes or len(ready)>self.max_ready):
                row=ready.pop()
                path=self._path(row["project_id"],row["cache_key"])
                # Never follow symlinks or remove anything outside cache root.
                if path.is_symlink():
                    raise RuntimeError("Cache eviction refused symlinked derivative")
                if path.is_file():
                    path.unlink()
                db.execute("""UPDATE slate_preview_cache SET state='EVICTED',
                    updated_ns=? WHERE project_id=? AND cache_key=? AND state='READY'""",
                    (time.time_ns(),row["project_id"],row["cache_key"]))
                total-=row["size_bytes"]
                removed.append(row["cache_key"])
        return removed
