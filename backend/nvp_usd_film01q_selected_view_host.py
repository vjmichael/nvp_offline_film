"""USD-FILM-01Q: protected/recoverable SELECTED-view 720-frame movie pipeline.

Render 90 eight-frame chunks, each choosing one camera per original source
frame. Never render unused source camera rolls. Each chunk has a fresh
director authorization and the existing BlenderWorkerSupervisor journal.
Interrupted/native-failed chunks MUST NOT be replayed without independently
verified process custody and a newly scoped approval. A complete edited
film still requires 90 real Cycles chunk receipts and actual FFmpeg AV output.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

from backend.nvp_blender_worker import (
    BlenderOperation,BlenderWorkerSupervisor,sha_file)
from backend.nvp_film_index import FilmIndex,_id
from backend.nvp_usd_film01r_quality import reviewed_quality,quality_hash
from backend.nvp_usd_film01o_recoverable_camera_roll_host import (
    RecoverableOriginalCameraRolls)
from backend.nvp_usd_film01o_original_camera_roll_source import (
    STAGE,MANIFEST,canonical,file_sha)
from backend.nvp_usd_film01q_selected_view_edit import (
    OriginalSelectedViewEdit,selected_render_plan,CHUNK,CHUNKS,
    CHUNK_FORMAT,RENDER_PLAN_FORMAT,edit_sha)
from backend.nvp_usd_film01p_source_multicam_film_conform import (
    _read_pcm_mix_from_original,_run,_probe,_decoded_frames,
    FRAMES,FPS,SAMPLES)

SCRIPT="nvp_usd_film01q_blender_selected_views.py"
MASK="nvp_usd_film01m_camera_ray_mask.py"
AUDIT="audit.json"
AUDIT_FORMAT="nvp.usd_film01q.native_selected_view_cycles_chunk_audit.v1"
FILM_FORMAT="nvp.usd_film01q.selected_original_720frame_film_with_pcm.v1"

def chunk_job_id(edit_document_sha256,start,attempt=1,render_profile_sha256=None):
    if (type(start) is not int or start not in range(0,FRAMES,CHUNK) or
        type(attempt) is not int or not 1<=attempt<=99 or
        type(edit_document_sha256) is not str or
        len(edit_document_sha256)!=64 or any(c not in "0123456789abcdef"
                                           for c in edit_document_sha256)):
        raise ValueError("Exact source edit, chunk and one bounded attempt required")
    profile=render_profile_sha256 or quality_hash(reviewed_quality("technical_smoke"))
    if (type(profile) is not str or len(profile)!=64 or
        any(c not in "0123456789abcdef" for c in profile)):
        raise ValueError("Only source-hashed original film render profiles are admitted")
    return f"filmQ_{edit_document_sha256[:12]}_{profile[:8]}_{start:04d}_a{attempt:02d}"


class ReviewedSelectedViewFilm:
    def __init__(self,index:FilmIndex,supervisor:BlenderWorkerSupervisor,
                 *,verify_director_action,prove_process_custody,
                 render_quality='technical_smoke'):
        if (not isinstance(index,FilmIndex) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not callable(verify_director_action) or
            not callable(prove_process_custody)):
            raise TypeError("Original source FilmIndex, existing native broker and host approvals required")
        self.index=index
        self.render_quality=reviewed_quality(render_quality)['name']
        self.supervisor=supervisor
        self.approve=verify_director_action
        self.custody=prove_process_custody
        self._original=RecoverableOriginalCameraRolls(
            index,supervisor,verify_director_action=lambda *_:False,
            prove_process_custody=lambda *_:False)

    def source_plan(self,pid,edit_id,revision):
        edit=OriginalSelectedViewEdit(
            self.index,verify_director_action=lambda *_:False).verify(
                pid,edit_id,revision)
        source_dir,source=self._original.source(
            pid,edit["camera_bank_id"],edit["camera_bank_revision"])
        planned=selected_render_plan(
            self.index,pid,edit_id,revision,
            original_source_directory=source_dir,
            render_quality=self.render_quality)
        record=self.index.read_revision(pid,edit_id,revision)
        if (planned["plan"]["edit_document_sha256"]!=record["document_sha256"]
            or planned["plan"]["source_bank_sha256"]!=
                source["source_camera_bank_sha256"]):
            raise PermissionError("Original source camera/render plan not authenticated")
        return source_dir,source,planned

    def _chunk(self,plan,start,attempt):
        if type(start) is not int or start not in range(0,FRAMES,CHUNK):
            raise ValueError("Selected shot chunk must be an exact 8-frame window")
        item=plan["plan"]["chunks"][start//CHUNK]
        if item["start_frame"]!=start or item["frame_count"]!=CHUNK:
            raise RuntimeError("Selected source chunk plan broken")
        return {
            "format":CHUNK_FORMAT,
            "plan_sha256":plan["plan_sha256"],
            "source_manifest_sha256":plan["plan"]["source_manifest_sha256"],
            "original_usd_sha256":plan["plan"]["original_usd_sha256"],
            "edit_document_sha256":plan["plan"]["edit_document_sha256"],
            "start_frame":start,"frame_count":CHUNK,
            "source_frames_sha256":item["source_frames_sha256"],
            "attempt":attempt}

    def _verify_completed(self,job_id,source_dir,source,planned,
                          start,attempt):
        state=self.supervisor.verify_completed(job_id)
        job=self.supervisor.root/job_id
        spec=self._chunk(planned,start,attempt)
        files={
            "chunk.json":canonical(spec),
            "plan.json":canonical(planned["plan"])}
        for name,expected_bytes in files.items():
            path=job/name
            if path.is_symlink() or not path.is_file() or path.read_bytes()!=expected_bytes:
                raise RuntimeError("Journalled original shot render spec/plan was changed")
        if (file_sha(job/"source.json")!=file_sha(source_dir/MANIFEST) or
            file_sha(job/"source.usda")!=source["source_usd_sha256"] or
            file_sha(job/SCRIPT)!=file_sha(
                Path(__file__).resolve().parents[1]/"tools"/SCRIPT) or
            file_sha(job/MASK)!=file_sha(
                Path(__file__).resolve().parents[1]/"tools"/MASK)):
            raise PermissionError("Original source/native worker script was replaced")
        receipt=json.loads((job/AUDIT).read_text("utf8"))
        fields={
            "format":AUDIT_FORMAT,"passed":True,
            "source_manifest_sha256":spec["source_manifest_sha256"],
            "source_usd_sha256":spec["original_usd_sha256"],
            "plan_sha256":spec["plan_sha256"],
            "edit_document_sha256":spec["edit_document_sha256"],
            "original_world_take_sha256":planned[
                "plan"]["original_world_take_sha256"],
            "original_performance_sha256":planned[
                "plan"]["original_performance_sha256"],
            "start_frame":start,"frame_count":CHUNK,
            "render_profile_sha256":planned["plan"]["render_profile_sha256"],
            "render_resolution_x":planned["plan"]["render_profile"]["resolution_x"],
            "render_resolution_y":planned["plan"]["render_profile"]["resolution_y"],
            "render_samples":planned["plan"]["render_profile"]["samples"],
            "attempt":attempt,"native_rendered_frames":CHUNK,
            "passed":True}
        if any(receipt.get(k)!=v for k,v in fields.items()):
            raise RuntimeError("Native edited film audit does not match source plan")
        rows=receipt.get("selected_view_frames")
        if type(rows) is not list or len(rows)!=CHUNK:
            raise RuntimeError("Native cycles outputs do not cover selected eight frames")
        from PIL import Image
        for j,row in enumerate(rows):
            frame=planned["plan"]["frames"][start+j]
            filename=f"frame_{start+j:04d}.png"
            picture=job/filename
            if (picture.is_symlink() or row.get("frame")!=start+j or
                row.get("original_film_tick")!=frame["original_film_tick"] or
                row.get("original_actor_state_sha256")!=frame[
                    "original_actor_state_sha256"] or
                row.get("selected_camera_id")!=frame["camera_id"] or
                row.get("selected_camera_prim")!=frame["source_camera_prim"] or
                row.get("view_cache_sha256")!=frame["view_cache_sha256"] or
                row.get("primary_ray_excluded_prims")!=frame[
                    "camera_ray_exclusions"] or
                row.get("rendered_png_file")!=filename or
                row.get("rendered_png_sha256")!=file_sha(picture) or
                row.get("actual_blender_cycles_pixels") is not True or
                row.get("original_actors_and_camera_position_reverified") is not True or
                row.get("camera_ray_mask_restored") is not True):
                raise RuntimeError("A source-selected original frame receipt did not verify")
            with Image.open(picture) as image:
                if image.format!="PNG" or image.size!=(
                    planned["plan"]["render_profile"]["resolution_x"],
                    planned["plan"]["render_profile"]["resolution_y"]):
                    raise RuntimeError("Selected viewpoint is not an actual expected PNG")
                image.verify()
        return {
            "job_id":job_id,"state":"REVERIFIED_NATIVE_SELECTED_FRAMES",
            "start_frame":start,"attempt":attempt,
            "native_selected_views_rendered":CHUNK,
            "camera_ids":[x["camera_id"] for x in planned[
                "plan"]["frames"][start:start+CHUNK]],
            "journal_state":state["state"]}

    def run_chunk(self,pid,edit_id,*,revision,start,attempt=1,director_event):
        """One new scoped native 8-frame job, or reverify completed journal."""
        _id(edit_id,"reviewed source edit")
        source_dir,source,planned=self.source_plan(pid,edit_id,revision)
        edit_sha256=planned["plan"]["edit_document_sha256"]
        job_id=chunk_job_id(edit_sha256,start,attempt,
                            planned['plan']['render_profile_sha256'])
        try:
            previous=self.supervisor.inspect(job_id)
        except KeyError:
            previous=None
        if previous is not None:
            if previous["state"]=="SUCCEEDED":
                return self._verify_completed(
                    job_id,source_dir,source,planned,start,attempt)
            raise PermissionError("Cannot automatically replay an interrupted native edit render")
        if attempt>1:
            histories=[]
            for a in range(1,attempt):
                ident=chunk_job_id(edit_sha256,start,a,
                    planned['plan']['render_profile_sha256'])
                try:
                    histories.append(self.supervisor.inspect(ident))
                except KeyError:
                    pass
            if not histories:
                raise PermissionError("Retry requires a prior persisted native job failure")
            if any(x["state"]=="SUCCEEDED" for x in histories):
                raise PermissionError("Cannot re-render an already committed chunk via retry")
            if any(x["state"] in ("RUNNING","CANCEL_REQUESTED")
                   for x in histories):
                raise PermissionError("Previous native worker has not completed recovery")
            if not all(self.custody(x["id"]) is True for x in histories):
                raise PermissionError("No independent OS worker process custody proof")
        spec=self._chunk(planned,start,attempt)
        selection=planned["plan"]["frames"][start:start+CHUNK]
        scope={
            "operation":"nvp.render.usd_film01q_selected_source_chunk.v1",
            "project_id":pid,"edit_id":edit_id,
            "edit_revision":revision,"edit_sha256":edit_sha256,
            "original_performance_sha256":planned["plan"][
                "original_performance_sha256"],
            "source_manifest_sha256":spec["source_manifest_sha256"],
            "source_usd_sha256":spec["original_usd_sha256"],
            "start_frame":start,"frame_count":CHUNK,"attempt":attempt,
            "camera_ids":[x["camera_id"] for x in selection],
            "selected_source_frames_sha256":spec["source_frames_sha256"],
            "native_worker_job_id":job_id,
            "render_profile_sha256":planned["plan"]["render_profile_sha256"]}
        if self.approve(director_event,scope) is not True:
            raise PermissionError("Fresh director approval for exact EDL camera chunk required")
        job=self.supervisor.root/job_id
        if job.exists() or job.is_symlink():
            raise FileExistsError("Native selected view journal evidence cannot be overwritten")
        job.mkdir(mode=0o700)
        try:
            scripts=Path(__file__).resolve().parents[1]/"tools"
            for name in (SCRIPT,MASK):
                path=scripts/name
                if not path.is_file() or path.is_symlink():
                    raise RuntimeError("Reviewed Blender source script absent")
                shutil.copyfile(path,job/name)
            shutil.copyfile(source_dir/MANIFEST,job/"source.json")
            shutil.copyfile(source_dir/STAGE,job/"source.usda")
            (job/"plan.json").write_bytes(canonical(planned["plan"]))
            (job/"chunk.json").write_bytes(canonical(spec))
            outputs={f"frame_{i:04d}.png":"png"
                     for i in range(start,start+CHUNK)}
            outputs[AUDIT]="json_audit"
            op=BlenderOperation(
                job_id=job_id,script=SCRIPT,
                script_sha256=file_sha(job/SCRIPT),
                inputs={
                    "source.usda":file_sha(job/"source.usda"),
                    "source.json":file_sha(job/"source.json"),
                    "plan.json":file_sha(job/"plan.json"),
                    "chunk.json":file_sha(job/"chunk.json"),
                    MASK:file_sha(job/MASK)},
                outputs=outputs,
                arguments={"--manifest":"chunk.json","--audit":AUDIT},
                timeout_seconds=planned['plan']['render_profile']['timeout_seconds'],
                memory_limit_mb=planned['plan']['render_profile']['max_worker_ram_mb'],
                require_linux_cgroup_v2=False,gpu_memory_mb=0)
            self.supervisor._validate(op)
            actual=self.supervisor.run(op)
            if actual["state"]!="SUCCEEDED":
                raise RuntimeError("Genuine Blender selected-view job failed: "+
                                   str(actual.get("error") or actual["state"]))
            return self._verify_completed(
                job_id,source_dir,source,planned,start,attempt)
        except Exception:
            # Preserve any started/journalled native work for crash recovery.
            try:
                self.supervisor.inspect(job_id)
            except KeyError:
                if job.exists() and not job.is_symlink():
                    shutil.rmtree(job)
            raise

    def progress(self,pid,edit_id,*,revision,approved_attempts=None):
        source_dir,source,planned=self.source_plan(pid,edit_id,revision)
        attempts=approved_attempts or {}
        completed=0
        blocked=[]
        next_start=None
        for start in range(0,FRAMES,CHUNK):
            attempt=attempts.get(start,1)
            job=chunk_job_id(planned["plan"]["edit_document_sha256"],
                             start,attempt,
                             planned["plan"]["render_profile_sha256"])
            try:
                status=self.supervisor.inspect(job)
            except KeyError:
                status=None
            if status is None:
                if next_start is None:
                    next_start=start
                continue
            if status["state"]=="SUCCEEDED":
                self._verify_completed(
                    job,source_dir,source,planned,start,attempt)
                completed+=CHUNK
            else:
                blocked.append({"job_id":job,"start_frame":start,
                                "state":status["state"],
                                "fresh_authorization_required":True})
        return {
            "edit_id":edit_id,"edit_revision":revision,
            "source_performance_sha256":planned["plan"][
                "original_performance_sha256"],
            "rendered_selected_frames_verified":completed,
            "total_selected_final_frames":FRAMES,
            "native_completed_chunks":completed//CHUNK,
            "native_chunks_required":CHUNKS,
            "next_unstarted_chunk":next_start,
            "blocked_interrupted_native_jobs":blocked,
            "finished":completed==FRAMES and not blocked,
            "unused_camera_rolls_not_rendered":True}

    def run_next(self,pid,edit_id,*,revision,director_event):
        progress=self.progress(pid,edit_id,revision=revision)
        if progress["blocked_interrupted_native_jobs"]:
            return {"state":"BLOCKED_NEEDS_OS_CUSTODY_PROOF_AND_NEW_APPROVAL",
                    "blocked_jobs":progress["blocked_interrupted_native_jobs"]}
        if progress["next_unstarted_chunk"] is None:
            return {"state":"ALL_SELECTED_FRAMES_INDEPENDENTLY_VERIFIED",
                    "native_selected_frames":progress[
                        "rendered_selected_frames_verified"]}
        return self.run_chunk(
            pid,edit_id,revision=revision,
            start=progress["next_unstarted_chunk"],
            director_event=director_event)

    def gather(self,pid,edit_id,*,revision,output_directory,approved_attempts=None):
        """Complete verified 720 selected PNGs, not any unselected camera roll."""
        source_dir,source,planned=self.source_plan(pid,edit_id,revision)
        attempts=approved_attempts or {}
        checked=[]
        for start in range(0,FRAMES,CHUNK):
            attempt=attempts.get(start,1)
            ident=chunk_job_id(
                planned["plan"]["edit_document_sha256"],start,attempt,
                planned["plan"]["render_profile_sha256"])
            checked.append(self._verify_completed(
                ident,source_dir,source,planned,start,attempt))
        directory=Path(output_directory)
        if directory.exists() or directory.is_symlink():
            raise FileExistsError("Never overwrite an accepted source-selected edit")
        directory.mkdir(mode=0o700,parents=True)
        receipt=[]
        try:
            for chunk in checked:
                job=self.supervisor.root/chunk["job_id"]
                audit=json.loads((job/AUDIT).read_text("utf8"))
                for frame in audit["selected_view_frames"]:
                    file=frame["rendered_png_file"]
                    shutil.copyfile(job/file,directory/file)
                    if file_sha(directory/file)!=frame["rendered_png_sha256"]:
                        raise RuntimeError("Selected original frame changed while gathering")
                    receipt.append({**frame,
                        "native_worker_job_id":chunk["job_id"]})
            if len(receipt)!=FRAMES or [x["frame"] for x in receipt]!=list(range(FRAMES)):
                raise RuntimeError("Final source-selected film picture missing frames")
            (directory/"source_selected_receipts.json").write_bytes(canonical(receipt))
            summary={
                "format":"nvp.usd_film01q.gathered_source_selected_720frames.v1",
                "edit_sha256":planned["plan"]["edit_document_sha256"],
                "original_performance_sha256":planned["plan"][
                    "original_performance_sha256"],
                "native_verified_frames":FRAMES,
                "native_verified_chunks":CHUNKS,
                "render_profile_sha256":planned["plan"]["render_profile_sha256"],
                "source_selected_receipts_sha256":file_sha(
                    directory/"source_selected_receipts.json"),
                "all_original_camera_rolls_required":False,
                "director_picture_approved":False}
            (directory/"gather_receipt.json").write_bytes(canonical(summary))
            return summary
        except Exception:
            shutil.rmtree(directory)
            raise

    def conform_edited_film(self,pid,edit_id,*,revision,pictures_dir,
                           destination_dir,ffmpeg,ffprobe,director_event):
        """Full genuine 30s video + one original PCM sound, no camera rolls."""
        source_dir,source,planned=self.source_plan(pid,edit_id,revision)
        pictures=Path(pictures_dir)
        if pictures.is_symlink() or not pictures.is_dir():
            raise PermissionError("No trusted source-selected rendered pictures")
        summary=json.loads((pictures/"gather_receipt.json").read_text("utf8"))
        if (summary.get("edit_sha256")!=planned["plan"][
                "edit_document_sha256"] or
            summary.get("native_verified_frames")!=FRAMES or
            summary.get("native_verified_chunks")!=CHUNKS or
            summary.get("source_selected_receipts_sha256")!=file_sha(
                pictures/"source_selected_receipts.json")):
            raise RuntimeError("No independent verified original selected picture set")
        # Re-verify the original worker journal, exact image bytes and EDL
        # even if the gather receipt claims all 720 frames are present.
        rows=json.loads((pictures/"source_selected_receipts.json").read_text("utf8"))
        if type(rows) is not list or len(rows)!=FRAMES:
            raise RuntimeError("Original selected picture timeline incomplete")
        jobs={}
        for i,row in enumerate(rows):
            expected=planned["plan"]["frames"][i]
            path=pictures/f"frame_{i:04d}.png"
            if (path.is_symlink() or row.get("frame")!=i or
                row.get("selected_camera_id")!=expected["camera_id"] or
                row.get("view_cache_sha256")!=expected["view_cache_sha256"] or
                row.get("original_actor_state_sha256")!=expected[
                    "original_actor_state_sha256"] or
                row.get("rendered_png_sha256")!=file_sha(path)):
                raise RuntimeError("Edited film pixels differ from source-locked EDL")
            job=chunk_job_id(planned["plan"]["edit_document_sha256"],(i//CHUNK)*CHUNK,
                             int(row.get("native_worker_job_id","_a00")[-2:]),
                             planned["plan"]["render_profile_sha256"])
            if row.get("native_worker_job_id")!=job:
                raise RuntimeError("Unrecognized restarted worker attempt")
            jobs[(i//CHUNK)*CHUNK]=job
        for start,job in jobs.items():
            self._verify_completed(job,source_dir,source,planned,start,
                                   int(job[-2:]))
        # Final picture/audio publication requires NEW, exact host approval.
        # A completed render chunk approval cannot authorize final export.
        authorization={
            "operation":"nvp.film01q.conform_original_selected_film.v1",
            "project_id":pid,"edit_id":edit_id,
            "edit_revision":revision,
            "edit_document_sha256":planned["plan"]["edit_document_sha256"],
            "original_world_take_sha256":planned["plan"][
                "original_world_take_sha256"],
            "original_performance_sha256":planned["plan"][
                "original_performance_sha256"],
            "selected_picture_receipts_sha256":summary[
                "source_selected_receipts_sha256"],
            "selected_native_frames":FRAMES,
            "original_pcm_48khz_required":True,
            "destination_dir":str(Path(destination_dir).resolve())}
        if self.approve(director_event,authorization) is not True:
            raise PermissionError(
                "A source chunk render authorization cannot silently approve final movie export")
        output=Path(destination_dir)
        if output.exists() or output.is_symlink():
            raise FileExistsError("Cannot overwrite original film edit output")
        output.mkdir(mode=0o700,parents=True)
        try:
            movie=output/"selected_original_30s_picture.mkv"
            _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
                  "-framerate",str(FPS),"-start_number","0",
                  "-i",str(pictures/"frame_%04d.png"),
                  "-frames:v",str(FRAMES),"-an",
                  "-c:v","ffv1",str(movie)])
            if _decoded_frames(movie,ffprobe)!=FRAMES:
                raise RuntimeError("Native selected picture is not 720 source frames")
            edit=OriginalSelectedViewEdit(
                self.index,verify_director_action=lambda *_:False).verify(
                    pid,edit_id,revision)
            stems=output/"original_source_stems"
            stems.mkdir()
            sound=_read_pcm_mix_from_original(
                self.index,pid,edit["original_world_take_id"],folder=stems)
            master=output/"original_30s_data_first_film_with_sound.mkv"
            _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
                  "-i",str(movie),"-i",sound["mix_file"],
                  "-map","0:v:0","-map","1:a:0",
                  "-c:v","copy","-c:a","pcm_s16le",
                  "-shortest",str(master)])
            streams=_probe(master,ffprobe)["streams"]
            v=[x for x in streams if x["codec_type"]=="video"]
            a=[x for x in streams if x["codec_type"]=="audio"]
            if (len(v)!=1 or len(a)!=1 or
                a[0].get("sample_rate")!="48000" or
                a[0].get("codec_name")!="pcm_s16le" or
                _decoded_frames(master,ffprobe)!=FRAMES):
                raise RuntimeError("Data-first edited movie audio/picture codec mismatch")
            decoded=output/"decoded_audio.raw"
            _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
                  "-i",str(master),"-map","0:a:0",
                  "-ar","48000","-ac","1","-f","s16le",str(decoded)])
            if (decoded.stat().st_size!=SAMPLES*2 or
                file_sha(decoded)!=sound["mix_original_pcm_essence_sha256"]):
                raise RuntimeError("Finished selected-view film altered original PCM")
            decoded.unlink()
            final={
                "format":FILM_FORMAT,
                "edit_document_sha256":planned["plan"]["edit_document_sha256"],
                "original_world_take_sha256":planned["plan"][
                    "original_world_take_sha256"],
                "original_performance_sha256":planned["plan"][
                    "original_performance_sha256"],
                "original_720_source_film_frames":FRAMES,
                "native_selected_frames_verified":FRAMES,
                "native_selected_chunks_verified":CHUNKS,
                "full_camera_rolls_required":False,
                "original_shared_pcm":sound,
                "final_original_picture_audio_sha256":file_sha(master),
                "film_file":master.name,
                "decoded_film_picture_and_pcm_verified":True,
                "director_picture_audio_approval":False}
            (output/"verified_film_receipt.json").write_bytes(canonical(final))
            return final
        except Exception:
            shutil.rmtree(output)
            raise
