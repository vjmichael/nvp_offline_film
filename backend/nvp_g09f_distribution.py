"""G09-F persistent film publication, portable import and owned library.

Both collections are outside the installed app tree, next to the creator's
original project store. Cancelled/interrupted package creation never
publishes an incomplete file. A new app process may resume packaging after
checking the completed G09-E manifest and exact source identity again.
Import verifies every archive entry and SHA before writing an atomic
library record. No arbitrary path, unzip, network fetch or executable load.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import shutil
import threading
import uuid

from backend.nvp_g09f_package import (
    FORMAT,MAX_PACKAGE_BYTES,MAX_CONTENT_BYTES,_canonical,_hash_package,
    _verified_manifest,build_portable,import_portable,verify_portable)
from backend.nvp_g09e_delivery import _folder as export_folder
from backend.nvp_g09f_reel_playback import VerifiedReelReader

HEX=re.compile(r"[a-f0-9]{32}\Z")
SHA=re.compile(r"[a-f0-9]{64}\Z")
ACTIVE=frozenset(("queued","packing"))
RECOVERABLE=frozenset(("interrupted","failed","cancelled"))
READ_LIMIT=100
MIN_DISK=256*1024**2

def _now():return datetime.now(timezone.utc).isoformat()

def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS g09f_packages(
        project_id TEXT NOT NULL,job_id TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL,source_sha256 TEXT NOT NULL,
        status TEXT NOT NULL,owner_id TEXT NOT NULL,
        package_sha256 TEXT,package_bytes INTEGER,
        packed_reels INTEGER NOT NULL DEFAULT 0,
        issue TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id,job_id),
        CHECK(status IN ('queued','packing','completed',
                         'interrupted','cancelled','failed')))""")
    db.execute("""CREATE TABLE IF NOT EXISTS g09f_library(
        project_id TEXT NOT NULL,film_id TEXT NOT NULL,
        package_sha256 TEXT NOT NULL,manifest_sha256 TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,reel_count INTEGER NOT NULL,
        duration_frames INTEGER NOT NULL,
        imported_at TEXT NOT NULL,
        PRIMARY KEY(project_id,film_id))""")
    db.execute("""CREATE INDEX IF NOT EXISTS g09f_project_library
        ON g09f_library(project_id,imported_at)""")

def _root(studio,create=True):
    root=Path(studio.db_path).resolve(strict=True).parent/"nvp_film_library"
    if root.is_symlink():
        raise RuntimeError("The owned film library was replaced by an unsafe link")
    if create:root.mkdir(mode=0o700,exist_ok=True)
    if not root.is_dir() or root.resolve()!=root:
        raise RuntimeError("The film library has an invalid root")
    return root

