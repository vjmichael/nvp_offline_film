"""WO4 LF01/LF02 trusted-host production supervisor.
Native codec execution requires host-provided project/codec authority, not
persisted executable paths. No detached CLI or generic subprocess launcher.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import time
from backend.nvp_production_journal import (
    ProductionJournal,TASK_KIND,SingletonSupervisor,AnotherSupervisorRunning,
    _require_owner)
from backend.nvp_wo4_pcm_stream import _protected_path,_hash_stream
from backend.nvp_production_cinema import CinemaJournal,TASK_KIND as CINEMA_TASK
from backend.nvp_wo3_native_codecs import common_codec_authority
from backend.nvp_wo4_picture_spool import encode_disk_xyz12,wrap_disk_j2k_picture,verify_frame_file
from backend.nvp_wo4_mxf_stream import _publish_protected
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_w1g_release_gate import inspect_original_process_journals
from backend.nvp_wo4_delivery_journal import CinemaDeliveryJournal
from backend.nvp_wo4_feature_journal import FeatureJournal
from backend.nvp_wo4_supervised_sound import wrap_supervised_sound
from backend.nvp_wo4_file_dcp import publish_file_backed_dcp
from backend.nvp_wo4_multireel import publish_multireel_dcp
import json

BLOCK_BYTES=1024*1024

def verify_approved_file(segment,*,check_cancel=lambda:False):
    file=Path(segment["source_path"])
    identity=_protected_path(file)
    before=file.stat()
    digest=hashlib.sha256()
    size=0
    with file.open("rb") as stream:
        opened=os.fstat(stream.fileno())
        if (opened.st_dev,opened.st_ino)!=identity or opened.st_size!=before.st_size:
            raise PermissionError("Approved source changed at open")
        while block:=stream.read(BLOCK_BYTES):
            if check_cancel():
                raise InterruptedError("Explicit native production cancellation")
            size+=len(block)
            if size>segment["expected_bytes"]:
                raise PermissionError("Approved media grew beyond source manifest")
            digest.update(block)
        after=os.fstat(stream.fileno())
    if (_protected_path(file)!=identity or file.stat().st_mtime_ns!=before.st_mtime_ns or
            after.st_size!=before.st_size or after.st_mtime_ns!=before.st_mtime_ns or
            size!=segment["expected_bytes"] or digest.hexdigest()!=segment["expected_sha256"]):
        raise PermissionError("Approved source SHA or size changed")
    return digest.hexdigest(),size


class ProductionSupervisor:
    def __init__(self,journal,*,resolve_project=None,codec_factory=None):
        if not isinstance(journal,ProductionJournal):
            raise TypeError("Trusted local production journal required")
        self.journal=journal
        self.owner="Supervisor"+os.urandom(16).hex()
        self.pid=os.getpid()
        self.resolve_project=resolve_project
        self.codec_factory=codec_factory
        if isinstance(journal,CinemaJournal) and (not callable(resolve_project)
                or not callable(codec_factory)):
            raise PermissionError("Native cinema requires trusted project and codec resolver")

    def _picture_check(self,job_id,position=None):
        last=[0.]
        def check():
            _require_owner(self.journal.root)
            if time.monotonic()-last[0]>=1.0:
                if position is None:
                    self.journal.heartbeat_track(self.owner,job_id)
                else:
                    self.journal.heartbeat(self.owner,job_id,position)
                last[0]=time.monotonic()
            return self.journal.status(job_id)["cancel_requested"]
        return check

    def _codecs(self,reel,check):
        index=self.resolve_project(reel["project_id"])
        if not isinstance(index,FilmIndex):
            raise PermissionError("Trusted FilmIndex resolver required")
        decision=index.read_revision(reel["project_id"],reel["decision_id"],reel["decision_revision"])
        if (decision["kind"]!="presentation" or
            decision["document_sha256"]!=reel["decision_sha256"] or
            OpenUSDTakeCapture(index,verify_creator_action=lambda *_:False).verify_take(
                reel["project_id"],reel["take_id"])["take_document_sha256"]!=reel["take_sha256"]):
            raise PermissionError("Original Take/mastering decision changed")
        codecs=self.codec_factory(reel["project_id"],check)
        if type(codecs) not in (list,tuple) or len(codecs)!=3:
            raise PermissionError("Trusted native codec roster required")
        authority=common_codec_authority(*codecs)
        if (authority.project_id!=reel["project_id"] or
                authority.pin!=reel["codec_manifest_sha256"] or authority.cancel is not check):
            raise PermissionError("Native codec project, manifest or cancellation authority differs")
        for codec,product,field in zip(codecs,
                ("OpenJPEG-opj_compress","ASDCP-asdcp_wrap","ASDCP-asdcp_info"),
                ("codec","wrapper","info")):
            if (codec.product!=product or codec.sha256!=reel[field+"_sha256"] or
                    str(codec.executable)!=reel[field+"_path"]):
                raise PermissionError("Approved codec roster changed")
        return codecs

    def _native_failure(self,uid,position,exc):
        # Never claim cancellation or safe recovery while a previous OS
        # process tree remains unresolved.
        inspect_original_process_journals()
        if self.journal.status(uid)["cancel_requested"]:
            self.journal.finalize_cancel(uid)
            return {"status":"CANCELLED","job_id":uid}
        if position is None:
            self.journal.track_review(self.owner,uid,type(exc).__name__)
        else:
            self.journal.mark_review(self.owner,uid,position,type(exc).__name__)
        return {"status":"REVIEW_REQUIRED","job_id":uid,"reason":type(exc).__name__,
                "production_dcp_accepted":False}

    def _run_cinema_frame(self,segment):
        uid,pos=segment["job_id"],segment["position"]
        try:
            reel=self.journal.reel(uid)
            check=self._picture_check(uid,pos)
            codec,_,_=self._codecs(reel,check)
            if check(): raise InterruptedError("Cancelled before staging")
            root=self.journal.spool(uid)
            root.mkdir(mode=0o700,exist_ok=True)
            _protected_path(root,directory=True)
            frame_dir=root/"frames"
            work_parent=root/"frame-work"
            for folder in (frame_dir,work_parent):
                folder.mkdir(mode=0o700,exist_ok=True)
                _protected_path(folder,directory=True)
            work=work_parent/f"{pos:06d}"
            work.mkdir(mode=0o700,exist_ok=False)
            _protected_path(work,directory=True)
            receipt=encode_disk_xyz12(codec,profile=reel["profile"],
                source_path=segment["source_path"],source_sha256=segment["expected_sha256"],
                source_take_sha=reel["take_sha256"],private_work=work,check_cancel=check)
            if (_hash_stream(Path(segment["source_path"]))!=(segment["expected_sha256"],
                    segment["expected_bytes"]) or check()):
                raise InterruptedError("Source changed or cancelled before checkpoint")
            out=frame_dir/f"{pos:06d}.j2c"
            _publish_protected(work/"frame.j2c",out,receipt["codestream_sha256"],
                               receipt["codestream_bytes"],check)
            committed=self.journal.finish_frame(self.owner,segment,receipt)
            return {"status":"PICTURE_FRAME_CHECKPOINTED","job_id":uid,"position":pos,
                    "sha256":committed["codestream_sha256"],"production_dcp_accepted":False}
        except (OSError,ValueError,RuntimeError,KeyError) as exc:
            return self._native_failure(uid,pos,exc)

    def _wrap_cinema_track(self,reel):
        uid=reel["job_id"]
        try:
            reel=self.journal.reel(uid)
            check=self._picture_check(uid)
            _,wrap,info=self._codecs(reel,check)
            root=self.journal.spool(uid)
            frames=root/"frames"
            _protected_path(frames,directory=True)
            with self.journal._read() as db:
                rows=[dict(x) for x in db.execute("""SELECT
                    f.position,f.file_sha256,f.file_bytes,s.source_path,s.expected_sha256,s.expected_bytes
                    FROM production_cinema_frames f JOIN production_segments s
                    ON f.job_id=s.job_id AND f.position=s.position
                    WHERE f.job_id=? ORDER BY f.position""",(uid,))]
            if len(rows)!=reel["frame_count"]:
                raise PermissionError("Missing durable picture frame checkpoint")
            for n,row in enumerate(rows):
                if (check() or row["position"]!=n or
                    _hash_stream(Path(row["source_path"]))!=(row["expected_sha256"],row["expected_bytes"]) or
                    verify_frame_file(frames/f"{n:06d}.j2c",row["file_sha256"],
                                      reel["profile"])!=row["file_bytes"]):
                    raise PermissionError("Approved source/checkpoint invalid or cancelled")
            stage=root/"mxf-stage"
            stage.mkdir(mode=0o700,exist_ok=False)
            _protected_path(stage,directory=True)
            receipt=wrap_disk_j2k_picture(wrap,info,frames_dir=frames,stage_dir=stage,
                frame_count=reel["frame_count"],profile=reel["profile"],asset_uuid=reel["picture_uuid"],
                source_take_sha=reel["take_sha256"],
                ordered_codestream_sha256=[row["file_sha256"] for row in rows],check_cancel=check)
            if check():
                raise InterruptedError("Cancelled before MXF checkpoint")
            _publish_protected(stage/"picture.mxf",root/"picture.mxf",
                               receipt["file_sha256"],receipt["file_bytes"],check)
            return self.journal.commit_track(self.owner,uid,receipt)
        except (OSError,ValueError,RuntimeError,KeyError) as exc:
            return self._native_failure(uid,None,exc)

    def _delivery_check(self,uid):
        last=[0.]
        def check():
            _require_owner(self.journal.root)
            if time.monotonic()-last[0]>=1.:
                self.journal.delivery_heartbeat(self.owner,uid)
                last[0]=time.monotonic()
            return self.journal.status(uid)["cancel_requested"]
        return check

    def _run_delivery(self,step):
        uid=step["job_id"]
        check=self._delivery_check(uid)
        try:
            root=self.journal.spool(uid)
            _protected_path(root,directory=True)
            reel=self.journal.reel(uid)
            d=self.journal.delivery(uid)
            plan=json.loads(d["approval_json"])
            self.journal._export_root_checked(d)
            _,wrap,info=self._codecs(reel,check)
            if check():
                raise InterruptedError("Delivery cancelled")
            if step["stage"]=="SOUND_RUNNING":
                work=root/"sound-stage"
                work.mkdir(mode=0o700,exist_ok=False)
                _protected_path(work,directory=True)
                receipt=wrap_supervised_sound(wrap,info,
                    candidate=self.journal.approved_sound_candidate(uid),
                    source_take_sha=reel["take_sha256"],frames=reel["frame_count"],
                    sound_uuid=d["sound_uuid"],stage_dir=work,check_cancel=check)
                if check():
                    raise InterruptedError("Cancelled before sound checkpoint")
                _publish_protected(work/"sound.mxf",root/"sound.mxf",
                                   receipt["file_sha256"],receipt["file_bytes"],check)
                return self.journal.commit_sound(self.owner,uid,receipt)
            if step["stage"]!="PACKAGE_RUNNING":
                raise PermissionError("Unknown native delivery stage")
            self.journal._verify_all_production_sources(uid)
            picture={"kind":"picture","asset_uuid":reel["picture_uuid"],
                "source_take_sha256":reel["take_sha256"],"file_path":str(root/"picture.mxf"),
                "file_sha256":reel["track_sha256"],"file_bytes":reel["track_bytes"],
                "profile":reel["profile"],"frame_count":reel["frame_count"],"edit_rate":[24,1],
                "source_modified":False,"production_dcp_accepted":False}
            sound={"kind":"sound","asset_uuid":d["sound_uuid"],
                "source_take_sha256":reel["take_sha256"],"file_path":str(root/"sound.mxf"),
                "file_sha256":d["sound_sha256"],"file_bytes":d["sound_bytes"],
                "frame_count":reel["frame_count"],"edit_rate":[24,1],
                "source_modified":False,"production_dcp_accepted":False}
            ids={"picture":reel["picture_uuid"],**{k:d[k+"_uuid"] for k in
                                                    ("sound","cpl","pkl","assetmap","reel")}}
            expected={"operation":"nvp.wo4.export_file_candidate.v1","job_id":uid,
                "source_take_sha256":reel["take_sha256"],"mastering_decision_sha256":reel["decision_sha256"],
                "picture":picture,"sound":sound,"ids":ids,"title":d["title"],
                "profile":reel["profile"],"frames":reel["frame_count"],
                "output_root":d["output_root"],"plaintext_export_explicitly_requested":True}
            def authorize(scope):
                live=self.journal.delivery(uid)
                return (scope==expected and not check() and live["approval_sha256"]==d["approval_sha256"]
                    and plan["plaintext_export_explicitly_requested"] is True and
                    plan["picture_mxf_sha256"]==reel["track_sha256"] and
                    plan["mastering_decision_sha256"]==reel["decision_sha256"])
            receipt=publish_file_backed_dcp(job_id=uid,picture=picture,sound=sound,title=d["title"],
                 profile=reel["profile"],frames=reel["frame_count"],output_root=d["output_root"],
                 ids=ids,check_cancel=check,approve=authorize,
                 mastering_decision_sha256=reel["decision_sha256"])
            return self.journal.commit_package(self.owner,uid,receipt)
        except (OSError,ValueError,RuntimeError,KeyError) as exc:
            inspect_original_process_journals()
            if self.journal.status(uid)["cancel_requested"]:
                self.journal.finalize_cancel(uid)
                return {"status":"CANCELLED","job_id":uid}
            self.journal.delivery_review(self.owner,uid,type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","job_id":uid,"reason":type(exc).__name__}

    def _run_index_commit(self,uid):
        try:
            return self.journal.commit_filmindex(uid,index=self.resolve_project(self.journal.status(uid)["project_id"]))
        except (OSError,ValueError,RuntimeError,KeyError) as exc:
            self.journal._mark_delivery_restart_review(uid,type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","job_id":uid,"reason":type(exc).__name__}

    def _run_multireel_feature(self,task):
        fid=task["feature_id"]
        m=task["manifest"]
        binding=m["source_reel_authority"][0]
        def check():
            return self.journal.feature_cancel_requested(fid,self.owner)
        try:
            snapshot=self.journal.feature(fid)
            self.journal._verify_feature_sources(m,index=self.resolve_project(m["project_id"]))
            expected={"operation":"nvp.wo4.export_multireel_candidate.v1",
                "source_take_sha256":binding["source_take_sha256"],
                "mastering_decision_sha256":binding["mastering_decision_sha256"],
                "source_reel_authority":m["source_reel_authority"],"feature_assembly_sha256":m["assembly_sha256"],
                "reels":m["reels"],"ids":m["ids"],"title":m["title"],"profile":m["profile"],
                "frames":sum(p["frames"] for p in m["reels"]),"output_root":m["output_root"],
                "plaintext_export_explicitly_requested":True}
            def authorize(scope):
                return (not check() and scope==expected and
                    self.journal.feature(fid)["manifest_sha256"]==snapshot["manifest_sha256"])
            result=publish_multireel_dcp(reels=m["reels"],ids=m["ids"],title=m["title"],
                profile=m["profile"],output_root=m["output_root"],check_cancel=check,approve=authorize,
                source_take_sha256=binding["source_take_sha256"],
                mastering_decision_sha256=binding["mastering_decision_sha256"],
                source_reel_authority=m["source_reel_authority"],feature_assembly_sha256=m["assembly_sha256"])
            if check():
                raise InterruptedError("Cancelled before feature checkpoint")
            receipt=self.journal.commit_feature(self.owner,fid,result)
            return {"status":"FEATURE_PUBLISHED_PENDING_INDEX","feature_id":fid,
                    "destination":receipt["destination"],"production_dcp_accepted":False}
        except (OSError,ValueError,RuntimeError,KeyError) as exc:
            if check():
                return self.journal.finalize_feature_cancel(fid,self.owner)
            self.journal.feature_review(self.owner,fid,type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","feature_id":fid,"reason":type(exc).__name__}

    def _run_feature_index(self,fid):
        try:
            return self.journal.commit_feature_index(fid,index=self.resolve_project(self.journal.feature(fid)["project_id"]))
        except (OSError,ValueError,RuntimeError,KeyError) as exc:
            self.journal._mark_feature_restart_review(fid)
            return {"status":"REVIEW_REQUIRED","feature_id":fid,"reason":type(exc).__name__}

    def run_one(self,*,after_claim=None):
        _require_owner(self.journal.root)
        for item in self.journal.list_jobs():
            status=self.journal.status(item["job_id"])
            if (status["task_kind"]==TASK_KIND and status["cancel_requested"] and
                    status["state"] not in ("CANCELLED","VERIFY_COMPLETE")):
                self.journal.finalize_cancel(item["job_id"])
        if isinstance(self.journal,CinemaJournal):
            with self.journal._read() as db:
                if db.execute("SELECT 1 FROM production_cinema_reels r JOIN production_jobs j ON j.job_id=r.job_id WHERE r.reel_state='TRACK_RUNNING' AND j.state!='CANCELLED'").fetchone():
                    raise PermissionError("Interrupted native track must be reconciled before work")
            for item in self.journal.list_jobs():
                status=self.journal.status(item["job_id"])
                if (status["task_kind"]==CINEMA_TASK and status["cancel_requested"]
                        and status["state"] not in ("CANCELLED","OUTPUT_READY")):
                    inspect_original_process_journals()
                    self.journal.finalize_cancel(item["job_id"])
        if isinstance(self.journal,CinemaDeliveryJournal):
            for item in self.journal.list_jobs():
                status=self.journal.status(item["job_id"])
                if status["cancel_requested"] and status["state"]=="OUTPUT_READY":
                    self.journal.finalize_cancel(item["job_id"])
        segment=self.journal.claim_next(self.owner,self.pid)
        if segment is None and isinstance(self.journal,CinemaJournal):
            segment=self.journal.claim_next(self.owner,self.pid,task_kind=CINEMA_TASK)
            if segment is None:
                track=self.journal.next_track(self.owner,self.pid)
                if track is not None:
                    return self._wrap_cinema_track(track)
            elif segment["task_kind"]==CINEMA_TASK:
                return self._run_cinema_frame(segment)
        if segment is None:
            if isinstance(self.journal,CinemaDeliveryJournal):
                pending=self.journal.next_pending_index()
                if pending is not None:
                    return self._run_index_commit(pending)
                step=self.journal.next_delivery(self.owner,self.pid)
                if step is not None:
                    return self._run_delivery(step)
            if isinstance(self.journal,FeatureJournal):
                with self.journal._read() as db:
                    cancelled=db.execute("SELECT feature_id FROM production_features WHERE state='QUEUED' AND cancel_requested=1 ORDER BY created_at LIMIT 1").fetchone()
                if cancelled is not None:
                    return self.journal.finalize_feature_cancel(cancelled["feature_id"],self.owner)
                pending=self.journal.next_feature_index()
                if pending is not None:
                    return self._run_feature_index(pending)
                task=self.journal.next_feature(self.owner)
                if task is not None:
                    return self._run_multireel_feature(task)
            return {"status":"IDLE","worker_kind":TASK_KIND}
        if segment["task_kind"]!=TASK_KIND:
            raise PermissionError("No unregistered production worker")
        job_id=segment["job_id"]
        try:
            if after_claim is not None:
                after_claim(dict(segment))
            last_heartbeat=time.monotonic()
            def check_cancel():
                nonlocal last_heartbeat
                _require_owner(self.journal.root)
                if time.monotonic()-last_heartbeat>=1:
                    self.journal.heartbeat(self.owner,job_id,segment["position"])
                    last_heartbeat=time.monotonic()
                return self.journal.claim_cancel_requested(self.owner,job_id,segment["position"])
            digest,size=verify_approved_file(segment,check_cancel=check_cancel)
            if check_cancel():
                raise InterruptedError("Cancelled before verification checkpoint")
            result=self.journal.finish_verified(self.owner,job_id,segment["position"],digest,size)
            return {"status":"SEGMENT_VERIFIED","job_id":job_id,
                    "segment":segment["position"],"job_state":result["state"],
                    "production_dcp_accepted":False}
        except (OSError,RuntimeError,ValueError) as exc:
            if self.journal.status(job_id)["cancel_requested"]:
                self.journal.finalize_cancel(job_id)
                return {"status":"CANCELLED","job_id":job_id}
            self.journal.mark_review(self.owner,job_id,segment["position"],type(exc).__name__)
            return {"status":"REVIEW_REQUIRED","job_id":job_id,"reason":type(exc).__name__,
                    "production_dcp_accepted":False}
