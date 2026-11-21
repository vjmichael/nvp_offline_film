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
    FORMAT as JOB_FORMAT,_canonical,_digest,_now,TICKS_PER_SECOND,_require_owner,ID_RE)
from backend.nvp_wo4_pcm_stream import _protected_path,_hash_stream
from backend.nvp_wo4_file_dcp import _export_root,_assert_export_root,_stream_digest
from backend.nvp_wo3_dcp_structure import _linked_entry
from backend.nvp_w1g_release_gate import inspect_original_process_journals
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo3_native_codecs import digest_file
from backend.nvp_film_index import FilmIndex,MAX_DEPENDENCIES
from backend import nvp_wo4_feature_pages as pages

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
            CREATE INDEX IF NOT EXISTS production_features_catalog_page
              ON production_features(project_id,project_db,created_at,feature_id);
            CREATE INDEX IF NOT EXISTS production_feature_ready
              ON production_features(state,created_at);
            """)
            pages.initialize(db)
            from backend.nvp_audio_recovery import initialize as initialize_audio
            initialize_audio(db)

    @staticmethod
    def _feature_row(db, feature_id):
        row=db.execute("SELECT * FROM production_features WHERE feature_id=?",(feature_id,)).fetchone()
        if row is None:
            raise KeyError("Native feature assembly not found")
        return row

    @staticmethod
    def _check_header(row,manifest):
        if any(manifest.get(k)!=row[k] for k in
            ("project_id","assembly_id","assembly_revision","assembly_sha256",
             "project_db","output_root","title","profile")):
            raise PermissionError("Feature manifest changed")

    def _verified_feature(self,db,feature_id):
        row=self._feature_row(db,feature_id)
        manifest=pages.source(db,feature_id,row["manifest_json"],row["manifest_sha256"])
        self._check_header(row,manifest)
        files=pages.output(db,feature_id,row["file_sha_json"],row["manifest_sha256"])
        result=dict(row)
        result["manifest_json"]=_canonical(manifest).decode('ascii')
        result["file_sha_json"]=None if files is None else _canonical(files).decode('ascii')
        return result

    def feature(self,feature_id):
        with self._read() as db:
            if not db.in_transaction:db.execute("BEGIN")
            return self._verified_feature(db,feature_id)

    def feature_page(self,feature_id,*,project_id,project_db,first=0,limit=32,kind="source"):
        """Read only; validate complete page chain, then return a redacted page."""
        if (type(first) is not int or first<0 or type(limit) is not int or
                not 1<=limit<=pages.PAGE or kind not in ("source","output")):
            raise ValueError("Bounded feature page required")
        with self._read() as db:
            if not db.in_transaction:db.execute("BEGIN")
            row=self._feature_row(db,feature_id)
            if row["project_id"]!=project_id or row["project_db"]!=str(project_db):
                raise PermissionError("Feature outside approved movie")
            header,count,items=pages.source(db,feature_id,row["manifest_json"],row["manifest_sha256"],first=first if kind=="source" else 0,limit=limit if kind=="source" else 1)
            self._check_header(row,header)
            n,files=pages.output(db,feature_id,row["file_sha_json"],row["manifest_sha256"],first=first if kind=="output" else 0,limit=limit if kind=="output" else 1)
            if kind=="source":
                entries=[{"reel":first+i+1,"frames":item["reels"]["frames"],
                          "picture_sha256":item["reels"]["picture"]["file_sha256"],
                          "sound_sha256":item["reels"]["sound"]["file_sha256"]} for i,item in enumerate(items)]
                total=count
            else:
                entries=[{"name":name,"sha256":digest} for name,digest in files];total=n
            if first>=total and (first!=0 or total!=0):raise ValueError("Feature page outside manifest")
            end=first+len(entries)
            return {"project_id":project_id,"feature_id":feature_id,"state":row["state"],
                    "kind":kind,"entries":entries,"total":total,"first":first,
                    "next_first":end if end<total else None,"manifest_sha256":row["manifest_sha256"],
                    "source_paths_exposed":False,"production_dcp_accepted":False}

    def submit_feature(self,index,project_id,*,assembly_id,
                       assembly_revision,ordered_job_ids,title,profile,
                       output_root,approve):
        if (not isinstance(index,FilmIndex) or not callable(approve) or
                type(ordered_job_ids) is not list or
                not 2<=len(ordered_job_ids)<=min(MAX_REELS,MAX_DEPENDENCIES-1) or
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
        ordered_job_ids=list(ordered_job_ids)
        root,root_identity=_export_root(output_root)
        project_db=Path(index.studio.db_path)
        db_identity=_protected_path(project_db)
        authorities=[]
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
            authorities.append({"source_take_sha256":reel["take_sha256"],"mastering_decision_sha256":reel["decision_sha256"],"indexed_receipt_sha256":d["filmindex_sha256"]})
            parts.append({
                "start_tick":start,"end_tick":start+frames*FRAME_TICKS,
                "frames":frames,"reel_uuid":d["reel_uuid"],
                "picture":{
                    "file_path":str(self.spool(job_id)/"picture.mxf"),
                    "file_sha256":reel["track_sha256"],
                    "file_bytes":reel["track_bytes"],
                    "asset_uuid":reel["picture_uuid"],"kind":"picture",
                    "source_take_sha256":reel["take_sha256"],"frame_count":frames,
                    "profile":profile,"edit_rate":[24,1],"source_modified":False,"production_dcp_accepted":False},
                "sound":{
                    "file_path":str(self.spool(job_id)/"sound.mxf"),
                    "file_sha256":d["sound_sha256"],
                    "file_bytes":d["sound_bytes"],
                    "asset_uuid":d["sound_uuid"],"kind":"sound",
                    "source_take_sha256":reel["take_sha256"],"frame_count":frames,
                    "edit_rate":[24,1],"source_modified":False,"production_dcp_accepted":False},
            })
            start+=frames*FRAME_TICKS
        if start!=data["end_tick"]:
            raise PermissionError("Feature Film Time differs from approved assembly")
        ids={key:str(uuid4()) for key in ("cpl","pkl","assetmap")}
        _check_manifest(parts,ids,authorities[0]["source_take_sha256"],profile,source_reel_authority=authorities)
        manifest={
            "format":FORMAT,"project_id":project_id,
            "assembly_id":assembly_id,
            "assembly_revision":assembly_revision,
            "assembly_sha256":assembly["document_sha256"],
            "title":title,"profile":profile,
            "ordered_reel_job_ids":ordered_job_ids,
            "reels":parts,"ids":ids,"source_reel_authority":authorities,
            "project_db":str(project_db.resolve(strict=True)),
            "project_db_identity":list(db_identity),"export_root_identity":list(root_identity),
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
               "output_root":str(root),"cpl_uuid":ids["cpl"],
               "plaintext_export_explicitly_requested":True}
        if approve(deepcopy(scope)) is not True:
            return {"status":"DENIED","source_modified":False}
        if (index.read_revision(project_id,assembly_id,assembly_revision)[
                "document_sha256"]!=assembly["document_sha256"]):
            raise PermissionError("Feature assembly changed during approval")
        _assert_export_root(root,root_identity)
        if _protected_path(project_db)!=db_identity:
            raise PermissionError("Project database changed during feature consent")
        _check_manifest(parts,ids,authorities[0]["source_take_sha256"],profile,source_reel_authority=authorities)
        self._verify_feature_sources(manifest,index=index)
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
            stored=pages.store_source(db,fid,manifest,manifest_sha)
            db.execute("UPDATE production_features SET manifest_json=? WHERE feature_id=?",(stored,fid))
        return {"format":FORMAT,"status":"QUEUED","feature_id":fid,
                "manifest_sha256":manifest_sha,"reel_count":len(parts),
                "total_frames":start//FRAME_TICKS,
                "production_dcp_accepted":False}

    def _assert_feature_idle(self):
        _require_owner(self.root)
        with self._read() as db:
            if db.execute("SELECT 1 FROM production_features WHERE state='STAGING'").fetchone():
                raise PermissionError("Interrupted feature lease requires reconciliation")

    def claim_next(self,owner_token,pid,**kwargs):
        self._assert_feature_idle()
        return super().claim_next(owner_token,pid,**kwargs)

    def next_track(self,owner,pid):
        self._assert_feature_idle()
        return super().next_track(owner,pid)

    def next_delivery(self,owner,pid):
        self._assert_feature_idle()
        return super().next_delivery(owner,pid)

    def next_feature(self,owner):
        _require_owner(self.root)
        if type(owner) is not str or not ID_RE.fullmatch(owner):
            raise PermissionError("Live feature owner required")
        with self._tx() as db:
            row=db.execute("""SELECT feature_id,manifest_json FROM
                production_features WHERE state='QUEUED'
                AND cancel_requested=0
                AND NOT EXISTS (SELECT 1 FROM production_features WHERE state='STAGING')
                AND NOT EXISTS (SELECT 1 FROM production_jobs WHERE state IN ('RUNNING','DELIVERY_RUNNING'))
                ORDER BY created_at LIMIT 1""").fetchone()
            if row is None:
                return None
            verified=self._verified_feature(db,row["feature_id"])
            db.execute("""UPDATE production_features SET
                state='STAGING',owner=?,updated_at=? WHERE feature_id=?""",
                (owner,_now(),row["feature_id"]))
            return {"feature_id":row["feature_id"],
                    "manifest":json.loads(verified["manifest_json"])}

    def feature_cancel_requested(self,feature_id,owner):
        _require_owner(self.root)
        with self._read() as db:
            row=db.execute("""SELECT owner,cancel_requested FROM
                     production_features WHERE feature_id=?""",
                     (feature_id,)).fetchone()
            if row is None or row["owner"]!=owner:
                raise PermissionError("Native feature worker lost ownership")
            return bool(row["cancel_requested"])

    def commit_feature(self,owner,feature_id,receipt):
        _require_owner(self.root)
        f=self.feature(feature_id)
        manifest=json.loads(f["manifest_json"])
        self._verify_feature_sources(manifest)
        folder=Path(f["output_root"])/("DCP_FEATURE_"+manifest["ids"]["cpl"])
        if (receipt.get("status")!="MULTIREEL_STRUCTURAL_DCP_PUBLISHED" or
                receipt.get("destination")!=str(folder) or
                receipt.get("cpl_uuid")!=manifest["ids"]["cpl"] or
                receipt.get("reel_count")!=len(manifest["reels"]) or
                receipt.get("source_reel_authority")!=manifest["source_reel_authority"] or
                receipt.get("source_take_sha256")!=manifest["source_reel_authority"][0]["source_take_sha256"] or
                receipt.get("mastering_decision_sha256")!=manifest["source_reel_authority"][0]["mastering_decision_sha256"] or
                receipt.get("feature_assembly_sha256")!=manifest["assembly_sha256"] or
                _linked_entry(folder) or not folder.is_dir()):
            raise PermissionError("No exact native multi-reel DCP published")
        expected=receipt.get("file_sha256")
        names={"CPL.xml","PKL.xml","ASSETMAP.xml","VOLINDEX.xml"}
        names.update(f"{kind}_{i:04d}.mxf" for i in range(len(manifest["reels"])) for kind in ("picture","sound"))
        if (type(expected) is not dict or set(expected)!=names or
                set(expected)!={p.name for p in folder.iterdir()} or
                any(_linked_entry(folder/name) or not (folder/name).is_file() or
                    digest_file(folder/name)!=digest for name,digest in expected.items())):
            raise PermissionError("Multi-reel output SHA manifest differs")
        audit=self._audit_new_feature_package(folder,manifest)
        if (audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
                audit["cpl_uuid"]!=manifest["ids"]["cpl"] or
                audit["reel_durations"]!=[r["frames"] for r in manifest["reels"]]):
            raise PermissionError("Published multi-reel CPL/PKL audit rejected")
        self._verify_feature_package(manifest,folder,audit)
        with self._tx() as db:
            row=db.execute("""SELECT state,owner,cancel_requested,
                             manifest_sha256 FROM production_features
                             WHERE feature_id=?""",(feature_id,)).fetchone()
            if (row is None or row["state"]!="STAGING" or
                    row["owner"]!=owner or row["cancel_requested"] or
                    row["manifest_sha256"]!=f["manifest_sha256"]):
                raise PermissionError("Stale feature worker may not commit output")
            if self._verified_feature(db,feature_id)!=f:
                raise PermissionError("Feature changed during output checkpoint")
            stored=pages.store_output(db,feature_id,expected,f["manifest_sha256"])
            db.execute("""UPDATE production_features SET
                state='PUBLISHED_PENDING_INDEX',owner=NULL,
                file_sha_json=?,updated_at=? WHERE feature_id=?""",
                (stored,_now(),feature_id))
        return {"status":"PUBLISHED_PENDING_INDEX","feature_id":feature_id,
                "destination":str(folder),"production_dcp_accepted":False}

    def _verify_feature_sources(self,m,*,index=None):
        if (type(m["ordered_reel_job_ids"]) is not list or len(m["ordered_reel_job_ids"])!=len(m["reels"]) or
                len(set(m["ordered_reel_job_ids"]))!=len(m["reels"])):
            raise PermissionError("Frozen feature reel list differs")
        _assert_export_root(Path(m["output_root"]),tuple(m["export_root_identity"]))
        _check_manifest(m["reels"],m["ids"],m["source_reel_authority"][0]["source_take_sha256"],m["profile"],
                        source_reel_authority=m["source_reel_authority"])
        if index is not None:
            db=Path(index.studio.db_path)
            if (str(db.resolve(strict=True))!=m["project_db"] or
                _protected_path(db)!=tuple(m["project_db_identity"]) or
                index.read_revision(m["project_id"],m["assembly_id"],m["assembly_revision"])["document_sha256"]!=m["assembly_sha256"]):
                raise PermissionError("Resolved feature project or assembly differs")
            assembly=index.read_revision(m["project_id"],m["assembly_id"],m["assembly_revision"])["data"]
            if "hierarchical_source_ref" in assembly:
                from backend import nvp_feature_sections as groups
                derived=groups.finite_export_plan(index,m["project_id"],assembly["hierarchical_source_ref"],
                    frame_ticks=FRAME_TICKS,profile=m["profile"],reel_budget=min(MAX_REELS,MAX_DEPENDENCIES-1),
                    read_reel=lambda uid:groups.native_reel_metadata(self,m["project_id"],uid))
                if derived!=assembly or derived["ordered_reel_job_ids"]!=m["ordered_reel_job_ids"]:
                    raise PermissionError("Derived feature hierarchy no longer matches immutable source")
        for job_id,part,authority in zip(m["ordered_reel_job_ids"],m["reels"],m["source_reel_authority"]):
            status=self.status(job_id); reel=self.reel(job_id); d=self.delivery(job_id)
            if (status["project_id"]!=m["project_id"] or status["state"]!="DCP_INDEXED" or
                d["phase"]!="INDEXED" or authority!={"source_take_sha256":reel["take_sha256"],
                "mastering_decision_sha256":reel["decision_sha256"],"indexed_receipt_sha256":d["filmindex_sha256"]} or
                part["picture"]["file_path"]!=str(self.spool(job_id)/"picture.mxf") or
                part["sound"]["file_path"]!=str(self.spool(job_id)/"sound.mxf") or
                part["picture"]["file_sha256"]!=reel["track_sha256"] or
                part["sound"]["file_sha256"]!=d["sound_sha256"] or
                part["picture"]["asset_uuid"]!=reel["picture_uuid"] or
                part["sound"]["asset_uuid"]!=d["sound_uuid"] or
                part["reel_uuid"]!=d["reel_uuid"]):
                raise PermissionError("Frozen indexed source reel changed")
            self._verify_all_production_sources(job_id)
            self._check_published(job_id)
            if index is not None and index.read_revision(m["project_id"],
                "WO3DCP_"+d["cpl_uuid"].replace("-",""),1)["document_sha256"]!=d["filmindex_sha256"]:
                raise PermissionError("Indexed source reel FilmIndex identity changed")

    @staticmethod
    def _audit_new_feature_package(folder, manifest):
        """New output and orphan adoption use the same strict grammar as
        the writer; the approved order and ranges are independently bound.
        """
        from backend.nvp_dci_package import inspect_cinema_package
        expected=[]
        start=0
        for part in manifest["reels"]:
            expected.append({"reel_uuid":part["reel_uuid"],"start_frame":start,
                "picture_uuid":part["picture"]["asset_uuid"],
                "sound_uuid":part["sound"]["asset_uuid"],"frames":part["frames"]})
            start+=part["frames"]
        return inspect_cinema_package(folder, expected_profile=manifest["profile"],
                                     expected_reels=expected)

    def _verify_feature_package(self,m,folder,audit):
        if audit["pkl_uuid"]!=m["ids"]["pkl"] or audit["reel_count"]!=len(m["reels"]):
            raise PermissionError("Feature package identity differs")
        from backend.nvp_wo3_dcp_structure import _xml,_value,NS_CPL,NS_AM
        cpl=_xml(folder,"CPL.xml",NS_CPL,"CompositionPlaylist")
        reels=cpl.find("{"+NS_CPL+"}ReelList")
        nodes=[] if reels is None else reels.findall("{"+NS_CPL+"}Reel")
        if _value(cpl,"ContentTitleText",NS_CPL)!=m["title"] or len(nodes)!=len(m["reels"]):
            raise PermissionError("Feature reel count differs")
        for i,(node,part) in enumerate(zip(nodes,m["reels"])):
            if _value(node,"Id",NS_CPL)!="urn:uuid:"+part["reel_uuid"]:
                raise PermissionError("Feature reel order differs")
            assets=node.find("{"+NS_CPL+"}AssetList")
            for kind,tag in (("picture","MainPicture"),("sound","MainSound")):
                entry=None if assets is None else assets.find("{"+NS_CPL+"}"+tag)
                if (entry is None or _value(entry,"Id",NS_CPL)!="urn:uuid:"+part[kind]["asset_uuid"] or
                    _value(entry,"EntryPoint",NS_CPL)!="0" or
                    _value(entry,"IntrinsicDuration",NS_CPL)!=str(part["frames"]) or
                    _value(entry,"Duration",NS_CPL)!=str(part["frames"]) or
                    _stream_digest(folder/f"{kind}_{i:04d}.mxf")["sha256"]!=part[kind]["file_sha256"]):
                    raise PermissionError("Feature ordered track changed")
        amap=_xml(folder,"ASSETMAP.xml",NS_AM,"AssetMap")
        if _value(amap,"Id",NS_AM)!="urn:uuid:"+m["ids"]["assetmap"]:
            raise PermissionError("Feature AssetMap identity differs")

    def _recheck_feature(self,feature_id):
        f=self.feature(feature_id)
        manifest=json.loads(f["manifest_json"])
        if _digest(_canonical(manifest))!=f["manifest_sha256"]:
            raise PermissionError("Feature manifest was altered in SQLite")
        folder=Path(f["output_root"])/("DCP_FEATURE_"+manifest["ids"]["cpl"])
        if _linked_entry(folder) or not folder.is_dir():
            raise PermissionError("Indexed feature package is missing")
        expected=json.loads(f["file_sha_json"])
        names={"CPL.xml","PKL.xml","ASSETMAP.xml","VOLINDEX.xml"}
        names.update(f"{kind}_{i:04d}.mxf" for i in range(len(manifest["reels"])) for kind in ("picture","sound"))
        if (type(expected) is not dict or set(expected)!=names or set(expected)!={p.name for p in folder.iterdir()}
                or any(_linked_entry(folder/name) or not (folder/name).is_file() or
                       digest_file(folder/name)!=sha for name,sha in expected.items())):
            raise PermissionError("Committed feature output hash mismatch")
        audit=inspect_dcp_structure(folder)
        if (audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
                audit["reel_durations"]!=[part["frames"] for part in manifest["reels"]] or
                audit["cpl_uuid"]!=manifest["ids"]["cpl"]):
            raise PermissionError("Committed feature CPL duration/UUID changed")
        self._verify_feature_package(manifest,folder,audit)
        self._verify_feature_sources(manifest)
        for job_id,part in zip(manifest["ordered_reel_job_ids"],
                               manifest["reels"]):
            reel_status=self.status(job_id)
            delivery=self.delivery(job_id)
            if (reel_status["project_id"]!=f["project_id"] or
                    reel_status["state"]!="DCP_INDEXED" or
                    delivery["phase"]!="INDEXED"):
                raise PermissionError("Original source reel job no longer indexed")
            self._verify_all_production_sources(job_id)
            self._check_published(job_id)
            for kind in ("picture","sound"):
                track=part[kind]
                file=Path(track["file_path"])
                if (_linked_entry(file) or not file.is_file() or
                        file.stat().st_size!=track["file_bytes"] or
                        digest_file(file)!=track["file_sha256"]):
                    raise PermissionError("Original feature reel source MXF changed")
        return f,manifest,folder,expected

    def next_feature_index(self):
        self._assert_feature_idle()
        with self._read() as db:
            row=db.execute("""SELECT feature_id FROM production_features
                   WHERE state='PUBLISHED_PENDING_INDEX' AND cancel_requested=0
                   ORDER BY created_at LIMIT 1""").fetchone()
            return None if row is None else row["feature_id"]

    def commit_feature_index(self,feature_id,*,index):
        _require_owner(self.root)
        if not isinstance(index,FilmIndex):
            raise PermissionError("Trusted project resolver required")
        f,manifest,folder,files=self._recheck_feature(feature_id)
        if f["state"] not in ("PUBLISHED_PENDING_INDEX","INDEXED"):
            raise PermissionError("Feature is not a published package")
        self._verify_feature_sources(manifest,index=index)
        assembly=index.read_revision(
            f["project_id"],f["assembly_id"],f["assembly_revision"])
        if assembly["document_sha256"]!=f["assembly_sha256"]:
            raise PermissionError("Frozen feature assembly changed")
        record_id="WO4FEATURE_"+manifest["ids"]["cpl"].replace("-","")
        doc={"format":FORMAT,"source_assembly_sha256":f["assembly_sha256"],
             "source_reel_authority":manifest["source_reel_authority"],"feature_manifest_sha256":f["manifest_sha256"],
             "ordered_reel_job_ids":manifest["ordered_reel_job_ids"],
             "frame_count":sum(p["frames"] for p in manifest["reels"]),
             "reel_count":len(manifest["reels"]),"title":f["title"],
             "destination_name":folder.name,"file_sha256":files,
             "cpl_uuid":"urn:uuid:"+manifest["ids"]["cpl"],
             "pkl_uuid":"urn:uuid:"+manifest["ids"]["pkl"],
             "assetmap_uuid":"urn:uuid:"+manifest["ids"]["assetmap"],
             "production_dcp_accepted":False,"ffmpeg_used":False,
             "original_source_modified":False}
        deps=[{"object_id":f["assembly_id"],"revision":f["assembly_revision"],"role":"presentation"}]
        expected=[f["assembly_sha256"]]
        for uid in manifest["ordered_reel_job_ids"]:
            d=self.delivery(uid)
            deps.append({"object_id":"WO3DCP_"+d["cpl_uuid"].replace("-",""),"revision":1,"role":"presentation"})
            expected.append(d["filmindex_sha256"])
        def guard(db):
            for edge,digest in zip(deps,expected):
                row=index._read_revision(db,f["project_id"],edge["object_id"],edge["revision"])
                if row is None or row["document_sha"]!=digest:
                    raise PermissionError("Feature source changed in FilmIndex commit")
        history=index.history(f["project_id"],record_id)
        if history:
            if len(history)!=1 or history[0]["revision"]!=1:
                raise PermissionError("Feature receipt identity was already reused")
            previous=index.read_revision(f["project_id"],record_id,1)
            if previous["kind"]!="presentation" or previous["data"]!=doc or sorted(previous["dependencies"],key=lambda d:d["object_id"])!=sorted(deps,key=lambda d:d["object_id"]):
                raise PermissionError("Existing FilmIndex feature source differs")
            doc_sha=previous["document_sha256"]
        else:
            result=index.register_revision(
                f["project_id"],record_id,"presentation",doc,
                expected_revision=0,
                dependencies=deps,precommit_guard=guard)
            doc_sha=result["document_sha256"]
        with self._tx() as db:
            row=db.execute("""SELECT state,filmindex_sha256,manifest_sha256,cancel_requested FROM
                production_features WHERE feature_id=?""",
                (feature_id,)).fetchone()
            if (row is None or row["state"] not in
                    ("PUBLISHED_PENDING_INDEX","INDEXED") or
                    row["manifest_sha256"]!=f["manifest_sha256"] or row["cancel_requested"] or
                    row["filmindex_sha256"] not in (None,doc_sha)):
                raise PermissionError("Feature index state changed during commit")
            db.execute("""UPDATE production_features SET state='INDEXED',
                 filmindex_sha256=?,updated_at=? WHERE feature_id=?""",
                 (doc_sha,_now(),feature_id))
        return {"status":"MULTIREEL_FEATURE_FILMINDEX_RECORDED",
                "feature_id":feature_id,"filmindex_sha256":doc_sha,
                "production_dcp_accepted":False}

    def feature_review(self,owner,feature_id,reason):
        _require_owner(self.root)
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
        _require_owner(self.root)
        f=self.feature(feature_id);m=json.loads(f["manifest_json"])
        root=Path(f["output_root"])
        artifacts=[root/(prefix+m["ids"]["cpl"]) for prefix in (".nvp-feature-stage-","DCP_FEATURE_")]
        with self._tx() as db:
            row=db.execute("""SELECT state,owner,cancel_requested
                FROM production_features WHERE feature_id=?""",
                (feature_id,)).fetchone()
            if (row is None or not row["cancel_requested"] or
                    row["state"] not in ("QUEUED","STAGING") or
                    (row["owner"] not in (None,owner))):
                raise PermissionError("Only authorized uncommitted feature can stop")
            if self._verified_feature(db,feature_id)!=f:
                raise PermissionError("Feature cancellation state changed")
            state="REVIEW_REQUIRED" if any(p.exists() or _linked_entry(p) for p in artifacts) else "CANCELLED"
            db.execute("""UPDATE production_features SET
                state=?,owner=NULL,updated_at=? WHERE feature_id=?""",
                (state,_now(),feature_id))
        return {"status":state,"feature_id":feature_id}

    def reconcile_features(self):
        _require_owner(self.root)
        reports=[];count=0;after=""
        while True:
            with self._read() as db:
                jobs=[row[0] for row in db.execute("SELECT feature_id FROM production_features WHERE feature_id>? ORDER BY feature_id LIMIT ?",(after,pages.PAGE))]
            if not jobs:break
            for uid in jobs:
                try:
                    f=self.feature(uid)
                    manifest=json.loads(f["manifest_json"])
                    root=Path(f["output_root"])
                    stage=root/(".nvp-feature-stage-"+manifest["ids"]["cpl"])
                    target=root/("DCP_FEATURE_"+manifest["ids"]["cpl"])
                    state=f["state"]
                    artifacts=stage.exists() or _linked_entry(stage) or target.exists() or _linked_entry(target)
                    if state in ("QUEUED","STAGING"):
                        if artifacts or state=="STAGING":
                            self._mark_feature_restart_review(uid);state="REVIEW_REQUIRED"
                        elif f["cancel_requested"]:
                            state=self.finalize_feature_cancel(uid,f["owner"])["status"]
                    elif state in ("PUBLISHED_PENDING_INDEX","INDEXED"):
                        self._recheck_feature(uid)
                except (OSError,RuntimeError,ValueError,TypeError,KeyError):
                    self._mark_feature_restart_review(uid);state="REVIEW_REQUIRED"
                count+=1
                if len(reports)<pages.PAGE:reports.append({"feature_id":uid,"state":state})
            after=jobs[-1]
        return {"format":FORMAT,"jobs":reports,"total_jobs":count,
                "report_truncated":count>len(reports),"deleted_uncommitted_files":False,
                "production_dcp_accepted":False}

    def approve_orphan_feature_adoption(self,feature_id,authorize):
        """Explicitly adopt a complete post-publish/pre-checkpoint feature.

        No mutation of the DCP directory, no overwrites and no acceptance of
        incomplete stages. All original source reels and approved MXFs, every
        copied asset and the exact CPL/PKL/AssetMap must match.
        """
        _require_owner(self.root)
        if not callable(authorize):
            raise PermissionError("Native creator review authorization required")
        f=self.feature(feature_id)
        if (f["state"]!="REVIEW_REQUIRED" or f["file_sha_json"] is not None
                or f["filmindex_sha256"] is not None or f["cancel_requested"]):
            raise PermissionError("Only uncommitted feature orphan may be reviewed")
        manifest=json.loads(f["manifest_json"])
        if _digest(_canonical(manifest))!=f["manifest_sha256"]:
            raise PermissionError("Frozen feature manifest integrity failed")
        root=Path(f["output_root"])
        folder=root/("DCP_FEATURE_"+manifest["ids"]["cpl"])
        stage=root/(".nvp-feature-stage-"+manifest["ids"]["cpl"])
        if (_linked_entry(root) or _linked_entry(folder) or
                not folder.is_dir() or stage.exists() or _linked_entry(stage)):
            raise PermissionError("Partial feature stage cannot be adopted")
        self._verify_feature_sources(manifest)
        names={"CPL.xml","PKL.xml","ASSETMAP.xml","VOLINDEX.xml"}
        expected_tracks=set()
        for i,part in enumerate(manifest["reels"]):
            job_id=manifest["ordered_reel_job_ids"][i]
            status=self.status(job_id)
            delivery=self.delivery(job_id)
            if (status["state"]!="DCP_INDEXED" or
                    status["project_id"]!=f["project_id"] or
                    delivery["phase"]!="INDEXED"):
                raise PermissionError("Frozen original reel index was revoked")
            self._verify_all_production_sources(job_id)
            self._check_published(job_id)
            for kind in ("picture","sound"):
                filename=f"{kind}_{i:04d}.mxf"
                names.add(filename)
                original=part[kind]
                if (_linked_entry(folder/filename) or
                        not (folder/filename).is_file() or
                        digest_file(folder/filename)!=original["file_sha256"]):
                    raise PermissionError("Feature MXF differs from verified original reel")
                expected_tracks.add((kind,original["asset_uuid"]))
        if {p.name for p in folder.iterdir()}!=names:
            raise PermissionError("Orphan feature has extra or missing package assets")
        report=self._audit_new_feature_package(folder,manifest)
        if (report["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
                report["cpl_uuid"]!=manifest["ids"]["cpl"] or
                report["pkl_uuid"]!=manifest["ids"]["pkl"] or
                report["reel_durations"]!=[r["frames"] for r in manifest["reels"]] or
                {(x["kind"],x["asset_id"]) for x in report["tracks"]}!=expected_tracks):
            raise PermissionError("Orphan multi-reel CPL/PKL/hash proof failed")
        self._verify_feature_package(manifest,folder,report)
        files={name:digest_file(folder/name) for name in sorted(names)}
        scope={"operation":"nvp.supervisor.adopt_verified_orphan_feature.v1",
               "feature_id":feature_id,
               "manifest_sha256":f["manifest_sha256"],
               "cpl_uuid":manifest["ids"]["cpl"],
               "file_sha256":files,
               "preserve_published_directory":True}
        if authorize(deepcopy(scope)) is not True:
            return {"status":"DENIED","feature_id":feature_id}
        self._verify_feature_sources(manifest)
        if (self._audit_new_feature_package(folder,manifest)["status"]!="STRUCTURE_AND_SHA_VERIFIED"
                or {p.name for p in folder.iterdir()}!=names
                or any(digest_file(folder/name)!=digest
                       for name,digest in files.items())):
            raise PermissionError("Feature changed during creator approval")
        with self._tx() as db:
            row=db.execute("""SELECT state,manifest_sha256,
                file_sha_json,cancel_requested FROM production_features
                WHERE feature_id=?""",(feature_id,)).fetchone()
            if (row is None or row["state"]!="REVIEW_REQUIRED" or
                    row["manifest_sha256"]!=f["manifest_sha256"] or
                    row["file_sha_json"] is not None or row["cancel_requested"]):
                raise PermissionError("Feature review changed before durable adoption")
            if self._verified_feature(db,feature_id)!=f:
                raise PermissionError("Feature changed during creator review")
            stored=pages.store_output(db,feature_id,files,f["manifest_sha256"])
            db.execute("""UPDATE production_features SET
                state='PUBLISHED_PENDING_INDEX',file_sha_json=?,
                owner=NULL,updated_at=? WHERE feature_id=?""",
                (stored,_now(),feature_id))
        return {"status":"PUBLISHED_PENDING_INDEX","feature_id":feature_id,
                "destination":str(folder),"file_sha256":files,
                "filesystem_mutated":False,"production_dcp_accepted":False}

    def _mark_feature_restart_review(self,feature_id):
        _require_owner(self.root)
        with self._tx() as db:
            db.execute("""UPDATE production_features
                SET state='REVIEW_REQUIRED',owner=NULL,updated_at=?
                WHERE feature_id=?""",(_now(),feature_id))
