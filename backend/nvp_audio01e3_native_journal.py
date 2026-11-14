"""AUDIO-01E.3: durable audio job journal and trusted-host recovery gate.

Host-side coordination for existing AUDIO-01D/E.2 functions. Does NOT launch
an OS-contained process or independently authenticate the user: callers must
supply a trusted creator approval callback and a stopped-worker attestation.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import sqlite3
from pathlib import Path

from backend.nvp_audio01d_chunked_recovery import (
    _read_state, _audit_chunks, _validate, _check_inputs,
)
from backend.nvp_audio01e2_orphan_recovery import reconcile_next_chunk
from backend.nvp_audio_checkpoint_stage_recovery import reconcile_checkpoint_stage
from backend.nvp_film_index import _id

FORMAT = "nvp.audio.native_job_journal.v1"
STATES = {"approved", "running", "recovery_required", "reconciled",
          "completed", "failed"}
TRANSITIONS = {
    "approved": {"running", "recovery_required", "failed"},
    "running": {"recovery_required", "completed", "failed"},
    "recovery_required": {"reconciled", "failed"},
    "reconciled": {"running", "completed", "recovery_required", "failed"},
    "completed": set(), "failed": set(),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class AudioJobJournal:
    """Persistent transitions and exact input binding, one job per identity.

    SQLite BEGIN IMMEDIATE serializes concurrent journal transitions, but
    external native worker exclusivity is still a host responsibility.
    """

    def __init__(self, database):
        self.path = Path(database)
        if self.path.is_symlink() or not self.path.parent.is_dir():
            raise RuntimeError("Untrusted journal database path")
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS audio_native_jobs(
                job_id TEXT PRIMARY KEY,
                spec_json TEXT NOT NULL, spec_sha TEXT NOT NULL,
                state TEXT NOT NULL, generation INTEGER NOT NULL,
                last_next_sample INTEGER NOT NULL,
                requires_cleanup INTEGER NOT NULL DEFAULT 0
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS audio_native_events(
                job_id TEXT NOT NULL, seq INTEGER NOT NULL,
                generation INTEGER NOT NULL, prev_state TEXT,
                next_state TEXT NOT NULL, next_sample INTEGER NOT NULL,
                note TEXT NOT NULL,
                PRIMARY KEY(job_id,seq),
                FOREIGN KEY(job_id) REFERENCES audio_native_jobs(job_id)
            )""")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(str(self.path), timeout=20)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=20000")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def register(self, job_id, plan, sources, total_samples, directory, *,
                 verify_creator_action, creator_event):
        """Only trusted desktop creator policy may authorize the exact scope."""
        _id(job_id, "native audio job identity")
        if not callable(verify_creator_action):
            raise TypeError("Trusted native creator verifier required")
        _validate(plan, sources, total_samples)
        paths = {sid: str(Path(path).resolve(strict=True))
                 for sid,path in sources.items()}
        target = Path(directory)
        if (target.is_symlink() or target.parent.is_symlink() or
            not target.parent.is_dir()):
            raise RuntimeError("Unsafe authorized audio staging directory")
        spec = {"format": FORMAT, "job_id": job_id, "plan": plan,
                "sources": paths, "total_samples": total_samples,
                "directory": str(target.absolute()),
                "source_sha256": {
                    sid: _sha_source(paths[sid]) for sid in sorted(paths)},
                "final_master": False, "director_approved": False}
        if verify_creator_action(creator_event, dict(spec)) is not True:
            raise PermissionError("Creator did not approve this native audio job")
        raw = canonical(spec).decode("ascii")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO audio_native_jobs(
                job_id,spec_json,spec_sha,state,generation,last_next_sample
            ) VALUES(?,?,?,?,?,?)""",(job_id,raw,digest(spec),"approved",0,0))
            db.execute("""INSERT INTO audio_native_events(
                job_id,seq,generation,prev_state,next_state,next_sample,note
            ) VALUES(?,1,0,NULL,'approved',0,'creator_authorized')""",(job_id,))
        return {"job_id": job_id,"state":"approved","spec_sha256":digest(spec)}

    def read(self, job_id):
        with self._db() as db:
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM audio_native_jobs WHERE job_id=?",
                           (job_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown audio job")
        result=dict(row)
        spec=json.loads(result["spec_json"])
        if digest(spec)!=result["spec_sha"] or spec.get("job_id")!=job_id:
            raise RuntimeError("Native audio job spec changed")
        result["spec"]=spec
        return result

    def transition(self, job_id, expected_generation, new_state, note, *,
                   next_sample=None, cleanup_required=None):
        if new_state not in STATES or type(note) is not str or not 1<=len(note)<=160:
            raise ValueError("Invalid audio journal transition")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT state,generation,last_next_sample,
                        requires_cleanup FROM audio_native_jobs WHERE job_id=?""",
                        (job_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown audio job")
            old,gen,sample,cleanup=row
            if gen!=expected_generation or new_state not in TRANSITIONS[old]:
                raise RuntimeError("Stale or illegal audio journal transition")
            if next_sample is None:
                next_sample=sample
            if (type(next_sample) is not int or
                next_sample<sample or next_sample>self.read(job_id)["spec"]["total_samples"]):
                raise ValueError("Invalid progress checkpoint")
            if cleanup_required is not None:
                if type(cleanup_required) is not bool:
                    raise TypeError("Cleanup flag must be boolean")
                cleanup=int(cleanup_required)
            updated=db.execute("""UPDATE audio_native_jobs SET
                state=?,generation=?,last_next_sample=?,requires_cleanup=?
                WHERE job_id=? AND generation=?""",
                (new_state,gen+1,next_sample,cleanup,job_id,gen)).rowcount
            if updated!=1:
                raise RuntimeError("Concurrent audio transition")
            db.execute("""INSERT INTO audio_native_events(
                job_id,seq,generation,prev_state,next_state,next_sample,note)
                VALUES(?,?,?,?,?,?,?)""",
                (job_id,gen+2,gen+1,old,new_state,next_sample,note))
        return {"state":new_state,"generation":gen+1,"next_sample":next_sample}

    def recover(self, job_id, *, attest_stopped):
        """Only after host confirms worker-tree termination/exclusive ownership.

        No optimistic recovery while a worker may still be alive.
        """
        row=self.read(job_id)
        if row["state"]!="recovery_required":
            raise RuntimeError("Recovery was not authorized by the journal")
        spec=row["spec"]
        if not callable(attest_stopped) or attest_stopped(job_id,spec)!=True:
            raise PermissionError("Host did not attest stopped worker and exclusive staging")
        sources=spec["sources"]
        for sid,expected in spec["source_sha256"].items():
            if _sha_source(sources[sid])!=expected:
                raise RuntimeError("Original authorized audio source changed")
        staged=reconcile_checkpoint_stage(spec["plan"],sources,spec["total_samples"],
                                           spec["directory"])
        # If a crash occurred after writing the final completion marker, the
        # source-verified chunk chain already covers the full intended range.
        current=_read_state(Path(spec["directory"]))
        if current["status"]=="complete":
            result={"status":"COMPLETED_CHECKPOINT_AFTER_RECOVERY","stage":staged}
        else:
            result=reconcile_next_chunk(spec["plan"],sources,spec["total_samples"],
                                        spec["directory"])
        stage=_read_state(Path(spec["directory"]))
        progress=_audit_chunks(Path(spec["directory"]),stage)
        if progress<row["last_next_sample"]:
            raise RuntimeError("Recovered checkpoint regressed")
        state=self.transition(job_id,row["generation"],"reconciled",
                              "source_verified_reconciliation",
                              next_sample=progress,cleanup_required=False)
        return {**state,"reconciliation":result}


def _sha_source(path):
    from backend.nvp_audio01_picture_follow import _sha_file
    return _sha_file(path)
