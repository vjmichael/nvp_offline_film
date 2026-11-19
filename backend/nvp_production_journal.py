"""WO4-LF01: authoritative durable, host-approved production job journal.

One native supervisor owns execution; the GUI is merely a client.
First admitted worker kind is deliberately read-only media integrity checking:
it proves independent-process jobs, leases, cancellation and restart, but does
NOT claim to encode cinema pictures or write a DCP yet. FFmpeg is not used.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from itertools import zip_longest
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from uuid import uuid4

from backend.nvp_film_index import FilmIndex
from backend.nvp_wo3_dcp_structure import _linked_entry
from backend.nvp_w1g_encrypted_source import require_efs_stage
from backend.nvp_wo4_pcm_stream import _protected_path,_hash_stream
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
import threading

FORMAT = "nvp.wo4.production_job.v1"
TASK_KIND = "VERIFY_APPROVED_MEDIA_V1"
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,79}\Z")
PROJECT_RE = re.compile(r"[0-9a-f]{32}\Z")
MAX_SEGMENTS = 12000
MAX_MANIFEST_BYTES = 3 * 1024 * 1024
MAX_STATUS_PAGE = 64
STATE_VALUES = frozenset((
    "QUEUED", "RUNNING", "VERIFY_COMPLETE", "REVIEW_REQUIRED", "CANCELLED"
))
SEGMENT_STATES = frozenset(("PENDING", "RUNNING", "VERIFIED", "REVIEW_REQUIRED"))


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _digest(text):
    return sha256(text).hexdigest()


def _safe_source(path):
    if type(path) is not str or not Path(path).is_absolute():
        raise PermissionError("Trusted absolute source media path required")
    file=Path(path)
    _protected_path(file)
    return str(file.resolve(strict=True))


_HELD={}
_LOCK=threading.RLock()


class AnotherSupervisorRunning(RuntimeError):
    pass


class SingletonSupervisor:
    """OS-held owner lease, not a codec launch or OS worker sandbox."""
    def __init__(self,root):
        _protected_path(Path(root),directory=True)
        self.root=Path(root).resolve(strict=True)
        self.path=self.root/"production-supervisor.lock"
        self.fd=None
        self.identity=None

    def __enter__(self):
        import msvcrt
        _protected_path(self.root,directory=True)
        with _LOCK:
            if self.root in _HELD:
                raise AnotherSupervisorRunning("Production journal already held here")
            if _linked_entry(self.path):
                raise PermissionError("Linked production ownership lock")
            fd=os.open(self.path,os.O_CREAT|os.O_RDWR|os.O_BINARY,0o600)
            try:
                st=os.fstat(fd)
                identity=(st.st_dev,st.st_ino)
                if _protected_path(self.path)!=identity:
                    raise PermissionError("Ownership lock changed at open")
                if st.st_size==0:
                    os.write(fd,b"0");os.fsync(fd)
                os.lseek(fd,0,os.SEEK_SET)
                try:
                    msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
                except OSError as exc:
                    raise AnotherSupervisorRunning("Production journal already owned") from exc
                self.fd,self.identity=fd,identity
                _HELD[self.root]=(self,os.getpid(),threading.get_ident())
                return self
            except BaseException:
                os.close(fd)
                raise

    def __exit__(self,*_):
        import msvcrt
        with _LOCK:
            if self.fd is not None:
                try:
                    os.lseek(self.fd,0,os.SEEK_SET)
                    msvcrt.locking(self.fd,msvcrt.LK_UNLCK,1)
                finally:
                    os.close(self.fd)
                    self.fd=None
                    _HELD.pop(self.root,None)


def _require_owner(root):
    with _LOCK:
        held=_HELD.get(root)
        if (held is None or held[0].fd is None or
                held[1:]!=(os.getpid(),threading.get_ident()) or
                _protected_path(held[0].path)!=held[0].identity):
            raise PermissionError("Live exclusive production supervisor lease required")


class ProductionJournal:
    """SQLite WAL + FULL durability, no arbitrary command or worker execution.

    A host must authenticate the creator before submitting a job or cancelling.
    The service API is process-local and does not open an HTTP/IPC listener.
    """

    def __init__(self, state_root):
        root=Path(state_root)
        if (os.name!="nt" or not root.is_absolute() or
                any(_linked_entry(x) for x in (root,*root.parents))):
            raise PermissionError("Local Windows encrypted production state required")
        if not root.exists():
            _protected_path(root.parent,directory=True)
            root.mkdir(mode=0o700,exist_ok=True)
            # A newly created directory must inherit EFS; never retrofit
            # encryption on an existing unrelated state tree.
            _protected_path(root,directory=True)
        self.root=root.resolve(strict=True)
        self.root_identity=_protected_path(self.root,directory=True)
        self.db_path=self.root/"production-journal.sqlite3"
        if not self.db_path.exists() and not _linked_entry(self.db_path):
            try:
                with self.db_path.open("xb"):
                    pass
            except FileExistsError:
                pass
        self.db_identity=_protected_path(self.db_path)
        with self._tx() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS production_jobs(
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    assembly_id TEXT NOT NULL,
                    assembly_revision INTEGER NOT NULL CHECK(assembly_revision>0),
                    assembly_sha256 TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    task_kind TEXT NOT NULL,
                    state TEXT NOT NULL,
                    owner_token TEXT,
                    owner_pid INTEGER,
                    updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1))
                );
                CREATE TABLE IF NOT EXISTS production_segments(
                    job_id TEXT NOT NULL REFERENCES production_jobs(job_id),
                    position INTEGER NOT NULL CHECK(position>=0),
                    start_tick INTEGER NOT NULL,
                    end_tick INTEGER NOT NULL,
                    source_path TEXT NOT NULL,
                    expected_sha256 TEXT NOT NULL,
                    expected_bytes INTEGER NOT NULL CHECK(expected_bytes>0),
                    state TEXT NOT NULL,
                    verified_sha256 TEXT,
                    verified_bytes INTEGER,
                    verified_at TEXT,
                    owner_token TEXT,
                    PRIMARY KEY(job_id,position)
                );
                CREATE TABLE IF NOT EXISTS production_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES production_jobs(job_id),
                    event_kind TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS production_segments_ready
                    ON production_segments(job_id,state,position);
            """)

    def _check_storage(self):
        if (_protected_path(self.root,directory=True)!=self.root_identity or
                _protected_path(self.db_path)!=self.db_identity):
            raise PermissionError("Production journal storage identity changed")
        for suffix in ("-wal","-shm","-journal"):
            sidecar=Path(str(self.db_path)+suffix)
            if sidecar.exists() or _linked_entry(sidecar):
                try:
                    _protected_path(sidecar)
                except FileNotFoundError:
                    if sidecar.exists() or _linked_entry(sidecar):
                        raise

    @contextmanager
    def _tx(self):
        self._check_storage()
        db = sqlite3.connect(str(self.db_path), timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            self._check_storage()
            yield db
            self._check_storage()
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def _read(self):
        """WAL snapshot readers never acquire the production write lease."""
        self._check_storage()
        db=sqlite3.connect(str(self.db_path), timeout=15, isolation_level=None)
        db.row_factory=sqlite3.Row
        try:
            self._check_storage()
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA busy_timeout=15000")
            yield db
        finally:
            db.close()

    def _event(self, db, job_id, kind, detail):
        db.execute("""INSERT INTO production_events
                      (job_id,event_kind,detail,recorded_at) VALUES(?,?,?,?)""",
                   (job_id, kind, detail, _now()))

    def submit(self, index: FilmIndex, project_id, *, assembly_id,
               assembly_revision, assembly_sha256, segments, approve):
        """Host-only creator-approved immutable FilmIndex/source manifest.

        The journal records absolute host-approved file paths but does not
        grant filesystem access. There is no user-supplied executable field.
        """
        if not isinstance(index, FilmIndex) or not callable(approve):
            raise PermissionError("Native FilmIndex and creator approval required")
        if (type(project_id) is not str or not PROJECT_RE.fullmatch(project_id)
                or type(assembly_id) is not str or not ID_RE.fullmatch(assembly_id)
                or type(assembly_revision) is not int or assembly_revision<1
                or type(assembly_sha256) is not str or
                not SHA_RE.fullmatch(assembly_sha256)):
            raise ValueError("Exact film project and assembly revision required")
        current = index.read_revision(project_id, assembly_id, assembly_revision)
        if (current["document_sha256"] != assembly_sha256
                or current["kind"] not in ("edit", "presentation")):
            raise PermissionError("Approved immutable assembly must be a film edit/presentation")
        if type(segments) is not list or not 1<=len(segments)<=MAX_SEGMENTS:
            raise ValueError("Bounded ordered film/media segments required")
        ordered = []
        last_end = None
        for i, segment in enumerate(segments):
            if type(segment) is not dict or set(segment) != {
                    "start_tick","end_tick","source_path",
                    "source_sha256","source_bytes"}:
                raise ValueError("Segment must bind exact time, source path, SHA and bytes")
            start, end = segment["start_tick"], segment["end_tick"]
            if (type(start) is not int or type(end) is not int or
                    not 0<=start<end<=2**63-1 or
                    (last_end is not None and start!=last_end)):
                raise ValueError("Segment Film Time must be contiguous and nonempty")
            digest=segment["source_sha256"]
            size=segment["source_bytes"]
            if (type(digest) is not str or not SHA_RE.fullmatch(digest)
                    or type(size) is not int or size<1 or size>2**63-1):
                raise ValueError("Source SHA-256 and integer bytes required")
            ordered.append({
                "position":i, "start_tick":start, "end_tick":end,
                "source_path":_safe_source(segment["source_path"]),
                "source_sha256":digest, "source_bytes":size
            })
            last_end=end
        manifest={
            "format":FORMAT, "task_kind":TASK_KIND,
            "project_id":project_id,
            "assembly_id":assembly_id, "assembly_revision":assembly_revision,
            "assembly_sha256":assembly_sha256,
            "assembly_dependencies":current["dependencies"],
            "start_tick":ordered[0]["start_tick"],
            "end_tick":ordered[-1]["end_tick"],
            "segments":ordered,
            "production_dcp_accepted":False, "ffmpeg_used":False
        }
        encoded=_canonical(manifest)
        if len(encoded)>MAX_MANIFEST_BYTES:
            raise ValueError("Production job manifest exceeds safe size")
        manifest_sha=_digest(encoded)
        scope={
            "operation":"nvp.supervisor.submit_approved_media_verification.v1",
            "project_id":project_id,"assembly_id":assembly_id,
            "assembly_revision":assembly_revision,
            "assembly_sha256":assembly_sha256,
            "manifest_sha256":manifest_sha,"task_kind":TASK_KIND,
            "segment_count":len(ordered),"first_tick":ordered[0]["start_tick"],
            "end_tick":ordered[-1]["end_tick"]
        }
        if approve(deepcopy(scope)) is not True:
            return {"format":FORMAT,"status":"DENIED","filesystem_mutated":False}
        if (index.read_revision(project_id,assembly_id,assembly_revision)
                ["document_sha256"]!=assembly_sha256):
            raise PermissionError("Assembly changed during production approval")
        for item in ordered:
            if (_safe_source(item["source_path"])!=item["source_path"] or
                    _hash_stream(Path(item["source_path"]))!=(item["source_sha256"],item["source_bytes"])):
                raise PermissionError("Approved source changed during approval")
        job_id=str(uuid4())
        now=_now()
        with self._tx() as db:
            db.execute("""INSERT INTO production_jobs(
                job_id,project_id,assembly_id,assembly_revision,assembly_sha256,
                manifest_sha256,manifest_json,task_kind,state,
                updated_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(
                    job_id,project_id,assembly_id,assembly_revision,assembly_sha256,
                    manifest_sha,encoded.decode("ascii"),TASK_KIND,
                    "QUEUED",now,now))
            db.executemany("""INSERT INTO production_segments(
                job_id,position,start_tick,end_tick,source_path,expected_sha256,
                expected_bytes,state) VALUES(?,?,?,?,?,?,?,?)""",
                [(job_id,x["position"],x["start_tick"],x["end_tick"],
                  x["source_path"],x["source_sha256"],x["source_bytes"],
                  "PENDING") for x in ordered])
            self._event(db,job_id,"JOB_SUBMITTED","Immutable approved revision-bound source plan")
        return {"format":FORMAT,"status":"QUEUED","job_id":job_id,
                "manifest_sha256":manifest_sha,"assembly_sha256":assembly_sha256,
                "segment_count":len(ordered),"production_dcp_accepted":False}

    def _verified_manifest(self,db,job_id):
        job=db.execute("SELECT * FROM production_jobs WHERE job_id=?",(job_id,)).fetchone()
        if job is None:
            raise KeyError("Production job not found")
        manifest=json.loads(job["manifest_json"])
        if (_digest(_canonical(manifest))!=job["manifest_sha256"] or
                any(manifest.get(k)!=job[k] for k in
                    ("project_id","assembly_id","assembly_revision","assembly_sha256","task_kind"))):
            raise RuntimeError("Production journal manifest integrity failed")
        ordered=manifest.get("segments",manifest.get("frames"))
        rows=db.execute("""SELECT position,start_tick,end_tick,source_path,
                                 expected_sha256,expected_bytes FROM production_segments
                          WHERE job_id=? ORDER BY position""",(job_id,))
        if type(ordered) is not list:
            raise RuntimeError("Production checkpoint source manifest incomplete")
        for row,expected in zip_longest(rows,ordered):
            if row is None or expected is None:
                raise RuntimeError("Production checkpoint source manifest incomplete")
            if dict(row)!={**{k:expected[k] for k in
                   ("position","start_tick","end_tick","source_path")},
                   "expected_sha256":expected["source_sha256"],
                   "expected_bytes":expected["source_bytes"]}:
                raise RuntimeError("Production checkpoint source manifest changed")
        return job,manifest

    def status(self, job_id):
        with self._read() as db:
            job,manifest=self._verified_manifest(db,job_id)
            segments=[dict(row) for row in db.execute(
                """SELECT position,start_tick,end_tick,state,verified_sha256,
                          verified_bytes,verified_at FROM production_segments
                   WHERE job_id=? ORDER BY position""",(job_id,))]
            return {
                "format":FORMAT,"job_id":job_id,
                "project_id":job["project_id"],
                "assembly_id":job["assembly_id"],
                "assembly_revision":job["assembly_revision"],
                "state":job["state"],"task_kind":job["task_kind"],
                "manifest_sha256":job["manifest_sha256"],
                "assembly_sha256":job["assembly_sha256"],
                "cancel_requested":bool(job["cancel_requested"]),
                "owner_pid":job["owner_pid"],
                "updated_at":job["updated_at"],
                "segments":segments,
                "verified_segments":sum(x["state"]=="VERIFIED" for x in segments),
                "total_segments":len(segments),
                "production_dcp_accepted":False
            }

    def status_page(self, job_id, *, first_position=0, limit=MAX_STATUS_PAGE,
                    expected_project_id=None):
        """Verified bounded status view; no new operation or retry authority."""
        if (type(first_position) is not int or first_position < 0 or
                type(limit) is not int or not 1 <= limit <= MAX_STATUS_PAGE):
            raise ValueError("Bounded production status page required")
        with self._read() as db:
            db.execute("BEGIN")
            if expected_project_id is not None:
                owner=db.execute("SELECT project_id FROM production_jobs WHERE job_id=?",
                                 (job_id,)).fetchone()
                if owner is None or owner["project_id"]!=expected_project_id:
                    raise PermissionError("Production job outside authorized project")
            job,_=self._verified_manifest(db,job_id)
            totals=db.execute("""SELECT COUNT(*), SUM(CASE WHEN state='VERIFIED' THEN 1 ELSE 0 END)
                  FROM production_segments WHERE job_id=?""",(job_id,)).fetchone()
            count, verified=totals[0],totals[1] or 0
            if first_position >= count:
                raise ValueError("Production status cursor outside original manifest")
            rows=[dict(row) for row in db.execute("""SELECT position,start_tick,end_tick,state,
                          verified_sha256,verified_bytes,verified_at FROM production_segments
                   WHERE job_id=? AND position>=? ORDER BY position LIMIT ?""",
                   (job_id,first_position,limit))]
            if not rows or [x["position"] for x in rows]!=list(range(first_position, first_position+len(rows))):
                raise RuntimeError("Production status positions changed")
            end=first_position+len(rows)
            return {"format":FORMAT,"job_id":job_id,"project_id":job["project_id"],
                    "assembly_id":job["assembly_id"],"assembly_revision":job["assembly_revision"],
                    "state":job["state"],"task_kind":job["task_kind"],
                    "manifest_sha256":job["manifest_sha256"],"assembly_sha256":job["assembly_sha256"],
                    "cancel_requested":bool(job["cancel_requested"]),"owner_pid":job["owner_pid"],
                    "updated_at":job["updated_at"],"segments":rows,"verified_segments":verified,
                    "total_segments":count,"next_position":end if end<count else None,
                    "production_dcp_accepted":False}

    def events(self, job_id, *, limit=200):
        if type(limit) is not int or not 1<=limit<=1000:
            raise ValueError("Bounded production event history required")
        with self._read() as db:
            exists=db.execute("SELECT 1 FROM production_jobs WHERE job_id=?",
                              (job_id,)).fetchone()
            if exists is None:
                raise KeyError("Production job not found")
            rows=db.execute("""SELECT id,event_kind,detail,recorded_at
                    FROM production_events WHERE job_id=?
                    ORDER BY id DESC LIMIT ?""",(job_id,limit)).fetchall()
            return [dict(row) for row in reversed(rows)]

    def heartbeat(self, owner_token, job_id, position):
        """Active native owner refreshes liveness without changing job state."""
        _require_owner(self.root)
        with self._tx() as db:
            row=db.execute("""SELECT s.owner_token AS segment_owner,
                   s.state AS segment_state,j.owner_token AS job_owner,
                   j.state AS job_state,j.cancel_requested
                FROM production_segments s JOIN production_jobs j
                ON s.job_id=j.job_id WHERE s.job_id=? AND s.position=?""",
                (job_id,position)).fetchone()
            if (row is None or row["segment_owner"]!=owner_token or
                    row["job_owner"]!=owner_token or
                    row["segment_state"]!="RUNNING" or
                    row["job_state"]!="RUNNING"):
                raise PermissionError("Stale/native-unowned worker heartbeat")
            db.execute("UPDATE production_jobs SET updated_at=? WHERE job_id=?",
                       (_now(),job_id))
            return {"job_id":job_id,
                    "cancel_requested":bool(row["cancel_requested"])}

    def list_jobs(self, project_id=None):
        if project_id is not None and (type(project_id) is not str or not PROJECT_RE.fullmatch(project_id)):
            raise ValueError("Invalid job project ID")
        with self._read() as db:
            rows=db.execute(
                """SELECT job_id,state,task_kind,updated_at FROM production_jobs
                   WHERE (? IS NULL OR project_id=?) ORDER BY created_at,job_id""",
                (project_id,project_id)).fetchall()
            return [dict(row) for row in rows]

    _claimable_tasks=frozenset((TASK_KIND,))

    def claim_next(self, owner_token, pid, *, task_kind=TASK_KIND):
        """Exclusive native supervisor manager calls; one committed segment lease."""
        _require_owner(self.root)
        if (task_kind not in self._claimable_tasks or
                type(owner_token) is not str or not ID_RE.fullmatch(owner_token)
                or type(pid) is not int or pid!=os.getpid()):
            raise PermissionError("Native worker identity required")
        with self._tx() as db:
            row=db.execute("""SELECT s.job_id,s.position,s.source_path,
                    s.expected_sha256,s.expected_bytes,s.start_tick,s.end_tick,
                    j.task_kind
                    FROM production_segments s JOIN production_jobs j
                      ON j.job_id=s.job_id
                    WHERE j.cancel_requested=0 AND j.task_kind=?
                      AND j.state IN ('QUEUED','RUNNING')
                      AND NOT EXISTS (SELECT 1 FROM production_segments active WHERE active.state='RUNNING')
                      AND s.state='PENDING'
                    ORDER BY j.created_at,s.position LIMIT 1""",(task_kind,)).fetchone()
            if row is None:
                return None
            job,_=self._verified_manifest(db,row["job_id"])
            if job["owner_token"] not in (None,owner_token):
                return None
            db.execute("""UPDATE production_jobs SET state='RUNNING',owner_token=?,
                owner_pid=?,updated_at=? WHERE job_id=?""",
                (owner_token,pid,_now(),row["job_id"]))
            db.execute("""UPDATE production_segments SET state='RUNNING',
                owner_token=? WHERE job_id=? AND position=?""",
                (owner_token,row["job_id"],row["position"]))
            self._event(db,row["job_id"],"SEGMENT_CLAIMED",str(row["position"]))
            return dict(row)

    def finish_verified(self, owner_token, job_id, position, digest, size):
        _require_owner(self.root)
        if (type(digest) is not str or not SHA_RE.fullmatch(digest)
                or type(size) is not int or size<1):
            raise ValueError("Real verified output SHA and size required")
        with self._tx() as db:
            job,_=self._verified_manifest(db,job_id)
            if job["task_kind"]!=TASK_KIND or job["state"]!="RUNNING":
                raise PermissionError("Not an active read-only verification task")
            row=db.execute("""SELECT s.expected_sha256,s.expected_bytes,s.source_path,
                         s.state,s.owner_token,j.owner_token AS job_owner,
                         j.cancel_requested
                  FROM production_segments s JOIN production_jobs j
                   ON j.job_id=s.job_id WHERE s.job_id=? AND s.position=?""",
                  (job_id,position)).fetchone()
            if (row is None or row["state"]!="RUNNING" or
                    row["owner_token"]!=owner_token or
                    row["job_owner"]!=owner_token):
                raise PermissionError("Wrong or stale native segment owner")
            if row["cancel_requested"]:
                raise RuntimeError("Cancellation requested; cannot commit segment")
            if (digest!=row["expected_sha256"] or size!=row["expected_bytes"] or
                    _hash_stream(Path(row["source_path"]))!=(digest,size)):
                raise PermissionError("Source segment changed; do not commit")
            db.execute("""UPDATE production_segments SET state='VERIFIED',
                verified_sha256=?,verified_bytes=?,verified_at=?,
                owner_token=NULL WHERE job_id=? AND position=?""",
                (digest,size,_now(),job_id,position))
            remaining=db.execute("""SELECT COUNT(*) FROM production_segments
                WHERE job_id=? AND state!='VERIFIED'""",(job_id,)).fetchone()[0]
            state="VERIFY_COMPLETE" if remaining==0 else "RUNNING"
            db.execute("""UPDATE production_jobs SET state=?,updated_at=?,
                         owner_token=?,owner_pid=? WHERE job_id=?""",
                (state,_now(),None if remaining==0 else owner_token,
                 None if remaining==0 else os.getpid(),job_id))
            self._event(db,job_id,"SEGMENT_VERIFIED",str(position))
            return {"job_id":job_id,"state":state,
                    "segment":position,"production_dcp_accepted":False}

    def mark_review(self, owner_token, job_id, position, reason):
        _require_owner(self.root)
        if type(reason) is not str or not 1<=len(reason)<=100:
            raise ValueError("Bounded error category required")
        with self._tx() as db:
            row=db.execute("""SELECT owner_token,state FROM production_segments
                    WHERE job_id=? AND position=?""",(job_id,position)).fetchone()
            if row is None or row["owner_token"]!=owner_token or row["state"]!="RUNNING":
                raise PermissionError("Only active native worker may flag review")
            db.execute("""UPDATE production_segments SET state='REVIEW_REQUIRED',
                owner_token=NULL WHERE job_id=? AND position=?""",
                (job_id,position))
            db.execute("""UPDATE production_jobs SET state='REVIEW_REQUIRED',
                owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            self._event(db,job_id,"SEGMENT_REVIEW_REQUIRED",reason)

    def authorize_review_retry(self, job_id, authorize):
        """Exact host-approved reviewed-source retry with short SQLite lease.

        The expensive original SHA verification runs OUTSIDE the write lease.
        The final transaction compares the same reviewed segment identities
        and leaves real media untouched. Next worker verifies bytes again.
        """
        _require_owner(self.root)
        if not callable(authorize):
            raise PermissionError("Native host retry authorization required")
        snap=self.status(job_id)
        if snap["state"]!="REVIEW_REQUIRED" or snap["task_kind"]!=TASK_KIND:
            raise PermissionError("Only reviewed source verification jobs may retry")
        scope={"operation":"nvp.supervisor.retry_source_verification.v1",
               "job_id":job_id,"manifest_sha256":snap["manifest_sha256"],
               "assembly_sha256":snap["assembly_sha256"]}
        if authorize(deepcopy(scope)) is not True:
            return {"status":"DENIED","job_id":job_id}
        with self._read() as db:
            segments=[dict(r) for r in db.execute(
                """SELECT position,source_path,expected_sha256,expected_bytes
                   FROM production_segments WHERE job_id=?
                   AND state='REVIEW_REQUIRED' ORDER BY position""",
                (job_id,))]
        if not segments:
            raise RuntimeError("No source segment requires review")
        import hashlib
        for segment in segments:
            file=Path(segment["source_path"])
            if _hash_stream(file)!=(segment["expected_sha256"],segment["expected_bytes"]):
                raise PermissionError("Reviewed original media unavailable or changed")
            digest=hashlib.sha256()
            size=0
            with file.open("rb") as handle:
                while chunk:=handle.read(1024*1024):
                    digest.update(chunk)
                    size+=len(chunk)
                    if size>segment["expected_bytes"]:
                        raise PermissionError("Original media grew during review")
            if (digest.hexdigest()!=segment["expected_sha256"] or
                    size!=segment["expected_bytes"]):
                raise PermissionError("Source still differs from approved SHA")
        with self._tx() as db:
            job=db.execute("""SELECT state,task_kind,manifest_sha256,
                               cancel_requested FROM production_jobs
                               WHERE job_id=?""",(job_id,)).fetchone()
            if (job is None or job["state"]!="REVIEW_REQUIRED" or
                    job["task_kind"]!=TASK_KIND or
                    job["manifest_sha256"]!=scope["manifest_sha256"] or
                    job["cancel_requested"]):
                raise PermissionError("Source review changed during authorization")
            current=[dict(r) for r in db.execute(
                """SELECT position,source_path,expected_sha256,expected_bytes
                   FROM production_segments WHERE job_id=?
                   AND state='REVIEW_REQUIRED' ORDER BY position""",
                (job_id,))]
            if current!=segments:
                raise PermissionError("Review segment identity changed during source check")
            for segment in segments:
                db.execute("""UPDATE production_segments SET state='PENDING',
                    verified_sha256=NULL,verified_bytes=NULL,verified_at=NULL,
                    owner_token=NULL WHERE job_id=? AND position=?""",
                    (job_id,segment["position"]))
            db.execute("""UPDATE production_jobs SET state='QUEUED',
                owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            self._event(db,job_id,"SOURCE_RETRY_APPROVED",
                        str(len(segments))+" restored source segments verified")
        return {"status":"QUEUED","job_id":job_id,
                "segments_requeued":len(segments)}

    def request_cancel(self, job_id, authorize):
        if not callable(authorize):
            raise PermissionError("Host creator authorization required")
        snapshot=self.status(job_id)
        scope={"operation":"nvp.supervisor.request_cancel.v1",
               "job_id":job_id,"manifest_sha256":snapshot["manifest_sha256"],
               "assembly_sha256":snapshot["assembly_sha256"]}
        if authorize(deepcopy(scope)) is not True:
            return {"status":"DENIED","job_id":job_id}
        with self._tx() as db:
            row=db.execute("SELECT state,manifest_sha256 FROM production_jobs WHERE job_id=?",
                           (job_id,)).fetchone()
            if row is None or row["manifest_sha256"]!=scope["manifest_sha256"]:
                raise PermissionError("Production state changed during approval")
            if row["state"] in ("VERIFY_COMPLETE","OUTPUT_READY",
                                 "DCP_PUBLISHED","DCP_INDEXED","CANCELLED"):
                raise RuntimeError("Completed job cannot be retrospectively cancelled")
            db.execute("""UPDATE production_jobs SET cancel_requested=1,
                        updated_at=? WHERE job_id=?""",(_now(),job_id))
            self._event(db,job_id,"CANCEL_REQUESTED","Explicit host authorization")
        return {"job_id":job_id,"status":"CANCEL_REQUESTED"}

    def finalize_cancel(self, job_id):
        """Only native supervisor after observing shutdown/worker checkpoint."""
        _require_owner(self.root)
        with self._tx() as db:
            job=db.execute("""SELECT state,cancel_requested FROM production_jobs
                           WHERE job_id=?""",(job_id,)).fetchone()
            if job is None or job["cancel_requested"]!=1:
                raise PermissionError("No authorized cancellation requested")
            if job["state"] in ("VERIFY_COMPLETE","OUTPUT_READY",
                                   "DCP_PUBLISHED","DCP_INDEXED"):
                raise RuntimeError("Completed job cannot be cancelled")
            db.execute("""UPDATE production_segments SET state='REVIEW_REQUIRED',owner_token=NULL
                 WHERE job_id=? AND state='RUNNING'""",(job_id,))
            db.execute("""UPDATE production_jobs SET state='CANCELLED',
                 owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            self._event(db,job_id,"CANCELLED","Native owner confirmed no work continues")

    def reconcile_after_restart(self):
        """Host-supervisor-only restart reconciliation. No files deleted.

        The only currently executable worker is read-only SHA verification,
        so interrupted checks can safely be put back to PENDING. A future
        output-producing worker must instead flag uncommitted stages for
        manual review and never silently retry/publish them.
        """
        _require_owner(self.root)
        reports=[]
        with self._tx() as db:
            jobs=db.execute("""SELECT job_id,task_kind,cancel_requested FROM production_jobs
                       WHERE task_kind=? AND state IN
                       ('QUEUED','RUNNING','VERIFY_COMPLETE','REVIEW_REQUIRED')""",
                       (TASK_KIND,)).fetchall()
            for job in jobs:
                job_id=job["job_id"]
                self._verified_manifest(db,job_id)
                if job["task_kind"]!=TASK_KIND:
                    raise PermissionError("Unknown production worker cannot be auto-recovered")
                rows=db.execute("""SELECT position,state,source_path,expected_sha256,
                          expected_bytes,verified_sha256,verified_bytes
                          FROM production_segments WHERE job_id=?
                          ORDER BY position""",(job_id,)).fetchall()
                damaged=[]
                interrupted=[]
                for item in rows:
                    if item["state"]=="RUNNING":
                        interrupted.append(item["position"])
                    if item["state"]=="VERIFIED":
                        try:
                            import hashlib
                            file=Path(item["source_path"])
                            if _hash_stream(file)!=(item["expected_sha256"],item["expected_bytes"]):
                                raise RuntimeError("Source missing or changed")
                            h=hashlib.sha256()
                            size=0
                            with file.open("rb") as inp:
                                while block:=inp.read(1024*1024):
                                    h.update(block)
                                    size+=len(block)
                            if (size!=item["verified_bytes"] or
                                    h.hexdigest()!=item["verified_sha256"] or
                                    size!=item["expected_bytes"] or
                                    h.hexdigest()!=item["expected_sha256"]):
                                raise RuntimeError("Verified source no longer matches")
                        except (OSError,RuntimeError):
                            damaged.append(item["position"])
                for position in interrupted:
                    db.execute("""UPDATE production_segments SET state='PENDING',
                               owner_token=NULL WHERE job_id=? AND position=?""",
                               (job_id,position))
                    self._event(db,job_id,"INTERRUPTED_READ_ONLY_CHECK",
                                str(position))
                for position in damaged:
                    db.execute("""UPDATE production_segments SET state='REVIEW_REQUIRED',
                                owner_token=NULL WHERE job_id=? AND position=?""",
                               (job_id,position))
                    self._event(db,job_id,"VERIFIED_SOURCE_TAMPERED",str(position))
                states=[r["state"] for r in db.execute(
                    "SELECT state FROM production_segments WHERE job_id=?",
                    (job_id,)).fetchall()]
                if job["cancel_requested"]:
                    state="CANCELLED"
                elif damaged or "REVIEW_REQUIRED" in states:
                    state="REVIEW_REQUIRED"
                elif all(s=="VERIFIED" for s in states):
                    state="VERIFY_COMPLETE"
                else:
                    state="QUEUED"
                db.execute("""UPDATE production_jobs SET state=?,
                    owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                    (state,_now(),job_id))
                reports.append({"job_id":job_id,"state":state,
                                "interrupted":interrupted,"tampered":damaged})
        return {"format":"nvp.wo4.supervisor_recovery.v1",
                "jobs":reports,"filesystem_mutated":False,
                "production_dcp_accepted":False}
