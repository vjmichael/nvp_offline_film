"""WO4-LF02/04: sound and full DCP transitions in ONE CinemaJournal.

Extends the existing SQLite database and independent ProductionSupervisor,
never creates a competing task queue. A private approved WAV is supervised
into sound MXF, then the matched picture+sound are file-backed packaged into
CPL/PKL/AssetMap. The final FilmIndex transaction is a separate recoverable
transition after no-replace publication.

A published output is not a certified DCI package and cannot be treated as
fully registered until both the DCP and FilmIndex SHA receipts agree.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import uuid4
import re

from backend.nvp_production_cinema import CinemaJournal,TASK_KIND as PICTURE_TASK,_protected_receipt
from backend.nvp_wo4_mastering_decision import FORMAT as DECISION_FORMAT
from backend.nvp_wo4_supervised_sound import _read_guarded_sound
from backend.nvp_partitioned_delivery_bridge import verify_finite_selection, partitioned_provenance
from backend.nvp_wo4_longfilm_audio import finite_reel_candidate
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_wo3_native_codecs import digest_file
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo3_dcp_package import FORMAT as PACKAGE_FORMAT
from backend.nvp_film_index import FilmIndex
from backend.nvp_production_journal import _now,_canonical,_digest,_require_owner,ID_RE
from backend.nvp_wo4_pcm_stream import _protected_path,_hash_stream
from backend.nvp_wo4_file_dcp import _export_root,_assert_export_root
from backend.nvp_wo3_dcp_structure import _linked_entry
from backend.nvp_w1g_release_gate import inspect_original_process_journals
from backend.nvp_wo4_file_dcp import _stream_digest

FORMAT="nvp.wo4.supervised_file_dcp_delivery.v1"
SHA=re.compile(r"[0-9a-f]{64}\Z")
ACTIVE=frozenset(("SOUND_PENDING","SOUND_RUNNING","SOUND_READY",
                  "PACKAGE_RUNNING","PUBLISHED_PENDING_INDEX"))
DELIVERY_STATES=frozenset((*ACTIVE,"INDEXED","REVIEW_REQUIRED"))

class CinemaDeliveryJournal(CinemaJournal):
    def __init__(self,state_root):
        super().__init__(state_root)
        with self._tx() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS production_cinema_delivery(
                job_id TEXT PRIMARY KEY REFERENCES production_jobs(job_id),
                project_db TEXT NOT NULL,output_root TEXT NOT NULL,
                title TEXT NOT NULL,wav_path TEXT NOT NULL,
                wav_sha256 TEXT NOT NULL,wav_bytes INTEGER NOT NULL,
                master_pcm_sha256 TEXT NOT NULL,channel_order TEXT NOT NULL,
                sound_uuid TEXT NOT NULL,cpl_uuid TEXT NOT NULL,
                pkl_uuid TEXT NOT NULL,assetmap_uuid TEXT NOT NULL,
                reel_uuid TEXT NOT NULL,
                phase TEXT NOT NULL,
                approval_json TEXT NOT NULL,approval_sha256 TEXT NOT NULL,
                sound_receipt_json TEXT,sound_receipt_sha256 TEXT,
                sound_sha256 TEXT,sound_bytes INTEGER,
                dcp_files_json TEXT,filmindex_sha256 TEXT,
                updated_at TEXT NOT NULL
            );
            """)

    def delivery(self,job_id):
        with self._read() as db:
            row=db.execute(
                "SELECT * FROM production_cinema_delivery WHERE job_id=?",
                (job_id,)).fetchone()
            if row is None:raise KeyError("Approved native cinema delivery absent")
            result=dict(row)
            plan=json.loads(row["approval_json"])
            base,manifest=self._verified_manifest(db,job_id)
            if (plan.get("project_id")!=base["project_id"] or plan.get("manifest_sha256")!=base["manifest_sha256"] or
                plan.get("source_take_sha256")!=manifest["source_take_sha256"] or
                plan.get("mastering_decision_sha256")!=base["assembly_sha256"] or
                plan.get("plaintext_export_explicitly_requested") is not True):
                raise PermissionError("Delivery approval detached from the frozen picture plan")
            if (_digest(_canonical(plan))!=row["approval_sha256"] or
                    any(plan.get(k)!=row[k] for k in
                        ("job_id","project_db","output_root","title","wav_path",
                         "wav_sha256","wav_bytes","master_pcm_sha256","sound_uuid",
                         "cpl_uuid","pkl_uuid","assetmap_uuid","reel_uuid")) or
                    plan.get("channel_order")!=json.loads(row["channel_order"])):
                raise PermissionError("Delivery approval manifest changed")
            if row["sound_sha256"] is not None:
                evidence=json.loads(row["sound_receipt_json"] or "null")
                if (type(evidence) is not dict or
                    _digest(_canonical(evidence))!=row["sound_receipt_sha256"] or
                    evidence.get("file_sha256")!=row["sound_sha256"] or
                    evidence.get("file_bytes")!=row["sound_bytes"]):
                    raise PermissionError("Sound checkpoint receipt changed")
            return result

    def approved_sound_candidate(self,job_id):
        row=self.delivery(job_id)
        reel=self.reel(job_id)
        plan=json.loads(row["approval_json"])
        return {
            "source_pcm_sha256":plan["source_pcm_sha256"],"gain":plan["gain"],
            "format":"nvp.wo4.streamed_pcm24_candidate.v1",
            "status":"STREAMED_PCM24_CANDIDATE_PUBLISHED",
            "destination":row["wav_path"],
            "wav_file_sha256":row["wav_sha256"],
            "wav_file_bytes":row["wav_bytes"],
            "master_pcm_sha256":row["master_pcm_sha256"],
            "original_take_sha256":reel["take_sha256"],
            "frame_count":reel["frame_count"],
            "channel_order":json.loads(row["channel_order"]),
            "sample_rate":48000,"sample_width_bytes":3,
            "source_modified":False,"production_audio_accepted":False
        }

    def attach_delivery(self,index:FilmIndex,job_id,*,sound_candidate,
                        output_root,title,approve,partitioned_receipt=None,
                        partitioned_reel_index=None,cancelled=lambda:False):
        if not isinstance(index,FilmIndex) or not callable(approve):
            raise PermissionError("Trusted native project and creator approval required")
        sound_candidate=deepcopy(sound_candidate)
        reel=self.reel(job_id)
        status=self.status(job_id)
        frame_ticks=TICKS_PER_SECOND//24
        if partitioned_receipt is not None:
            if sound_candidate is not None:
                raise PermissionError("Choose one trusted audio input")
            partitioned_receipt=deepcopy(partitioned_receipt)
            sound_candidate=verify_finite_selection(index,self,status["project_id"],job_id,
                partitioned_receipt,partitioned_reel_index,frame_ticks=frame_ticks,
                select=finite_reel_candidate,cancelled=cancelled)
        elif (type(sound_candidate) is not dict or partitioned_reel_index is not None or
              "partitioned_manifest_sha256" in sound_candidate):
            raise PermissionError("Partitioned audio requires native set verification")
        if (status["task_kind"]!=PICTURE_TASK or
                status["state"]!="OUTPUT_READY" or
                _linked_entry(self.spool(job_id))):
            raise PermissionError("Only a completed approved picture MXF can be packaged")
        if not 3<=reel["frame_count"]<=7200:
            raise PermissionError("Exact bounded sound/picture duration required")
        with self._read() as db:
            if db.execute("SELECT 1 FROM production_cinema_delivery WHERE job_id=?",
                          (job_id,)).fetchone():
                raise FileExistsError("Cinema delivery already approved for this job")
        decision=index.read_revision(status["project_id"],reel["decision_id"],reel["decision_revision"])
        if (decision["document_sha256"]!=reel["decision_sha256"] or
                decision["kind"]!="presentation" or
                decision["data"].get("format")!=DECISION_FORMAT or
                decision["data"].get("source_take_sha256")!=reel["take_sha256"]):
            raise PermissionError("Original mastering decision changed")
        data=decision["data"]
        if (sound_candidate.get("master_pcm_sha256")!=data["sound_sha256"] or
                sound_candidate.get("channel_order")!=data["channel_order"] or
                sound_candidate.get("source_pcm_sha256")!=data["source_pcm_sha256"] or
                sound_candidate.get("gain")!=data["gain"] or
                sound_candidate.get("frame_count")!=reel["frame_count"]):
            raise PermissionError("PCM24 not bound to approved mastering decision")
        wav=_read_guarded_sound(
            sound_candidate,reel["frame_count"],reel["take_sha256"])
        pic=self.spool(job_id)/"picture.mxf"
        if _hash_stream(pic)!=(reel["track_sha256"],reel["track_bytes"]):
            raise PermissionError("Original picture checkpoint changed")
        root,root_identity=_export_root(output_root)
        project_db=Path(index.studio.db_path)
        db_identity=_protected_path(project_db)
        if (type(title) is not str or not 1<=len(title)<=80 or
                any(ord(c)<32 or c in "<>&" for c in title)):
            raise ValueError("Bounded plain-text cinema title required")
        ids={k:str(uuid4()) for k in ("sound","cpl","pkl","assetmap","reel")}
        scope={
            "operation":"nvp.supervisor.approve_file_backed_dcp.v1",
            "job_id":job_id,"project_id":status["project_id"],
            "manifest_sha256":status["manifest_sha256"],
            "source_take_sha256":reel["take_sha256"],
            "mastering_decision_sha256":reel["decision_sha256"],
            "picture_mxf_sha256":reel["track_sha256"],
            "wav_sha256":sound_candidate["wav_file_sha256"],
            "master_pcm_sha256":sound_candidate["master_pcm_sha256"],
            "frame_count":reel["frame_count"],
            "output_root":str(root),
            "title":title,"cpl_uuid":ids["cpl"],
            "project_db":str(project_db.resolve(strict=True)),
            "project_db_identity":list(db_identity),"export_root_identity":list(root_identity),
            "wav_path":str(wav),"wav_bytes":sound_candidate["wav_file_bytes"],
            "source_pcm_sha256":sound_candidate["source_pcm_sha256"],"gain":sound_candidate["gain"],
            "channel_order":sound_candidate["channel_order"],
            **{k+"_uuid":v for k,v in ids.items()},
            "plaintext_export_explicitly_requested":True,"preserve_on_crash":True
        }
        if partitioned_receipt is not None:
            scope["partitioned_audio"]=partitioned_provenance(sound_candidate,data,reel["frame_count"],frame_ticks)
        if approve(deepcopy(scope)) is not True:
            return {"format":FORMAT,"status":"DENIED","source_modified":False}
        if partitioned_receipt is not None:
            again=verify_finite_selection(index,self,status["project_id"],job_id,
                partitioned_receipt,partitioned_reel_index,frame_ticks=frame_ticks,
                select=finite_reel_candidate,cancelled=cancelled)
            if again!=sound_candidate:
                raise PermissionError("Partitioned audio changed during approval")
        _assert_export_root(root,root_identity)
        if (_protected_path(project_db)!=db_identity or
                _read_guarded_sound(sound_candidate,reel["frame_count"],
                                reel["take_sha256"])!=wav or
                _hash_stream(pic)!=(reel["track_sha256"],reel["track_bytes"]) or
                index.read_revision(status["project_id"],reel["decision_id"],reel["decision_revision"])[
                    "document_sha256"]!=reel["decision_sha256"]):
            raise PermissionError("Approved cinema source changed during consent")
        with self._tx() as db:
            current=db.execute("""SELECT state,manifest_sha256,cancel_requested
                FROM production_jobs WHERE job_id=?""",(job_id,)).fetchone()
            if (current is None or current["state"]!="OUTPUT_READY" or
                    current["cancel_requested"] or
                    current["manifest_sha256"]!=scope["manifest_sha256"]):
                raise PermissionError("Cinema job changed during approval")
            db.execute("""INSERT INTO production_cinema_delivery(
                job_id,project_db,output_root,title,wav_path,wav_sha256,
                wav_bytes,master_pcm_sha256,channel_order,sound_uuid,cpl_uuid,
                pkl_uuid,assetmap_uuid,reel_uuid,phase,updated_at,approval_json,approval_sha256)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job_id,str(project_db.resolve(strict=True)),str(root),title,
                 str(wav),sound_candidate["wav_file_sha256"],
                 sound_candidate["wav_file_bytes"],
                 sound_candidate["master_pcm_sha256"],
                 json.dumps(sound_candidate["channel_order"]),ids["sound"],
                 ids["cpl"],ids["pkl"],ids["assetmap"],ids["reel"],
                 "SOUND_PENDING",_now(),_canonical(scope).decode("ascii"),_digest(_canonical(scope))))
            self._event(db,job_id,"DCP_DELIVERY_APPROVED",
                        ids["cpl"]+" / frame and WAV SHA-bound")
        return {"format":FORMAT,"status":"SOUND_PENDING","job_id":job_id,
                "cpl_uuid":ids["cpl"],"production_dcp_accepted":False}

    def claim_next(self,owner_token,pid,**kwargs):
        _require_owner(self.root)
        with self._read() as db:
            if db.execute("SELECT 1 FROM production_jobs WHERE state='DELIVERY_RUNNING'").fetchone():
                raise PermissionError("Unresolved native delivery lease")
        return super().claim_next(owner_token,pid,**kwargs)

    def finalize_cancel(self,job_id):
        _require_owner(self.root)
        try:
            d=self.delivery(job_id)
        except KeyError:
            return super().finalize_cancel(job_id)
        inspect_original_process_journals()
        with self._tx() as db:
            j=db.execute("SELECT state,cancel_requested FROM production_jobs WHERE job_id=?",(job_id,)).fetchone()
            if (j is None or not j["cancel_requested"] or
                d["phase"] not in ("SOUND_PENDING","SOUND_RUNNING","SOUND_READY","PACKAGE_RUNNING","REVIEW_REQUIRED")):
                raise PermissionError("No authorized uncommitted delivery cancellation")
            db.execute("UPDATE production_cinema_delivery SET phase='CANCELLED',updated_at=? WHERE job_id=?",(_now(),job_id))
            db.execute("UPDATE production_jobs SET state='CANCELLED',owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?",(_now(),job_id))
            self._event(db,job_id,"DELIVERY_CANCELLED","Preserved staged artifacts")
        return {"status":"CANCELLED","job_id":job_id}

    def next_delivery(self,owner,pid):
        """Claim next sound/package stage only after previous durable checkpoint."""
        _require_owner(self.root)
        if type(owner) is not str or not ID_RE.fullmatch(owner) or pid!=os.getpid():
            raise PermissionError("Live native delivery owner required")
        with self._tx() as db:
            row=db.execute("""SELECT d.*,r.frame_count,r.profile,r.take_sha256,
                r.picture_uuid,r.track_sha256,r.track_bytes,j.state,j.owner_token
                FROM production_cinema_delivery d
                JOIN production_cinema_reels r ON r.job_id=d.job_id
                JOIN production_jobs j ON j.job_id=d.job_id
                WHERE d.phase IN ('SOUND_PENDING','SOUND_READY')
                AND j.cancel_requested=0
                AND j.state IN ('OUTPUT_READY','DELIVERY_RUNNING')
                AND NOT EXISTS (SELECT 1 FROM production_segments WHERE state='RUNNING')
                AND NOT EXISTS (SELECT 1 FROM production_cinema_reels r JOIN production_jobs j ON r.job_id=j.job_id WHERE r.reel_state='TRACK_RUNNING' AND j.state!='CANCELLED')
                AND NOT EXISTS (SELECT 1 FROM production_jobs WHERE state='DELIVERY_RUNNING')
                ORDER BY j.created_at LIMIT 1""").fetchone()
            if row is None or row["owner_token"] not in (None,owner):
                return None
            self._verified_manifest(db,row["job_id"])
            self.delivery(row["job_id"])
            next_phase=("SOUND_RUNNING" if row["phase"]=="SOUND_PENDING"
                        else "PACKAGE_RUNNING")
            db.execute("""UPDATE production_cinema_delivery
                SET phase=?,updated_at=? WHERE job_id=?""",
                (next_phase,_now(),row["job_id"]))
            db.execute("""UPDATE production_jobs SET state='DELIVERY_RUNNING',
                owner_token=?,owner_pid=?,updated_at=? WHERE job_id=?""",
                (owner,pid,_now(),row["job_id"]))
            self._event(db,row["job_id"],"DELIVERY_STAGE_CLAIMED",next_phase)
            return {**dict(row),"stage":next_phase}

    def delivery_heartbeat(self,owner,job_id):
        _require_owner(self.root)
        with self._tx() as db:
            row=db.execute("""SELECT j.owner_token,j.cancel_requested,
                d.phase FROM production_jobs j JOIN production_cinema_delivery d
                ON j.job_id=d.job_id WHERE j.job_id=?""",(job_id,)).fetchone()
            if (row is None or row["owner_token"]!=owner or
                    row["phase"] not in ("SOUND_RUNNING","PACKAGE_RUNNING")):
                raise PermissionError("Native sound/package lease lost")
            db.execute("UPDATE production_jobs SET updated_at=? WHERE job_id=?",
                       (_now(),job_id))
            return bool(row["cancel_requested"])

    def commit_sound(self,owner,job_id,receipt):
        _require_owner(self.root)
        delivery=self.delivery(job_id)
        reel=self.reel(job_id)
        output=self.spool(job_id)/"sound.mxf"
        if (receipt.get("status")!="SOUND_MXF_STAGE_VERIFIED" or
                receipt.get("asset_uuid")!=delivery["sound_uuid"] or
                receipt.get("original_take_sha256")!=reel["take_sha256"] or
                receipt.get("frame_count")!=reel["frame_count"] or
                receipt.get("master_pcm_sha256")!=delivery["master_pcm_sha256"] or
                receipt.get("source_master_wav_sha256")!=delivery["wav_sha256"] or
                receipt.get("wrapper_sha256")!=reel["wrapper_sha256"] or
                receipt.get("info_sha256")!=reel["info_sha256"] or
                not _protected_receipt(receipt.get("native_wrap_receipt")) or
                not _protected_receipt(receipt.get("native_info_receipt")) or
                receipt["native_wrap_receipt"].get("native_codec_sha256")!=reel["wrapper_sha256"] or
                receipt["native_info_receipt"].get("native_codec_sha256")!=reel["info_sha256"] or
                _hash_stream(output)!=(receipt.get("file_sha256"),receipt.get("file_bytes"))):
            raise PermissionError("Uncommitted sound MXF cannot be trusted")
        _read_guarded_sound(self.approved_sound_candidate(job_id),reel["frame_count"],reel["take_sha256"])
        with self._tx() as db:
            row=db.execute("""SELECT d.phase,j.owner_token,j.cancel_requested
                FROM production_cinema_delivery d JOIN production_jobs j
                ON j.job_id=d.job_id WHERE d.job_id=?""",(job_id,)).fetchone()
            if (row is None or row["phase"]!="SOUND_RUNNING" or
                    row["owner_token"]!=owner or row["cancel_requested"]):
                raise PermissionError("Native sound MXF lost its owner/authorization")
            db.execute("""UPDATE production_cinema_delivery
                SET phase='SOUND_READY',sound_sha256=?,sound_bytes=?,sound_receipt_sha256=?,sound_receipt_json=?,
                updated_at=? WHERE job_id=?""",
                (receipt["file_sha256"],receipt["file_bytes"],_digest(_canonical(receipt)),_canonical(receipt).decode("ascii"),_now(),job_id))
            db.execute("""UPDATE production_jobs SET state='OUTPUT_READY',
                owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            self._event(db,job_id,"SOUND_MXF_CHECKPOINT",receipt["file_sha256"])
        return {"status":"FILE_BACKED_SOUND_MXF_READY","job_id":job_id,
                "sha256":receipt["file_sha256"],
                "production_dcp_accepted":False}

    def delivery_review(self,owner,job_id,reason):
        _require_owner(self.root)
        if type(reason) is not str or not 1<=len(reason)<=80:
            raise ValueError("Bounded native delivery failure reason")
        with self._tx() as db:
            row=db.execute("""SELECT j.owner_token,d.phase
                FROM production_jobs j JOIN production_cinema_delivery d
                ON j.job_id=d.job_id WHERE j.job_id=?""",(job_id,)).fetchone()
            if (row is None or row["owner_token"]!=owner or
                    row["phase"] not in ("SOUND_RUNNING","PACKAGE_RUNNING")):
                raise PermissionError("Only active owner may mark delivery review")
            db.execute("""UPDATE production_cinema_delivery
                SET phase='REVIEW_REQUIRED',updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            db.execute("""UPDATE production_jobs SET state='REVIEW_REQUIRED',
                owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            self._event(db,job_id,"DCP_STAGE_REVIEW_REQUIRED",reason)

    def commit_package(self,owner,job_id,receipt):
        _require_owner(self.root)
        d=self.delivery(job_id)
        self._verify_all_production_sources(job_id)
        reel=self.reel(job_id)
        self._export_root_checked(d)
        folder=Path(d["output_root"])/("DCP_"+d["cpl_uuid"])
        if (receipt.get("status")!="STRUCTURAL_FILE_DCP_PUBLISHED" or
                receipt.get("destination")!=str(folder) or
                receipt.get("cpl_uuid")!="urn:uuid:"+d["cpl_uuid"] or
                receipt.get("mastering_decision_sha256")!=reel["decision_sha256"] or
                receipt.get("source_take_sha256")!=reel["take_sha256"] or
                receipt.get("file_sha256") is None or
                _linked_entry(folder) or not folder.is_dir()):
            raise PermissionError("No trusted atomically published DCP receipt")
        audit=inspect_dcp_structure(folder)
        if (audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
                audit["cpl_uuid"]!=d["cpl_uuid"] or
                audit["reel_durations"]!=[self.reel(job_id)["frame_count"]]):
            raise PermissionError("Published package failed independent hash audit")
        self._verify_package_identity(job_id,folder,audit)
        paths={x.name for x in folder.iterdir()}
        if paths!=set(receipt["file_sha256"]):
            raise PermissionError("Unexpected or missing published SMPTE assets")
        for name,sha in receipt["file_sha256"].items():
            if sha!=digest_file(folder/name):
                raise PermissionError("Published DCP asset bytes differ")
        with self._tx() as db:
            row=db.execute("""SELECT d.phase,j.owner_token,j.cancel_requested
                FROM production_jobs j JOIN production_cinema_delivery d
                ON j.job_id=d.job_id WHERE j.job_id=?""",(job_id,)).fetchone()
            if (row is None or row["phase"]!="PACKAGE_RUNNING" or
                    row["owner_token"]!=owner or row["cancel_requested"]):
                raise PermissionError("DCP owner changed before journal commit")
            db.execute("""UPDATE production_cinema_delivery SET
                phase='PUBLISHED_PENDING_INDEX',dcp_files_json=?,updated_at=?
                WHERE job_id=?""",
                (json.dumps(receipt["file_sha256"],sort_keys=True),_now(),job_id))
            db.execute("""UPDATE production_jobs SET state='DCP_PUBLISHED',
                owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            self._event(db,job_id,"DCP_PUBLISHED_AWAITING_FILMINDEX",
                        d["cpl_uuid"])
        return {"status":"PUBLISHED_PENDING_INDEX","job_id":job_id,
                "destination":str(folder),"production_dcp_accepted":False}

    def _export_root_checked(self,d):
        plan=json.loads(d["approval_json"])
        root=Path(d["output_root"])
        _assert_export_root(root,tuple(plan["export_root_identity"]))
        return root

    def _verify_package_identity(self,job_id,folder,audit):
        d=self.delivery(job_id)
        reel=self.reel(job_id)
        self._export_root_checked(d)
        if (audit["pkl_uuid"]!=d["pkl_uuid"] or audit["reel_count"]!=1 or
            audit["reel_durations"]!=[reel["frame_count"]] or
            {(x["kind"],x["asset_id"]) for x in audit["tracks"]}!={
                ("picture",reel["picture_uuid"]),("sound",d["sound_uuid"])} or
            _stream_digest(folder/"picture.mxf")["sha256"]!=reel["track_sha256"] or
            _stream_digest(folder/"sound.mxf")["sha256"]!=d["sound_sha256"]):
            raise PermissionError("DCP differs from committed source track identities")
        from backend.nvp_wo3_dcp_structure import _xml,_value,NS_CPL,NS_AM
        cpl=_xml(folder,"CPL.xml",NS_CPL,"CompositionPlaylist")
        reels=cpl.find("{"+NS_CPL+"}ReelList")
        nodes=[] if reels is None else reels.findall("{"+NS_CPL+"}Reel")
        if (_value(cpl,"ContentTitleText",NS_CPL)!=d["title"] or len(nodes)!=1 or
                _value(nodes[0],"Id",NS_CPL)!="urn:uuid:"+d["reel_uuid"]):
            raise PermissionError("Package reel UUID differs")
        assets=nodes[0].find("{"+NS_CPL+"}AssetList")
        for tag in ("MainPicture","MainSound"):
            entry=None if assets is None else assets.find("{"+NS_CPL+"}"+tag)
            if (entry is None or _value(entry,"EntryPoint",NS_CPL)!="0" or
                _value(entry,"IntrinsicDuration",NS_CPL)!=str(reel["frame_count"]) or
                _value(entry,"Duration",NS_CPL)!=str(reel["frame_count"])):
                raise PermissionError("Package track range differs")
        amap=_xml(folder,"ASSETMAP.xml",NS_AM,"AssetMap")
        if _value(amap,"Id",NS_AM)!="urn:uuid:"+d["assetmap_uuid"]:
            raise PermissionError("Package AssetMap UUID differs")

    def _check_published(self,job_id):
        d=self.delivery(job_id)
        self._export_root_checked(d)
        if d["phase"] not in ("PUBLISHED_PENDING_INDEX","INDEXED"):
            raise PermissionError("No committed published package awaiting FilmIndex")
        folder=Path(d["output_root"])/("DCP_"+d["cpl_uuid"])
        if _linked_entry(folder) or not folder.is_dir():
            raise PermissionError("Published DCP missing or linked")
        expected=json.loads(d["dcp_files_json"])
        if type(expected) is not dict or not expected:
            raise PermissionError("Durable file hash receipt missing")
        if {x.name for x in folder.iterdir()}!=set(expected):
            raise PermissionError("DCP package file list changed")
        for name,sha in expected.items():
            if Path(name).name!=name or not SHA.fullmatch(sha):
                raise PermissionError("Invalid trusted DCP package file hash")
            if digest_file(folder/name)!=sha:
                raise PermissionError("Published DCP file changed since commit")
        audit=inspect_dcp_structure(folder)
        if audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or audit["cpl_uuid"]!=d["cpl_uuid"]:
            raise PermissionError("Independent published DCP recheck failed")
        self._verify_package_identity(job_id,folder,audit)
        return folder,expected

    def _verify_all_production_sources(self,job_id):
        """Reopen original media and all intermediate checkpoint receipts."""
        reel=self.reel(job_id)
        delivery=self.delivery(job_id)
        root=self.spool(job_id)
        if _linked_entry(root):
            raise PermissionError("Approved production spool redirected")
        _read_guarded_sound(
            self.approved_sound_candidate(job_id),
            reel["frame_count"],reel["take_sha256"])
        with self._read() as db:
            frames=[dict(row) for row in db.execute("""SELECT
                s.position,s.source_path,s.expected_sha256,s.expected_bytes,
                s.state,f.file_sha256,f.file_bytes,f.receipt_sha256,f.receipt_json
                FROM production_segments s
                LEFT JOIN production_cinema_frames f
                ON f.job_id=s.job_id AND f.position=s.position
                WHERE s.job_id=? ORDER BY s.position""",(job_id,))]
        if len(frames)!=reel["frame_count"]:
            raise PermissionError("Approved image manifest incomplete")
        from backend.nvp_wo4_picture_spool import verify_frame_file
        for index,item in enumerate(frames):
            source=Path(item["source_path"])
            file=root/"frames"/f"{index:06d}.j2c"
            if (item["position"]!=index or item["state"]!="VERIFIED" or
                    not item["receipt_json"] or _digest(item["receipt_json"].encode("ascii"))!=item["receipt_sha256"] or
                    _hash_stream(source)!=(item["expected_sha256"],item["expected_bytes"]) or
                    not isinstance(item["file_sha256"],str) or
                    verify_frame_file(file,item["file_sha256"],reel["profile"])
                    !=item["file_bytes"]):
                raise PermissionError("Source XYZ12/JPEG2000 SHA no longer approved")
        picture=root/"picture.mxf"
        sound=root/"sound.mxf"
        if (not reel["track_receipt_json"] or _digest(reel["track_receipt_json"].encode("ascii"))!=reel["track_receipt_sha256"] or
                _hash_stream(picture)!=(reel["track_sha256"],reel["track_bytes"]) or
                _hash_stream(sound)!=(delivery["sound_sha256"],delivery["sound_bytes"])):
            raise PermissionError("Source-bound picture/sound MXF checkpoint changed")
        return True

    def commit_filmindex(self,job_id,*,index):
        """Restart-safe post-publish FilmIndex commit, no repeat output write."""
        _require_owner(self.root)
        if not isinstance(index,FilmIndex):
            raise PermissionError("Trusted host project resolver required")
        d=self.delivery(job_id)
        reel=self.reel(job_id)
        folder,files=self._check_published(job_id)
        self._verify_all_production_sources(job_id)
        status=self.status(job_id)
        if status["cancel_requested"] or status["state"] not in ("DCP_PUBLISHED","DCP_INDEXED"):
            raise PermissionError("Unexpected delivery state before FilmIndex")
        project_db=Path(index.studio.db_path)
        approved=json.loads(d["approval_json"])
        if (str(project_db.resolve(strict=True))!=d["project_db"] or
                _protected_path(project_db)!=tuple(approved["project_db_identity"])):
            raise PermissionError("Native resolved FilmIndex identity differs")
        pid=status["project_id"]
        take=index.read_revision(pid,reel["take_id"],reel["take_revision"])
        decision=index.read_revision(pid,reel["decision_id"],reel["decision_revision"])
        if (take["kind"]!="take" or
                take["document_sha256"]!=reel["take_sha256"] or
                take["data"].get("frozen") is not True or
                decision["document_sha256"]!=reel["decision_sha256"]):
            raise PermissionError("Immutable Take/decision changed before indexing")
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        verified=OpenUSDTakeCapture(
            index,verify_creator_action=lambda *_:False
        ).verify_take(pid,reel["take_id"])
        if (verified["status"]!="VERIFIED_FROZEN_DATA_TAKE" or
                verified["take_document_sha256"]!=reel["take_sha256"]):
            raise PermissionError("Original USD/temporal data changed")
        record_id="WO3DCP_"+d["cpl_uuid"].replace("-","")
        data={
            "format":PACKAGE_FORMAT,"title":d["title"],
            "original_take_sha256":reel["take_sha256"],
            "destination_name":folder.name,
            "file_sha256":files,
            "assetmap_uuid":"urn:uuid:"+d["assetmap_uuid"],
            "pkl_uuid":"urn:uuid:"+d["pkl_uuid"],
            "cpl_uuid":"urn:uuid:"+d["cpl_uuid"],
            "frame_count":reel["frame_count"],
            "source_job_id":job_id,
            "mastering_decision_sha256":reel["decision_sha256"],
            "delivery_approval_sha256":d["approval_sha256"],"sound_receipt_sha256":d["sound_receipt_sha256"],
            "picture_receipt_sha256":reel["track_receipt_sha256"],
            "structural_integrity_verified":True,
            "independent_essence_decode_verified":False,
            "production_dcp_accepted":False,
            "original_data_modified":False,"ffmpeg_used":False
        }
        dependencies=[
            {"object_id":reel["take_id"],"revision":reel["take_revision"],"role":"source_take"},
            {"object_id":reel["decision_id"],"revision":reel["decision_revision"],"role":"presentation"}]
        def guard(db):
            for edge,expected in zip(dependencies,(reel["take_sha256"],reel["decision_sha256"])):
                row=index._read_revision(db,pid,edge["object_id"],edge["revision"])
                if row is None or row["document_sha"]!=expected:
                    raise PermissionError("Original source changed inside FilmIndex commit")
        existing=index.history(pid,record_id)
        if existing:
            if len(existing)!=1 or existing[0]["revision"]!=1:
                raise PermissionError("Published presentation identity reused")
            old=index.read_revision(pid,record_id,1)
            if old["kind"]!="presentation" or old["data"]!=data or sorted(old["dependencies"],key=lambda d:d["object_id"])!=sorted(dependencies,key=lambda d:d["object_id"]):
                raise PermissionError("Existing FilmIndex DCP receipt differs")
            receipt_sha=old["document_sha256"]
        else:
            published=index.register_revision(
                pid,record_id,"presentation",data,
                expected_revision=0,dependencies=dependencies,precommit_guard=guard)
            receipt_sha=published["document_sha256"]
        # A crash after FilmIndex commit but before this SQLite row is safe:
        # on restart, exact-record comparison above recognizes that commit.
        with self._tx() as db:
            row=db.execute("""SELECT phase,filmindex_sha256,approval_sha256 FROM
                production_cinema_delivery WHERE job_id=?""",(job_id,)).fetchone()
            if row is None or row["phase"] not in ("PUBLISHED_PENDING_INDEX","INDEXED"):
                raise PermissionError("Delivery changed while indexing")
            if row["approval_sha256"]!=d["approval_sha256"] or row["filmindex_sha256"] not in (None,receipt_sha):
                raise PermissionError("Different FilmIndex revision was already committed")
            db.execute("""UPDATE production_cinema_delivery SET phase='INDEXED',
                filmindex_sha256=?,updated_at=? WHERE job_id=?""",
                (receipt_sha,_now(),job_id))
            db.execute("""UPDATE production_jobs SET state='DCP_INDEXED',
                owner_token=NULL,owner_pid=NULL,updated_at=?
                WHERE job_id=?""",(_now(),job_id))
            self._event(db,job_id,"DCP_FILMINDEX_COMMITTED",receipt_sha)
        return {"format":FORMAT,"status":"STRUCTURAL_DCP_FILMINDEX_RECORDED",
                "job_id":job_id,"destination":str(folder),
                "output_receipt_sha256":receipt_sha,
                "production_dcp_accepted":False,
                "independent_dci_validator_passed":False}

    def request_delivery_cancel(self,job_id,authorize):
        """Host-authorized cancellation before sound/DCP publication."""
        if not callable(authorize):
            raise PermissionError("Trusted native cancellation confirmation required")
        d=self.delivery(job_id)
        if d["phase"] not in ("SOUND_PENDING","SOUND_RUNNING",
                              "SOUND_READY","PACKAGE_RUNNING"):
            raise PermissionError("Published or indexed package cannot be cancelled")
        status=self.status(job_id)
        scope={"operation":"nvp.supervisor.cancel_file_dcp_delivery.v1",
               "job_id":job_id,"manifest_sha256":status["manifest_sha256"],
               "cpl_uuid":d["cpl_uuid"],"delivery_phase":d["phase"],
               "delivery_approval_sha256":d["approval_sha256"]}
        if authorize(deepcopy(scope)) is not True:
            return {"status":"DENIED","job_id":job_id}
        with self._tx() as db:
            current=db.execute("""SELECT d.phase,j.manifest_sha256,d.approval_sha256,
                j.cancel_requested FROM production_cinema_delivery d
                JOIN production_jobs j ON j.job_id=d.job_id
                WHERE d.job_id=?""",(job_id,)).fetchone()
            if (current is None or current["phase"]!=scope["delivery_phase"]
                    or current["manifest_sha256"]!=scope["manifest_sha256"]
                    or current["approval_sha256"]!=scope["delivery_approval_sha256"]
                    or current["cancel_requested"]):
                raise PermissionError("Delivery changed while confirming cancellation")
            db.execute("UPDATE production_jobs SET cancel_requested=1,updated_at=? WHERE job_id=?",
                       (_now(),job_id))
            self._event(db,job_id,"DCP_CANCEL_REQUESTED","Creator-authorized")
        return {"status":"CANCEL_REQUESTED","job_id":job_id}

    def next_pending_index(self):
        _require_owner(self.root)
        with self._read() as db:
            row=db.execute("""SELECT d.job_id FROM production_cinema_delivery d
                    JOIN production_jobs j ON j.job_id=d.job_id
                    WHERE d.phase='PUBLISHED_PENDING_INDEX'
                      AND j.state='DCP_PUBLISHED' AND j.cancel_requested=0
                    ORDER BY j.created_at LIMIT 1""").fetchone()
            return row["job_id"] if row is not None else None

    def delivery_reconcile(self):
        """Retain interrupted stages; auto-resume only explicit durable index gap."""
        _require_owner(self.root)
        inspect_original_process_journals()
        records=[]
        with self._read() as db:
            jobs=[dict(x) for x in db.execute(
                """SELECT d.job_id,d.phase,d.wav_path,d.wav_sha256,
                          d.sound_sha256,d.sound_bytes,d.output_root,d.cpl_uuid
                   FROM production_cinema_delivery d""")]
        for job in jobs:
            uid=job["job_id"]
            phase=job["phase"]
            self.delivery(uid)
            if self.status(uid)["state"]=="CANCELLED":
                if phase not in ("PUBLISHED_PENDING_INDEX","INDEXED","CANCELLED"):
                    with self._tx() as db:
                        db.execute("UPDATE production_cinema_delivery SET phase='CANCELLED',updated_at=? WHERE job_id=?",(_now(),uid))
                records.append({"job_id":uid,"phase":"CANCELLED"})
                continue
            if phase=="INDEXED":
                try:
                    self._check_published(uid)
                    self._verify_all_production_sources(uid)
                except (OSError,ValueError,PermissionError,RuntimeError):
                    self._mark_delivery_restart_review(uid,"IndexedFilesTampered")
                    phase="REVIEW_REQUIRED"
            elif phase=="PUBLISHED_PENDING_INDEX":
                # Revalidate exact published package during next run_one; no
                # automatic source rewrite or directory promotion.
                try:
                    self._check_published(uid)
                    self._verify_all_production_sources(uid)
                except (OSError,ValueError,PermissionError,RuntimeError):
                    self._mark_delivery_restart_review(uid,"PublishedFilesTampered")
                    phase="REVIEW_REQUIRED"
            elif self.status(uid)["cancel_requested"]:
                self.finalize_cancel(uid)
                phase="CANCELLED"
            elif phase in ("SOUND_RUNNING","PACKAGE_RUNNING"):
                self._mark_delivery_restart_review(uid,"InterruptedNativeStage")
                phase="REVIEW_REQUIRED"
            elif phase in ("SOUND_PENDING","SOUND_READY"):
                try:
                    wav=Path(job["wav_path"])
                    if (_linked_entry(wav) or not wav.is_file() or
                            digest_file(wav)!=job["wav_sha256"]):
                        raise PermissionError("Approved WAV changed")
                    self._export_root_checked(self.delivery(uid))
                    if phase=="SOUND_PENDING" and (self.spool(uid)/"sound-stage").exists():
                        raise PermissionError("Uncommitted sound stage requires review")
                    if phase=="SOUND_READY":
                        export=self._export_root_checked(self.delivery(uid))
                        for candidate in (export/(".nvp-wo4-dcp-stage-"+uid),export/("DCP_"+job["cpl_uuid"])):
                            if candidate.exists() or _linked_entry(candidate):
                                raise PermissionError("Uncommitted export requires explicit review")
                        sound=self.spool(uid)/"sound.mxf"
                        if (_linked_entry(sound) or not sound.is_file() or
                                digest_file(sound)!=job["sound_sha256"] or
                                sound.stat().st_size!=job["sound_bytes"]):
                            raise PermissionError("Committed sound MXF changed")
                except (OSError,PermissionError,ValueError):
                    self._mark_delivery_restart_review(uid,"SourceSoundTampered")
                    phase="REVIEW_REQUIRED"
            records.append({"job_id":uid,"phase":phase})
        return {"format":FORMAT,"jobs":records,
                "uncommitted_outputs_deleted":False,
                "production_dcp_accepted":False}

    def approve_orphan_dcp_adoption(self,job_id,authorize):
        """Explicitly adopt a fully verified DCP stranded after OS promotion.

        This never moves, deletes, or rewrites the published folder. The
        original approved picture/sound MXF bytes, UUIDs, durations, Film Time,
        and all source custody must match before authorizing the operation.
        Staged/partial folders are *not* eligible for adoption.
        """
        _require_owner(self.root)
        inspect_original_process_journals()
        if not callable(authorize):
            raise PermissionError("Trusted native creator recovery approval required")
        d=self.delivery(job_id)
        reel=self.reel(job_id)
        state=self.status(job_id)
        if (state["state"]!="REVIEW_REQUIRED" or
                d["phase"]!="REVIEW_REQUIRED" or
                d["dcp_files_json"] is not None or
                d["filmindex_sha256"] is not None or
                d["sound_sha256"] is None or
                state["cancel_requested"]):
            raise PermissionError("Only uncommitted published DCP may be reviewed")
        output=self._export_root_checked(d)
        folder=output/("DCP_"+d["cpl_uuid"])
        stage=output/(".nvp-wo4-dcp-stage-"+job_id)
        if (_linked_entry(output) or not output.is_dir() or
                _linked_entry(folder) or not folder.is_dir() or
                stage.exists() or _linked_entry(stage)):
            raise PermissionError("Only a complete unmixed published DCP is eligible")
        # Inspect all original/derived media and reject any altered source.
        self._verify_all_production_sources(job_id)
        audit=inspect_dcp_structure(folder)
        expected_files={"picture.mxf","sound.mxf","CPL.xml","PKL.xml",
                        "ASSETMAP.xml","VOLINDEX.xml"}
        if ({p.name for p in folder.iterdir()}!=expected_files or
                audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
                audit["reel_count"]!=1 or
                audit["reel_durations"]!=[reel["frame_count"]] or
                audit["cpl_uuid"]!=d["cpl_uuid"] or
                audit["pkl_uuid"]!=d["pkl_uuid"] or
                {(x["kind"],x["asset_id"]) for x in audit["tracks"]}!={
                    ("picture",reel["picture_uuid"]),
                    ("sound",d["sound_uuid"])} or
                digest_file(folder/"picture.mxf")!=reel["track_sha256"] or
                digest_file(folder/"sound.mxf")!=d["sound_sha256"]):
            raise PermissionError("Orphan DCP does not match approved native MXF receipts")
        from backend.nvp_wo3_dcp_structure import (
            _xml, _value, NS_CPL, NS_AM)
        cpl=_xml(folder,"CPL.xml",NS_CPL,"CompositionPlaylist")
        reels=cpl.find("{"+NS_CPL+"}ReelList")
        nodes=[] if reels is None else reels.findall("{"+NS_CPL+"}Reel")
        if (len(nodes)!=1 or
                _value(nodes[0],"Id",NS_CPL)!="urn:uuid:"+d["reel_uuid"]):
            raise PermissionError("Orphan DCP reel UUID changed")
        amap=_xml(folder,"ASSETMAP.xml",NS_AM,"AssetMap")
        if _value(amap,"Id",NS_AM)!="urn:uuid:"+d["assetmap_uuid"]:
            raise PermissionError("Orphan DCP asset-map UUID changed")
        self._verify_package_identity(job_id,folder,audit)
        file_hashes={name:digest_file(folder/name) for name in sorted(expected_files)}
        scope={"operation":"nvp.supervisor.adopt_verified_orphan_dcp.v1",
               "job_id":job_id,"manifest_sha256":state["manifest_sha256"],
               "approved_take_sha256":reel["take_sha256"],
               "cpl_uuid":d["cpl_uuid"],
               "file_sha256":file_hashes,"preserve_published_directory":True}
        if authorize(deepcopy(scope)) is not True:
            return {"status":"DENIED","job_id":job_id}
        # Consent is not a shortcut around source or output verification.
        self._verify_all_production_sources(job_id)
        if (inspect_dcp_structure(folder)["status"]!="STRUCTURE_AND_SHA_VERIFIED"
                or {p.name for p in folder.iterdir()}!=expected_files or
                any(digest_file(folder/name)!=expected for name,expected
                    in file_hashes.items()) or
                digest_file(folder/"picture.mxf")!=reel["track_sha256"] or
                digest_file(folder/"sound.mxf")!=d["sound_sha256"]):
            raise PermissionError("Approved orphan DCP changed during review")
        with self._tx() as db:
            row=db.execute("""SELECT d.phase,d.dcp_files_json,d.sound_sha256,
                    j.state,j.manifest_sha256,j.cancel_requested
                    FROM production_cinema_delivery d JOIN production_jobs j
                    ON j.job_id=d.job_id WHERE j.job_id=?""",(job_id,)).fetchone()
            if (row is None or row["phase"]!="REVIEW_REQUIRED" or
                    row["dcp_files_json"] is not None or
                    row["sound_sha256"]!=d["sound_sha256"] or
                    row["state"]!="REVIEW_REQUIRED" or row["cancel_requested"] or
                    row["manifest_sha256"]!=scope["manifest_sha256"]):
                raise PermissionError("Delivery review status changed before receipt")
            db.execute("""UPDATE production_cinema_delivery SET
                    phase='PUBLISHED_PENDING_INDEX',dcp_files_json=?,updated_at=?
                    WHERE job_id=?""",
                    (json.dumps(file_hashes,sort_keys=True),_now(),job_id))
            db.execute("""UPDATE production_jobs SET state='DCP_PUBLISHED',
                    owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                    (_now(),job_id))
            self._event(db,job_id,"ORPHAN_DCP_ADOPTED_AFTER_EXACT_REVIEW",
                        d["cpl_uuid"])
        return {"status":"PUBLISHED_PENDING_INDEX","job_id":job_id,
                "destination":str(folder),"file_sha256":file_hashes,
                "filesystem_mutated":False,"production_dcp_accepted":False}

    def _mark_delivery_restart_review(self,job_id,reason):
        _require_owner(self.root)
        with self._tx() as db:
            db.execute("""UPDATE production_cinema_delivery SET
                phase='REVIEW_REQUIRED',updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            db.execute("""UPDATE production_jobs SET state='REVIEW_REQUIRED',
                owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            self._event(db,job_id,"DELIVERY_RESTART_REVIEW_REQUIRED",reason)
