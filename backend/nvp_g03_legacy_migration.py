"""G03-M1: no-destruction migration staging for existing NVP films.

A live legacy Studio film has more than its screenplay: SQLite project rows,
FilmIndex content-addressed blobs, scene/take metadata, and some worker/caches
whose project identity may not be safely known. This migrator inventories
known project rows and verified FilmIndex blobs into a *separate* DPAPI/AES-GCM
candidate, NEVER switches the live project or deletes/rewrites originals.

A candidate is an encrypted immutable archive, NOT a completed native film
migration. Unknown global tables, untracked source roots and worker journals
block cutover; a future explicit reviewed converter must account for them.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from pathlib import Path
import re
import secrets
import sqlite3

from backend.nvp_g03_live_store import LiveFilmStore, LiveFilmError
from backend.nvp_g03_windows_vault import _no_link
from backend.nvp_studio import Studio

ID=re.compile(r"[a-f0-9]{32}\Z")
SHA=re.compile(r"[a-f0-9]{64}\Z")
MAX_ROWS=250_000
MAX_BLOB_BYTES=256*1024*1024
MAX_TOTAL=1024*1024*1024
MAX_TABLES=512


class MigrationRefused(RuntimeError):
    pass


def _encode_sql(value):
    if isinstance(value,bytes):
        return {"bytes_b64":base64.b64encode(value).decode("ascii")}
    if value is None or isinstance(value,(str,int,float)):
        return value
    raise MigrationRefused("Unsupported legacy SQL field type")


def _sha_file(file):
    h=hashlib.sha256()
    with file.open("rb") as stream:
        while chunk:=stream.read(512*1024):
            h.update(chunk)
    return h.hexdigest()


def _component_check(path,root):
    """Reject junction/reparse/symlink through every path component."""
    if not path.is_relative_to(root):
        raise MigrationRefused("Legacy asset escapes owned source root")
    check=root
    _no_link(check)
    for component in path.relative_to(root).parts:
        check=check/component
        _no_link(check)


class LegacyFilmMigration:
    def __init__(self,studio,*,candidate_root=None,review_check=None):
        if not isinstance(studio,Studio):
            raise TypeError("Original trusted NVP Studio required")
        self.studio=studio
        self.root=studio.db_path.parent.absolute()
        self.candidates=Path(candidate_root or
            (self.root/"nvp_g03_migration_candidates")).absolute()
        if self.candidates==self.root or not self.candidates.is_relative_to(self.root):
            raise MigrationRefused("Stage must remain in the same owner-controlled film home")
        if review_check is not None and not callable(review_check):
            raise TypeError("Trusted creator review callback required")
        self.review_check=review_check

    def _snapshot(self,pid):
        if type(pid) is not str or not ID.fullmatch(pid):
            raise MigrationRefused("Invalid legacy film ID")
        source=sqlite3.connect(
            "file:"+str(self.studio.db_path.resolve())+"?mode=ro",uri=True,timeout=15)
        memory=sqlite3.connect(":memory:")
        memory.row_factory=sqlite3.Row
        try:
            source.backup(memory, pages=100)
            tables=[x[0] for x in memory.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='table' AND name NOT LIKE 'sqlite_%'
                   ORDER BY name""").fetchall()]
            if not tables or len(tables)>MAX_TABLES or "projects" not in tables:
                raise MigrationRefused("Unexpected Studio SQLite schema")
            project=memory.execute(
                "SELECT * FROM projects WHERE id=?",(pid,)).fetchone()
            if project is None:
                raise MigrationRefused("Legacy movie does not exist")
            index={}
            unknown=[]
            count=0
            for table in tables:
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",table):
                    raise MigrationRefused("Unknown SQL table identity")
                columns=[r[1] for r in memory.execute(
                    f'PRAGMA table_info("{table}")').fetchall()]
                key="id" if table=="projects" else "project_id" if "project_id" in columns else None
                if key is None:
                    nonempty=memory.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone()
                    if nonempty is not None:
                        unknown.append(table)
                    continue
                rows=memory.execute(
                    f'SELECT * FROM "{table}" WHERE "{key}"=?',(pid,)).fetchall()
                stored=[]
                for row in rows:
                    count+=1
                    if count>MAX_ROWS:
                        raise MigrationRefused("Legacy film SQL row inventory exceeds cap")
                    stored.append({column:_encode_sql(row[column])
                                   for column in columns})
                if stored:
                    # JSON sorting provides stable contents across DB reopens;
                    # no row semantics are inferred from SQLite insertion order.
                    canonical=lambda row:json.dumps(row,sort_keys=True,
                        separators=(",",":"),allow_nan=False)
                    index[table]=sorted(stored,key=canonical)
            # Project rows alone do not reconstruct a usable original film.
            # Record the actual reviewed SQLite DDL so an independent process
            # can rebuild relational constraints, indexes and revision history
            # without touching source. sqlite_autoindex is implicit in CREATE
            # TABLE; never synthesize a replacement constraint.
            schema=[]
            for kind,name,owner,ddl in memory.execute(
                """SELECT type,name,tbl_name,sql FROM sqlite_master
                   WHERE name NOT LIKE 'sqlite_%'
                     AND type IN ('table','index','view','trigger')
                   ORDER BY type,name"""):
                if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",name) or
                        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",owner) or
                        not isinstance(ddl,str) or len(ddl)>1024*1024):
                    raise MigrationRefused("Legacy schema has unreviewed DDL")
                if kind=="table" and not re.match(
                        r"^CREATE\\s+TABLE\\b",ddl,re.IGNORECASE):
                    raise MigrationRefused(
                        "Legacy virtual/extension table needs independent converter")
                schema.append({"type":kind,"name":name,"table":owner,"sql":ddl})
            if len(schema)>MAX_TABLES*4:
                raise MigrationRefused("Legacy relational schema exceeds bound")
            data={"format":"nvp.g03.legacy.sql_snapshot.v2",
                  "project_id":pid,"tables":index,"schema":schema,
                  "user_version":memory.execute("PRAGMA user_version").fetchone()[0],
                  "application_id":memory.execute("PRAGMA application_id").fetchone()[0]}
            encoded=json.dumps(data,sort_keys=True,
                separators=(",",":"),ensure_ascii=True).encode("utf8")
            if len(encoded)>MAX_TOTAL:
                raise MigrationRefused("Legacy SQL snapshot exceeds migration limit")
            return dict(project),encoded,unknown
        finally:
            memory.close()
            source.close()

    def _blob_inventory(self,pid):
        """Index *all* registered FilmIndex source blobs; do not infer refs."""
        blob_root=self.root/(self.studio.db_path.stem+"_film_blobs")
        with self.studio._connection() as db:
            exists=db.execute("""SELECT 1 FROM sqlite_master WHERE
                type='table' AND name='film_blob_refs'""").fetchone()
            records=(db.execute("""SELECT sha256,size_bytes,media_type
                FROM film_blob_refs WHERE project_id=? ORDER BY sha256""",
                (pid,)).fetchall() if exists else [])
        result=[]
        total=0
        for row in records:
            sha,size,mime=row
            if (type(sha) is not str or not SHA.fullmatch(sha) or
                    type(size) is not int or not 0<=size<=MAX_BLOB_BYTES):
                raise MigrationRefused("Bad FilmIndex source asset metadata")
            source=blob_root/pid/sha[:2]/sha
            if not source.is_file():
                raise MigrationRefused("Original FilmIndex blob missing")
            _component_check(source,self.root)
            if source.stat().st_size!=size or _sha_file(source)!=sha:
                raise MigrationRefused("Original FilmIndex blob changed/corrupt")
            total+=size
            if total>MAX_TOTAL:
                raise MigrationRefused("Legacy FilmIndex source exceeds migration budget")
            result.append({"sha256":sha,"size_bytes":size,"media_type":mime,
                           "path":source})
        # The original FilmIndex can retain unindexed/orphan source payloads.
        # Never represent a complete migration without an independent audit
        # of those bytes and their provenance.
        folder=blob_root/pid
        if folder.exists():
            _component_check(folder,self.root)
            known={row["path"] for row in result}
            extra=[]
            count=0
            for candidate in folder.rglob("*"):
                count+=1
                if count>MAX_ROWS:
                    raise MigrationRefused("FilmIndex filesystem exceeds inventory cap")
                _component_check(candidate,self.root)
                if candidate.is_file() and candidate not in known:
                    extra.append(candidate.relative_to(folder).as_posix())
            if extra:
                raise MigrationRefused(
                    "Unindexed FilmIndex bytes require independent recovery review")
        return result

    def _sidecar_inventory(self,pid):
        """Account for identified project-scoped files outside FilmIndex.

        Never guess that a global native worker journal belongs to this film.
        Report those separately for independent host/source review.
        """
        exclude=(self.candidates,
                 self.root/"nvp_g03_encrypted_live",
                 self.root/(self.studio.db_path.stem+"_film_blobs"))
        located=[]
        ambiguous=[]
        unattributed=[]
        seen=0
        total=0
        # The Studio database is shared, not a project sidecar. Its WAL/SHM
        # are captured by the SQL backup, not silently assigned to one movie.
        database=self.studio.db_path.relative_to(self.root).as_posix()
        shared_sql={database,database+"-wal",database+"-shm"}
        for directory,dirs,files in os.walk(self.root,followlinks=False):
            here=Path(directory)
            safe=[]
            for name in dirs:
                candidate=here/name
                if any(candidate==root or candidate.is_relative_to(root)
                       for root in exclude):
                    continue
                safe.append(name)
            dirs[:]=safe
            for name in files:
                seen+=1
                if seen>MAX_ROWS:
                    raise MigrationRefused("Unclassified film home has too many files")
                source=here/name
                relative=source.relative_to(self.root).as_posix()
                if (name in {"worker_jobs.sqlite3","worker_journal.sqlite3"} or
                        (name.endswith(".sqlite3") and
                         "worker" in relative.lower())) and (
                        pid not in source.parts and pid not in name):
                    ambiguous.append(relative)
                if pid not in source.parts and pid not in source.name:
                    if relative not in shared_sql:
                        _component_check(source,self.root)
                        info=source.lstat()
                        if (not stat.S_ISREG(info.st_mode) or
                                info.st_size>MAX_BLOB_BYTES):
                            raise MigrationRefused(
                                "Unattributed legacy file requires manual recovery review")
                        total+=info.st_size
                        if total>MAX_TOTAL:
                            raise MigrationRefused("Unattributed legacy data exceeds inventory cap")
                        unattributed.append({"relative":relative,
                            "sha256":_sha_file(source),"size_bytes":info.st_size})
                    continue
                _component_check(source,self.root)
                info=source.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_size>MAX_BLOB_BYTES:
                    raise MigrationRefused("Project sidecar is not a bounded regular file")
                digest=_sha_file(source)
                total+=info.st_size
                if total>MAX_TOTAL:
                    raise MigrationRefused("Project sidecar files exceed migration budget")
                located.append({"relative":relative,"sha256":digest,
                                "size_bytes":info.st_size,"path":source})
        return (sorted(located,key=lambda x:x["relative"]),
                sorted(set(ambiguous)),
                sorted(unattributed,key=lambda x:x["relative"]))


    def _journal_provenance(self,pid,ambiguous):
        """Read-only forensic classification; never acquire/write worker journal.

        A global worker record may mention a movie ID but still be owned by an
        active process. Evidence is deliberately *not* interpreted as permission
        to migrate, pause, relaunch, scrub or delete that worker.
        """
        report=[]
        for relative in ambiguous:
            path=self.root/relative
            _component_check(path,self.root)
            size=path.stat().st_size
            if size>64*1024*1024:
                raise MigrationRefused("Global worker journal exceeds forensic cap")
            digest=_sha_file(path)
            # SQLite may keep freshly committed worker state in its separate
            # WAL. Hash and recheck it independently; inspecting only the
            # database file is not an exact worker-journal inventory.
            sidecar_paths=[Path(str(path)+ext) for ext in ("-wal","-shm")]
            sidecars=[]
            for extra in sidecar_paths:
                if not extra.exists():
                    continue
                _component_check(extra,self.root)
                if not extra.is_file() or extra.stat().st_size>64*1024*1024:
                    raise MigrationRefused("Worker WAL/SHM is invalid or oversized")
                sidecars.append({"name":extra.name,
                                 "sha256":_sha_file(extra),
                                 "size_bytes":extra.stat().st_size})
            info={"relative":relative,"sha256":digest,
                  "size_bytes":size,"format":"unknown",
                  "wal_and_shm":sidecars,
                  "matching_project_rows":0,
                  "unclassified_tables":[],
                  "live_worker_custody_proved":False,
                  "safe_to_cutover":False}
            with path.open("rb") as stream:
                signature=stream.read(16)
            if signature==b"SQLite format 3\x00":
                conn=sqlite3.connect(
                    "file:"+str(path.resolve())+"?mode=ro",uri=True,timeout=5)
                try:
                    conn.row_factory=sqlite3.Row
                    checked=conn.execute("PRAGMA integrity_check").fetchone()
                    if checked is None or checked[0]!="ok":
                        raise MigrationRefused("Global worker journal SQLite corrupt")
                    tables=[r[0] for r in conn.execute(
                        """SELECT name FROM sqlite_master WHERE type='table'
                           AND name NOT LIKE 'sqlite_%' ORDER BY name""")]
                    if len(tables)>MAX_TABLES:
                        raise MigrationRefused("Too many native worker journal tables")
                    for table in tables:
                        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",table):
                            raise MigrationRefused("Unknown worker SQLite table identity")
                        columns=[r[1] for r in conn.execute(
                            f'PRAGMA table_info("{table}")')]
                        if "project_id" in columns:
                            count=conn.execute(
                                f'SELECT COUNT(*) FROM "{table}" WHERE project_id=?',
                                (pid,)).fetchone()[0]
                            info["matching_project_rows"]+=count
                            if count>MAX_ROWS:
                                raise MigrationRefused("Excess worker custody records")
                        elif conn.execute(
                                f'SELECT 1 FROM "{table}" LIMIT 1').fetchone():
                            info["unclassified_tables"].append(table)
                    info["format"]="sqlite"
                    info["tables"]=len(tables)
                finally:
                    conn.close()
            else:
                info["format"]="opaque_unclassified"
            # Recheck after forensic read; concurrent writer invalidates any
            # inventory hash, never implies safe process custody.
            if _sha_file(path)!=digest:
                raise MigrationRefused("Global worker journal changed during review")
            for item in sidecars:
                replay=path.parent/item["name"]
                if (not replay.is_file() or
                        replay.stat().st_size!=item["size_bytes"] or
                        _sha_file(replay)!=item["sha256"]):
                    raise MigrationRefused("Worker WAL/SHM changed during inventory")
            for extra in sidecar_paths:
                if extra.exists() and extra.name not in {
                        entry["name"] for entry in sidecars}:
                    raise MigrationRefused("New worker WAL/SHM appeared during review")
            report.append(info)
        return report


    def inspect(self,pid):
        metadata,raw,unknown=self._snapshot(pid)
        blobs=self._blob_inventory(pid)
        sidecars,ambiguous,unattributed=self._sidecar_inventory(pid)
        journals=self._journal_provenance(pid,ambiguous)
        evidence={"format":"nvp.g03.migration_inventory.v1",
                  "project_id":pid,
                  "legacy_sql_sha256":hashlib.sha256(raw).hexdigest(),
                  "legacy_sql_bytes":len(raw),
                  "filmindex_blobs":[
                      {"sha256":b["sha256"],"size_bytes":b["size_bytes"],
                       "media_type":b["media_type"]}
                      for b in blobs],
                  "unknown_nonproject_tables":unknown,
                  "unclassified_worker_journals":ambiguous,
                  "unattributed_original_files":unattributed,
                  "global_worker_journal_provenance":journals,
                  "project_sidecars":[
                      {"relative":entry["relative"],"sha256":entry["sha256"],
                       "size_bytes":entry["size_bytes"]} for entry in sidecars],
                  "full_film_cutover_authorized":False,
                  "original_film_modified":False,
                  "active_legacy_workers_migrated":False}
        seal=json.dumps(evidence,sort_keys=True,separators=(",",":")).encode()
        evidence["inventory_sha256"]=hashlib.sha256(seal).hexdigest()
        return evidence

    def stage_encrypted_candidate(self,pid,passphrase,reviewed_inventory_sha):
        """Reviewed copy-only seal; no switching/erasing original movies."""
        if self.review_check is None:
            raise MigrationRefused("No real director review authority was supplied")
        first=self.inspect(pid)
        if (reviewed_inventory_sha != first["inventory_sha256"] or
                not self.review_check(pid,reviewed_inventory_sha)):
            raise MigrationRefused("Director has not approved this exact inventory")
        # Unknown global rows do not prevent *copying* known bytes into an
        # encrypted candidate, but the candidate is never a complete cutover.
        meta,raw,unknown=self._snapshot(pid)
        blobs=self._blob_inventory(pid)
        sidecars,ambiguous,unattributed=self._sidecar_inventory(pid)
        if hashlib.sha256(raw).hexdigest()!=first["legacy_sql_sha256"]:
            raise MigrationRefused("Original film changed after creator review")
        self.candidates.mkdir(parents=True,exist_ok=True)
        _no_link(self.candidates)
        store=LiveFilmStore(self.candidates)
        if store.exists(pid):
            raise MigrationRefused("A protected migration candidate already exists")
        # Create separate encrypted snapshot with same project ID and
        # authoritative screenplay. The original Studio DB is untouched.
        store.create(pid,meta["title"],meta["idea"],meta["screenplay"],passphrase)
        token="g03-staging-"+secrets.token_urlsafe(32)
        store.authorize(pid,passphrase,token)
        try:
            summary=store.put_original(pid,token,
                "migration/legacy-project-tables.json",raw,"application/json")
            if summary["sha256"]!=first["legacy_sql_sha256"]:
                raise MigrationRefused("Sealed SQLite snapshot disagrees with source")
            for blob in blobs:
                data=blob["path"].read_bytes()
                if hashlib.sha256(data).hexdigest()!=blob["sha256"]:
                    raise MigrationRefused("Original source changed during sealing")
                saved=store.put_original(pid,token,
                    "migration/filmindex/"+blob["sha256"],data,
                    blob["media_type"])
                if saved["sha256"]!=blob["sha256"]:
                    raise MigrationRefused("Stored encrypted FilmIndex source mismatch")
            for sidecar in sidecars:
                raw_sidecar=sidecar["path"].read_bytes()
                if hashlib.sha256(raw_sidecar).hexdigest()!=sidecar["sha256"]:
                    raise MigrationRefused("Original sidecar changed during sealing")
                stored=store.put_original(pid,token,
                    "migration/sidecars/"+sidecar["relative"],raw_sidecar,
                    "application/octet-stream")
                if stored["sha256"]!=sidecar["sha256"]:
                    raise MigrationRefused("Staged sidecar differs from original")
            fresh=self.inspect(pid)
            if fresh["inventory_sha256"]!=first["inventory_sha256"]:
                raise MigrationRefused("Original source changed during migration staging")
            if store.get_original(pid,token,
                "migration/legacy-project-tables.json")!=raw:
                raise MigrationRefused("Staged SQL failed independent decrypt/reopen")
            for blob in blobs:
                if hashlib.sha256(store.get_original(pid,token,
                    "migration/filmindex/"+blob["sha256"])).hexdigest()!=blob["sha256"]:
                    raise MigrationRefused("Staged FilmIndex blob failed verification")
            for sidecar in sidecars:
                restored=store.get_original(pid,token,
                    "migration/sidecars/"+sidecar["relative"])
                if hashlib.sha256(restored).hexdigest()!=sidecar["sha256"]:
                    raise MigrationRefused("Candidate sidecar reopened with wrong bytes")
            return {"status":"ENCRYPTED_CANDIDATE_VERIFIED",
                    "project_id":pid,"inventory_sha256":first["inventory_sha256"],
                    "copied_filmindex_blobs":len(blobs),
                    "copied_project_sidecars":len(sidecars),
                    "unclassified_worker_journals":ambiguous,
                    "unattributed_original_files":[x["relative"] for x in unattributed],
                    "unknown_global_tables":unknown,
                    "legacy_film_untouched":True,"active_project_switched":False,
                    "complete_confidentiality":False}
        finally:
            store.revoke(pid)
