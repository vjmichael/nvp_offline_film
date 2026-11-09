"""USD-FILM-01T: durable 01S queue + original 01Q selected-frame renderer.

Never manufacture the missing 720 pixels. The immutable FilmIndex edit
selects each real camera view. A single bounded batch approval covers exact
ordered 8-frame tickets; each native tool operation receives fresh,
single-consumption, host-only authorization derived from that one scope.
Source frames are evaluated from actual OpenUSD at low-fi stage and genuine
Blender/Cycles 01Q receipts are checked independently at hi-fi stage.

One source performance, 90 unique selected native chunks, 720 frames,
one original 48kHz PCM soundtrack. On restart interrupted claims block;
only independently verified native outcomes may be reconciled.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import math

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_resource_guard import collect_resources
from backend.nvp_usd_film01q_selected_view_host import (
    ReviewedSelectedViewFilm,chunk_job_id,CHUNK,CHUNKS,FRAMES,AUDIT)
from backend.nvp_usd_film01q_selected_view_edit import edit_sha
from backend.nvp_usd_film01s_adaptive_batch import (
    Shot,BatchPreferences,DurableShotBatchQueue,PREVIEW,FINAL)
from backend.nvp_usd_film01s_resource_service import NVPAdaptiveShotService
from backend.nvp_usd_film01r_quality import reviewed_quality
from backend.nvp_usd_film01o_original_camera_roll_source import (
    STAGE,MANIFEST,canonical,file_sha)

FORMAT="nvp.usd_film01t.original_selected_durable_queue.v1"
BATCH_FORMAT="nvp.usd_film01t.authorize_exact_source_chunk_group.v1"


def _identity(pid,edit_id,revision,plan):
    body={
        "project_id":pid,"edit_id":edit_id,"revision":revision,
        "original_performance_sha256":plan["original_performance_sha256"],
        "original_usd_sha256":plan["original_usd_sha256"],
        "edit_document_sha256":plan["edit_document_sha256"],
        "render_profile_sha256":plan["render_profile_sha256"],
        # Include the entire exact 720-frame selected-camera render plan,
        # not only its source IDs: changes in native source evaluation,
        # view-cache algorithm or framing create a NEW durable queue.
        "selected_frame_plan_sha256":edit_sha(plan)}
    return "FilmT_"+edit_sha(body)[:48]


def _shot(start):
    if type(start) is not int or start not in range(0,FRAMES,CHUNK):
        raise ValueError("Exactly 90 eight-frame original selected-view shots")
    return Shot(f"Source_{start:04d}", "SelectedOriginalView",
                start,start+CHUNK)


class OriginalSelectedFilmBatch:
    def __init__(self,index:FilmIndex,supervisor:BlenderWorkerSupervisor,
                 *,queue_workspace,verify_director_action,
                 prove_process_custody,
                 render_quality="technical_smoke",
                 collect_host_resources=collect_resources):
        if (not isinstance(index,FilmIndex) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not callable(verify_director_action) or
            not callable(prove_process_custody)):
            raise TypeError("Only source-authoritative FilmIndex and native OS broker")
        self.index=index
        self.supervisor=supervisor
        self.approve=verify_director_action
        self.custody=prove_process_custody
        self.profile=reviewed_quality(render_quality)
        self.film=ReviewedSelectedViewFilm(
            index,supervisor,
            verify_director_action=lambda *_:False,
            prove_process_custody=prove_process_custody,
            render_quality=render_quality)
        self.queue=DurableShotBatchQueue(queue_workspace)
        self.service=NVPAdaptiveShotService(
            supervisor,self.queue,collect_host_resources=collect_host_resources)
        self._resources=collect_host_resources

    def _current(self,pid,edit_id,revision):
        _require_pid(pid)
        _id(edit_id,"original source edit")
        source_dir,source,wrapped=self.film.source_plan(
            pid,edit_id,revision)
        plan=wrapped["plan"]
        if (plan["selected_final_frame_count"]!=720 or
            len(plan["frames"])!=720 or len(plan["chunks"])!=90 or
            plan["render_profile"]!=self.profile):
            raise RuntimeError("Only a source verified 720-frame original selected edit")
        return source_dir,source,wrapped,_identity(pid,edit_id,revision,plan)

    def prepare(self,pid,edit_id,revision,preferences):
        if not isinstance(preferences,BatchPreferences):
            raise TypeError("Typed director group and worker preference required")
        if (preferences.renderer!="cpu" or
            preferences.final_worker_ram_mb!=self.profile["max_worker_ram_mb"]):
            raise PermissionError("Queue RAM/GPU promise must match reviewed Cycles job")
        source_dir,source,wrapped,plan_id=self._current(pid,edit_id,revision)
        jobs=[_shot(i) for i in range(0,FRAMES,CHUNK)]
        planned=self.service.prepare(
            plan_id,wrapped["plan"]["original_performance_sha256"],
            jobs,preferences)
        if (len(planned["plan"]["source_shots"])!=CHUNKS or
            len(planned["plan"]["selected_final_shot_ids"])!=CHUNKS):
            raise RuntimeError("Cannot queue fewer than 90 original selected chunks")
        return {"format":FORMAT,
                "project_id":pid,"edit_id":edit_id,"edit_revision":revision,
                "source_edit_sha256":wrapped["plan"]["edit_document_sha256"],
                "source_render_plan_sha256":wrapped["plan_sha256"],
                "profile_sha256":wrapped["plan"]["render_profile_sha256"],
                "original_usd_sha256":wrapped["plan"]["original_usd_sha256"],
                "plan_id":plan_id,"wrapped_queue":planned,
                "expected_selected_frames":FRAMES,
                "original_camera_rolls_not_required":True,
                "renderer_started":False}

    def enqueue(self,prepared,*,director_event):
        if (type(prepared) is not dict or
            prepared.get("format")!=FORMAT or
            prepared.get("renderer_started") is not False):
            raise ValueError("One immutable original selected source queue preview")
        pid=prepared["project_id"]
        _,_,wrapped,current_id=self._current(
            pid,prepared["edit_id"],prepared["edit_revision"])
        if (current_id!=prepared["plan_id"] or
            wrapped["plan_sha256"]!=prepared["source_render_plan_sha256"] or
            wrapped["plan"]["edit_document_sha256"]!=prepared["source_edit_sha256"] or
            wrapped["plan"]["original_usd_sha256"]!=prepared["original_usd_sha256"] or
            wrapped["plan"]["render_profile_sha256"]!=prepared["profile_sha256"]):
            raise PermissionError("Director's edited source/profiles changed before enqueue")
        plan=prepared["wrapped_queue"]
        if (plan["plan"]["plan_id"]!=current_id or
            plan["plan"]["original_performance_sha256"]!=wrapped["plan"][
                "original_performance_sha256"] or
            plan["plan"]["source_shots"]!=[
                {"shot_id":_shot(i).shot_id,"camera_id":"SelectedOriginalView",
                 "source_in_frame":i,"source_out_frame":i+CHUNK}
                for i in range(0,FRAMES,CHUNK)]):
            raise PermissionError("Original selected edit ticket inventory was changed")
        approval_scope={
            "operation":"nvp.film01t.enqueue_original_selected_scene.v1",
            "project_id":pid,"edit_id":prepared["edit_id"],
            "edit_revision":prepared["edit_revision"],
            "original_edit_sha256":prepared["source_edit_sha256"],
            "source_render_plan_sha256":prepared["source_render_plan_sha256"],
            "render_profile_sha256":prepared["profile_sha256"],
            "plan_id":current_id,"queue_sha256":plan["plan_sha256"],
            "selected_frames":720,"selected_chunks":90,
            "original_camera_rolls_required":False}
        if self.approve(director_event,approval_scope) is not True:
            raise PermissionError("Explicit source-locked queue consent required")
        # This secondary 01S authorization is host-issued from the single
        # exact enqueue consent above, not a browser-supplied bypass.
        guard=object()
        used=set()
        def checked(event,scope):
            if (event is not guard or used or
                scope.get("operation")!="nvp.film01s.enqueue_virtual_shot_batches.v1" or
                scope.get("plan_id")!=current_id or
                scope.get("plan_sha256")!=plan["plan_sha256"] or
                scope.get("source_performance_sha256")!=wrapped["plan"][
                    "original_performance_sha256"]):
                return False
            used.add("enqueue")
            return True
        return self.queue.enqueue(plan,director_event=guard,authorize=checked)

    def _assert_saved(self,pid,edit_id,revision):
        _,source,wrapped,identity=self._current(pid,edit_id,revision)
        manifest=self.queue._load(identity)
        if (manifest["plan_id"]!=identity or
            manifest["original_performance_sha256"]!=wrapped["plan"][
                "original_performance_sha256"] or
            manifest["selected_final_shot_ids"]!=[
                _shot(i).shot_id for i in range(0,FRAMES,CHUNK)] or
            manifest["source_shots"]!=[
                {"shot_id":_shot(i).shot_id,
                 "camera_id":"SelectedOriginalView",
                 "source_in_frame":i,"source_out_frame":i+CHUNK}
                for i in range(0,FRAMES,CHUNK)]):
            raise RuntimeError("Persisted group does not belong to selected editor revision")
        return wrapped,identity,manifest

    def status(self,pid,edit_id,revision):
        wrapped,identity,manifest=self._assert_saved(pid,edit_id,revision)
        result=self.queue.status(identity)
        return {"format":FORMAT,"edit_id":edit_id,
                "source_edit_sha256":wrapped["plan"]["edit_document_sha256"],
                "render_plan_sha256":wrapped["plan_sha256"],
                "render_profile":self.profile["name"],
                "original_performance_sha256":wrapped["plan"][
                    "original_performance_sha256"],
                "camera_rolls_required":False,
                "picture_frames_expected":720,
                "native_selected_chunks_required":90,
                "queue":result,"production_movie_complete":False,
                "nvp_authorization_per_group_and_step":True}

    def recover_interrupted(self,pid,edit_id,revision):
        """After app restart, claims do not become silently runnable again."""
        _,identity,_=self._assert_saved(pid,edit_id,revision)
        # Native OS supervisor still owns verifying that descendants stopped.
        return self.queue.recover_interrupted(identity)

    def _verify_original_evaluation(self,source_dir,source,wrapped,start):
        """Read actual native USD at eight original film timestamps, not CGI."""
        from pxr import Usd,UsdGeom
        stage_file=source_dir/STAGE
        if (stage_file.is_symlink() or
            file_sha(stage_file)!=wrapped["plan"]["original_usd_sha256"]):
            raise RuntimeError("Original USD input altered before geometry evaluation")
        stage=Usd.Stage.Open(str(stage_file))
        if not stage:
            raise RuntimeError("Native source USD stage cannot open")
        originals=source.get("original_frame_evidence")
        if type(originals) is not list or len(originals)!=720:
            raise PermissionError("Original source world lacks frame evidence")
        observed=[]
        for i in range(start,start+CHUNK):
            row=originals[i]
            chosen=wrapped["plan"]["frames"][i]
            if (row["frame"]!=i or
                row["original_film_tick"]!=chosen["original_film_tick"] or
                row["original_actor_state_sha256"]!=chosen[
                    "original_actor_state_sha256"]):
                raise RuntimeError("Native source Film Time mismatch")
            time=Usd.TimeCode(float(i+1))
            for entry in row["original_actor_positions"]+[
                x for x in row["original_camera_positions"]
                if x["camera_id"]==chosen["camera_id"]]:
                prim=stage.GetPrimAtPath(entry["source_prim"])
                if not prim or not prim.IsDefined():
                    raise RuntimeError("Original source actor/camera prim disappeared")
                matrix=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(time)
                pos=matrix.ExtractTranslation()
                if any(not math.isfinite(float(pos[j])) or
                    abs(float(pos[j])-entry["position_m"][j])>0.02
                    for j in range(3)):
                    raise RuntimeError("Actual USD actor/camera motion no longer matches original")
            observed.append({
                "source_frame":i,
                "film_tick":chosen["original_film_tick"],
                "actor_state_sha256":chosen["original_actor_state_sha256"],
                "camera_id":chosen["camera_id"],
                "view_cache_sha256":chosen["view_cache_sha256"]})
        return sha256(canonical({
            "source_usd_sha256":file_sha(stage_file),
            "source_render_plan_sha256":wrapped["plan_sha256"],
            "source_verified_original_viewpoint_frames":observed})).hexdigest()

    def _verify_final_native_receipt(self,source_dir,source,wrapped,start,attempt):
        plan=wrapped["plan"]
        job_id=chunk_job_id(
            plan["edit_document_sha256"],start,attempt,
            plan["render_profile_sha256"])
        reverified=self.film._verify_completed(
            job_id,source_dir,source,wrapped,start,attempt)
        if (reverified["state"]!="REVERIFIED_NATIVE_SELECTED_FRAMES" or
            reverified["native_selected_views_rendered"]!=CHUNK):
            raise RuntimeError("Native Cycles source result was not reverified")
        receipt_file=self.supervisor.root/job_id/AUDIT
        return file_sha(receipt_file),job_id

    def preview_next_group(self,pid,edit_id,revision,*,max_tickets=None):
        """Read-only exact bounded group preview for OS approval."""
        source_dir,source,wrapped,identity=self._current(
            pid,edit_id,revision)
        _,_,manifest=self._assert_saved(pid,edit_id,revision)
        candidate=self.service.suggest_next(identity)
        if candidate["state"]!="READY_FOR_NVP_AUTHORIZATION":
            return {"format":FORMAT,"state":candidate["state"],
                    "reason":candidate.get("reason"),
                    "source_edit_sha256":wrapped["plan"]["edit_document_sha256"],
                    "queue":self.queue.status(identity)}
        ticket=candidate["ticket"]
        group=ticket["batch_index"]
        quality=ticket["quality"]
        width=manifest["shots_per_batch"]
        count=width if max_tickets is None else max_tickets
        if type(count) is not int or not 1<=count<=width:
            raise ValueError("A director may request at most one approved group")
        state=self.queue.status(identity)
        planned=[x for x in state["shot_tickets"] if
                 x["quality"]==quality and x["batch_index"]==group and
                 x["state"]=="QUEUED"][:count]
        if not planned:
            raise RuntimeError("Group selected with no original source tickets")
        exact=[]
        for item in planned:
            start=int(item["shot_id"].split("_")[1])
            chunk=wrapped["plan"]["chunks"][start//CHUNK]
            exact.append({
                "shot_id":item["shot_id"],
                "start_frame":start,"frame_count":CHUNK,
                "source_frames_sha256":chunk["source_frames_sha256"],
                "original_camera_ids":chunk["camera_ids"],
                "ticket_sha256":item["ticket_sha256"],
                "attempt":item["attempt"]+1})
        scope={
            "format":BATCH_FORMAT,
            "operation":"nvp.film01t.approve_exact_original_selected_group.v1",
            "project_id":pid,"edit_id":edit_id,"revision":revision,
            "source_edit_sha256":wrapped["plan"]["edit_document_sha256"],
            "source_render_plan_sha256":wrapped["plan_sha256"],
            "render_profile_sha256":wrapped["plan"]["render_profile_sha256"],
            "original_performance_sha256":wrapped["plan"][
                "original_performance_sha256"],
            "queue_plan_id":identity,
            "queue_manifest_sha256":sha256(canonical(manifest)).hexdigest(),
            "quality":quality,"batch_index":group,
            "bounded_ticket_count":len(exact),
            "exact_source_tickets":exact,
            "full_camera_rolls_requested":False}
        return scope

    def advance_group(self,pid,edit_id,revision,*,director_event,
                      max_tickets=None):
        """Run one OS-approved group; no cross-stage or cross-edit grants."""
        scope=self.preview_next_group(
            pid,edit_id,revision,max_tickets=max_tickets)
        if scope.get("format")!=BATCH_FORMAT:
            return scope
        source_dir,source,wrapped,identity=self._current(
            pid,edit_id,revision)
        quality=scope["quality"]
        group=scope["batch_index"]
        exact=scope["exact_source_tickets"]
        if self.approve(director_event,scope) is not True:
            raise PermissionError("Director refused exact source-shot group")
        results=[]
        for item in exact:
            start=item["start_frame"]
            ticket_id=item["shot_id"]
            if self.service.suggest_next(identity).get("ticket",{}).get(
                    "shot_id")!=ticket_id:
                # A different queued item, interruption or hardware change
                # invalidates this batch rather than silently skipping work.
                break
            fresh=object()
            used=set()
            def authorize_step(event,step):
                if event is not fresh or step.get("attempt")!=item["attempt"]:
                    return False
                operation=step.get("operation")
                if operation=="nvp.film01s.claim_one_source_shot.v1":
                    if ("queue" in used or step.get("plan_id")!=identity or
                        step.get("quality")!=quality or
                        step.get("shot_id")!=ticket_id or
                        step.get("shot_sha256")!=item["ticket_sha256"] or
                        step.get("original_performance_sha256")!=scope[
                            "original_performance_sha256"]):
                        return False
                    used.add("queue")
                    return True
                if operation=="nvp.render.usd_film01q_selected_source_chunk.v1":
                    if (quality!=FINAL or "native" in used or
                        step.get("edit_sha256")!=scope["source_edit_sha256"] or
                        step.get("start_frame")!=start or
                        step.get("frame_count")!=CHUNK or
                        step.get("selected_source_frames_sha256")!=item[
                            "source_frames_sha256"] or
                        step.get("render_profile_sha256")!=scope[
                            "render_profile_sha256"] or
                        step.get("original_performance_sha256")!=scope[
                            "original_performance_sha256"]):
                        return False
                    used.add("native")
                    return True
                return False
            claim=self.service.claim_next(
                identity,director_event=fresh,
                authorize=authorize_step,
                prove_prior_worker_stopped=lambda p,q,s,a:
                    self.custody(p,q,s,a) is True)
            if not claim.get("admitted"):
                results.append({"shot_id":ticket_id,
                                "state":claim.get("state","NOT_ADMITTED"),
                                "reason":claim.get("reason")})
                break
            try:
                if quality==PREVIEW:
                    receipt=self._verify_original_evaluation(
                        source_dir,source,wrapped,start)
                    native_id=None
                else:
                    # The 01Q broker receives a *new* step-specific,
                    # single-use host grant derived from the creator's exact
                    # group approval. The read-only verification host must
                    # never silently acquire render authority.
                    native=ReviewedSelectedViewFilm(
                        self.index,self.supervisor,
                        verify_director_action=authorize_step,
                        prove_process_custody=self.custody,
                        render_quality=self.profile["name"])
                    rendered=native.run_chunk(
                        pid,edit_id,revision=revision,
                        start=start,attempt=claim["attempt"],
                        director_event=fresh)
                    if rendered["start_frame"]!=start:
                        raise RuntimeError("Native source-selected renderer returned wrong source time")
                    receipt,native_id=self._verify_final_native_receipt(
                        source_dir,source,wrapped,start,claim["attempt"])
                def independent(check):
                    if (check.get("plan_id")!=identity or
                        check.get("shot_id")!=ticket_id or
                        check.get("quality")!=quality or
                        check.get("attempt")!=claim["attempt"] or
                        check.get("native_receipt_sha256")!=receipt):
                        return False
                    try:
                        if quality==PREVIEW:
                            return self._verify_original_evaluation(
                                source_dir,source,wrapped,start)==receipt
                        actual,_=self._verify_final_native_receipt(
                            source_dir,source,wrapped,start,claim["attempt"])
                        return actual==receipt
                    except (OSError,ValueError,RuntimeError,PermissionError):
                        return False
                self.queue.finish(identity,quality=quality,
                    shot_id=ticket_id,attempt=claim["attempt"],
                    verified_receipt_sha256=receipt,
                    verify_native_renderer_result=independent)
                results.append({"shot_id":ticket_id,"quality":quality,
                                "state":"INDEPENDENTLY_VERIFIED",
                                "start_frame":start,
                                "receipt_sha256":receipt,
                                "native_worker_job_id":native_id})
            except Exception:
                # A native failure is not a successful film shot. Keeping
                # FAILED in FULL-sync SQLite ensures restart cannot replay.
                self.queue.fail(identity,quality=quality,
                    shot_id=ticket_id,attempt=claim["attempt"])
                raise
        status=self.queue.status(identity)
        return {
            "format":FORMAT,"state":"APPROVED_GROUP_ADVANCED",
            "source_edit_sha256":wrapped["plan"]["edit_document_sha256"],
            "quality":quality,"batch_index":group,
            "authorized_shots":len(exact),
            "verified_shots_in_this_action":len([
                x for x in results if x["state"]=="INDEPENDENTLY_VERIFIED"]),
            "results":results,
            "queue":status,
            "full_720_frame_film_completed":False}

    def reconcile_original_result(self,pid,edit_id,revision,*,quality,shot_id):
        """After restart, adopt a real terminal native receipt, never rerun it."""
        source_dir,source,wrapped,identity=self._current(pid,edit_id,revision)
        _,_,_=self._assert_saved(pid,edit_id,revision)
        state=self.queue.status(identity)
        row=next((x for x in state["shot_tickets"]
                  if x["quality"]==quality and x["shot_id"]==shot_id),None)
        if row is None or row["state"] not in ("RUNNING","INTERRUPTED","FAILED"):
            raise PermissionError("No exact source ticket awaiting reconciliation")
        attempt=row["attempt"]
        start=int(shot_id.split("_")[1])
        if start not in range(0,FRAMES,CHUNK):
            raise ValueError("Corrupt original frame window")
        if quality==PREVIEW:
            # No native process is launched for original OpenUSD source
            # frame evaluation. It can be independently redone, not replayed.
            receipt=self._verify_original_evaluation(
                source_dir,source,wrapped,start)
        elif quality==FINAL:
            receipt,_=self._verify_final_native_receipt(
                source_dir,source,wrapped,start,attempt)
        else:
            raise ValueError("Unknown source quality ticket")
        def stopped(context):
            if (context["plan_id"]!=identity or
                context["shot_id"]!=shot_id or
                context["attempt"]!=attempt):
                return False
            if quality==PREVIEW:
                return True
            return self.custody(identity,quality,shot_id,attempt) is True
        def independently_verified(context):
            if (context["native_receipt_sha256"]!=receipt or
                context["source_performance_sha256"]!=wrapped["plan"][
                    "original_performance_sha256"] or
                context["ticket_sha256"]!=row["ticket_sha256"]):
                return False
            try:
                if quality==PREVIEW:
                    return self._verify_original_evaluation(
                        source_dir,source,wrapped,start)==receipt
                actual,_=self._verify_final_native_receipt(
                    source_dir,source,wrapped,start,attempt)
                return actual==receipt
            except (RuntimeError,ValueError,KeyError,OSError,PermissionError):
                return False
        self.queue.reconcile_verified_completed(
            identity,quality=quality,shot_id=shot_id,attempt=attempt,
            verified_receipt_sha256=receipt,
            prove_native_worker_stopped=stopped,
            verify_original_source_outcome=independently_verified)
        return {"format":FORMAT,"state":"RECONCILED_INDEPENDENTLY_VERIFIED",
                "plan_id":identity,"quality":quality,"shot_id":shot_id,
                "attempt":attempt,"receipt_sha256":receipt,
                "old_permission_replayed":False}

    def finished_source_frames(self,pid,edit_id,revision):
        wrapped,identity,_=self._assert_saved(pid,edit_id,revision)
        state=self.queue.status(identity)
        final=[x for x in state["shot_tickets"] if x["quality"]==FINAL]
        if len(final)!=CHUNKS or any(x["state"]!="SUCCEEDED" for x in final):
            raise RuntimeError("Cannot assemble 30s film until 90 native Cycles chunks pass")
        source_dir,source,wrapped,_=self._current(pid,edit_id,revision)
        attempts={}
        for item in final:
            start=int(item["shot_id"].split("_")[1])
            actual,_=self._verify_final_native_receipt(
                source_dir,source,wrapped,start,item["attempt"])
            if actual!=item["receipt_sha256"]:
                raise RuntimeError("Queued native 30-second source changed since acceptance")
            attempts[start]=item["attempt"]
        return attempts

    def conform(self,pid,edit_id,revision,*,pictures_dir,destination_dir,
                ffmpeg,ffprobe,director_event):
        attempts=self.finished_source_frames(pid,edit_id,revision)
        pictures=Path(pictures_dir)
        if pictures.exists():
            # A creator may deny the final export after verified PNG
            # gathering. On a later attempt do not overwrite 720 images.
            # Verify all immutable source picture bytes and receipt again.
            receipt_file=pictures/"gather_receipt.json"
            manifest_file=pictures/"source_selected_receipts.json"
            if (pictures.is_symlink() or receipt_file.is_symlink() or
                manifest_file.is_symlink() or not receipt_file.is_file() or
                not manifest_file.is_file()):
                raise PermissionError("Unverified prior source-selected gather")
            summary=json.loads(receipt_file.read_text("utf8"))
            _,_,planned,_=self._current(pid,edit_id,revision)
            if (summary.get("format")!=
                    "nvp.usd_film01q.gathered_source_selected_720frames.v1" or
                summary.get("edit_sha256")!=planned["plan"][
                    "edit_document_sha256"] or
                summary.get("render_profile_sha256")!=planned["plan"][
                    "render_profile_sha256"] or
                summary.get("native_verified_frames")!=720 or
                summary.get("source_selected_receipts_sha256")!=
                    file_sha(manifest_file)):
                raise RuntimeError("Existing gathered original picture bytes changed")
        else:
            self.film.gather(pid,edit_id,revision=revision,
                             output_directory=pictures_dir,
                             approved_attempts=attempts)
        # Film/conform has a separate exact native OS confirmation in
        # the original 01Q host (this coordinator does not bypass it).
        self.film.approve=self.approve
        return self.film.conform_edited_film(
            pid,edit_id,revision=revision,
            pictures_dir=pictures_dir,destination_dir=destination_dir,
            ffmpeg=ffmpeg,ffprobe=ffprobe,director_event=director_event)
