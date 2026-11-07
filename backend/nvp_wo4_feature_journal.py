"""WO4 LF02/LF04 durable multi-reel feature orchestration in ONE supervisor.

Trust model: a real FilmIndex feature assembly pins exact ordered source reel
job IDs and signed-64-bit Film Time. Every input reel has a verified immutable
native indexed DCP receipt; the trusted creator separately approves the final
canonical feature manifest. The feature keeps its own state in the SAME SQLite
WAL journal and uses the SAME SingletonSupervisor process ownership.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import os
from uuid import uuid4

from backend.nvp_wo4_delivery_journal import CinemaDeliveryJournal
from backend.nvp_wo4_multireel import (
    FORMAT as OUTPUT_FORMAT,_check_manifest,publish_multireel_dcp)
from backend.nvp_wo4_resource_budget import MAX_REELS
from backend.nvp_production_journal import (
    FORMAT as JOB_FORMAT,_canonical,_digest,_now,TICKS_PER_SECOND)
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo3_native_codecs import digest_file
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio

FORMAT="nvp.wo4.durable_multireel_feature.v1"
ASSEMBLY_FORMAT="nvp.wo4.approved_feature_assembly.v1"
FRAME_TICKS=TICKS_PER_SECOND//24

class FeatureJournal(CinemaDeliveryJournal):
    def __init__(self,state_root):
        super().__init__(state_root)
        with self._tx() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS production_features(
              feature_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              assembly_id TEXT NOT NULL,
              assembly_revision INTEGER NOT NULL,
              assembly_sha256 TEXT NOT NULL,
              project_db TEXT NOT NULL,
              output_root TEXT NOT NULL,
              title TEXT NOT NULL,
              profile TEXT NOT NULL,
              manifest_json TEXT NOT NULL,
              manifest_sha256 TEXT NOT NULL,
              state TEXT NOT NULL,
              owner TEXT,
              cancel_requested INTEGER NOT NULL DEFAULT 0,
              file_sha_json TEXT,filmindex_sha256 TEXT,
              updated_at TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS production_feature_ready
              ON production_features(state,created_at);
            """)

    def feature(self,feature_id):
        with self._read() as db:
            row=db.execute("""SELECT * FROM production_features
                          WHERE feature_id=?""",(feature_id,)).fetchone()
            if row is None:
                raise KeyError("Native feature assembly not found")
            return dict(row)

    def submit_feature(self,index,project_id,*,assembly_id,
                       assembly_revision,ordered_job_ids,title,profile,
                       output_root,approve):
        if (not isinstance(index,FilmIndex) or not callable(approve) or
                type(ordered_job_ids) is not list or
                not 2<=len(ordered_job_ids)<=MAX_REELS or
                len(set(ordered_job_ids))!=len(ordered_job_ids)):
            raise PermissionError("Trusted feature assembly and creator approval required")
        assembly=index.read_revision(project_id,assembly_id,assembly_revision)
        data=assembly["data"]
        if (assembly["kind"] not in ("edit","presentation") or
                data.get("format")!=ASSEMBLY_FORMAT or
                data.get("ordered_reel_job_ids")!=ordered_job_ids or
                type(data.get("start_tick")) is not int or
                data["start_tick"]!=0 or
                type(data.get("end_tick")) is not int or
                data["end_tick"]<=0):
            raise PermissionError("Frozen feature assembly does not pin exact reel order")
        if (type(title) is not str or not 1<=len(title)<=80 or
                any(ord(c)<32 or c in "<>&" for c in title) or
                type(profile) is not str):
            raise ValueError("Valid approved title and cinema profile required")
        root=Path(output_root)
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            raise PermissionError("Trusted native export root required")
        project_db=Path(index.studio.db_path)
        if (not project_db.is_absolute() or project_db.is_symlink() or
                not project_db.is_file()):
            raise PermissionError("Native FilmIndex database must be on disk")
        root=root.resolve(strict=True)
        parts=[]
        start=0
        for job_id in ordered_job_ids:
            j=self.status(job_id)
            reel=self.reel(job_id)
            d=self.delivery(job_id)
            if (j["project_id"]!=project_id or
                    j["state"]!="DCP_INDEXED" or d["phase"]!="INDEXED" or
                    not d["filmindex_sha256"] or reel["profile"]!=profile):
                raise PermissionError("Every source reel must be indexed in one project/profile")
            # The complete original Take/J2K/MXF/WAV chain is still immutable.
            self._verify_all_production_sources(job_id)
            folder,files=self._check_published(job_id)
            output_id="WO3DCP_"+d["cpl_uuid"].replace("-","")
            index_receipt=index.read_revision(project_id,output_id,1)
            if index_receipt["document_sha256"]!=d["filmindex_sha256"]:
                raise PermissionError("Source reel FilmIndex receipt changed")
            frames=reel["frame_count"]
            parts.append({
                "start_tick":start,"end_tick":start+frames*FRAME_TICKS,
                "frames":frames,"reel_uuid":d["reel_uuid"],
                "picture":{
                    "file_path":str(self.spool(job_id)/"picture.mxf"),
                    "file_sha256":reel["track_sha256"],
                    "file_bytes":reel["track_bytes"],
                    "asset_uuid":reel["picture_uuid"]},
                "sound":{
                    "file_path":str(self.spool(job_id)/"sound.mxf"),
                    "file_sha256":d["sound_sha256"],
                    "file_bytes":d["sound_bytes"],
                    "asset_uuid":d["sound_uuid"]},
            })
            start+=frames*FRAME_TICKS
        if start!=data["end_tick"]:
            raise PermissionError("Feature Film Time differs from approved assembly")
        ids={key:str(uuid4()) for key in ("cpl","pkl","assetmap")}
        _check_manifest(parts,ids)
        manifest={
            "format":FORMAT,"project_id":project_id,
            "assembly_id":assembly_id,
            "assembly_revision":assembly_revision,
            "assembly_sha256":assembly["document_sha256"],
            "title":title,"profile":profile,
            "ordered_reel_job_ids":ordered_job_ids,
            "reels":parts,"ids":ids,
            "output_root":str(root),"production_dcp_accepted":False,
            "ffmpeg_used":False,
        }
        encoded=_canonical(manifest)
        if len(encoded)>3*1024*1024:
            raise ValueError("Feature manifest exceeds bounded journal size")
        manifest_sha=_digest(encoded)
        scope={"operation":"nvp.supervisor.approve_feature_multireel_v1",
               "project_id":project_id,
               "assembly_id":assembly_id,
               "assembly_revision":assembly_revision,
               "assembly_sha256":assembly["document_sha256"],
               "manifest_sha256":manifest_sha,
               "reel_count":len(parts),"end_tick":start,
               "output_root":str(root),"cpl_uuid":ids["cpl"]}
        if approve(deepcopy(scope)) is not True:
            return {"status":"DENIED","source_modified":False}
        if (index.read_revision(project_id,assembly_id,assembly_revision)[
                "document_sha256"]!=assembly["document_sha256"]):
            raise PermissionError("Feature assembly changed during approval")
        _check_manifest(parts,ids) # source hashes again after consent
        fid=str(uuid4())
        now=_now()
        with self._tx() as db:
            db.execute("""INSERT INTO production_features(
              feature_id,project_id,assembly_id,assembly_revision,
              assembly_sha256,project_db,output_root,title,profile,
              manifest_json,manifest_sha256,state,updated_at,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                fid,project_id,assembly_id,assembly_revision,
                assembly["document_sha256"],str(project_db.resolve(strict=True)),
                str(root),title,profile,encoded.decode("ascii"),manifest_sha,
                "QUEUED",now,now))
        return {"format":FORMAT,"status":"QUEUED","feature_id":fid,
                "manifest_sha256":manifest_sha,"reel_count":len(parts),
                "total_frames":start//FRAME_TICKS,
                "production_dcp_accepted":False}

    def next_feature(self,owner):
        with self._tx() as db:
            row=db.execute("""SELECT feature_id,manifest_json FROM
                production_features WHERE state='QUEUED'
                AND cancel_requested=0 ORDER BY created_at LIMIT 1""").fetchone()
            if row is None:
                return None
            db.execute("""UPDATE production_features SET
                state='STAGING',owner=?,updated_at=? WHERE feature_id=?""",
                (owner,_now(),row["feature_id"]))
            return {"feature_id":row["feature_id"],
                    "manifest":json.loads(row["manifest_json"])}

    def feature_cancel_requested(self,feature_id,owner):
        with self._read() as db:
            row=db.execute("""SELECT owner,cancel_requested FROM
                     production_features WHERE feature_id=?""",
                     (feature_id,)).fetchone()
            if row is None or row["owner"]!=owner:
                raise PermissionError("Native feature worker lost ownership")
            return bool(row["cancel_requested"])

    def commit_feature(self,owner,feature_id,receipt):
        f=self.feature(feature_id)
        manifest=json.loads(f["manifest_json"])
        folder=Path(f["output_root"])/("DCP_FEATURE_"+manifest["ids"]["cpl"])
        if (receipt.get("status")!="MULTIREEL_STRUCTURAL_DCP_PUBLISHED" or
                receipt.get("destination")!=str(folder) or
                receipt.get("cpl_uuid")!=manifest["ids"]["cpl"] or
                receipt.get("reel_count")!=len(manifest["reels"]) or
                folder.is_symlink() or not folder.is_dir()):
            raise PermissionError("No exact native multi-reel DCP published")
        expected=receipt.get("file_sha256")
        if (type(expected) is not dict or
                set(expected)!={p.name for p in folder.iterdir()} or
                any(digest_file(folder/name)!=digest for name,digest in expected.items())):
            raise PermissionError("Multi-reel output SHA manifest differs")
        audit=inspect_dcp_structure(folder)
        if (audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
                audit["cpl_uuid"]!=manifest["ids"]["cpl"] or
                audit["reel_durations"]!=[r["frames"] for r in manifest["reels"]]):
            raise PermissionError("Published multi-reel CPL/PKL audit rejected")
        with self._tx() as db:
            row=db.execute("""SELECT state,owner,cancel_requested,
                             manifest_sha256 FROM production_features
                             WHERE feature_id=?""",(feature_id,)).fetchone()
            if (row is None or row["state"]!="STAGING" or
                    row["owner"]!=owner or row["cancel_requested"] or
                    row["manifest_sha256"]!=f["manifest_sha256"]):
                raise PermissionError("Stale feature worker may not commit output")
            db.execute("""UPDATE production_features SET
                state='PUBLISHED_PENDING_INDEX',owner=NULL,
                file_sha_json=?,updated_at=? WHERE feature_id=?""",
                (json.dumps(expected,sort_keys=True),_now(),feature_id))
        return {"status":"PUBLISHED_PENDING_INDEX","feature_id":feature_id,
                "destination":str(folder),"production_dcp_accepted":False}

    def _recheck_feature(self,feature_id):
        f=self.feature(feature_id)
        manifest=json.loads(f["manifest_json"])
        if _digest(_canonical(manifest))!=f["manifest_sha256"]:
            raise PermissionError("Feature manifest was altered in SQLite")
        folder=Path(f["output_root"])/("DCP_FEATURE_"+manifest["ids"]["cpl"])
        if folder.is_symlink() or not folder.is_dir():
            raise PermissionError("Indexed feature package is missing")
        expected=json.loads(f["file_sha_json"])
        if (not expected or set(expected)!={p.name for p in folder.iterdir()}
                or any(digest_file(folder/name)!=sha
                       for name,sha in expected.items())):
            raise PermissionError("Committed feature output hash mismatch")
        audit=inspect_dcp_structure(folder)
        if (audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
                audit["reel_durations"]!=[part["frames"] for part in manifest["reels"]] or
                audit["cpl_uuid"]!=manifest["ids"]["cpl"]):
            raise PermissionError("Committed feature CPL duration/UUID changed")
        for part in manifest["reels"]:
            for kind in ("picture","sound"):
                track=part[kind]
                file=Path(track["file_path"])
                if (file.is_symlink() or not file.is_file() or
                        file.stat().st_size!=track["file_bytes"] or
                        digest_file(file)!=track["file_sha256"]):
                    raise PermissionError("Original feature reel source MXF changed")
        return f,manifest,folder,expected

    def next_feature_index(self):
        with self._read() as db:
            row=db.execute("""SELECT feature_id FROM production_features
                   WHERE state='PUBLISHED_PENDING_INDEX' AND cancel_requested=0
                   ORDER BY created_at LIMIT 1""").fetchone()
            return None if row is None else row["feature_id"]

    def commit_feature_index(self,feature_id):
        f,manifest,folder,files=self._recheck_feature(feature_id)
        if f["state"] not in ("PUBLISHED_PENDING_INDEX","INDEXED"):
            raise PermissionError("Feature is not a published package")
        index=FilmIndex(Studio(Path(f["project_db"])))
        assembly=index.read_revision(
            f["project_id"],f["assembly_id"],f["assembly_revision"])
        if assembly["document_sha256"]!=f["assembly_sha256"]:
            raise PermissionError("Frozen feature assembly changed")
        record_id="WO4FEATURE_"+manifest["ids"]["cpl"].replace("-","")
        doc={"format":FORMAT,"source_assembly_sha256":f["assembly_sha256"],
             "ordered_reel_job_ids":manifest["ordered_reel_job_ids"],
             "frame_count":sum(p["frames"] for p in manifest["reels"]),
             "reel_count":len(manifest["reels"]),"title":f["title"],
             "destination_name":folder.name,"file_sha256":files,
             "cpl_uuid":"urn:uuid:"+manifest["ids"]["cpl"],
             "pkl_uuid":"urn:uuid:"+manifest["ids"]["pkl"],
             "assetmap_uuid":"urn:uuid:"+manifest["ids"]["assetmap"],
             "production_dcp_accepted":False,"ffmpeg_used":False,
             "original_source_modified":False}
        history=index.history(f["project_id"],record_id)
        if history:
            if len(history)!=1 or history[0]["revision"]!=1:
                raise PermissionError("Feature receipt identity was already reused")
            previous=index.read_revision(f["project_id"],record_id,1)
            if previous["data"]!=doc:
                raise PermissionError("Existing FilmIndex feature source differs")
            doc_sha=previous["document_sha256"]
        else:
            result=index.register_revision(
                f["project_id"],record_id,"presentation",doc,
                expected_revision=0,
                dependencies=[{"object_id":f["assembly_id"],
                  "revision":f["assembly_revision"],"role":"presentation"}])
            doc_sha=result["document_sha256"]
        with self._tx() as db:
            row=db.execute("""SELECT state,filmindex_sha256 FROM
                production_features WHERE feature_id=?""",
                (feature_id,)).fetchone()
            if (row is None or row["state"] not in
                    ("PUBLISHED_PENDING_INDEX","INDEXED") or
                    row["filmindex_sha256"] not in (None,doc_sha)):
                raise PermissionError("Feature index state changed during commit")
            db.execute("""UPDATE production_features SET state='INDEXED',
                 filmindex_sha256=?,updated_at=? WHERE feature_id=?""",
                 (doc_sha,_now(),feature_id))
        return {"status":"MULTIREEL_FEATURE_FILMINDEX_RECORDED",
                "feature_id":feature_id,"filmindex_sha256":doc_sha,
                "production_dcp_accepted":False}

    def feature_review(self,owner,feature_id,reason):
        if type(reason) is not str or not 1<=len(reason)<=80:
            raise ValueError("Bounded feature failure category required")
        with self._tx() as db:
            row=db.execute("""SELECT owner,state FROM production_features
                        WHERE feature_id=?""",(feature_id,)).fetchone()
            if row is None or row["owner"]!=owner or row["state"]!="STAGING":
                raise PermissionError("Only active feature supervisor may require review")
            db.execute("""UPDATE production_features SET state='REVIEW_REQUIRED',
                owner=NULL,updated_at=? WHERE feature_id=?""",(_now(),feature_id))

    def request_feature_cancel(self,feature_id,authorize):
        if not callable(authorize):
            raise PermissionError("Native host cancellation approval required")
        f=self.feature(feature_id)
        if f["state"] not in ("QUEUED","STAGING"):
            raise PermissionError("Published multi-reel feature cannot be cancelled")
        scope={"operation":"nvp.supervisor.cancel_feature_dcp.v1",
               "feature_id":feature_id,
               "manifest_sha256":f["manifest_sha256"]}
        if authorize(deepcopy(scope)) is not True:
            return {"status":"DENIED","feature_id":feature_id}
        with self._tx() as db:
            row=db.execute("""SELECT state,manifest_sha256
                 FROM production_features WHERE feature_id=?""",
                 (feature_id,)).fetchone()
            if (row is None or row["state"]!=f["state"] or
                    row["manifest_sha256"]!=f["manifest_sha256"]):
                raise PermissionError("Multi-reel job changed during cancellation")
            db.execute("""UPDATE production_features SET
                cancel_requested=1,updated_at=? WHERE feature_id=?""",
                (_now(),feature_id))
        return {"status":"CANCEL_REQUESTED","feature_id":feature_id}

    def finalize_feature_cancel(self,feature_id,owner):
        with self._tx() as db:
            row=db.execute("""SELECT state,owner,cancel_requested
                FROM production_features WHERE feature_id=?""",
                (feature_id,)).fetchone()
            if (row is None or not row["cancel_requested"] or
                    row["state"] not in ("QUEUED","STAGING") or
                    (row["owner"] not in (None,owner))):
                raise PermissionError("Only authorized uncommitted feature can stop")
            db.execute("""UPDATE production_features SET
                state='CANCELLED',owner=NULL,updated_at=? WHERE feature_id=?""",
                (_now(),feature_id))
        return {"status":"CANCELLED","feature_id":feature_id}

    def reconcile_features(self):
        reports=[]
        with self._read() as db:
            jobs=[dict(x) for x in db.execute("""SELECT feature_id,state,
                output_root,manifest_json FROM production_features""")]
        for f in jobs:
            uid=f["feature_id"]
            manifest=json.loads(f["manifest_json"])
            root=Path(f["output_root"])
            stage=root/(".nvp-feature-stage-"+manifest["ids"]["cpl"])
            target=root/("DCP_FEATURE_"+manifest["ids"]["cpl"])
            state=f["state"]
            if state in ("QUEUED","STAGING"):
                if (state=="STAGING" or stage.exists() or stage.is_symlink()
                        or target.exists() or target.is_symlink()):
                    self._mark_feature_restart_review(uid)
                    state="REVIEW_REQUIRED"
            elif state in ("PUBLISHED_PENDING_INDEX","INDEXED"):
                try:self._recheck_feature(uid)
                except (OSError,RuntimeError,PermissionError,ValueError,TypeError):
                    self._mark_feature_restart_review(uid)
                    state="REVIEW_REQUIRED"
            reports.append({"feature_id":uid,"state":state})
        return {"format":FORMAT,"jobs":reports,
                "deleted_uncommitted_files":False,
                "production_dcp_accepted":False}

    def _mark_feature_restart_review(self,feature_id):
        with self._tx() as db:
            db.execute("""UPDATE production_features
                SET state='REVIEW_REQUIRED',owner=NULL,updated_at=?
                WHERE feature_id=?""",(_now(),feature_id))
