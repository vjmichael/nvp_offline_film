"""P1-F finite multi-shot Cycles reel execution with durable fail-closed journal.

Each picture instant is an original-Take-addressed, independently audited
Blender worker job. A batch creator approval is ONLY admission to this
finite source manifest; each actual worker still needs its own exact host
authorization and private-film sandbox proof. No token is replayed, no
interrupted job is accepted, no partial film is a completed master.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import time

from backend.nvp_film_index import FilmIndex, _require_pid, _id
from backend.nvp_p1f_p2_reel_plan import P1FReelPlan
from backend.nvp_p1f_cycles_picture_sound import P1FOriginalPictureSound

FORMAT="nvp.p1f.durable_source_bound_multishot.v1"
BATCH_ID=re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,39}$")
MAX_FRAMES_PER_BATCH=240
ACTIVE=frozenset(("RUNNING","CANCEL_REQUESTED"))
TERMINAL=frozenset(("ACCEPTED","FAILED","CANCELLED","INTERRUPTED","INVALIDATED"))


def _canonical(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),
                      allow_nan=False,ensure_ascii=True)


def _sha(v):
    return sha256(_canonical(v).encode("ascii")).hexdigest()


class P1FDurableShotReels:
    """Trusted-host only; one worker per frame and no silent resume/replay."""

    def __init__(self,index:FilmIndex,renderer:P1FOriginalPictureSound,
                 *,approve_batch,verify_batch_live):
        if (not isinstance(index,FilmIndex) or
                not isinstance(renderer,P1FOriginalPictureSound) or
                not callable(approve_batch) or not callable(verify_batch_live)):
            raise TypeError("Native FilmIndex, source-authored renderer and creator gate required")
        self.index=index
        self.renderer=renderer
        self.reels=P1FReelPlan(index)
        self.approve_batch=approve_batch
        self.verify_batch_live=verify_batch_live
        self.db=renderer.supervisor.root/"p1f_durable_shots.sqlite3"
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS source_batches (
                    batch_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL, plan_sha TEXT NOT NULL,
                    manifest_json TEXT NOT NULL, manifest_sha TEXT NOT NULL,
                    state TEXT NOT NULL, created_ns INTEGER NOT NULL,
                    updated_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_frames (
                    batch_id TEXT NOT NULL, frame_index INTEGER NOT NULL,
                    job_id TEXT NOT NULL UNIQUE, state TEXT NOT NULL,
                    source_sha TEXT NOT NULL, receipt_sha TEXT,
                    receipt_json TEXT, error TEXT,
                    PRIMARY KEY(batch_id, frame_index),
                    FOREIGN KEY(batch_id) REFERENCES source_batches(batch_id)
                );
            """)

    @contextmanager
    def _connect(self):
        db=sqlite3.connect(self.db,timeout=20,isolation_level=None)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA busy_timeout=20000")
            db.execute("PRAGMA foreign_keys=ON")
            yield db
        finally:
            db.close()

    def create_batch(self,pid,plan_id,batch_id,*,reel_index,
                     first_frame_offset,frame_count,creator_event):
        _require_pid(pid);_id(plan_id,"original reel plan")
        if type(batch_id) is not str or not BATCH_ID.fullmatch(batch_id):
            raise ValueError("Invalid durable source batch identity")
        if (type(reel_index) is not int or reel_index<0 or
                type(first_frame_offset) is not int or first_frame_offset<0 or
                type(frame_count) is not int or
                not 1<=frame_count<=MAX_FRAMES_PER_BATCH):
            raise ValueError("Finite batch needs exact frame range and reel")
        plan=self.reels.read(pid,plan_id)
        reels=plan["data"]["reels"]
        if reel_index>=len(reels) or (
                first_frame_offset+frame_count>reels[reel_index]["frame_count"]):
            raise ValueError("A finite source batch may not cross a 10-second reel")
        slug=sha256(_canonical([pid,plan_id,batch_id]).encode()).hexdigest()[:20]
        shots=[]
        for offset in range(first_frame_offset,first_frame_offset+frame_count):
            shot=self.reels.picture_instant(pid,plan_id,reel_index,offset)
            if shot["edit_document_sha256"]!=plan["data"]["edit_document_sha256"]:
                raise RuntimeError("Original source edit identity changed")
            shots.append({
                "reel_index":reel_index,"frame_offset":offset,
                "global_frame":shot["output_frame"],
                "source_tick":shot["source_tick"],
                "output_tick":shot["output_tick"],
                "take_id":shot["source_take_id"],
                "take_sha256":shot["source_take_sha256"],
                "camera_path":shot["source_camera"],
                "job_id":f"p1f_{slug}_{offset:05d}",
            })
        doc={
            "format":FORMAT,"project_id":pid,"plan_id":plan_id,
            "plan_document_sha256":plan["document_sha256"],
            "batch_id":batch_id,"source_frames":shots,
            "creator_worker_authorized":False,
            "entire_reel_rendered":False,
            "film_master_approved":False,
        }
        hash_=_sha(doc)
        approval={
            "operation":"nvp.p1f.admit_finite_source_batch.v1",
            "project_id":pid,"plan_id":plan_id,
            "plan_document_sha256":plan["document_sha256"],
            "batch_id":batch_id,"batch_document_sha256":hash_,
            "frame_count":len(shots),
        }
        if self.approve_batch(creator_event,dict(approval)) is not True:
            raise PermissionError("Creator did not authorize this exact finite source manifest")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM source_batches WHERE batch_id=?",(batch_id,)
            ).fetchone():
                raise RuntimeError("One-use batch ID already registered; no replay")
            # An attacker or a racing creator UI could otherwise mint a NEW
            # batch/job ID for the SAME source frame while the first durable
            # Job is queued/running/accepted. Check under the exact SQLite
            # BEGIN IMMEDIATE writer lease, not in an earlier UI preflight.
            requested={shot["global_frame"] for shot in shots}
            previous=db.execute("""SELECT b.batch_id,b.manifest_json,
                  b.manifest_sha,b.plan_sha,f.frame_index,f.job_id,
                  f.state,f.source_sha
                  FROM source_batches b JOIN source_frames f
                    ON f.batch_id=b.batch_id
                  WHERE b.project_id=? AND b.plan_id=?
                  ORDER BY b.batch_id,f.frame_index""",(pid,plan_id)).fetchall()
            for old_id,old_raw,old_digest,old_plan,idx,old_job,state,old_sha in previous:
                if old_plan!=plan["document_sha256"]:
                    raise RuntimeError("Previous batch references changed source plan")
                try:
                    prior=json.loads(old_raw)
                    frame=prior["source_frames"][idx]
                    valid=(_canonical(prior)==old_raw and
                           _sha(prior)==old_digest and
                           prior["project_id"]==pid and
                           prior["plan_id"]==plan_id and
                           prior["batch_id"]==old_id and
                           prior["plan_document_sha256"]==old_plan and
                           frame["job_id"]==old_job and
                           _sha(frame)==old_sha)
                except (KeyError,IndexError,TypeError,ValueError) as exc:
                    raise RuntimeError("Historical source frame ledger is malformed") from exc
                if not valid:
                    raise RuntimeError("Historical source frame provenance changed")
                if frame["global_frame"] in requested and state not in (
                        "FAILED","CANCELLED","INTERRUPTED"):
                    raise RuntimeError(
                        "Original film frame already queued, accepted or untrusted; no overlapping worker admission")
            now=time.time_ns()
            db.execute("""INSERT INTO source_batches VALUES(?,?,?,?,?,?,?, ?,?)""",
                       (batch_id,pid,plan_id,plan["document_sha256"],
                        _canonical(doc),hash_,"PLANNED",now,now))
            db.executemany("""INSERT INTO source_frames(
                batch_id,frame_index,job_id,state,source_sha)
                VALUES(?,?,?,?,?)""",[
                    (batch_id,i,shot["job_id"],"PLANNED",_sha(shot))
                    for i,shot in enumerate(shots)])
            db.commit()
        return {"status":"PLANNED","batch_id":batch_id,"frames":len(shots),
                "manifest_sha256":hash_,"entire_film_rendered":False}

    def _manifest(self,batch_id):
        if type(batch_id) is not str or not BATCH_ID.fullmatch(batch_id):
            raise ValueError("Invalid durable batch")
        with self._connect() as db:
            row=db.execute("""SELECT project_id,plan_id,plan_sha,
                manifest_json,manifest_sha,state FROM source_batches
                WHERE batch_id=?""",(batch_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown finite source batch")
        pid,plan_id,source_sha,raw,digest,state=row
        try:
            doc=json.loads(raw)
        except (TypeError,ValueError) as exc:
            raise RuntimeError("Unreadable durable source batch") from exc
        if (_canonical(doc)!=raw or _sha(doc)!=digest or
                doc.get("format")!=FORMAT or doc.get("project_id")!=pid or
                doc.get("plan_id")!=plan_id or doc.get("batch_id")!=batch_id or
                doc.get("plan_document_sha256")!=source_sha or
                doc.get("creator_worker_authorized") is not False or
                doc.get("entire_reel_rendered") is not False or
                doc.get("film_master_approved") is not False):
            raise RuntimeError("Tampered or overstated source batch manifest")
        plan=self.reels.read(pid,plan_id)
        if plan["document_sha256"]!=source_sha:
            raise RuntimeError("Original reel plan changed since batch authorization")
        return doc,state

    def run_next(self,batch_id,*,creator_event,width=320,height=180,samples=8,
                 reviewed_look_id=None):
        """Run ONE fresh, still-authorized frame; never resume interrupted work."""
        doc,state=self._manifest(batch_id)
        if state!="PLANNED":
            raise RuntimeError("Batch cancelled/blocked; no further worker dispatch")
        # Recheck current host creator policy for EACH new worker; approval
        # of a batch does not create an indefinite or revocation-proof grant.
        scope={
            "operation":"nvp.p1f.verify_finite_source_batch_live.v1",
            "project_id":doc["project_id"],"plan_id":doc["plan_id"],
            "plan_document_sha256":doc["plan_document_sha256"],
            "batch_id":batch_id,
            "batch_document_sha256":_sha(doc),
            "frame_count":len(doc["source_frames"]),
        }
        if self.verify_batch_live(dict(scope)) is not True:
            raise PermissionError("Finite creator approval revoked or no longer current")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT frame_index,job_id,source_sha
                 FROM source_frames WHERE batch_id=? AND state='PLANNED'
                 ORDER BY frame_index LIMIT 1""",(batch_id,)).fetchone()
            if row is None:
                db.commit()
                return {"status":"NO_PENDING_FRAMES","batch_id":batch_id}
            index,job_id,source_sha=row
            frame=doc["source_frames"][index]
            if frame["job_id"]!=job_id or _sha(frame)!=source_sha:
                raise RuntimeError("Durable source frame changed since creator authorization")
            changed=db.execute("""UPDATE source_frames SET state='RUNNING'
                    WHERE batch_id=? AND frame_index=? AND state='PLANNED'""",
                   (batch_id,index)).rowcount
            if changed!=1:
                raise RuntimeError("Duplicate or racing source worker")
            db.commit()
        # Each physical worker still performs its own one-use creator
        # authorization and independently established FS/network isolation.
        try:
            render=self.renderer.render_frame(
                doc["project_id"],doc["plan_id"],
                frame["reel_index"],frame["frame_offset"],job_id,
                creator_event=creator_event,
                width=width,height=height,samples=samples,
                reviewed_look_id=reviewed_look_id)
            if (render.get("format")!="nvp.p1f.independent_picture_audio_receipt.v1"
                    or render.get("passed") is not True or
                    render.get("job_id")!=job_id or
                    render.get("plan_document_sha256")!=doc["plan_document_sha256"] or
                    render.get("entire_film_rendered") is not False):
                raise RuntimeError("Native worker did not independently deliver picture and sound")
            again=self.renderer.verify_delivered(
                doc["project_id"],doc["plan_id"],job_id)
            if again!=render:
                raise RuntimeError("Reopened verified worker delivery receipt differs")
            serialized=_canonical(render)
            digest=sha256(serialized.encode()).hexdigest()
        except BaseException as exc:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current=db.execute("""SELECT state FROM source_frames
                     WHERE batch_id=? AND frame_index=?""",(batch_id,index)).fetchone()
                if current is not None:
                    target=("CANCELLED" if current[0]=="CANCEL_REQUESTED"
                            else "FAILED" if current[0]=="RUNNING" else "INTERRUPTED")
                    db.execute("""UPDATE source_frames
                        SET state=?,error=? WHERE batch_id=? AND frame_index=?""",
                        (target,(type(exc).__name__+": "+str(exc))[:500],
                         batch_id,index))
                    db.execute("""UPDATE source_batches SET state='BLOCKED',updated_ns=?
                        WHERE batch_id=?""",(time.time_ns(),batch_id))
                    db.commit()
            raise
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current=db.execute("""SELECT state FROM source_frames
                 WHERE batch_id=? AND frame_index=?""",(batch_id,index)).fetchone()
            batch=db.execute("""SELECT state FROM source_batches
                 WHERE batch_id=?""",(batch_id,)).fetchone()
            if current!=("RUNNING",) or batch!=("PLANNED",):
                db.execute("""UPDATE source_frames SET state='INTERRUPTED'
                   WHERE batch_id=? AND frame_index=?""",(batch_id,index))
                db.execute("""UPDATE source_batches SET state='BLOCKED',updated_ns=?
                   WHERE batch_id=?""",(time.time_ns(),batch_id))
                db.commit()
                raise RuntimeError("Host cancellation/restart raced with Cycles acceptance")
            db.execute("""UPDATE source_frames SET state='ACCEPTED',receipt_sha=?,
                receipt_json=? WHERE batch_id=? AND frame_index=?""",
                (digest,serialized,batch_id,index))
            left=db.execute("""SELECT COUNT(*) FROM source_frames
                WHERE batch_id=? AND state!='ACCEPTED'""",(batch_id,)).fetchone()[0]
            if left==0:
                db.execute("""UPDATE source_batches SET state='FRAMES_VERIFIED',
                    updated_ns=? WHERE batch_id=?""",(time.time_ns(),batch_id))
            db.commit()
        return {"status":"FRAME_ACCEPTED","batch_id":batch_id,
                "frame_index":index,"remaining":left,
                "receipt_sha256":digest,"entire_film_rendered":False}

    def cancel(self,batch_id):
        """Persistent cancellation request; all unstarted frames cease forever."""
        self._manifest(batch_id)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("""SELECT state FROM source_batches
                    WHERE batch_id=?""",(batch_id,)).fetchone()[0]!="PLANNED":
                raise RuntimeError("Batch already terminal or blocked")
            db.execute("""UPDATE source_frames SET state='CANCELLED'
                WHERE batch_id=? AND state='PLANNED'""",(batch_id,))
            jobs=db.execute("""SELECT job_id FROM source_frames
                WHERE batch_id=? AND state='RUNNING'""",(batch_id,)).fetchall()
            db.execute("""UPDATE source_frames SET state='CANCEL_REQUESTED'
                WHERE batch_id=? AND state='RUNNING'""",(batch_id,))
            db.execute("""UPDATE source_batches SET state='BLOCKED',updated_ns=?
                WHERE batch_id=?""",(time.time_ns(),batch_id))
            db.commit()
        for (job_id,) in jobs:
            self.renderer.supervisor.cancel(job_id)
        return {"status":"CANCELLED_OR_UNTRUSTED","batch_id":batch_id,
                "pending_worker_reconciliation":len(jobs)}

    def reconcile_restart(self,batch_id):
        """Record unverified in-flight ownership, NEVER accept a guessed PID."""
        doc,_=self._manifest(batch_id)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count=db.execute("""UPDATE source_frames SET state='INTERRUPTED',
                 error='Host restarted: native worker/OS cleanup not independently proven'
                 WHERE batch_id=? AND state IN ('RUNNING','CANCEL_REQUESTED')""",
                 (batch_id,)).rowcount
            if count:
                db.execute("""UPDATE source_batches SET state='BLOCKED',updated_ns=?
                      WHERE batch_id=?""",(time.time_ns(),batch_id))
            db.commit()
        return {"batch_id":batch_id,"interrupted":count,
                "safe_to_auto_replay":False,"kernel_cleanup_verified":False}

    def verify(self,batch_id):
        """Independently re-audit every accepted frame, never accept partials."""
        doc,state=self._manifest(batch_id)
        with self._connect() as db:
            rows=db.execute("""SELECT frame_index,job_id,state,source_sha,
                receipt_sha,receipt_json FROM source_frames
                WHERE batch_id=? ORDER BY frame_index""",(batch_id,)).fetchall()
        if len(rows)!=len(doc["source_frames"]):
            raise RuntimeError("Durable batch is missing source frame rows")
        accepted=0
        for (i,job_id,frame_state,source_sha,digest,serialized) in rows:
            if (i>=len(doc["source_frames"]) or
                    _sha(doc["source_frames"][i])!=source_sha or
                    job_id!=doc["source_frames"][i]["job_id"]):
                raise RuntimeError("Authorized original-shot frame identity changed")
            if frame_state!="ACCEPTED":
                continue
            try:
                if serialized is None or sha256(serialized.encode()).hexdigest()!=digest:
                    raise RuntimeError("Durable frame audit receipt changed")
                original=json.loads(serialized)
                reopened=self.renderer.verify_delivered(
                    doc["project_id"],doc["plan_id"],job_id)
                if _canonical(reopened)!=serialized or original!=reopened:
                    raise RuntimeError("Original picture/audio changed since acceptance")
            except BaseException:
                with self._connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("""UPDATE source_frames SET state='INVALIDATED'
                        WHERE batch_id=? AND frame_index=? AND state='ACCEPTED'""",
                        (batch_id,i))
                    db.execute("""UPDATE source_batches SET state='BLOCKED',updated_ns=?
                         WHERE batch_id=?""",(time.time_ns(),batch_id))
                    db.commit()
                raise
            accepted+=1
        completed=(state=="FRAMES_VERIFIED" and accepted==len(rows))
        if state=="FRAMES_VERIFIED" and not completed:
            raise RuntimeError("Cannot publish an incomplete original-shot reel")
        return {"batch_id":batch_id,"status":state,"frames_accepted":accepted,
                "frame_count":len(rows),"all_frames_verified":completed,
                "entire_film_rendered":False,"film_master_approved":False}
