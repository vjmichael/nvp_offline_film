"""STACK-02A: independently launched Blender worker with durable, fail-closed journal.

This is a process supervisor, NOT a renderer or a Blender code library.
The trusted NVP host supplies a SHA-pinned executable, trusted-script SHA,
approved input hashes, explicit output contract and a confined workspace.
The model/browser cannot submit executable paths or arbitrary Python scripts.

Known limitation: a host crash cannot prove termination of an orphaned worker
on all OSes. Recovery marks it INTERRUPTED, never accepted, and blocks reuse.
Windows Job Objects / persistent kernel containment are a later acceptance gate.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Mapping

from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_host_lease import exclusive_worker_host

JOB_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
SHA = re.compile(r"^[a-f0-9]{64}$")
VALID_KINDS = frozenset({"png","json_audit","blend","exr"})
ALLOWED_ARGS = frozenset({"--output","--manifest","--audit","--render","--take","--plan","--out"})
TERMINAL = frozenset({"SUCCEEDED","FAILED","CANCELLED","TIMED_OUT","INTERRUPTED"})


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024*1024), b""):
            h.update(part)
    return h.hexdigest()


def _safe_relative(root: Path, name: str, *, must_exist: bool = False) -> Path:
    if not isinstance(name,str) or not name or len(name)>240 or "\x00" in name:
        raise ValueError("Invalid worker file name")
    raw=Path(name)
    if raw.is_absolute() or any(p in ("..","") for p in raw.parts):
        raise ValueError("Worker file must be relative to its approved job directory")
    resolved=(root/raw).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Worker file escapes approved directory through symlink")
    if must_exist and (not resolved.is_file() or (root/raw).is_symlink()):
        raise ValueError("Pinned worker input missing or symlinked")
    if not must_exist and (root/raw).is_symlink():
        raise ValueError("Worker output may not be a symlink")
    return resolved


@dataclass(frozen=True)
class BlenderOperation:
    job_id: str
    script: str
    script_sha256: str
    inputs: Mapping[str,str]
    outputs: Mapping[str,str]
    arguments: Mapping[str,str]
    scene: str | None = None
    timeout_seconds: int = 90
    memory_limit_mb: int = 8192
    require_linux_cgroup_v2: bool = False

    def canonical(self) -> str:
        return json.dumps(asdict(self),sort_keys=True,separators=(",",":"),allow_nan=False)


class BlenderWorkerSupervisor:
    """One active-worker host with SQLite FULL-sync journal and bounded process tree.

    The caller must be a trusted host path, not a model-exposed arbitrary command
    execution API. No worker result is accepted before all file/hash audits pass.
    """

    def __init__(self, workspace: str | Path, *, blender_executable: str | Path,
                 blender_sha256: str, blender_version: str):
        self.root=Path(workspace).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        if self.root.is_symlink():
            raise ValueError("Worker workspace must not be a symlink")
        self.db=self.root/"worker_jobs.sqlite3"
        binary=Path(blender_executable).resolve()
        if (not binary.is_file() or not SHA.fullmatch(blender_sha256) or
            not isinstance(blender_version,str) or
            not blender_version.startswith("Blender ")):
            raise ValueError("Worker binary, SHA or expected Blender version invalid")
        if binary.is_relative_to(self.root):
            raise ValueError("Blender executable must not be located in an untrusted job workspace")
        self.binary=binary
        self.binary_sha256=blender_sha256
        self.blender_version=blender_version
        self._lock=threading.RLock()
        self._running={}
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS worker_jobs (
                  job_id TEXT PRIMARY KEY, spec_sha256 TEXT NOT NULL,
                  spec_json TEXT NOT NULL, state TEXT NOT NULL,
                  created_utc REAL NOT NULL, updated_utc REAL NOT NULL,
                  worker_pid INTEGER, exit_code INTEGER, error TEXT,
                  output_manifest_json TEXT, progress_bytes INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS worker_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                  at_utc REAL NOT NULL, state TEXT NOT NULL, detail TEXT NOT NULL
                );
            """)

    @contextmanager
    def _connect(self):
        # sqlite3.Connection.__exit__ commits/rolls back, but it DOES NOT
        # close the handle. Explicit closure is essential on Windows so the
        # user can delete/uninstall worker journals without WinError 32.
        connection=sqlite3.connect(self.db,timeout=15,isolation_level=None)
        try:
            connection.execute("PRAGMA busy_timeout=15000")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            yield connection
        finally:
            connection.close()

    def _transition(self, job_id: str, state: str, *, error=None,
                    worker_pid=None, exit_code=None, outputs=None, progress=None):
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE worker_jobs SET state=?,updated_utc=?,error=?,
                worker_pid=COALESCE(?,worker_pid),exit_code=COALESCE(?,exit_code),
                output_manifest_json=COALESCE(?,output_manifest_json),
                progress_bytes=COALESCE(?,progress_bytes)
                WHERE job_id=?""",
                (state,time.time(),error,worker_pid,exit_code,
                 json.dumps(outputs,sort_keys=True) if outputs is not None else None,
                 progress,job_id))
            db.execute("INSERT INTO worker_events(job_id,at_utc,state,detail) VALUES (?,?,?,?)",
                       (job_id,time.time(),state,(error or "")[:2000]))
            db.commit()

    def inspect(self, job_id: str):
        if not JOB_ID.fullmatch(job_id):
            raise ValueError("Invalid job ID")
        with self._connect() as db:
            row=db.execute("""SELECT job_id,spec_sha256,state,created_utc,updated_utc,
                 worker_pid,exit_code,error,output_manifest_json,progress_bytes
                 FROM worker_jobs WHERE job_id=?""",(job_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown worker job")
        names=("id","spec_sha256","state","created_utc","updated_utc","worker_pid",
               "exit_code","error","output_manifest_json","progress_bytes")
        doc=dict(zip(names,row))
        doc["outputs"]=json.loads(doc.pop("output_manifest_json")) if doc["output_manifest_json"] else None
        return doc

    def verify_completed(self, job_id: str):
        """Independent restart-safe output verification; not trust in journal alone."""
        status=self.inspect(job_id)
        if status["state"]!="SUCCEEDED" or not status["outputs"]:
            raise RuntimeError("No successfully verified worker output is available")
        with self._connect() as db:
            row=db.execute("SELECT spec_json FROM worker_jobs WHERE job_id=?",(job_id,)).fetchone()
        if not row:
            raise KeyError("Worker job was not journaled")
        if hashlib.sha256(row[0].encode()).hexdigest()!=status["spec_sha256"]:
            raise RuntimeError("Worker job specification changed")
        spec=BlenderOperation(**json.loads(row[0]))
        jobdir=(self.root/job_id).resolve()
        self._check_inputs(spec,jobdir)
        fresh=self._audit_outputs(spec,jobdir)
        if fresh!=status["outputs"]:
            raise RuntimeError("Blender output changed since successful acceptance")
        return status

    def events(self, job_id: str):
        self.inspect(job_id)
        with self._connect() as db:
            records=db.execute("SELECT at_utc,state,detail FROM worker_events WHERE job_id=? ORDER BY id",(job_id,)).fetchall()
        return [{"at":a,"state":b,"detail":c} for a,b,c in records]

    def probe(self):
        if sha_file(self.binary)!=self.binary_sha256:
            raise RuntimeError("Pinned Blender executable SHA-256 changed")
        try:
            result=subprocess.run([str(self.binary),"-b","--version"],
                                  capture_output=True,text=True,timeout=15,check=False)
        except (subprocess.TimeoutExpired,OSError) as exc:
            raise RuntimeError("Pinned Blender binary failed version probe") from exc
        if result.returncode or not result.stdout.splitlines() or result.stdout.splitlines()[0].strip()!=self.blender_version:
            raise RuntimeError("Blender version differs from pinned worker policy")
        return {"blender":self.blender_version,"binary_sha256":self.binary_sha256,
                "binary_path":str(self.binary)}

    def _validate(self, op: BlenderOperation):
        if not isinstance(op,BlenderOperation) or not JOB_ID.fullmatch(op.job_id):
            raise ValueError("Invalid typed Blender job")
        if type(op.timeout_seconds) is not int or not 1<=op.timeout_seconds<=600:
            raise ValueError("Worker timeout must be 1 to 600 seconds")
        if type(op.memory_limit_mb) is not int or not 256<=op.memory_limit_mb<=65536:
            raise ValueError("Worker memory limit must be 256 to 65536 MiB")
        if type(op.require_linux_cgroup_v2) is not bool:
            raise ValueError("Strict Linux cgroup requirement must be boolean")
        if (not SHA.fullmatch(op.script_sha256) or type(op.inputs) is not dict or
            type(op.outputs) is not dict or type(op.arguments) is not dict or
            not 1<=len(op.outputs)<=12 or len(op.inputs)>32):
            raise ValueError("Invalid bounded Blender job inputs or outputs")
        jobdir=self.root/op.job_id
        if jobdir.is_symlink():
            raise ValueError("Worker job directory is a symlink")
        jobdir.mkdir(exist_ok=True)
        jobdir=jobdir.resolve()
        # Source and script are immutable during process execution.
        script=_safe_relative(jobdir,op.script,must_exist=True)
        if sha_file(script)!=op.script_sha256:
            raise RuntimeError("Blender script SHA mismatch before launch")
        for name,sha in op.inputs.items():
            if not isinstance(name,str) or not isinstance(sha,str) or not SHA.fullmatch(sha):
                raise ValueError("Unpinned worker input")
            file=_safe_relative(jobdir,name,must_exist=True)
            if sha_file(file)!=sha:
                raise RuntimeError("Worker source SHA mismatch before launch")
        if op.scene is not None and op.scene not in op.inputs:
            raise ValueError("Scene .blend must be explicitly pinned as input")
        for name,kind in op.outputs.items():
            if kind not in VALID_KINDS:
                raise ValueError("Unsupported worker output media type")
            target=_safe_relative(jobdir,name)
            if target.exists():
                raise RuntimeError("Worker output exists before launch; do not overwrite results")
            target.parent.mkdir(parents=True,exist_ok=True)
        if len(op.arguments)>12 or any(flag not in ALLOWED_ARGS for flag in op.arguments):
            raise ValueError("Only declared Blender worker script flags are allowed")
        argv=[]
        for flag,value in op.arguments.items():
            if type(value) is not str:
                raise ValueError("Blender argument must be a workspace-relative file/directory")
            target=_safe_relative(jobdir,value)
            # Inputs and outputs must be specifically authorized in the contract.
            if value not in op.inputs and value not in op.outputs:
                if not (flag=="--out" and target.is_relative_to(jobdir)):
                    raise ValueError("Unlisted worker input/output path")
            argv.extend([flag,str(target)])
        return jobdir,script,argv

    def _audit_outputs(self, op: BlenderOperation, jobdir: Path):
        manifest={}
        for rel,kind in op.outputs.items():
            path=_safe_relative(jobdir,rel,must_exist=True)
            size=path.stat().st_size
            if not 8<=size<=512*1024*1024:
                raise RuntimeError("Blender output size outside approved bound")
            with path.open("rb") as f:
                head=f.read(8)
            if ((kind=="png" and head!=b"\x89PNG\r\n\x1a\n") or
                # Blender 5.x can save Zstandard-compressed .blend containers
                # (28 b5 2f fd), not just legacy raw BLENDER headers. Media
                # magic is only a preflight; independent Blender reopen/audit
                # establishes actual scene validity before NVP acceptance.
                (kind=="blend" and not (head.startswith(b"BLENDER") or
                    head.startswith(bytes.fromhex("28b52ffd")))) or
                (kind=="exr" and head[:4]!=b"\x76\x2f\x31\x01")):
                raise RuntimeError("Blender output failed media magic verification")
            if kind=="json_audit":
                doc=json.loads(path.read_text("utf8"))
                if doc.get("passed") is not True:
                    raise RuntimeError("Blender audit JSON lacks explicit passed=true")
            manifest[rel]={"kind":kind,"bytes":size,"sha256":sha_file(path)}
        return manifest

    def _check_inputs(self, op: BlenderOperation, jobdir: Path):
        if sha_file(_safe_relative(jobdir,op.script,must_exist=True))!=op.script_sha256:
            raise RuntimeError("Trusted Blender script changed during worker execution")
        for rel,sha in op.inputs.items():
            if sha_file(_safe_relative(jobdir,rel,must_exist=True))!=sha:
                raise RuntimeError("Approved worker input changed during execution")

    def _terminate_tree(self, proc):
        if not hasattr(proc, "terminate_tree"):
            raise RuntimeError("Uncontained worker is forbidden")
        proc.terminate_tree()
        if proc.poll() is None:
            raise RuntimeError("Kernel-contained worker termination unproven")

    def cancel(self, job_id: str):
        with self._lock:
            token=self._running.get(job_id)
        if token is None:
            return False
        token.set()
        return True

    @exclusive_worker_host
    def recover_interrupted(self):
        """After restart never accept or replay an in-flight job automatically.

        This records that OS-level orphan cleanup remains UNPROVEN, not success.
        Cross-process exclusive ownership is enforced by the OS lease; a
        second active NVP instance cannot steal live worker journal ownership.
        """
        with self._lock:
            if self._running:
                raise RuntimeError("Cannot recover while this supervisor owns live processes")
            with self._connect() as db:
                records=db.execute("SELECT job_id FROM worker_jobs WHERE state IN ('RUNNING','CANCEL_REQUESTED')").fetchall()
            for (job_id,) in records:
                self._transition(job_id,"INTERRUPTED",
                    error="Host restarted while worker running; output is untrusted; orphan cleanup not proven")
        return [r[0] for r in records]

    @exclusive_worker_host
    def run(self, op: BlenderOperation):
        if not isinstance(op, BlenderOperation) or not JOB_ID.fullmatch(op.job_id):
            raise ValueError("Invalid typed Blender job")
        digest=hashlib.sha256(op.canonical().encode()).hexdigest()
        # Query the durable ledger before touching the workspace. A replay of
        # an accepted ID must be rejected as a duplicate, not as an unexpected
        # preexisting output file; altered IDs are an explicit conflict.
        with self._lock,self._connect() as prior_db:
            previous=prior_db.execute(
                "SELECT spec_sha256 FROM worker_jobs WHERE job_id=?",
                (op.job_id,)).fetchone()
        if previous is not None:
            if previous[0]!=digest:
                raise RuntimeError("Idempotency ID reused for different Blender operation")
            raise RuntimeError("Blender job already registered; never rerun or overwrite an existing attempt")
        jobdir,script,script_args=self._validate(op)
        self.probe()
        with self._lock,self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            exists=db.execute("SELECT spec_sha256,state FROM worker_jobs WHERE job_id=?",(op.job_id,)).fetchone()
            if exists:
                db.rollback()
                if exists[0]!=digest:
                    raise RuntimeError("Idempotency ID reused for different Blender operation")
                raise RuntimeError("Blender job already registered; never rerun or overwrite an existing attempt")
            now=time.time()
            db.execute("""INSERT INTO worker_jobs
                (job_id,spec_sha256,spec_json,state,created_utc,updated_utc)
                VALUES (?,?,?,?,?,?)""",(op.job_id,digest,op.canonical(),"PREPARED",now,now))
            db.execute("INSERT INTO worker_events(job_id,at_utc,state,detail) VALUES (?,?,?,?)",
                       (op.job_id,now,"PREPARED","Pinned inputs checked"))
            db.commit()
        log=jobdir/"worker_stdout.log"
        err=jobdir/"worker_stderr.log"
        command=[str(self.binary),"-b"]
        if op.scene:
            command.append(str(_safe_relative(jobdir,op.scene,must_exist=True)))
        else:
            command.append("--factory-startup")
        # Blender defaults can treat Python exceptions as a nonfatal CLI
        # condition. Ensure script exceptions produce nonzero process exit
        # even if a partial output file was left behind.
        command+=["-t","2","--python-exit-code","70","--python",str(script),"--"]+script_args
        token=threading.Event()
        proc=None
        with self._lock:
            self._running[op.job_id]=token
        try:
            with log.open("wb") as stdout, err.open("wb") as stderr:
                proc=launch_contained(command,cwd=str(jobdir),stdout=stdout,stderr=stderr,
                                      memory_mb=op.memory_limit_mb,
                                      linux_cgroup_tree_required=op.require_linux_cgroup_v2)
                self._transition(op.job_id,"RUNNING",worker_pid=proc.pid)
                started=time.monotonic()
                while proc.poll() is None:
                    if token.is_set():
                        self._transition(op.job_id,"CANCEL_REQUESTED")
                        self._terminate_tree(proc)
                        self._transition(op.job_id,"CANCELLED",exit_code=proc.returncode,
                                         error="Explicit creator/host cancellation")
                        return self.inspect(op.job_id)
                    if time.monotonic()-started>op.timeout_seconds:
                        self._terminate_tree(proc)
                        self._transition(op.job_id,"TIMED_OUT",exit_code=proc.returncode,
                                         error="Pinned Blender operation exceeded time budget")
                        return self.inspect(op.job_id)
                    time.sleep(.1)
                    self._transition(op.job_id,"RUNNING",progress=log.stat().st_size)
                rc=proc.wait(timeout=10)
                if token.is_set():
                    self._transition(op.job_id,"CANCELLED",exit_code=rc,
                                     error="Cancellation requested before output acceptance")
                    return self.inspect(op.job_id)
                if rc:
                    raise RuntimeError("Blender worker returned nonzero exit code "+str(rc))
                self._check_inputs(op,jobdir)
                audited=self._audit_outputs(op,jobdir)
                self._transition(op.job_id,"SUCCEEDED",exit_code=0,outputs=audited,
                                 progress=log.stat().st_size)
                return self.inspect(op.job_id)
        except Exception as exc:
            if proc is not None and proc.poll() is None:
                self._terminate_tree(proc)
            self._transition(op.job_id,"FAILED",exit_code=proc.returncode if proc is not None else None,
                             error=(type(exc).__name__+": "+str(exc))[:2000])
            return self.inspect(op.job_id)
        finally:
            if proc is not None and hasattr(proc,"close"):
                proc.close()
            with self._lock:
                self._running.pop(op.job_id,None)
