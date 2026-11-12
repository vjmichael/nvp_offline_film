"""G03-E1: host-owned *live* encrypted film storage, Windows DPAPI + AES-GCM.

New encrypted movies only. The working SQLite schema and source assets never
touch plaintext disk; SQLite operates in memory and each transaction publishes
a new authenticated encrypted immutable snapshot, then one atomic HEAD.

This component does not magically encrypt the legacy shared NVP Studio,
historical OpenUSD/PCM caches or backups. The native legacy workers must be
denied for secured movies until routed through scoped broker receipts.

No model/LLM/React client may receive key material, DPAPI entropy or raw
asset paths. Caller must verify an authenticated local-director grant first.
"""
from __future__ import annotations

import hashlib
import io
import json
from contextlib import contextmanager
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import stat
import tempfile
import threading
import time

from backend.nvp_g03_windows_vault import (
    VaultError, _crypto, _dpapi, _key_create, _key_open,
    _encrypt_file, _decrypt_file, _no_link, _relative, _token
)
from backend.nvp_studio import parse_screenplay, now

ID = re.compile(r"[a-f0-9]{32}\Z")
MAX_DB_BYTES = 64 * 1024 * 1024
MAX_ASSET = 256 * 1024 * 1024
MAX_SCREENPLAY = 1_000_000


class LiveFilmError(VaultError):
    pass


class _HashSink:
    def write(self, data):
        pass


