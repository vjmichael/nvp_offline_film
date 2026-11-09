"""USD-FILM-02M-F — durable unapproved film-world proposal ledger.

An AI/designer may propose a bounded ORIGINAL USD district, hide instances
or hand-place original referenced building parts. These are not FilmIndex
world revisions. Only a separate exact-source native director confirmation
can publish; that approval is never received from the model/browser.

Host-owned SQLite WAL/FULL keeps reversible drafts across application
restart. A commit interrupted after the immutable FilmIndex transaction
may be reconciled from exact source, never replayed with an old grant.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
import threading

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_studio import now
from backend.nvp_usd_film02m_e_district import (
    OriginalFilmDistrict,FORMAT as DISTRICT_FORMAT)
from backend.nvp_usd_film02m_modular_buildings import _sha

FORMAT="nvp.usd_film02m_f.durable_director_proposal.v1"
PREVIEW_FORMAT="nvp.usd_film02m_f.original_source_lowfi_preview.v1"
DIFF_FORMAT="nvp.usd_film02m_f.original_layer_diff.v1"
MAX_HISTORY=48
PARAMETERS={
    "seed","source_buildings","grid_cols","grid_rows","lot_spacing_m",
    "world_origin_m","source_triangle_budget","source_instance_budget"}
ACTIONS={"hide_generated","unhide_generated",
         "place_original","remove_manual"}


def _json(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False)


class OriginalDistrictDrafts:
    def __init__(self,index:FilmIndex,state_root:Path,*,confirm,
                 model_session_id=None):
        if not isinstance(index,FilmIndex) or not callable(confirm):
            raise TypeError("Real original FilmIndex and native director confirmation required")
        root=Path(state_root)
        if not root.is_absolute() or root.is_symlink():
            raise PermissionError("Only host-owned absolute non-symlinked draft storage")
        self.root=root.resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/"original-film02mf-proposals.sqlite3"
        self.index=index
        self.confirm=confirm
        # Native bridge owns this across its service instances. A new installed
        # process has a different host session, so orphaned attempts cannot
        # become live merely because an old provider returns after restart.
        self.model_session_id=model_session_id or secrets.token_hex(16)
        if (type(self.model_session_id) is not str or
            len(self.model_session_id)!=32 or
            any(c not in "0123456789abcdef" for c in self.model_session_id)):
            raise ValueError("Only host-minted model session identity")
        self.district=OriginalFilmDistrict(
            index,verify_director_action=lambda *_:False)
        self.lock=threading.RLock()
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS authoring_drafts(
              draft_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,district_id TEXT NOT NULL,
              proposed_by TEXT NOT NULL,base_revision INTEGER NOT NULL,
              base_sha TEXT NOT NULL,parameters_json TEXT NOT NULL,
              operations_json TEXT NOT NULL,undo_json TEXT NOT NULL,
              version INTEGER NOT NULL,state TEXT NOT NULL,
              original_plan_sha TEXT NOT NULL,
              original_usd_root_sha TEXT NOT NULL,
              published_revision INTEGER,published_sha TEXT,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_film02mf_project
              ON authoring_drafts(project_id,updated_at);
            CREATE TABLE IF NOT EXISTS authoring_model_evidence(
              draft_id TEXT PRIMARY KEY,
              evidence_json TEXT NOT NULL,
              FOREIGN KEY(draft_id) REFERENCES authoring_drafts(draft_id)
            );
            CREATE TABLE IF NOT EXISTS authoring_model_attempts(
              attempt_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              district_id TEXT NOT NULL,
              expected_revision INTEGER NOT NULL,
              model_id TEXT NOT NULL,
              direction_sha256 TEXT NOT NULL,
              catalog_sha256 TEXT NOT NULL,
              host_session_id TEXT NOT NULL,
              state TEXT NOT NULL,
              draft_id TEXT,
              failure_category TEXT,
              started_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_film02mg_project
              ON authoring_model_attempts(project_id,updated_at);
            """)

    @contextmanager
    def _db(self):
        c=sqlite3.connect(str(self.db),timeout=15,isolation_level=None)
        c.row_factory=sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=FULL")
            c.execute("PRAGMA busy_timeout=15000")
            yield c
        finally:
            c.close()

    def _base(self,pid,did,expected):
        if type(expected) is not int or expected<0:
            raise ValueError("Exact original district base revision required")
        try:
            record=self.index.read_revision(pid,did)
        except KeyError:
            record=None
        latest=record["revision"] if record else 0
        if latest!=expected:
            raise RuntimeError("Original approved district changed; reopen before proposing")
        if record and (record["kind"]!="presentation" or
                       record["data"].get("format")!=DISTRICT_FORMAT):
            raise PermissionError("Cannot replace another original FilmIndex object type")
        if record:
            with self.district.open(pid,did,expected):
                pass
        return record["document_sha256"] if record else None

    def _plan(self,pid,params,operations):
        if type(params) is not dict or set(params)!=PARAMETERS:
            raise PermissionError("Only typed approved source building generator inputs")
        if type(operations) is not list or len(operations)>64:
            raise ValueError("Bounded original stronger layer operations required")
        return self.district.plan(pid,**params,director_overrides=operations)

    def _verify_stage(self,pid,plan):
        with self.district._stage(pid,plan) as stage:
            receipt=dict(stage["receipt"])
        return receipt

    def _one(self,db,pid,draft_id):
        _require_pid(pid)
        if type(draft_id) is not str or not (
                len(draft_id)==24 and all(x in "0123456789abcdef"
                                          for x in draft_id)):
            raise PermissionError("Only host-minted original proposal identity")
        row=db.execute("""SELECT d.*,e.evidence_json AS model_evidence_json
                          FROM authoring_drafts d
                          LEFT JOIN authoring_model_evidence e ON e.draft_id=d.draft_id
                          WHERE d.draft_id=? AND d.project_id=?""",
                       (draft_id,pid)).fetchone()
        if row is None:
            raise KeyError("Unknown project-bound original scene proposal")
        return dict(row)

    def _values(self,row):
        params=json.loads(row["parameters_json"])
        operations=json.loads(row["operations_json"])
        history=json.loads(row["undo_json"])
        if (type(params) is not dict or type(operations) is not list or
            type(history) is not list or len(history)>MAX_HISTORY):
            raise RuntimeError("Original draft ledger content malformed")
        return params,operations,history

    def _reopen(self,pid,row,*,rebuild_stage=False):
        params,ops,history=self._values(row)
        plan=self._plan(pid,params,ops)
        if _sha(plan)!=row["original_plan_sha"]:
            raise RuntimeError("Original proposal source SHA no longer matches")
        self._base(pid,row["district_id"],row["base_revision"])
        receipt=self._verify_stage(pid,plan) if rebuild_stage else None
        if (receipt is not None and
            receipt["district_root_sha256"]!=row["original_usd_root_sha"]):
            raise RuntimeError("Native original generated/director layer SHA no longer matches draft")
        return plan,receipt

    def _overview(self,row):
        return {
            "format":FORMAT,"draft_id":row["draft_id"],
            "project_id":row["project_id"],"district_id":row["district_id"],
            "proposed_by":row["proposed_by"],
            "observed_model_evidence": (
                json.loads(row["model_evidence_json"])
                if row.get("model_evidence_json") else None),
            "base_revision":row["base_revision"],
            "base_source_sha256":row["base_sha"] or None,
            "version":row["version"],"state":row["state"],
            "original_plan_sha256":row["original_plan_sha"],
            "original_usd_root_sha256":row["original_usd_root_sha"],
            "undo_steps":len(json.loads(row["undo_json"])),
            "director_approved":row["state"]=="COMMITTED",
            "published_revision":row["published_revision"],
            "published_sha256":row["published_sha"],
            "original_actor_takes_modified":False,
            "native_blender_workers_started":0}

    def _recover_model_attempts(self,db,pid):
        """Old-process GENERATING is interrupted, not automatically resumed."""
        db.execute("BEGIN IMMEDIATE")
        db.execute("""UPDATE authoring_model_attempts SET
            state='INTERRUPTED_REQUIRES_NEW_GENERATION',
            failure_category='host_session_terminated',
            updated_at=?
            WHERE project_id=? AND state='GENERATING'
            AND host_session_id<>?""",
            (now(),pid,self.model_session_id))
        db.commit()

    def start_model_attempt(self,pid,district_id,revision,model_id,
                            direction_sha256,catalog_sha256):
        _require_pid(pid)
        _id(district_id,"world model attempt district")
        for name,value in (
                ("direction",direction_sha256),
                ("catalog",catalog_sha256)):
            if (type(value) is not str or len(value)!=64 or
                any(c not in "0123456789abcdef" for c in value)):
                raise ValueError("Model attempt requires exact "+name+" SHA")
        if (type(model_id) is not str or not 1<=len(model_id)<=256):
            raise ValueError("Host-selected model identity required")
        with self.lock,self._db() as db:
            self._base(pid,district_id,revision)
            self._recover_model_attempts(db,pid)
            db.execute("BEGIN IMMEDIATE")
            if db.execute("""SELECT 1 FROM authoring_model_attempts
                WHERE project_id=? AND state='GENERATING' LIMIT 1""",
                (pid,)).fetchone():
                raise RuntimeError("An earlier model proposal is still generating")
            attempt=secrets.token_hex(12)
            stamp=now()
            db.execute("""INSERT INTO authoring_model_attempts
                (attempt_id,project_id,district_id,expected_revision,
                 model_id,direction_sha256,catalog_sha256,host_session_id,
                 state,started_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,'GENERATING',?,?)""",
                (attempt,pid,district_id,revision,model_id,
                 direction_sha256,catalog_sha256,
                 self.model_session_id,stamp,stamp))
            db.commit()
            return attempt

    def fail_model_attempt(self,pid,attempt_id,category):
        if category not in ("provider_failed","source_changed",
                            "model_response_denied","session_closed"):
            category="model_response_denied"
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE authoring_model_attempts
                SET state='FAILED',failure_category=?,updated_at=?
                WHERE project_id=? AND attempt_id=? AND state='GENERATING'
                AND host_session_id=?""",
                (category,now(),pid,attempt_id,self.model_session_id))
            db.commit()

    def catalog(self,pid):
        _require_pid(pid)
        self.index.studio.get_project(pid)
        candidates=[]
        for row in self.index.list_objects(pid,kind="world")[:128]:
            try:
                with self.district.kit.open_building(
                        pid,row["object_id"],row["head_revision"]) as opened:
                    candidates.append({
                        "building_id":row["object_id"],
                        "revision":row["head_revision"],
                        "document_sha256":opened["record"]["document_sha256"],
                        "source_triangles":sum(
                            int(x["source_mesh_triangle_count"]) for x in
                            opened["referenced_modules"]),
                        "modules":opened["mesh_count"]})
            except (KeyError,PermissionError,RuntimeError,ValueError,TypeError):
                continue
            if len(candidates)>=24:
                break
        districts=[]
        for row in self.index.list_objects(pid,kind="presentation")[:128]:
            try:
                saved=self.index.read_revision(pid,row["object_id"],row["head_revision"])
                if saved["data"].get("format")==DISTRICT_FORMAT:
                    with self.district.open(pid,row["object_id"],row["head_revision"]):
                        pass
                    districts.append({
                        "district_id":row["object_id"],
                        "revision":row["head_revision"],
                        "document_sha256":saved["document_sha256"],
                        "source_instance_count":len(saved["data"][
                            "generated_instances"]),
                        "source_seed":saved["data"]["seed"],
                        "base_parameters":{
                            "seed":saved["data"]["seed"],
                            "source_buildings":[{
                                "building_id":p["building_id"],
                                "revision":p["revision"]} for p in
                                saved["data"]["original_prototypes"]],
                            "grid_cols":saved["data"]["grid_cols"],
                            "grid_rows":saved["data"]["grid_rows"],
                            "lot_spacing_m":saved["data"]["lot_spacing_m"],
                            "world_origin_m":saved["data"]["world_origin_m"],
                            "source_triangle_budget":saved["data"][
                                "source_triangle_budget"],
                            "source_instance_budget":saved["data"][
                                "source_instance_budget"]}})
            except (KeyError,RuntimeError,PermissionError,ValueError,TypeError):
                continue
            if len(districts)>=24:break
        from backend.nvp_usd_film01e_world_take import FORMAT as WORLD_TAKE_FORMAT
        world_takes=[]
        for item in self.index.list_objects(pid,kind="take")[:128]:
            try:
                record=self.index.read_revision(
                    pid,item["object_id"],item["head_revision"])
                if (item["head_revision"]==1 and
                    record["data"].get("format")==WORLD_TAKE_FORMAT and
                    record["data"].get("frozen") is True):
                    world_takes.append({
                        "take_id":item["object_id"],
                        "take_sha256":record["document_sha256"],
                        "checkpoint_ticks":record["data"]["checkpoint_ticks"],
                        "shot_id":record["data"]["camera_shot_id"],
                        "shot_revision":record["data"]["camera_shot_revision"],
                        "original_actor_count":len(record["data"][
                            "canonical_original_actors"])})
            except (KeyError,ValueError,TypeError,PermissionError):
                continue
            if len(world_takes)>=32:
                break
        with self._db() as db:
            self._recover_model_attempts(db,pid)
            attempts=db.execute("""SELECT attempt_id,district_id,
                expected_revision,model_id,direction_sha256,catalog_sha256,
                state,draft_id,failure_category,started_at,updated_at
                FROM authoring_model_attempts
                WHERE project_id=? ORDER BY updated_at DESC LIMIT 20""",
                (pid,)).fetchall()
            drafts=db.execute("""SELECT d.*,e.evidence_json AS model_evidence_json
                FROM authoring_drafts d
                LEFT JOIN authoring_model_evidence e ON e.draft_id=d.draft_id
                WHERE d.project_id=? ORDER BY d.updated_at DESC LIMIT 40""",
                (pid,)).fetchall()
        return {
            "format":"nvp.usd_film02m_f.native_source_catalog.v1",
            "project_id":pid,"source_buildings":candidates,
            "approved_districts":districts,
            "original_world_takes":world_takes,
            "drafts":[self._overview(dict(x)) for x in drafts],
            "model_attempts":[dict(x) for x in attempts],
            "native_blender_workers_started":0,
            "original_film_takes_modified":False}

    def create(self,pid,district_id,*,expected_revision,params,
               proposed_by,model_evidence=None,model_attempt_id=None):
        _require_pid(pid)
        _id(district_id,"original film district proposed ID")
        if proposed_by not in ("director","ai"):
            raise PermissionError("A proposal needs an explicit director/AI provenance")
        if model_evidence is not None:
            from backend.nvp_usd_film02m_g_model_world_candidate import FORMAT as MODEL_FORMAT
            if (proposed_by!="ai" or type(model_evidence) is not dict or
                model_evidence.get("format")!=MODEL_FORMAT or
                model_evidence.get("status")!="GENERATED_UNAPPROVED" or
                model_evidence.get("project_id")!=pid or
                model_evidence.get("district_id")!=district_id or
                model_evidence.get("expected_revision")!=expected_revision or
                model_evidence.get("params")!=params or
                model_evidence.get("creative_approval_granted") is not False or
                model_evidence.get("worker_authorization_granted") is not False or
                model_evidence.get("proposal_durable") is not False):
                raise PermissionError("Host-bound source model evidence does not match draft")
        if model_attempt_id is not None and (
                type(model_attempt_id) is not str or
                len(model_attempt_id)!=24 or
                any(c not in "0123456789abcdef" for c in model_attempt_id)
                or model_evidence is None):
            raise PermissionError("Native model attempt identity/evidence required")
        with self.lock:
            base=self._base(pid,district_id,expected_revision)
            # A new director proposal based on an approved revision must
            # preserve its existing stronger USD layer opinions by default,
            # not silently erase hidden buildings and hand placements.
            base_ops=(self.index.read_revision(
                pid,district_id,expected_revision)["data"].get(
                    "original_director_operations",[])
                if expected_revision else [])
            plan=self._plan(pid,params,base_ops)
            receipt=self._verify_stage(pid,plan)
            draft_id=secrets.token_hex(12)
            stamp=now()
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO authoring_drafts(
                    draft_id,project_id,district_id,proposed_by,base_revision,
                    base_sha,parameters_json,operations_json,undo_json,
                    version,state,original_plan_sha,original_usd_root_sha,
                    created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,1,'DRAFT',?,?,?,?)""",
                    (draft_id,pid,district_id,proposed_by,expected_revision,
                     base or "",_json(params),_json(base_ops),"[]",_sha(plan),
                     receipt["district_root_sha256"],stamp,stamp))
                if model_evidence is not None:
                    db.execute("""INSERT INTO authoring_model_evidence(
                        draft_id,evidence_json) VALUES(?,?)""",
                        (draft_id,_json(model_evidence)))
                if model_attempt_id is not None:
                    changed=db.execute("""UPDATE authoring_model_attempts SET
                        state='DRAFT_SAVED',draft_id=?,updated_at=?
                        WHERE attempt_id=? AND project_id=? AND
                        district_id=? AND expected_revision=? AND
                        model_id=? AND state='GENERATING' AND
                        host_session_id=?""",
                        (draft_id,now(),model_attempt_id,pid,district_id,
                         expected_revision,model_evidence["model_id"],
                         self.model_session_id))
                    if changed.rowcount!=1:
                        raise RuntimeError(
                            "Model attempt interrupted/stale before source draft publication")
                db.commit()
            return self.reopen(pid,draft_id)

    def _reconcile_pending(self,db,pid,row):
        """Never reuse old approval: reconcile one already-granted exact commit."""
        if row["state"]!="APPROVED_PENDING_PUBLISH":
            return row
        params,ops,_=self._values(row)
        plan=self._plan(pid,params,ops)
        if _sha(plan)!=row["original_plan_sha"]:
            raise RuntimeError("Cannot reconcile altered original proposal bytes")
        try:
            current=self.index.read_revision(pid,row["district_id"])
        except KeyError:
            current=None
        head=current["revision"] if current else 0
        if head==row["base_revision"]:
            state="INTERRUPTED_NEEDS_NEW_APPROVAL"
            completed=None
        elif head==row["base_revision"]+1:
            data=current["data"]
            original={k:v for k,v in data.items() if k!="native_source_receipt"}
            if (data.get("format")!=DISTRICT_FORMAT or
                original!=plan or data.get("native_source_receipt",{}).get(
                    "district_root_sha256")!=row["original_usd_root_sha"]):
                state="CONFLICT_NEEDS_REVIEW"
                completed=None
            else:
                with self.district.open(pid,row["district_id"],head):
                    pass
                state="COMMITTED"
                completed=current
        else:
            state="CONFLICT_NEEDS_REVIEW"
            completed=None
        db.execute("BEGIN IMMEDIATE")
        db.execute("""UPDATE authoring_drafts SET state=?,
            published_revision=?,published_sha=?,version=version+1,
            updated_at=? WHERE project_id=? AND draft_id=? AND
            state='APPROVED_PENDING_PUBLISH'""",
            (state,completed["revision"] if completed else None,
             completed["document_sha256"] if completed else None,
             now(),pid,row["draft_id"]))
        db.commit()
        return self._one(db,pid,row["draft_id"])

    def reopen(self,pid,draft_id):
        with self.lock,self._db() as db:
            row=self._one(db,pid,draft_id)
            if row["state"]=="APPROVED_PENDING_PUBLISH":
                row=self._reconcile_pending(db,pid,row)
            if row["state"]=="DRAFT":
                self._reopen(pid,row,rebuild_stage=True)
            elif row["state"]=="COMMITTED":
                saved=self.index.read_revision(
                    pid,row["district_id"],row["published_revision"])
                if saved["document_sha256"]!=row["published_sha"]:
                    raise RuntimeError("Approved immutable original FilmIndex receipt changed")
                with self.district.open(
                        pid,row["district_id"],row["published_revision"]) as result:
                    if result["record"]["document_sha256"]!=row["published_sha"]:
                        raise RuntimeError("Approved original USD source can no longer reopen")
            return self._overview(row)

    def _change(self,pid,draft_id,version,change):
        if type(version) is not int or version<1:
            raise ValueError("Exact draft edit version required")
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._one(db,pid,draft_id)
            if row["state"]!="DRAFT" or row["version"]!=version:
                raise RuntimeError("Stale or closed source proposal; reopen first")
            self._reopen(pid,row,rebuild_stage=False)
            params,ops,history=self._values(row)
            next_ops=change(ops)
            if next_ops==ops:
                raise ValueError("No actual original stronger layer change")
            history=(history+[ops])[-MAX_HISTORY:]
            plan=self._plan(pid,params,next_ops)
            receipt=self._verify_stage(pid,plan)
            db.execute("""UPDATE authoring_drafts SET operations_json=?,
                undo_json=?,original_plan_sha=?,original_usd_root_sha=?,
                version=version+1,updated_at=?
                WHERE draft_id=? AND version=? AND state='DRAFT'""",
                (_json(next_ops),_json(history),_sha(plan),
                 receipt["district_root_sha256"],now(),draft_id,version))
            db.commit()
        return self.reopen(pid,draft_id)

    def edit(self,pid,draft_id,version,action):
        if type(action) is not dict or action.get("op") not in ACTIONS:
            raise PermissionError("AI/director can only propose typed source layer changes")
        kind=action["op"]
        if kind in ("hide_generated","unhide_generated"):
            if set(action)!={"op","instance_id"} or type(action["instance_id"]) is not int:
                raise ValueError("Source generated instance ID required")
            def change(operations):
                current=[x for x in operations if not (
                    x["op"]=="hide_generated" and
                    x["instance_id"]==action["instance_id"])]
                if kind=="hide_generated":
                    current.append({"op":"hide_generated",
                                    "instance_id":action["instance_id"]})
                elif len(current)==len(operations):
                    raise ValueError("Source instance not previously hidden")
                return current
        elif kind=="place_original":
            if set(action)!={"op","name","building_id","position_m","yaw_deg"}:
                raise ValueError("Only typed original source building reference placement")
            def change(operations):
                if any(x.get("name")==action["name"] for x in operations):
                    raise ValueError("Manual original building name must be unique")
                return operations+[dict(action)]
        else:
            if set(action)!={"op","name"}:
                raise ValueError("Remove only one exact manual source building")
            def change(operations):
                current=[x for x in operations if not (
                    x["op"]=="place_original" and x["name"]==action["name"])]
                if len(current)==len(operations):
                    raise ValueError("Original director placement not found")
                return current
        return self._change(pid,draft_id,version,change)

    def undo(self,pid,draft_id,version):
        if type(version) is not int or version<1:
            raise ValueError("Exact original draft version needed for undo")
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._one(db,pid,draft_id)
            if row["state"]!="DRAFT" or row["version"]!=version:
                raise RuntimeError("Original draft is stale or no longer editable")
            self._reopen(pid,row)
            params,ops,history=self._values(row)
            if not history:
                raise ValueError("Original proposal has no reversible change")
            old=history.pop()
            plan=self._plan(pid,params,old)
            receipt=self._verify_stage(pid,plan)
            db.execute("""UPDATE authoring_drafts SET operations_json=?,
                undo_json=?,original_plan_sha=?,original_usd_root_sha=?,
                version=version+1,updated_at=?
                WHERE draft_id=? AND state='DRAFT' AND version=?""",
                (_json(old),_json(history),_sha(plan),
                 receipt["district_root_sha256"],now(),draft_id,version))
            db.commit()
        return self.reopen(pid,draft_id)

    def discard(self,pid,draft_id,version):
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._one(db,pid,draft_id)
            if type(version) is not int or row["version"]!=version or (
                    row["state"]!="DRAFT"):
                raise RuntimeError("Original source proposal cannot be discarded twice/stale")
            db.execute("""UPDATE authoring_drafts SET state='DISCARDED',
                version=version+1,updated_at=? WHERE draft_id=?""",
                (now(),draft_id))
            db.commit()
        return self.reopen(pid,draft_id)

    def _diff(self,pid,row,plan):
        old=None
        if row["base_revision"]:
            old=self.index.read_revision(
                pid,row["district_id"],row["base_revision"])["data"]
        old_operations=old.get("original_director_operations",[]) if old else []
        current=plan["original_director_operations"]
        oldset={_sha(x):x for x in old_operations}
        newset={_sha(x):x for x in current}
        return {
            "format":DIFF_FORMAT,
            "base_revision":row["base_revision"],
            "base_source_sha256":row["base_sha"] or None,
            "new_source_plan_sha256":_sha(plan),
            "generated_slots":len(plan["generated_instances"]),
            "generated_source_changed":old is None or any(
                old.get(k)!=plan[k] for k in (
                    "seed","original_prototypes","grid_cols","grid_rows",
                    "lot_spacing_m","world_origin_m")),
            "added_director_opinions":[newset[k] for k in
                                      sorted(newset.keys()-oldset.keys())],
            "removed_director_opinions":[oldset[k] for k in
                                        sorted(oldset.keys()-newset.keys())],
            "actual_source_triangles_estimated":plan[
                "actual_source_triangles_estimated"],
            "original_film_takes_modified":False,
            "no_source_material_or_actor_mutation":True}

    def preview(self,pid,draft_id):
        with self.lock,self._db() as db:
            row=self._one(db,pid,draft_id)
            if row["state"]!="DRAFT":
                raise RuntimeError("Only an unapproved source proposal can preview")
            plan,receipt=self._reopen(pid,row,rebuild_stage=True)
            by_id={x["building_id"]:x for x in plan["original_prototypes"]}
            hidden=set(plan["director_invisible_instance_ids"])
            things=[]
            for item in plan["generated_instances"]:
                prototype=by_id[item["building_id"]]
                things.append({
                    "instance_id":item["instance_id"],
                    "name":"Generated_"+str(item["instance_id"]),
                    "building_id":item["building_id"],
                    "position_local_m":item["position_local_m"],
                    "yaw_deg":item["yaw_deg"],
                    "source_bounds_m":prototype["original_bounds_m"],
                    "source_building_sha256":prototype["building_sha256"],
                    "source_mesh_count":prototype["mesh_count"],
                    "hidden":item["instance_id"] in hidden,
                    "director_placed":False})
            for item in plan["director_manual_overrides"]:
                prototype=by_id[item["building_id"]]
                things.append({
                    "instance_id":None,"name":item["name"],
                    "building_id":item["building_id"],
                    "position_local_m":item["position_m"],
                    "yaw_deg":item["yaw_deg"],
                    "source_bounds_m":prototype["original_bounds_m"],
                    "source_building_sha256":prototype["building_sha256"],
                    "source_mesh_count":prototype["mesh_count"],
                    "hidden":False,"director_placed":True})
            return {
                "format":PREVIEW_FORMAT,"proposal":self._overview(row),
                "source_plan_sha256":_sha(plan),
                "generated_source_layer_sha256":receipt[
                    "generated_layer_sha256"],
                "director_override_layer_sha256":receipt[
                    "director_override_layer_sha256"],
                "usd_layer_root_sha256":receipt["district_root_sha256"],
                "instances":things,
                "diff":self._diff(pid,row,plan),
                "source_triangles_estimated":plan[
                    "actual_source_triangles_estimated"],
                "source_prototype_count":len(plan["original_prototypes"]),
                "verified_openusd_point_instancer":receipt[
                    "actual_native_usd_point_instancer_count"],
                "native_usd_source_reopened":True,
                "preview_is_source_bounds_not_cycles_pixels":True,
                "original_world_takes_modified":False,
                "native_blender_workers_started":0}

    def approve_and_commit(self,pid,draft_id,version,
                           source_sha,stage_sha):
        """Actual OS director grant is minted only inside publish callback."""
        with self.lock,self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._one(db,pid,draft_id)
            if (row["state"]!="DRAFT" or
                type(version) is not int or version!=row["version"] or
                type(source_sha) is not str or source_sha!=row["original_plan_sha"] or
                type(stage_sha) is not str or stage_sha!=row["original_usd_root_sha"]):
                raise PermissionError("No matching current original source draft for approval")
            plan,receipt=self._reopen(pid,row,rebuild_stage=True)
            if _sha(plan)!=source_sha or receipt[
                    "district_root_sha256"]!=stage_sha:
                raise PermissionError("Original USD source or layer changed since director preview")
            params,operations,_=self._values(row)
            scoped={"source_plan":source_sha,
                    "source_stage":stage_sha,
                    "draft_id":draft_id,
                    "draft_version":version,
                    "base_revision":row["base_revision"],
                    "base_sha":row["base_sha"] or None,
                    "added_operations":len(operations)}
            grant=object()
            fired=[False]
            def approve(event,scope):
                if event is not grant or fired[0] or (
                    scope.get("operation")!=
                    "nvp.film02m_e.publish_original_layered_district.v1" or
                    scope.get("project_id")!=pid or
                    scope.get("district_id")!=row["district_id"] or
                    scope.get("original_source_plan_sha256")!=source_sha or
                    scope.get("native_original_layer_source_sha256")!=stage_sha or
                    scope.get("expected_revision")!=row["base_revision"]):
                    return False
                fired[0]=True
                granted=self.confirm({
                    "operation":"nvp.film02m_f.commit_exact_original_district.v1",
                    "project_id":pid,
                    "district_id":row["district_id"],
                    "draft_id":draft_id,
                    "version":version,
                    "base_revision":row["base_revision"],
                    "base_source_sha256":row["base_sha"] or None,
                    "original_source_plan_sha256":source_sha,
                    "native_original_layer_source_sha256":stage_sha,
                    "generated_instances":len(plan["generated_instances"]),
                    "source_triangles_estimated":plan[
                        "actual_source_triangles_estimated"],
                    "manual_opinion_count":len(operations)}) is True
                if granted:
                    # Make the real OS-confirmed one-use approval durable
                    # BEFORE the separate FilmIndex source write. A crash
                    # cannot cause it to be used again.
                    db.execute("""UPDATE authoring_drafts SET
                        state='APPROVED_PENDING_PUBLISH',updated_at=?
                        WHERE draft_id=? AND project_id=? AND
                        state='DRAFT' AND version=?""",
                        (now(),draft_id,pid,version))
                    db.commit()
                return granted
            host=OriginalFilmDistrict(
                self.index,verify_director_action=approve)
            published=host.publish(
                pid,row["district_id"],**params,
                director_overrides=operations,
                expected_revision=row["base_revision"],director_event=grant)
            if not fired[0]:
                raise RuntimeError("Native creator consent callback was not actually reached")
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE authoring_drafts SET state='COMMITTED',
                published_revision=?,published_sha=?,version=version+1,
                updated_at=? WHERE draft_id=? AND
                state='APPROVED_PENDING_PUBLISH' AND version=?""",
                (published["revision"],published["document_sha256"],
                 now(),draft_id,version))
            db.commit()
        with self.district.open(
                pid,row["district_id"],published["revision"]) as reopened:
            if reopened["record"]["document_sha256"]!=published[
                    "document_sha256"]:
                raise RuntimeError("Approved original scene revision failed independent reopen")
        return {
            **self.reopen(pid,draft_id),
            "format":"nvp.usd_film02m_f.original_director_approved_commit.v1",
            "original_source_plan_sha256":source_sha,
            "original_usd_root_sha256":stage_sha,
            "original_film_take_modified":False,
            "native_cycles_render_started":False}