class G09FDistribution:
    def __init__(self,long_delivery,studio,*,access,protected_movie):
        self.long=long_delivery
        self.studio=studio
        self.access=access
        self.protected_movie=protected_movie
        self.owner=uuid.uuid4().hex
        self.guard=threading.RLock()
        self.threads={}
        self.cancelled=set()
        self.reader=VerifiedReelReader()
        self._reconciled=False

    @contextmanager
    def _db(self):
        with self.studio._connection() as db:
            _schema(db)
            yield db

    def _auth(self,pid,token):
        if type(pid) is not str or not HEX.fullmatch(pid):
            raise ValueError("Select your original film project")
        if not self.access().permitted(pid,token,renew=False):
            raise PermissionError("Unlock your film to manage distributed copies")
        if self.protected_movie().exists(pid):
            raise PermissionError(
                "Protected film distribution needs encrypted portable media "
                "and source-key custody. This working-film library remains "
                "disabled for protected projects.")

    def _row(self,pid,job):
        with self._db() as db:
            result=db.execute("""SELECT * FROM g09f_packages
                WHERE project_id=? AND job_id=?""",(pid,job)).fetchone()
            if result is None:raise KeyError("No film package job exists")
            return dict(result)

    def reconcile(self):
        with self.guard:
            if self._reconciled:return
            with self._db() as db:
                # Host-owned packager is an in-process thread. Another
                # instance cannot own a previous process's in-memory work.
                db.execute("""UPDATE g09f_packages SET
                    status='interrupted',issue=?,updated_at=?
                    WHERE owner_id!=? AND status IN ('queued','packing')""",
                    ("Portable film packaging stopped before publication.",
                     _now(),self.owner))
            self._reconciled=True

    def _completed_source(self,pid,job,token):
        self._auth(pid,token)
        folder,manifest=self.long._completed(pid,job,token)
        src_record=self.long._job(pid,job)
        manifest_file=folder/"manifest.json"
        raw=manifest_file.read_bytes()
        digest=sha256(raw).hexdigest()
        if digest!=src_record["manifest_sha256"]:
            raise RuntimeError("The completed film manifest changed before packaging")
        _verified_manifest(manifest)
        return folder,manifest,digest

    def _public(self,row):
        return {"format":FORMAT,"job_id":row["job_id"],
            "status":row["status"],"packed_reels":row["packed_reels"],
            "package_sha256":row["package_sha256"] if (
                row["status"]=="completed") else None,
            "package_bytes":row["package_bytes"] if (
                row["status"]=="completed") else None,
            "issue":row["issue"],
            "resumable":row["status"] in RECOVERABLE,
            "source_preserved":True,
            "filmmaker_identity_cryptographically_signed":False}

    def status(self,pid,job,token):
        self._auth(pid,token)
        self.reconcile()
        return self._public(self._row(pid,job))

    def start(self,pid,job,token):
        folder,manifest,digest=self._completed_source(pid,job,token)
        self.reconcile()
        if shutil.disk_usage(folder).free < (
                sum(ref["bytes"] for ref in manifest["reels"])+MIN_DISK):
            raise RuntimeError(
                "Not enough local disk space for a portable copy. "
                "Your checked film reels are still safe.")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT * FROM g09f_packages
                WHERE project_id=? AND job_id=?""",(pid,job)).fetchone()
            if row is not None:
                if row["status"]=="completed":
                    raise RuntimeError("A portable version of this film is already ready")
                if row["status"] in ACTIVE:
                    raise RuntimeError("This film is already being packaged")
                if row["manifest_sha256"]!=digest or (
                    row["source_sha256"]!=manifest["source_sha256"]):
                    raise RuntimeError("The film changed after a prior distribution attempt")
                db.execute("""UPDATE g09f_packages SET
                    status='queued',owner_id=?,packed_reels=0,
                    issue=NULL,updated_at=?
                    WHERE project_id=? AND job_id=?""",
                    (self.owner,_now(),pid,job))
            else:
                db.execute("""INSERT INTO g09f_packages(
                    project_id,job_id,manifest_sha256,source_sha256,status,
                    owner_id,created_at,updated_at)
                    VALUES(?,?,?,?,'queued',?,?,?)""",
                    (pid,job,digest,manifest["source_sha256"],
                     self.owner,_now(),_now()))
        with self.guard:self.cancelled.discard((pid,job))
        self._start(pid,job,token)
        return self.status(pid,job,token)

    def _start(self,pid,job,token):
        with self.guard:
            if (pid,job) in self.threads:
                raise RuntimeError("A native film publication already owns this reel set")
            t=threading.Thread(
                target=self._pack,args=(pid,job,token),
                name="nvp-g09f-film-"+job[:8],daemon=True)
            self.threads[(pid,job)]=t
            t.start()

    def _change(self,pid,job,status,*,issue=None,sha=None,size=None,progress=None):
        with self._db() as db:
            db.execute("""UPDATE g09f_packages SET status=?,issue=?,
                package_sha256=COALESCE(?,package_sha256),
                package_bytes=COALESCE(?,package_bytes),
                packed_reels=COALESCE(?,packed_reels),
                updated_at=? WHERE project_id=? AND job_id=? AND owner_id=?""",
                (status,issue,sha,size,progress,_now(),pid,job,self.owner))

    def _pack(self,pid,job,token):
        try:
            folder,manifest,digest=self._completed_source(pid,job,token)
            self._change(pid,job,"packing")
            dest=folder/"film.nvpfilm"
            record=self._row(pid,job)
            if dest.is_symlink():
                raise RuntimeError("A prior portable film destination is an unsafe link")
            if dest.exists():
                # Crash between atomic publication and SQLite commit:
                # independently validate exact already-published film.
                proof=verify_portable(dest,validate_reels=True)
                if (proof["metadata"]["film_manifest_sha256"]!=digest or
                    proof["manifest"]["source_sha256"]!=record["source_sha256"]):
                    raise RuntimeError("A prior portable film does not belong to this exact edit")
                receipt={"package_sha256":proof["package_sha256"],
                         "package_bytes":proof["package_bytes"]}
            else:
                def check():
                    with self.guard:
                        stop=(pid,job) in self.cancelled
                    return stop or not self.access().permitted(
                        pid,token,renew=False)
                def progress(n,total):
                    if n==total or n%4==0:
                        self._change(pid,job,"packing",progress=n)
                receipt=build_portable(
                    folder,manifest,dest,cancel=check,progress=progress)
            self._auth(pid,token)
            self._change(pid,job,"completed",
                         sha=receipt["package_sha256"],
                         size=receipt["package_bytes"],
                         progress=len(manifest["reels"]))
        except InterruptedError:
            self._change(pid,job,"cancelled",
                issue="Packaging stopped; the completed reel originals remain intact.")
        except PermissionError:
            self._change(pid,job,"interrupted",
                issue="The film was locked; review the movie and retry packaging.")
        except Exception:
            self._change(pid,job,"failed",
                issue="The completed film package could not be independently checked.")
        finally:
            with self.guard:
                self.threads.pop((pid,job),None)
                self.cancelled.discard((pid,job))

    def cancel(self,pid,job,token):
        self._auth(pid,token)
        rec=self._row(pid,job)
        if rec["status"] not in ACTIVE:
            raise RuntimeError("The film is not currently being packaged")
        with self.guard:self.cancelled.add((pid,job))
        return self.status(pid,job,token)

    def file(self,pid,job,token):
        rec=self.status(pid,job,token)
        if rec["status"]!="completed":
            raise RuntimeError("Download only an independently checked completed package")
        folder,_,digest=self._completed_source(pid,job,token)
        if digest!=self._row(pid,job)["manifest_sha256"]:
            raise RuntimeError("Original finished film changed since publication")
        file=folder/"film.nvpfilm"
        if file.is_symlink() or not file.is_file() or (
                file.stat().st_size!=rec["package_bytes"] or
                _hash_package(file)!=rec["package_sha256"]):
            raise RuntimeError("Published film package no longer matches its original")
        return file

    def upload_target(self,pid,token):
        self._auth(pid,token)
        root=_root(self.studio)
        folder=root/pid
        if folder.is_symlink():raise RuntimeError("Film library path is unsafe")
        folder.mkdir(mode=0o700,exist_ok=True)
        if folder.resolve()!=folder:raise RuntimeError("Film library root was changed")
        name=".upload-"+uuid.uuid4().hex+".partial"
        return folder/name

    def import_uploaded(self,pid,token,uploaded):
        self._auth(pid,token)
        incoming=Path(uploaded)
        folder=incoming.parent
        expected=_root(self.studio)/pid
        if (folder!=expected or not incoming.name.startswith(".upload-") or
            incoming.suffix!=".partial" or incoming.is_symlink() or
            not incoming.is_file()):
            raise PermissionError("Only director-selected local film files may be imported")
        film=uuid.uuid4().hex
        dest=folder/film
        proof=import_portable(incoming,dest)
        manifest=json.loads((dest/"manifest.json").read_text(encoding="utf8"))
        # No path supplied by archive metadata enters SQLite or native routes.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO g09f_library(
                project_id,film_id,package_sha256,manifest_sha256,
                source_sha256,reel_count,duration_frames,imported_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (pid,film,proof["package_sha256"],
                 proof["manifest_sha256"],proof["source_sha256"],
                 proof["reels_imported"],manifest["total_frames"],_now()))
        return {"format":FORMAT,"film_id":film,
            "reel_count":proof["reels_imported"],
            "duration_seconds":manifest["total_frames"]/24,
            "package_sha256":proof["package_sha256"],
            "verified":True,"original_film_unchanged":True,
            "distribution_origin_signature_verified":False}

    def library(self,pid,token):
        self._auth(pid,token)
        with self._db() as db:
            items=[dict(r) for r in db.execute("""SELECT film_id,
                package_sha256,manifest_sha256,source_sha256,reel_count,
                duration_frames,imported_at FROM g09f_library
                WHERE project_id=? ORDER BY imported_at DESC,film_id DESC
                LIMIT ?""",(pid,READ_LIMIT))]
        return [{"id":r["film_id"],
                "duration_seconds":r["duration_frames"]/24,
                "reels":r["reel_count"],"imported_at":r["imported_at"],
                "package_sha256":r["package_sha256"],
                "source_sha256":r["source_sha256"],
                "verified_at_import":True,
                "origin_signature_verified":False}
                for r in items]

    def library_source(self,pid,film_id,token):
        self._auth(pid,token)
        if type(film_id) is not str or not HEX.fullmatch(film_id):
            raise ValueError("Select a previously imported film")
        with self._db() as db:
            row=db.execute("""SELECT * FROM g09f_library WHERE
                project_id=? AND film_id=?""",(pid,film_id)).fetchone()
        if row is None:raise KeyError("This film is not in your original movie library")
        folder=_root(self.studio)/pid/film_id
        if folder.is_symlink() or not folder.is_dir() or folder.resolve()!=folder:
            raise RuntimeError("Your imported film collection path is unsafe")
        file=folder/"manifest.json"
        if file.is_symlink() or not file.is_file() or file.stat().st_size>2*1024**2:
            raise RuntimeError("The source of the imported film is unavailable")
        raw=file.read_bytes()
        if sha256(raw).hexdigest()!=row["manifest_sha256"]:
            raise RuntimeError("The library film manifest was changed after import")
        data=json.loads(raw)
        refs=_verified_manifest(data)
        if (row["reel_count"]!=len(refs) or
            row["source_sha256"]!=data["source_sha256"]):
            raise RuntimeError("An imported film's original source identity was changed")
        return folder,data

    def completed_source(self,pid,job,token):
        folder,manifest,digest=self._completed_source(pid,job,token)
        return folder,manifest
