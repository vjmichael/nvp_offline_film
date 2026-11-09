"""USD-FILM-01O: restart-recoverable, source-locked full camera roll jobs.

Each 30-second source camera roll = 720 original 24fps frames in NINETY
bounded eight-frame Cycles jobs. Jobs use existing SHA-pinned native Blender
supervisor, kernel custody, SQLite durable journal, cancellation and
independent output re-verification. An interrupted job is NEVER automatically
retried or accepted. A fresh attempt needs a new job ID and a NEW exact
director authorization plus an actual host OS-custody proof callback.

This host NEVER claims finished film until nine (or chosen) fully verified
camera rolls and their independent picture+audio conform have been checked.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

from backend.nvp_blender_worker import (
    BlenderOperation,BlenderWorkerSupervisor,sha_file)
from backend.nvp_film_index import FilmIndex
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_usd_film01o_original_camera_roll_source import (
    original_camera_roll_source,STAGE,MANIFEST,FORMAT as SOURCE_FORMAT,
    canonical,file_sha)

SCRIPT="nvp_usd_film01o_blender_camera_chunk.py"
MASK="nvp_usd_film01m_camera_ray_mask.py"
AUDIT="audit.json"
CHUNK_FORMAT="nvp.usd_film01o.reviewed_native_cycles_chunk.v1"
AUDIT_FORMAT="nvp.usd_film01o.native_cycles_chunk_audit.v1"
FRAMES=720
CHUNK=8
CHUNKS_PER_ROLL=90
MAX_RETRIES=99
ROLL_FORMAT="nvp.usd_film01o.supervisor_verified_original_camera_roll.v1"


def chunk_id(bank_sha,camera_id,start,attempt=1):
    if (type(attempt) is not int or not 1<=attempt<=MAX_RETRIES or
        type(start) is not int or start not in range(0,720,CHUNK)):
        raise ValueError("Bounded original camera chunk identity required")
    key=sha256(camera_id.encode("utf8")).hexdigest()[:10]
    return f"filmO_{bank_sha[:12]}_{key}_{start:04d}_a{attempt:02d}"


class RecoverableOriginalCameraRolls:
    def __init__(self,index:FilmIndex,supervisor:BlenderWorkerSupervisor,
                 *,verify_director_action,prove_process_custody):
        if (not isinstance(index,FilmIndex) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not callable(verify_director_action) or
            not callable(prove_process_custody)):
            raise TypeError("Original FilmIndex, contained supervisor and host approvals required")
        self.index=index
        self.supervisor=supervisor
        self.approve=verify_director_action
        self.custody=prove_process_custody

    def _bank(self,pid,bank_id,revision):
        bank=DirectorCameraBank(
            self.index,verify_director_action=lambda *_:False)
        doc=bank.verify(pid,bank_id,revision)
        if not 1<=doc["camera_count"]<=96 or doc["source_duration_ticks"]<30*7056000000:
            raise ValueError("Only full 30s original director camera performance admitted")
        record=self.index.read_revision(pid,bank_id,revision)
        return doc,record

    def source(self,pid,bank_id,revision):
        """Build once, then revalidate pinned source identities on restart."""
        doc,record=self._bank(pid,bank_id,revision)
        directory=self.supervisor.root/("filmO_source_"+record[
            "document_sha256"][:24])
        if not directory.exists():
            original_camera_roll_source(self.index,pid,bank_id,
                revision=revision,folder=directory)
        if directory.is_symlink():
            raise PermissionError("Original render source was replaced by symlink")
        manifest=directory/MANIFEST
        stage=directory/STAGE
        if (manifest.is_symlink() or stage.is_symlink() or
            not manifest.is_file() or not stage.is_file()):
            raise RuntimeError("Restart found missing original camera source bundle")
        src=json.loads(manifest.read_text("utf8"))
        take=self.index.read_revision(pid,doc["world_take_id"],1)
        if (src.get("format")!=SOURCE_FORMAT or
            src.get("source_camera_bank_sha256")!=record["document_sha256"] or
            src.get("original_world_take_sha256")!=take["document_sha256"] or
            src.get("original_world_sha256")!=doc["source_world_sha256"] or
            src.get("original_performance_sha256")!=doc["source_performance_sha256"] or
            src.get("source_usd_sha256")!=file_sha(stage) or
            src.get("source_usd_size_bytes")!=stage.stat().st_size or
            src.get("frame_count")!=FRAMES or
            type(src.get("original_frame_evidence")) is not list or
            len(src["original_frame_evidence"])!=FRAMES or
            [x["camera_id"] for x in src["cameras"]]!=[
                c["camera_id"] for c in doc["cameras"]]):
            raise RuntimeError("Saved camera-roll source no longer matches authoritative FilmIndex")
        # Do not trust a self-consistent sidecar to replace the actual source
        # motion: independently evaluate checkpoint actor poses from
        # reopened immutable FilmIndex scene, not the derived file's claims.
        from pxr import Usd,UsdGeom
        from backend.nvp_usd_film01_world import OpenUSDWorldComposer
        original=take["data"]
        with OpenUSDWorldComposer(self.index).open(
                pid,original["world_id"],original["world_revision"]) as world:
            world.load([original["original_scene_takes"][0]["set"]])
            for frame in (0,239,240,479,480,719):
                evidence=src["original_frame_evidence"][frame]
                if (evidence["frame"]!=frame or
                    evidence["original_film_tick"]!=frame*7056000000//24):
                    raise RuntimeError("Original source frame clock changed on restart")
                actors={x["actor_id"]:x for x in evidence["original_actor_positions"]}
                for actor in original["canonical_original_actors"]:
                    original_prim=world.stage.GetPrimAtPath(
                        actor["composed_actor_prim"])
                    xyz=UsdGeom.Xformable(
                        original_prim).ComputeLocalToWorldTransform(
                            Usd.TimeCode(float(evidence["original_film_tick"]))
                        ).ExtractTranslation()
                    expected=actors[actor["actor_id"]]["position_m"]
                    if any(abs(float(xyz[i])-expected[i])>1e-6 for i in range(3)):
                        raise RuntimeError("Saved camera-roll performer no longer matches original USD")
        return directory,src

    @staticmethod
    def _chunk_spec(src,camera_id,start,attempt):
        if camera_id not in {c["camera_id"] for c in src["cameras"]}:
            raise PermissionError("Camera absent from immutable director source bank")
        if start not in range(0,FRAMES,CHUNK):
            raise ValueError("Original camera chunk boundary must be eight frames")
        return {
            "format":CHUNK_FORMAT,
            "source_manifest_sha256":None, # filled by verified source caller
            "source_usd_sha256":src["source_usd_sha256"],
            "camera_bank_sha256":src["source_camera_bank_sha256"],
            "camera_id":camera_id,"start_frame":start,
            "frame_count":min(CHUNK,FRAMES-start),"attempt":attempt}

    def _validate_job(self,job_id,src,source_directory,camera_id,start,attempt):
        status=self.supervisor.verify_completed(job_id)
        job=self.supervisor.root/job_id
        chunk=json.loads((job/"chunk.json").read_text("utf8"))
        expected=self._chunk_spec(src,camera_id,start,attempt)
        expected["source_manifest_sha256"]=file_sha(source_directory/MANIFEST)
        if chunk!=expected:
            raise RuntimeError("Recovered journal references wrong source camera chunk")
        audit=json.loads((job/AUDIT).read_text("utf8"))
        rows=audit.get("original_frame_receipts")
        if (audit.get("format")!=AUDIT_FORMAT or audit.get("passed") is not True
            or audit.get("source_manifest_sha256")!=expected[
                "source_manifest_sha256"] or
            audit.get("source_usd_sha256")!=expected["source_usd_sha256"] or
            audit.get("original_camera_bank_sha256")!=expected["camera_bank_sha256"] or
            audit.get("original_world_take_sha256")!=src["original_world_take_sha256"] or
            audit.get("original_performance_sha256")!=src["original_performance_sha256"] or
            audit.get("camera_id")!=camera_id or
            audit.get("start_frame")!=start or
            audit.get("frame_count")!=expected["frame_count"] or
            audit.get("attempt")!=attempt or
            type(rows) is not list or len(rows)!=expected["frame_count"] or
            audit.get("actual_native_cycles_frames")!=len(rows)):
            raise RuntimeError("Native Cycles job receipt differs from source and journal")
        from PIL import Image
        for j,row in enumerate(rows):
            frame=start+j
            evidence=src["original_frame_evidence"][frame]
            name=f"frame_{frame:04d}.png"
            path=job/name
            if (row.get("frame")!=frame or
                row.get("original_film_tick")!=evidence["original_film_tick"] or
                row.get("original_actor_state_sha256")!=
                    evidence["original_actor_state_sha256"] or
                row.get("rendered_png_file")!=name or
                row.get("rendered_png_sha256")!=file_sha(path) or
                row.get("actual_native_cycles_image") is not True or
                row.get("original_actor_positions_independently_checked") is not True or
                row.get("original_camera_position_independently_checked") is not True or
                row.get("ray_visibility_restored_for_next_frame") is not True):
                raise RuntimeError("One of eight camera frames failed independent source verification")
            with Image.open(path) as image:
                if image.format!="PNG" or image.size!=(320,180):
                    raise RuntimeError("Native original Cycles picture has wrong raster")
                image.verify()
        return {"job_id":job_id,"camera_id":camera_id,
                "start_frame":start,"frame_count":len(rows),
                "attempt":attempt,"state":"REVERIFIED_COMPLETED",
                "native_frames_checked":len(rows),
                "supervisor_journal_state":status["state"]}

    def run_chunk(self,pid,bank_id,*,revision,camera_id,start,
                  attempt=1,director_event):
        """Exactly one bounded native process, with per-attempt authority."""
        doc,record=self._bank(pid,bank_id,revision)
        source_dir,src=self.source(pid,bank_id,revision)
        job_id=chunk_id(record["document_sha256"],camera_id,start,attempt)
        existing=None
        try:
            existing=self.supervisor.inspect(job_id)
        except KeyError:
            pass
        if existing is not None:
            if existing["state"]=="SUCCEEDED":
                return self._validate_job(
                    job_id,src,source_dir,camera_id,start,attempt)
            raise PermissionError(
                "Interrupted/failed/running job cannot be automatically replayed; "
                "inspect custody and use a new director-authorized attempt ID")
        if attempt>1:
            previous=[chunk_id(
                record["document_sha256"],camera_id,start,i)
                for i in range(1,attempt)]
            found=[]
            for pid_previous in previous:
                try:
                    found.append(self.supervisor.inspect(pid_previous))
                except KeyError:
                    continue
            if not found:
                raise PermissionError("New retry attempt lacks a prior recorded failure")
            if any(s["state"] in ("RUNNING","CANCEL_REQUESTED") for s in found):
                raise PermissionError("Prior job is still active")
            if any(s["state"]=="SUCCEEDED" for s in found):
                raise PermissionError("Completed chunk already has authoritative evidence")
            if not all(self.custody(s["id"]) is True for s in found):
                raise PermissionError(
                    "New attempt forbidden without independent OS process custody proof")
        chunk=self._chunk_spec(src,camera_id,start,attempt)
        chunk["source_manifest_sha256"]=file_sha(source_dir/MANIFEST)
        scope={
            "operation":"nvp.render.usd_film01o_chunk.v1",
            "project_id":pid,"camera_bank_sha256":record["document_sha256"],
            "original_world_take_sha256":src["original_world_take_sha256"],
            "original_performance_sha256":src["original_performance_sha256"],
            "source_usd_sha256":src["source_usd_sha256"],
            "source_manifest_sha256":chunk["source_manifest_sha256"],
            "camera_id":camera_id,"start_frame":start,
            "frame_count":chunk["frame_count"],
            "new_job_id":job_id,"attempt":attempt}
        if self.approve(director_event,scope) is not True:
            raise PermissionError("Fresh exact director approval required per camera chunk")
        root=self.supervisor.root/job_id
        if root.exists() or root.is_symlink():
            raise FileExistsError("Unjournaled existing job folder cannot be reused")
        root.mkdir(mode=0o700)
        try:
            scripts=Path(__file__).resolve().parents[1]/"tools"
            for name in (SCRIPT,MASK):
                source=scripts/name
                if not source.is_file() or source.is_symlink():
                    raise RuntimeError("Reviewed pinned Blender worker script absent")
                shutil.copyfile(source,root/name)
            shutil.copyfile(source_dir/STAGE,root/"source.usda")
            shutil.copyfile(source_dir/MANIFEST,root/"source.json")
            (root/"chunk.json").write_bytes(canonical(chunk))
            outputs={f"frame_{i:04d}.png":"png" for i in range(
                start,start+chunk["frame_count"])}
            outputs[AUDIT]="json_audit"
            op=BlenderOperation(job_id=job_id,
                script=SCRIPT,script_sha256=file_sha(root/SCRIPT),
                inputs={
                    "source.usda":file_sha(root/"source.usda"),
                    "source.json":file_sha(root/"source.json"),
                    "chunk.json":file_sha(root/"chunk.json"),
                    MASK:file_sha(root/MASK)},
                outputs=outputs,
                arguments={"--manifest":"chunk.json","--audit":AUDIT},
                timeout_seconds=600,memory_limit_mb=8192,
                require_linux_cgroup_v2=False,gpu_memory_mb=0)
            self.supervisor._validate(op)
            state=self.supervisor.run(op)
            if state["state"]!="SUCCEEDED":
                raise RuntimeError("Actual native source Cycles chunk failed: "+
                                   str(state.get("error") or state["state"]))
            return self._validate_job(
                job_id,src,source_dir,camera_id,start,attempt)
        except Exception:
            # Never remove a journaled job or native failure evidence.
            try:
                self.supervisor.inspect(job_id)
            except KeyError:
                if root.exists() and not root.is_symlink():
                    shutil.rmtree(root)
            raise

    def progress(self,pid,bank_id,*,revision,approved_attempts=None):
        """Restart-safe inventory; never infer success from an output file."""
        doc,record=self._bank(pid,bank_id,revision)
        sources,manifest=self.source(pid,bank_id,revision)
        attempts=approved_attempts or {}
        summary=[]
        for cam in manifest["cameras"]:
            camera_id=cam["camera_id"]
            status={"camera_id":camera_id,"completed_chunks":0,
                    "native_verified_frames":0,"blocked_chunks":[],
                    "next_eligible_chunk":None}
            for start in range(0,FRAMES,CHUNK):
                attempt=attempts.get(camera_id,{}).get(start,1)
                job_id=chunk_id(record["document_sha256"],
                                camera_id,start,attempt)
                try:
                    prior=self.supervisor.inspect(job_id)
                except KeyError:
                    prior=None
                if prior is None:
                    if status["next_eligible_chunk"] is None:
                        status["next_eligible_chunk"]=start
                    continue
                if prior["state"]=="SUCCEEDED":
                    self._validate_job(
                        job_id,manifest,sources,camera_id,start,attempt)
                    status["completed_chunks"]+=1
                    status["native_verified_frames"]+=min(CHUNK,FRAMES-start)
                else:
                    status["blocked_chunks"].append({
                        "start_frame":start,"job_id":job_id,
                        "state":prior["state"],"reissue_not_automatic":True})
            status["completed_original_camera_roll"]=(
                status["completed_chunks"]==CHUNKS_PER_ROLL)
            summary.append(status)
        return {"source_camera_bank_sha256":record["document_sha256"],
                "source_performance_sha256":manifest[
                    "original_performance_sha256"],
                "camera_rolls":summary,
                "total_verified_original_frames":sum(
                    x["native_verified_frames"] for x in summary),
                "full_source_coverage_frames_required":len(summary)*FRAMES,
                "all_rolls_completed":all(x[
                    "completed_original_camera_roll"] for x in summary),
                "failed_or_interrupted_jobs_must_not_auto_replay":True}

    def run_next(self,pid,bank_id,*,revision,director_event):
        """Run ONE new approved chunk; never silently retry interrupted jobs."""
        report=self.progress(pid,bank_id,revision=revision)
        for camera in report["camera_rolls"]:
            if camera["blocked_chunks"]:
                return {"state":"BLOCKED_NEEDS_NATIVE_RECOVERY_AND_FRESH_APPROVAL",
                        "camera_id":camera["camera_id"],
                        "blocked_chunks":camera["blocked_chunks"]}
        for camera in report["camera_rolls"]:
            if camera["next_eligible_chunk"] is not None:
                return self.run_chunk(
                    pid,bank_id,revision=revision,
                    camera_id=camera["camera_id"],
                    start=camera["next_eligible_chunk"],
                    attempt=1,director_event=director_event)
        return {"state":"ALL_CAMERA_ROLL_CHUNKS_REVERIFIED",
                "full_original_frames":report["total_verified_original_frames"],
                "no_automatic_media_master_acceptance":True}

    def gather_roll(self,pid,bank_id,*,revision,camera_id,
                    folder,approved_attempts=None):
        """No roll until ALL 90 exact chunks were independently reverified."""
        doc,record=self._bank(pid,bank_id,revision)
        source_dir,src=self.source(pid,bank_id,revision)
        attempts=approved_attempts or {}
        camera=next((c for c in src["cameras"]
                     if c["camera_id"]==camera_id),None)
        if camera is None:
            raise KeyError("No source camera identity in this original performance")
        jobs=[]
        for start in range(0,FRAMES,CHUNK):
            attempt=attempts.get(start,1)
            id=chunk_id(record["document_sha256"],camera_id,start,attempt)
            jobs.append(self._validate_job(
                id,src,source_dir,camera_id,start,attempt))
        destination=Path(folder)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Never overwrite accepted source camera footage")
        destination.mkdir(mode=0o700,parents=True)
        receipts=[]
        try:
            for part in jobs:
                start=part["start_frame"]
                job=self.supervisor.root/part["job_id"]
                audit=json.loads((job/AUDIT).read_text("utf8"))
                for row in audit["original_frame_receipts"]:
                    frame=row["frame"]
                    name=f"frame_{frame:04d}.png"
                    target=destination/name
                    shutil.copyfile(job/name,target)
                    if file_sha(target)!=row["rendered_png_sha256"]:
                        raise RuntimeError("Gathered camera picture differs from verified Blender job")
                    source_frame=src["original_frame_evidence"][frame]
                    receipts.append({
                        "actual_native_cycles_image":True,
                        "original_film_tick":source_frame["original_film_tick"],
                        "original_actor_state_sha256":source_frame[
                            "original_actor_state_sha256"],
                        "original_world_sha256":src["original_world_sha256"],
                        "original_performance_sha256":src["original_performance_sha256"],
                        "original_camera_bank_sha256":src["source_camera_bank_sha256"],
                        "original_camera_path":camera["source_camera_prim"],
                        "original_camera_id":camera_id,
                        "rendered_png_sha256":row["rendered_png_sha256"],
                        "verified_supervisor_job_id":part["job_id"],
                    })
            if len(receipts)!=FRAMES:
                raise RuntimeError("Full original camera footage is not complete")
            (destination/"frame_receipts.json").write_bytes(canonical(receipts))
            result={
                "format":ROLL_FORMAT,
                "camera_id":camera_id,
                "original_world_take_sha256":src["original_world_take_sha256"],
                "original_performance_sha256":src["original_performance_sha256"],
                "camera_bank_sha256":record["document_sha256"],
                "source_usd_sha256":src["source_usd_sha256"],
                "frame_count":FRAMES,"fps":24,
                "verified_chunk_count":CHUNKS_PER_ROLL,
                "verified_native_render_frames":FRAMES,
                "frame_receipts_sha256":file_sha(
                    destination/"frame_receipts.json"),
                "director_picture_approval":False,
                "original_audio_mixed":False}
            (destination/"roll_receipt.json").write_bytes(canonical(result))
            return result
        except Exception:
            shutil.rmtree(destination)
            raise