class LiveFilmStore:
    """Host-owned storage. The active session map is never persisted."""

    def __init__(self, root, *, clock=time.monotonic, grant_checker=None):
        self.root = Path(root).absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        _no_link(self.root)
        self.clock = clock
        self.grant_checker = grant_checker
        self._guard = threading.RLock()
        self._keys = {}
        self._leases = {}

    def _folder(self, pid):
        if not isinstance(pid, str) or not ID.fullmatch(pid):
            raise LiveFilmError("Invalid encrypted movie ID")
        return self.root / pid

    @contextmanager
    def _write_mutex(self,folder):
        """Host-level OS file lock, not just a Python-thread lock.

        Two independent NVP processes must not deserialize the same encrypted
        HEAD and accidentally publish competing stale SQLite state.
        """
        target=folder/".host-commit.lock"
        if target.exists():
            _no_link(target)
        flags=os.O_CREAT|os.O_RDWR
        flags|=getattr(os,"O_NOFOLLOW",0)
        fd=os.open(str(target),flags,0o600)
        locked=False
        start=self.clock()
        try:
            if os.fstat(fd).st_size==0:
                os.write(fd,b"\0")
                os.fsync(fd)
            if os.name=="nt":
                import msvcrt
                while self.clock()-start<20:
                    os.lseek(fd,0,os.SEEK_SET)
                    try:
                        msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
                        locked=True
                        break
                    except OSError:
                        time.sleep(.05)
            else:
                import fcntl
                while self.clock()-start<20:
                    try:
                        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        locked=True
                        break
                    except BlockingIOError:
                        time.sleep(.05)
            if not locked:
                raise LiveFilmError("Encrypted film is busy with another host writer")
            yield
        finally:
            if locked:
                if os.name=="nt":
                    os.lseek(fd,0,os.SEEK_SET)
                    msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
                else:
                    fcntl.flock(fd,fcntl.LOCK_UN)
            os.close(fd)

    def exists(self, pid):
        path = self._folder(pid)
        return path.is_dir() and (path / "key.nvpdpapi").is_file()

    @staticmethod
    def _write_fsync(path, data, *, exclusive=True):
        mode = "xb" if exclusive else "wb"
        with path.open(mode) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

    @staticmethod
    def _new_sqlite(title, idea, screenplay):
        if not all(type(x) is str for x in (title, idea, screenplay)):
            raise LiveFilmError("Invalid movie metadata types")
        if not title.strip() or len(title)>150 or len(idea)>10000:
            raise LiveFilmError("Invalid movie title or idea")
        if len(screenplay)>MAX_SCREENPLAY:
            raise LiveFilmError("Screenplay exceeds film limit")
        parse_screenplay(screenplay)
        db=sqlite3.connect(":memory:")
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA journal_mode=MEMORY")
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
        CREATE TABLE film_metadata(
            id INTEGER PRIMARY KEY CHECK(id=1),
            title TEXT NOT NULL, idea TEXT NOT NULL,
            screenplay TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE revisions(
            revision INTEGER PRIMARY KEY, screenplay TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE source_assets(
            name TEXT PRIMARY KEY, opaque_id TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            media_type TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE worker_receipts(
            receipt_id TEXT PRIMARY KEY, asset_name TEXT NOT NULL,
            operation TEXT NOT NULL, digest TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        """)
        db.execute("""INSERT INTO film_metadata
             (id,title,idea,screenplay,revision,updated_at) VALUES
             (1,?,?,?,?,?)""",(title.strip(),idea,screenplay,0,now()))
        db.commit()
        return db

    @staticmethod
    def _open_sqlite(raw):
        if type(raw) is not bytes or len(raw)>MAX_DB_BYTES:
            raise LiveFilmError("Invalid encrypted SQLite size")
        db=sqlite3.connect(":memory:")
        db.row_factory=sqlite3.Row
        try:
            db.deserialize(raw)
            db.execute("PRAGMA temp_store=MEMORY")
            db.execute("PRAGMA foreign_keys=ON")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise LiveFilmError("Encrypted SQLite failed integrity check")
            tables={r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"film_metadata","revisions","source_assets",
                    "worker_receipts"} <= tables:
                raise LiveFilmError("Encrypted SQLite schema missing")
            return db
        except Exception:
            db.close()
            raise

    def _read_key_info(self, folder):
        _no_link(folder)
        k=folder/"key.nvpdpapi"
        _no_link(k)
        if k.stat().st_size>16384:
            raise LiveFilmError("Oversized encrypted movie key metadata")
        return json.loads(k.read_text("utf8"))

    def create(self, pid, title, idea, screenplay, passphrase):
        """Create new encrypted live movie; never stages plaintext on disk."""
        folder=self._folder(pid)
        _dpapi();_crypto()
        if folder.exists():
            raise LiveFilmError("Encrypted film already exists")
        db=self._new_sqlite(title,idea,screenplay)
        try:
            raw=db.serialize()
        finally:
            db.close()
        if len(raw)>MAX_DB_BYTES:
            raise LiveFilmError("Initial film database too large")
        parent=folder.parent
        stage=Path(tempfile.mkdtemp(prefix=".nvp-secured-create-",dir=parent))
        try:
            _no_link(stage)
            (stage/"revisions").mkdir()
            (stage/"assets").mkdir()
            key,metadata=_key_create(passphrase,pid)
            self._write_fsync(stage/"key.nvpdpapi",
                              json.dumps(metadata,sort_keys=True).encode("utf8"))
            revision=self._seal_db(stage,pid,key,raw,0)
            self._publish_head(stage,revision)
            if folder.exists():
                raise LiveFilmError("Concurrent encrypted film creation")
            os.replace(stage,folder)
            return {"encrypted":True,"project_id":pid,"revision":0,
                    "plaintext_working_db":False}
        finally:
            if stage.exists():
                shutil.rmtree(stage)

    @staticmethod
    def _head(folder):
        _no_link(folder)
        path=folder/"HEAD.json"
        _no_link(path)
        if path.stat().st_size>4096:
            raise LiveFilmError("Encrypted film HEAD oversized")
        info=json.loads(path.read_text("utf8"))
        if (type(info) is not dict or set(info)!={"sequence","name","sha256"} or
                type(info["sequence"]) is not int or info["sequence"]<0 or
                type(info["name"]) is not str or
                info["name"] != f"db.{info['sequence']:012d}.nvpsealed" or
                not re.fullmatch(r"[a-f0-9]{64}",info["sha256"])):
            raise LiveFilmError("Invalid encrypted film HEAD")
        return info

    @staticmethod
    def _publish_head(folder,record):
        target=folder/"HEAD.json"
        scratch=folder/(".nvp-head-"+secrets.token_hex(12))
        LiveFilmStore._write_fsync(scratch,
             json.dumps(record,sort_keys=True,separators=(",",":")).encode())
        try:
            os.replace(scratch,target)
        finally:
            scratch.unlink(missing_ok=True)

    @staticmethod
    def _seal_db(folder,pid,key,raw,seq):
        name=f"db.{seq:012d}.nvpsealed"
        output=folder/"revisions"/name
        _encrypt_file(io.BytesIO(raw),output,key=key,project_id=pid,
                      name=f"live-sqlite-v1/{seq}")
        data_hash=hashlib.sha256(output.read_bytes()).hexdigest()
        return {"sequence":seq,"name":name,"sha256":data_hash}

    def _read_db(self,folder,pid,key):
        head=self._head(folder)
        file=folder/"revisions"/head["name"]
        _no_link(file)
        ciphertext=file.read_bytes()
        if hashlib.sha256(ciphertext).hexdigest()!=head["sha256"]:
            raise LiveFilmError("Encrypted SQLite HEAD integrity mismatch")
        if len(ciphertext)>MAX_DB_BYTES+4096:
            raise LiveFilmError("Encrypted SQLite snapshot oversized")
        memory=io.BytesIO()
        _decrypt_file(file,memory,key=key,project_id=pid,
                      name=f"live-sqlite-v1/{head['sequence']}")
        db=self._open_sqlite(memory.getvalue())
        return db,head

    def authorize(self,pid,passphrase,session_token):
        """Unlock only from a separately verified host/HTTP director session."""
        if not isinstance(session_token,str) or len(session_token)<20:
            raise LiveFilmError("Host director grant is required")
        folder=self._folder(pid)
        if not self.exists(pid):
            raise LiveFilmError("Encrypted film not found")
        with self._guard:
            key=_key_open(passphrase,pid,self._read_key_info(folder))
            db,_=self._read_db(folder,pid,key)
            db.close()
            self._keys[session_token]=(pid,key)
            return True

    def revoke(self,pid):
        with self._guard:
            self._keys={k:v for k,v in self._keys.items() if v[0]!=pid}
            self._leases={k:v for k,v in self._leases.items() if v["pid"]!=pid}

    def local_session_live(self,pid,token):
        """Cheap same-host revocation gate for a PCM evaluator.

        This is NOT an authorization grant: cross-process generation and
        expiry still require the full _session() check on a bounded timer,
        every new sealed chunk and before completed-reel publication.
        A local movie lock immediately clears _keys under this guard.
        """
        with self._guard:
            entry=self._keys.get(token) if isinstance(token,str) else None
            return entry is not None and entry[0]==pid

    def _session(self,pid,token):
        if not isinstance(token,str):
            raise LiveFilmError("Film must be unlocked by its director")
        if self.grant_checker is not None and not self.grant_checker(pid,token):
            self.revoke(pid)
            raise LiveFilmError("Host film permission is missing or revoked")
        entry=self._keys.get(token)
        if not entry or entry[0]!=pid:
            raise LiveFilmError("Movie is locked; host key is unavailable")
        return entry[1]

    def read(self,pid,token):
        with self._guard:
            key=self._session(pid,token)
            db,_=self._read_db(self._folder(pid),pid,key)
            try:
                row=db.execute("SELECT * FROM film_metadata WHERE id=1").fetchone()
                if row is None:
                    raise LiveFilmError("Encrypted film metadata missing")
                result=dict(row)
                scenes=parse_screenplay(result["screenplay"])
                for scene in scenes:
                    scene["shots"]=[]
                result["id"]=pid
                result["scenes"]=scenes
                result["bible"]={
                    "characters":sorted({actor for s in scenes for actor in s["characters"]}),
                    "locations":list(dict.fromkeys(s["heading"] for s in scenes))}
                result["archived_shots"]=0
                result["encrypted"]=True
                result["source_assets"]=[dict(row) for row in db.execute(
                    """SELECT name,sha256,size_bytes,media_type
                       FROM source_assets ORDER BY name""")]
                return result
            finally:
                db.close()

    def _change(self,pid,token,mutator):
        with self._guard:
            key=self._session(pid,token)
            folder=self._folder(pid)
            with self._write_mutex(folder):
                return self._change_locked(pid,token,mutator,key,folder)

    def _change_locked(self,pid,token,mutator,key,folder):
        db,head=self._read_db(folder,pid,key)
        try:
            result=mutator(db,key,folder)
            db.commit()
            raw=db.serialize()
            if len(raw)>MAX_DB_BYTES:
                raise LiveFilmError("Live encrypted film database too large")
            # Crash between an immutable revision write and HEAD publish
            # leaves an encrypted orphan. Never clobber it on restart.
            nums=[head["sequence"]]
            for candidate in (folder/"revisions").glob("db.*.nvpsealed"):
                match=re.fullmatch(r"db\.(\d{12})\.nvpsealed",candidate.name)
                if match:
                    nums.append(int(match.group(1)))
            next_seq=max(nums)+1
            record=self._seal_db(folder,pid,key,raw,next_seq)
            self._session(pid,token)
            self._publish_head(folder,record)
            return result
        finally:
            db.close()

    def save_screenplay(self,pid,token,screenplay,expected_revision):
        if type(screenplay) is not str or len(screenplay)>MAX_SCREENPLAY:
            raise LiveFilmError("Screenplay exceeds permitted size")
        parse_screenplay(screenplay)
        def update(db,key,folder):
            old=db.execute("SELECT screenplay,revision FROM film_metadata WHERE id=1").fetchone()
            if old["revision"]!=expected_revision:
                raise LiveFilmError("Screenplay changed elsewhere; reload before editing")
            db.execute("""INSERT OR IGNORE INTO revisions
                (revision,screenplay,updated_at) VALUES (?,?,?)""",
                (expected_revision,old["screenplay"],now()))
            db.execute("""UPDATE film_metadata SET screenplay=?,
                revision=revision+1,updated_at=? WHERE id=1""",
                (screenplay,now()))
        self._change(pid,token,update)
        return self.read(pid,token)

    def put_original(self,pid,token,name,data,media_type="application/octet-stream",
                     *,receipt_id=None):
        """Original source bytes sealed before SQLite index publication.

        Data comes through the trusted host. No raw filesystem path is accepted
        by the web/model boundary and no plaintext staging file is written.
        """
        name=str(_relative(name))
        if type(data) is not bytes or len(data)>MAX_ASSET:
            raise LiveFilmError("Invalid original asset size")
        if type(media_type) is not str or len(media_type)>120:
            raise LiveFilmError("Invalid source type")
        def mutate(db,key,folder):
            if db.execute("SELECT 1 FROM source_assets WHERE name=?",(name,)).fetchone():
                raise LiveFilmError("Original is immutable; choose another asset identity")
            opaque=_token(name,key)
            final=folder/"assets"/(opaque+".nvpsealed")
            if final.exists():
                # A power cut after source sealing but before the encrypted
                # SQLite commit may leave an unindexed original. Resume only
                # when that original authenticates and exactly matches this
                # proposed immutable identity and source data.
                _no_link(final)
                previous=_decrypt_file(final,_HashSink(),key=key,
                                       project_id=pid,name="original/"+name)
                if previous!={"sha256":hashlib.sha256(data).hexdigest(),
                             "size_bytes":len(data)}:
                    raise LiveFilmError("Existing original differs after interrupted commit")
                reused=True
            else:
                _encrypt_file(io.BytesIO(data),final,key=key,project_id=pid,
                              name="original/"+name)
                reused=False
            try:
                # Independent authenticated readback before index publication.
                result=_decrypt_file(final,_HashSink(),key=key,
                                     project_id=pid,name="original/"+name)
                digest=hashlib.sha256(data).hexdigest()
                if result!={"sha256":digest,"size_bytes":len(data)}:
                    raise LiveFilmError("Original encrypted readback mismatch")
                db.execute("""INSERT INTO source_assets
                    (name,opaque_id,sha256,size_bytes,media_type,created_at)
                    VALUES (?,?,?,?,?,?)""",
                    (name,opaque,digest,len(data),media_type,now()))
                if receipt_id is not None:
                    db.execute("""INSERT INTO worker_receipts
                        (receipt_id,asset_name,operation,digest,recorded_at)
                        VALUES (?,?,?,?,?)""",
                        (receipt_id,name,"write_original",digest,now()))
                return {"name":name,"sha256":digest,"size_bytes":len(data),
                        "original_modified":False,"encrypted":True}
            except Exception:
                if not reused:
                    final.unlink(missing_ok=True)
                raise
        return self._change(pid,token,mutate)

    def get_original(self,pid,token,name):
        name=str(_relative(name))
        with self._guard:
            key=self._session(pid,token)
            folder=self._folder(pid)
            db,_=self._read_db(folder,pid,key)
            try:
                entry=db.execute("""SELECT opaque_id,sha256,size_bytes
                    FROM source_assets WHERE name=?""",(name,)).fetchone()
            finally:
                db.close()
            if not entry:
                raise LiveFilmError("Unknown protected source")
            source=folder/"assets"/(entry["opaque_id"]+".nvpsealed")
            _no_link(source)
            target=io.BytesIO()
            result=_decrypt_file(source,target,key=key,project_id=pid,
                                 name="original/"+name)
            if result!={"sha256":entry["sha256"],"size_bytes":entry["size_bytes"]}:
                raise LiveFilmError("Protected original failed independent digest")
            return target.getvalue()

    def worker_grant(self,pid,token,asset_name,operation,*,human_approved=False):
        """One-use reviewed host grant. Never return raw key or source path.

        This does NOT authorize legacy external workers. Only supervised
        in-process host broker calls can redeem these grants.
        """
        if human_approved is not True:
            raise LiveFilmError("Human-approved one-use worker permission required")
        asset_name=str(_relative(asset_name))
        if operation not in {"read_original","write_original"}:
            raise LiveFilmError("Unrecognized protected worker operation")
        with self._guard:
            self._session(pid,token)
            receipt_id=secrets.token_urlsafe(32)
            self._leases[receipt_id]={"pid":pid,"token":token,
                                      "name":asset_name,"operation":operation,
                                      "expires":self.clock()+30}
            return receipt_id

    def worker_execute(self,pid,lease,operation,asset_name,*,data=None,
                       media_type="application/octet-stream"):
        """Restricted in-process host broker. Legacy external workers are DENIED."""
        asset_name=str(_relative(asset_name))
        with self._guard:
            grant=self._leases.pop(lease,None)
            if (grant is None or grant["pid"]!=pid or
                    grant["operation"]!=operation or
                    grant["name"]!=asset_name or
                    grant["expires"]<=self.clock()):
                raise LiveFilmError("Worker authority expired, replayed or mismatched")
            self._session(pid,grant["token"])
            if operation=="read_original":
                payload=self.get_original(pid,grant["token"],asset_name)
                def receipt(db,key,folder):
                    db.execute("""INSERT INTO worker_receipts
                        (receipt_id,asset_name,operation,digest,recorded_at)
                        VALUES (?,?,?,?,?)""",
                        (lease,asset_name,operation,
                         hashlib.sha256(payload).hexdigest(),now()))
                self._change(pid,grant["token"],receipt)
                return payload
            if operation=="write_original":
                return self.put_original(
                    pid,grant["token"],asset_name,data,
                    media_type=media_type,receipt_id=lease)
            raise LiveFilmError("Unsupported worker operation")

    def worker_run_transition(self,pid,token,worker_id,source_name,
                              source_sha256,state,*,output_sha256=None,
                              exit_code=None):
        """Host-only durable receipt; always encrypted with live movie SQL.

        Native ownership evidence must accompany a terminal result. A source
        string, process command or original path is never stored in a public
        telemetry/worker SQLite journal.
        """
        valid={"RUNNING","SUCCEEDED","CANCELLED","FAILED",
               "INTERRUPTED_UNVERIFIED","CUSTODY_UNPROVEN"}
        if not isinstance(worker_id,str) or not re.fullmatch(r"[a-f0-9]{32}",worker_id):
            raise LiveFilmError("Invalid worker run identity")
        if state not in valid:
            raise LiveFilmError("Invalid protected worker state")
        if not isinstance(source_sha256,str) or not re.fullmatch(
                r"[a-f0-9]{64}",source_sha256):
            raise LiveFilmError("Original digest is invalid")
        def record(db,key,folder):
            db.execute("""CREATE TABLE IF NOT EXISTS protected_worker_runs(
                worker_id TEXT PRIMARY KEY,source_name TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,state TEXT NOT NULL,
                output_sha256 TEXT,exit_code INTEGER,
                recorded_at TEXT NOT NULL)""")
            prior=db.execute("SELECT state FROM protected_worker_runs WHERE worker_id=?",
                             (worker_id,)).fetchone()
            if prior is None:
                if state!="RUNNING":
                    raise LiveFilmError("Protected worker must first be registered")
                db.execute("""INSERT INTO protected_worker_runs
                    (worker_id,source_name,source_sha256,state,output_sha256,
                     exit_code,recorded_at) VALUES (?,?,?,?,?,?,?)""",
                    (worker_id,source_name,source_sha256,state,None,None,now()))
            else:
                if prior[0]!="RUNNING":
                    raise LiveFilmError("Protected worker already has a terminal state")
                if state=="RUNNING":
                    raise LiveFilmError("Protected worker run ID cannot be replayed")
                db.execute("""UPDATE protected_worker_runs SET state=?,
                    output_sha256=?,exit_code=?,recorded_at=? WHERE worker_id=?""",
                    (state,output_sha256,exit_code,now(),worker_id))
        self._change(pid,token,record)

    def protected_worker_runs(self,pid,token):
        with self._guard:
            key=self._session(pid,token)
            db,_=self._read_db(self._folder(pid),pid,key)
            try:
                exists=db.execute("""SELECT 1 FROM sqlite_master WHERE
                    type='table' AND name='protected_worker_runs'""").fetchone()
                if not exists:return []
                return [dict(r) for r in db.execute(
                    "SELECT * FROM protected_worker_runs ORDER BY worker_id")]
            finally:
                db.close()

    def reconcile_interrupted_workers(self,pid,token):
        """Cold-start journal reconciliation; never infer process-tree death.

        The OS job should terminate on handle close, but after a crash there
        is no independently observed job-handle exit receipt. Keep the run
        interrupted/unverified, never publish its staged output or replay.
        """
        with self._guard:
            records=self.protected_worker_runs(pid,token)
            incomplete=[r for r in records if r["state"]=="RUNNING"]
            if not incomplete:return []
            for row in incomplete:
                self.worker_run_transition(
                    pid,token,row["worker_id"],row["source_name"],
                    row["source_sha256"],"INTERRUPTED_UNVERIFIED")
            return [r["worker_id"] for r in incomplete]

    def worker_receipts(self,pid,token):
        """Auditable receipts remain inside authenticated live SQLite."""
        with self._guard:
            key=self._session(pid,token)
            db,_=self._read_db(self._folder(pid),pid,key)
            try:
                return [dict(x) for x in db.execute(
                    "SELECT * FROM worker_receipts ORDER BY recorded_at,receipt_id")]
            finally:
                db.close()

    def recover_screenplay(self,pid,token,commit_sequence,expected_revision,
                           *,human_approved=False):
        """Human-reviewed, new encrypted revision from an authenticated earlier one.

        Never changes or deletes original Take/source assets. No silent
        downgrade: optimistic revision conflict and host grant are mandatory.
        """
        if human_approved is not True:
            raise LiveFilmError("Director-approved recovery is required")
        if type(commit_sequence) is not int or commit_sequence<0:
            raise LiveFilmError("Invalid authenticated recovery sequence")
        with self._guard:
            key=self._session(pid,token)
            folder=self._folder(pid)
            db,head=self._read_db(folder,pid,key)
            db.close()
            if commit_sequence>head["sequence"]:
                raise LiveFilmError("Cannot restore an uncommitted film revision")
            path=folder/"revisions"/f"db.{commit_sequence:012d}.nvpsealed"
            _no_link(path)
            buffer=io.BytesIO()
            _decrypt_file(path,buffer,key=key,project_id=pid,
                          name=f"live-sqlite-v1/{commit_sequence}")
            old=self._open_sqlite(buffer.getvalue())
            try:
                previous=old.execute(
                    "SELECT screenplay FROM film_metadata WHERE id=1").fetchone()
                if previous is None:
                    raise LiveFilmError("Recovered film metadata missing")
                screenplay=previous[0]
            finally:
                old.close()
            def revise(db,key,folder):
                current=db.execute(
                    "SELECT revision,screenplay FROM film_metadata WHERE id=1").fetchone()
                if current is None or current["revision"]!=expected_revision:
                    raise LiveFilmError("Movie changed after recovery was reviewed")
                db.execute("""INSERT OR IGNORE INTO revisions
                    (revision,screenplay,updated_at) VALUES (?,?,?)""",
                    (expected_revision,current["screenplay"],now()))
                db.execute("""UPDATE film_metadata SET screenplay=?,revision=?,
                    updated_at=? WHERE id=1""",
                    (screenplay,expected_revision+1,now()))
                db.execute("""CREATE TABLE IF NOT EXISTS recovery_receipts(
                    receipt_id TEXT PRIMARY KEY,
                    selected_commit_sequence INTEGER NOT NULL,
                    resulting_revision INTEGER NOT NULL,
                    source_sha256 TEXT NOT NULL, recorded_at TEXT NOT NULL)""")
                db.execute("""INSERT INTO recovery_receipts VALUES (?,?,?,?,?)""",(
                    secrets.token_hex(16),commit_sequence,expected_revision+1,
                    hashlib.sha256(screenplay.encode("utf8")).hexdigest(),now()))
            self._change(pid,token,revise)
            return self.read(pid,token)

    def recovery_receipts(self,pid,token):
        with self._guard:
            key=self._session(pid,token)
            db,_=self._read_db(self._folder(pid),pid,key)
            try:
                exists=db.execute("""SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name='recovery_receipts'""").fetchone()
                if not exists:
                    return []
                return [dict(r) for r in db.execute(
                    "SELECT * FROM recovery_receipts ORDER BY recorded_at")]
            finally:
                db.close()

    def recovery_candidates(self,pid,token):
        """Return authenticated immutable revision IDs for human review.

        Recovery never silently rolls back an accepted edit. HEAD must still
        verify; independent file integrity checks run on chosen revision.
        """
        with self._guard:
            key=self._session(pid,token)
            folder=self._folder(pid)
            _,head=self._read_db(folder,pid,key)
            entries=[]
            for seq in range(head["sequence"]+1):
                path=folder/"revisions"/f"db.{seq:012d}.nvpsealed"
                if not path.is_file():
                    continue
                try:
                    raw=io.BytesIO()
                    _decrypt_file(path,raw,key=key,project_id=pid,
                                  name=f"live-sqlite-v1/{seq}")
                    con=self._open_sqlite(raw.getvalue())
                    value=con.execute("SELECT revision FROM film_metadata").fetchone()[0]
                    con.close()
                    entries.append({"commit_sequence":seq,"screenplay_revision":value})
                except Exception:
                    # Never offer an unauthenticated checkpoint for restore.
                    continue
            return entries
