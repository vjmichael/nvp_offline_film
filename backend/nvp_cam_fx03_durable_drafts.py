"""CAM-FX-03/04: durable director camera drafts and model attempt custody.

All draft edits, undo, status changes and completed AI candidates are atomic
SQLite transactions with optimistic revision checks. A partially interrupted
native OS approval is NEVER retried. The authoritative approved camera rail
is a separate FilmIndex revision; draft history cannot grant execution rights.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import json
import secrets
import sqlite3
import threading

from backend.nvp_film_index import FilmIndex,_require_pid,_id
from backend.nvp_studio import now
from backend.nvp_cam_fx01_camera_rails import (
    OriginalCameraRails,normalize_rail,_hash)
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank

FORMAT="nvp.cam_fx03.durable_original_camera_rail_draft.v1"
ATTEMPT="nvp.cam_fx04.durable_unapproved_model_camera_proposal.v1"
MAX_UNDO=24
MAX_ROWS=128

def _json(x):
    return json.dumps(x,sort_keys=True,ensure_ascii=True,
                      allow_nan=False,separators=(",",":"))

def _sha(x):
    if type(x) is not str or len(x)!=64 or any(
            c not in "0123456789abcdef" for c in x):
        raise ValueError("Expected source-bound lowercase SHA256")
    return x

def _attempt(x):
    if (type(x) is not str or len(x)!=24 or
        any(c not in "0123456789abcdef" for c in x)):
        raise PermissionError("Only NVP-minted model attempt IDs")
    return x

class DurableOriginalCameraDrafts:
    def __init__(self,index:FilmIndex,root,*,host_session_id):
        if not isinstance(index,FilmIndex):
            raise TypeError("Original director FilmIndex is required")
        p=Path(root)
        if not p.is_absolute() or p.is_symlink():
            raise PermissionError("Camera draft storage must be a host-owned absolute directory")
        p.mkdir(parents=True,exist_ok=True)
        self.root=p.resolve()
        self.path=self.root/"original-camera-rail-drafts.sqlite3"
        self.index=index
        self.lock=threading.RLock()
        self.session=_sha(host_session_id) if len(host_session_id)==64 else None
        if (self.session is None or
            self.path.is_symlink()):
            raise PermissionError("Camera draft journal needs a host session and safe SQLite path")
        self.rails=OriginalCameraRails(
            index,verify_director_action=lambda *_:False)
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS camera_drafts(
              draft_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              rail_id TEXT NOT NULL,
              base_revision INTEGER NOT NULL,
              base_sha TEXT,
              version INTEGER NOT NULL,
              state TEXT NOT NULL,
              spec_json TEXT NOT NULL,
              undo_json TEXT NOT NULL,
              spec_sha TEXT NOT NULL,
              preview_sha TEXT NOT NULL,
              source_take_sha TEXT NOT NULL,
              layer_sha TEXT NOT NULL,
              published_revision INTEGER,
              published_sha TEXT,
              proposed_by TEXT NOT NULL,
              model_evidence_json TEXT,
              publishing_session_id TEXT,
              updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_camfx_draft_project
              ON camera_drafts(project_id,updated_at);
            CREATE TABLE IF NOT EXISTS camera_model_attempts(
              attempt_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              draft_id TEXT NOT NULL,
              model_id TEXT NOT NULL,
              base_version INTEGER NOT NULL,
              rail_spec_sha TEXT NOT NULL,
              source_context_sha TEXT NOT NULL,
              direction_sha TEXT NOT NULL,
              host_session_id TEXT NOT NULL,
              state TEXT NOT NULL,
              failure_category TEXT,
              result_version INTEGER,
              provider_receipt_sha TEXT,
              updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_camfx_model_project
              ON camera_model_attempts(project_id,updated_at);
            """)

    @contextmanager
    def _db(self):
        db=sqlite3.connect(str(self.path),timeout=15,isolation_level=None)
        db.row_factory=sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA busy_timeout=15000")
            yield db
        finally:
            db.close()

    def _source_head(self,pid,rail_id,revision):
        _require_pid(pid);_id(rail_id,"original camera rail ID")
        if type(revision) is not int or revision<0:
            raise ValueError("Exact rail base revision required")
        head=None
        try:
            head=self.index.read_revision(pid,rail_id)
        except KeyError:
            pass
        if (head["revision"] if head else 0)!=revision:
            raise RuntimeError("Rail source base changed; reload before editing")
        return head["document_sha256"] if head else None

    def _row(self,db,pid,did):
        _require_pid(pid);_attempt(did)
        row=db.execute("""SELECT * FROM camera_drafts WHERE
                         project_id=? AND draft_id=?""",(pid,did)).fetchone()
        if row is None:
            raise KeyError("No project-owned camera source draft")
        return row

    def _reconcile(self,db,pid):
        # Old process generation is never resumed. In-progress OS decisions
        # are terminal until the director explicitly requests a NEW approval.
        db.execute("""UPDATE camera_model_attempts
            SET state='INTERRUPTED_REQUIRES_NEW_GENERATION',
                failure_category='old_host_session',updated_at=?
            WHERE project_id=? AND state='GENERATING' AND
                  host_session_id<>?""",(now(),pid,self.session))
        db.execute("""UPDATE camera_drafts
            SET state='INTERRUPTED_REQUIRES_NEW_APPROVAL',updated_at=?
            WHERE project_id=? AND state='PUBLISHING'
              AND publishing_session_id<>?""",
            (now(),pid,self.session))

    def _result(self,row,*,validate_source=True):
        spec=json.loads(row["spec_json"])
        state=row["state"]
        base_current=True
        try:
            self._source_head(row["project_id"],row["rail_id"],row["base_revision"])
        except RuntimeError:
            base_current=False
        if validate_source and state=="DRAFT" and base_current:
            preview=self.rails.preview(
                row["project_id"],row["rail_id"],spec,
                expected_revision=row["base_revision"])
            if (preview["proposal_sha256"]!=row["preview_sha"] or
                preview["rail_layer_sha256"]!=row["layer_sha"] or
                preview["world_take_sha256"]!=row["source_take_sha"]):
                raise RuntimeError("Durable camera draft evidence no longer matches source")
        return {
            "format":FORMAT,
            "draft_id":row["draft_id"],"project_id":row["project_id"],
            "rail_id":row["rail_id"],"base_revision":row["base_revision"],
            "base_sha256":row["base_sha"],"version":row["version"],
            "state":(state if base_current or state=="PUBLISHED" else
                "STALE_SOURCE_REQUIRES_NEW_DRAFT"),
            "rail_spec":spec,
            "spec_sha256":row["spec_sha"],
            "proposal_sha256":row["preview_sha"],
            "stronger_usd_sha256":row["layer_sha"],
            "source_world_take_sha256":row["source_take_sha"],
            "undo_depth":len(json.loads(row["undo_json"])),
            "proposed_by":row["proposed_by"],
            "published_revision":row["published_revision"],
            "published_sha256":row["published_sha"],
            "model_evidence":json.loads(row["model_evidence_json"])
                if row["model_evidence_json"] else None,
            "native_approval_granted":False,
            "source_actor_takes_and_pcm_changed":False}

    def _normalized(self,pid,spec):
        if type(spec) is not dict:
            raise ValueError("Only exact camera rail source data may save")
        bank=DirectorCameraBank(
            self.index,verify_director_action=lambda *_:False).verify(
                pid,spec["camera_bank_id"],spec["camera_bank_revision"])
        return normalize_rail(spec,bank["source_duration_ticks"])

    def create(self,pid,rail_id,base_revision,spec,*,proposed_by="director"):
        if proposed_by not in ("director","model"):
            raise ValueError("Only explicitly attributed camera draft origins")
        original=self._source_head(pid,rail_id,base_revision)
        spec=self._normalized(pid,spec)
        preview=self.rails.preview(
            pid,rail_id,spec,expected_revision=base_revision)
        did=secrets.token_hex(12)
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if self._source_head(pid,rail_id,base_revision)!=original:
                raise RuntimeError("Original rail changed while creating draft")
            db.execute("""INSERT INTO camera_drafts VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                did,pid,rail_id,base_revision,original,1,"DRAFT",
                _json(spec),_json([]),_hash(spec),
                preview["proposal_sha256"],preview["world_take_sha256"],
                preview["rail_layer_sha256"],None,None,proposed_by,
                None,None,now()))
            db.commit()
        return self.reopen(pid,did)

    def reopen(self,pid,draft_id):
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._reconcile(db,pid)
            row=self._row(db,pid,draft_id)
            db.commit()
        return self._result(row)

    def catalog(self,pid):
        _require_pid(pid)
        self.index.studio.get_project(pid)
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._reconcile(db,pid)
            rows=db.execute("""SELECT draft_id,rail_id,base_revision,
                version,state,updated_at FROM camera_drafts WHERE
                project_id=? ORDER BY updated_at DESC LIMIT ?""",
                (pid,MAX_ROWS)).fetchall()
            attempts=db.execute("""SELECT attempt_id,draft_id,model_id,
                state,failure_category,result_version FROM camera_model_attempts
                WHERE project_id=? ORDER BY updated_at DESC LIMIT ?""",
                (pid,MAX_ROWS)).fetchall()
            db.commit()
        return {"format":"nvp.cam_fx03.original_camera_draft_catalog.v1",
            "project_id":pid,"drafts":[dict(x) for x in rows],
            "model_attempts":[dict(x) for x in attempts],
            "native_worker_authorized":False}

    def _modify(self,pid,did,version,spec,*,is_undo=False,
                model_evidence=None,origin="director"):
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,pid,did)
            if (row["version"]!=version or row["state"]!="DRAFT"):
                raise RuntimeError("Draft version changed or no longer editable")
            old_spec=json.loads(row["spec_json"])
            stack=json.loads(row["undo_json"])
            if is_undo:
                if not stack:
                    raise ValueError("No durable camera edit available to undo")
                spec=stack.pop()
            else:
                spec=self._normalized(pid,spec)
                stack=(stack+[old_spec])[-MAX_UNDO:]
            if not self._source_head(pid,row["rail_id"],row["base_revision"])==row["base_sha"]:
                raise RuntimeError("Camera source changed before draft edit")
            preview=self.rails.preview(
                pid,row["rail_id"],spec,expected_revision=row["base_revision"])
            if (preview["world_take_sha256"]!=row["source_take_sha"]):
                raise PermissionError("Cannot change immutable original actor/PCM source")
            revised=db.execute("""UPDATE camera_drafts
                SET version=?,spec_json=?,undo_json=?,spec_sha=?,
                    preview_sha=?,layer_sha=?,proposed_by=?,
                    model_evidence_json=?,updated_at=?
                WHERE project_id=? AND draft_id=? AND version=? AND state='DRAFT'""",
                (version+1,_json(spec),_json(stack),_hash(spec),
                 preview["proposal_sha256"],preview["rail_layer_sha256"],
                 origin,_json(model_evidence) if model_evidence else None,
                 now(),pid,did,version))
            if revised.rowcount!=1:
                raise RuntimeError("Concurrent camera draft modification")
            db.commit()
        return self.reopen(pid,did)

    def save(self,pid,did,version,spec):
        return self._modify(pid,did,version,spec)

    def undo(self,pid,did,version):
        return self._modify(pid,did,version,None,is_undo=True)

    def discard(self,pid,did,version):
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,pid,did)
            if row["state"]!="DRAFT" or row["version"]!=version:
                raise PermissionError("Cannot discard changed or already approved rail")
            db.execute("""UPDATE camera_drafts SET state='DISCARDED',
                updated_at=? WHERE project_id=? AND draft_id=?""",
                (now(),pid,did))
            db.commit()
        return self.reopen(pid,did)

    def begin_publish(self,pid,did,version,proposal_sha):
        _sha(proposal_sha)
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,pid,did)
            if (row["state"]!="DRAFT" or row["version"]!=version or
                row["preview_sha"]!=proposal_sha or
                self._source_head(pid,row["rail_id"],row["base_revision"])!=row["base_sha"]):
                raise PermissionError("Fresh reviewed source draft/revision required")
            db.execute("""UPDATE camera_drafts
                SET state='PUBLISHING',publishing_session_id=?,
                    updated_at=? WHERE draft_id=?""",
                (self.session,now(),did))
            db.commit()
        return self._result(row)

    def complete_publish(self,pid,did,version,receipt):
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,pid,did)
            if (row["version"]!=version or row["state"] not in (
                    "PUBLISHING","INTERRUPTED_REQUIRES_NEW_APPROVAL")):
                raise PermissionError("Camera publish journal no longer owns operation")
            if receipt is None:
                db.execute("""UPDATE camera_drafts
                    SET state='INTERRUPTED_REQUIRES_NEW_APPROVAL',
                        updated_at=? WHERE draft_id=?""",(now(),did))
            else:
                original=self.index.read_revision(
                    pid,row["rail_id"],row["base_revision"]+1)
                if (original["document_sha256"]!=receipt["document_sha256"] or
                    original["revision"]!=row["base_revision"]+1 or
                    original["data"].get("rail_spec")!=json.loads(row["spec_json"]) or
                    original["data"].get("rail_layer_sha256")!=row["layer_sha"]):
                    raise RuntimeError("Published native layer and durable director draft differ")
                db.execute("""UPDATE camera_drafts SET state='PUBLISHED',
                    published_revision=?,published_sha=?,updated_at=?
                    WHERE draft_id=?""",
                    (receipt["revision"],receipt["document_sha256"],now(),did))
            db.commit()
        return self.reopen(pid,did)

    def recover_published(self,pid,did):
        """Only reconciliation of an existing FilmIndex commit, never retries."""
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,pid,did)
            if row["state"]!="INTERRUPTED_REQUIRES_NEW_APPROVAL":
                db.commit()
                return self._result(row)
            try:
                committed=self.index.read_revision(
                    pid,row["rail_id"],row["base_revision"]+1)
            except KeyError:
                committed=None
            if (committed and committed["data"].get("rail_spec")==
                    json.loads(row["spec_json"]) and
                committed["data"].get("rail_layer_sha256")==row["layer_sha"]):
                db.execute("""UPDATE camera_drafts
                    SET state='PUBLISHED',published_revision=?,published_sha=?,
                        updated_at=? WHERE draft_id=?""",
                    (committed["revision"],committed["document_sha256"],
                     now(),did))
            db.commit()
        return self.reopen(pid,did)

    def start_model(self,pid,did,version,model_id,source_sha,direction_sha):
        for value in (source_sha,direction_sha):_sha(value)
        if type(model_id) is not str or not 1<=len(model_id)<=256:
            raise PermissionError("Host-selected local model required")
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,pid,did)
            if row["state"]!="DRAFT" or row["version"]!=version:
                raise PermissionError("AI can advise only current unapproved draft")
            pending=db.execute("""SELECT 1 FROM camera_model_attempts
                 WHERE project_id=? AND state='GENERATING' LIMIT 1""",
                 (pid,)).fetchone()
            if pending:
                raise RuntimeError("Only one unapproved camera model proposal in flight")
            aid=secrets.token_hex(12)
            db.execute("""INSERT INTO camera_model_attempts
                (attempt_id,project_id,draft_id,model_id,base_version,
                 rail_spec_sha,source_context_sha,direction_sha,
                 host_session_id,state,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,'GENERATING',?)""",
                (aid,pid,did,model_id,version,row["spec_sha"],
                 source_sha,direction_sha,self.session,now()))
            db.commit()
        return aid

    def model_status(self,pid,aid):
        _attempt(aid);_require_pid(pid)
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._reconcile(db,pid)
            row=db.execute("""SELECT * FROM camera_model_attempts
                WHERE project_id=? AND attempt_id=?""",(pid,aid)).fetchone()
            db.commit()
        if row is None:
            raise KeyError("Camera proposal model attempt is not project-owned")
        draft=self.reopen(pid,row["draft_id"]) if row["state"]=="DRAFT_UPDATED_UNAPPROVED" else None
        return {"format":ATTEMPT,"attempt_id":aid,"project_id":pid,
                "draft_id":row["draft_id"],"model_id":row["model_id"],
                "state":row["state"],"failure_category":row["failure_category"],
                "result_version":row["result_version"],
                "provider_receipt_sha256":row["provider_receipt_sha"],
                "draft":draft,"director_approval_granted":False,
                "native_worker_authorized":False}

    def cancel_model(self,pid,aid):
        _attempt(aid)
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE camera_model_attempts
                SET state='CANCELLED',failure_category='director_cancelled',
                updated_at=? WHERE project_id=? AND attempt_id=?
                AND state='GENERATING' AND host_session_id=?""",
                (now(),pid,aid,self.session))
            db.commit()
        return self.model_status(pid,aid)

    def fail_model(self,pid,aid,category):
        _attempt(aid)
        if category not in ("source_changed","model_failed","invalid_proposal",
                            "host_shutdown"):
            category="invalid_proposal"
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE camera_model_attempts SET
                state='FAILED',failure_category=?,updated_at=?
                WHERE project_id=? AND attempt_id=?
                AND state='GENERATING' AND host_session_id=?""",
                (category,now(),pid,aid,self.session))
            db.commit()

    def complete_model(self,pid,aid,version,source_sha,proposed_spec,evidence):
        _attempt(aid);_sha(source_sha)
        if type(evidence) is not dict or not evidence:
            raise ValueError("Only typed model source provenance")
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT * FROM camera_model_attempts
                WHERE project_id=? AND attempt_id=?""",(pid,aid)).fetchone()
            if (row is None or row["state"]!="GENERATING" or
                row["host_session_id"]!=self.session or
                row["source_context_sha"]!=source_sha or
                row["base_version"]!=version):
                raise PermissionError("Cancelled/interrupted model cannot publish an old response")
            draft=self._row(db,pid,row["draft_id"])
            if (draft["version"]!=version or draft["state"]!="DRAFT" or
                draft["spec_sha"]!=row["rail_spec_sha"]):
                raise RuntimeError("Director edited draft while AI generated")
            if self._source_head(pid,draft["rail_id"],
                                 draft["base_revision"])!=draft["base_sha"]:
                raise RuntimeError("Original film camera source changed during AI")
            proposed_spec=self._normalized(pid,proposed_spec)
            preview=self.rails.preview(
                pid,draft["rail_id"],proposed_spec,
                expected_revision=draft["base_revision"])
            if preview["world_take_sha256"]!=draft["source_take_sha"]:
                raise PermissionError("Model cannot replace frozen actor world Take")
            stack=json.loads(draft["undo_json"])
            stack=(stack+[json.loads(draft["spec_json"])])[-MAX_UNDO:]
            db.execute("""UPDATE camera_drafts SET version=?,
                spec_json=?,undo_json=?,spec_sha=?,preview_sha=?,
                layer_sha=?,proposed_by='model',model_evidence_json=?,
                updated_at=? WHERE draft_id=?""",
                (version+1,_json(proposed_spec),_json(stack),
                 _hash(proposed_spec),preview["proposal_sha256"],
                 preview["rail_layer_sha256"],_json(evidence),now(),
                 draft["draft_id"]))
            db.execute("""UPDATE camera_model_attempts SET
                state='DRAFT_UPDATED_UNAPPROVED',result_version=?,
                provider_receipt_sha=?,updated_at=?
                WHERE attempt_id=?""",
                (version+1,sha256(_json(evidence).encode("ascii")).hexdigest(),
                 now(),aid))
            db.commit()
        return self.model_status(pid,aid)
