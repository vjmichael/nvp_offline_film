"""USD-FILM-01T native NVP desktop bridge methods.

Reuses the current WO5→WO6 pywebview exact-origin authority, 01R native
Blender supervisor/worker thread, and one 01S durable queue. There is no
browser-edit/render HTTP endpoint and no alternate process launcher.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import secrets
import shutil

from backend.nvp_usd_film01r_quality import reviewed_quality
from backend.nvp_usd_film01s_adaptive_batch import BatchPreferences
from backend.nvp_usd_film01t_selected_queue import (
    OriginalSelectedFilmBatch,FORMAT as QUEUE_FORMAT,
    BATCH_FORMAT as GROUP_FORMAT)


class OriginalSelectedFilmDesktopMixin:
    def _film01t_host(self,quality,approve):
        self._native_window()
        worker=self._get_host().supervisor
        workspace=self._wo5_state/"original-selected-film-queues"
        if workspace.is_symlink():
            raise PermissionError("Original source queue may not be symlinked")
        return OriginalSelectedFilmBatch(
            self.index,worker,queue_workspace=workspace,
            verify_director_action=approve,
            # A native job missing explicit independently verified OS
            # descendant custody must stay blocked on restart/retry.
            prove_process_custody=lambda *_:False,
            render_quality=quality)

    def _film01t_prefs(self,request):
        allowed={"project_id","edit_id","revision","render_quality",
                 "shots_per_batch","parallel_worker_limit"}
        if type(request) is not dict or set(request)!=allowed:
            raise PermissionError("Exactly source-edited production queue request")
        self._wo5_project(request["project_id"])
        profile=reviewed_quality(request["render_quality"])
        prefs=BatchPreferences(
            shots_per_batch=request["shots_per_batch"],
            parallel_worker_limit=request["parallel_worker_limit"],
            renderer="cpu",final_worker_ram_mb=profile["max_worker_ram_mb"])
        return profile,prefs

    def _film01t_confirm(self,scope):
        window=self._native_window()
        if (type(scope) is not dict or scope.get("operation") not in {
                "nvp.film01t.enqueue_original_selected_scene.v1",
                "nvp.film01t.approve_exact_original_selected_group.v1",
                "nvp.film01q.conform_original_selected_film.v1"}):
            return False
        original=(scope.get("source_edit_sha256") or
                  scope.get("original_edit_sha256") or
                  scope.get("edit_document_sha256"))
        if type(original) is not str or len(original)!=64:
            return False
        operation=scope["operation"]
        description=(
            "Data-first source-selected film operation.\n"
            "Project: "+str(scope.get("project_id",""))+"\n"
            "Original edit SHA: "+original+"\n"
            "Operation: "+operation+"\n"
            "Quality profile SHA: "+str(scope.get("render_profile_sha256",""))+"\n"
            "Original performance SHA: "+
              str(scope.get("original_performance_sha256",""))+"\n"
            "Source shots (this request): "+
              str(scope.get("bounded_ticket_count",
                  scope.get("selected_chunks","final mux")))+"\n"
            "Only the exact frames/cameras in the fixed source group may run.\n"
            "The original ActorID performance and soundtrack are immutable.\n"
            "NVP remains responsible for resource limits and worker custody.\n"
            "Approve this exact production action?")
        return window.create_confirmation_dialog(
            "NVP — Original Selected-View Film",description) is True

    def film01t_preview_queue(self,request):
        profile,prefs=self._film01t_prefs(request)
        host=self._film01t_host(profile["name"],lambda *_:False)
        planned=host.prepare(
            request["project_id"],request["edit_id"],
            request["revision"],prefs)
        queue=planned["wrapped_queue"]["plan"]
        return {
            "format":"nvp.film01t.original_source_batch_preview.v1",
            "source_edit_sha256":planned["source_edit_sha256"],
            "source_render_plan_sha256":planned["source_render_plan_sha256"],
            "source_performance_sha256":queue["original_performance_sha256"],
            "plan_id":planned["plan_id"],
            "render_quality":profile["name"],
            "render_profile_sha256":planned["profile_sha256"],
            "effective_shots_per_batch":queue["shots_per_batch"],
            "preview_ticket_count":90,"final_native_chunk_count":90,
            "selected_final_source_frames":720,
            "total_real_blender_frames_started":0,
            "full_camera_rolls_not_required":True}

    def film01t_enqueue(self,request):
        profile,prefs=self._film01t_prefs(request)
        grant=object()
        host=self._film01t_host(
            profile["name"],
            lambda event,scope:event is grant and self._film01t_confirm(scope))
        planned=host.prepare(
            request["project_id"],request["edit_id"],request["revision"],prefs)
        status=host.enqueue(planned,director_event=grant)
        return {"format":"nvp.film01t.native_queue_enqueued.v1",
                "plan_id":planned["plan_id"],
                "source_edit_sha256":planned["source_edit_sha256"],
                "queue":status,"native_workers_started":0,
                "old_authorization_reused":False}

    def film01t_status(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","edit_id","revision","render_quality"}:
            raise ValueError("Exact source edit/quality for read-only queue status")
        self._wo5_project(request["project_id"])
        host=self._film01t_host(
            request["render_quality"],lambda *_:False)
        return host.status(
            request["project_id"],request["edit_id"],request["revision"])

    def film01t_advance(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","edit_id","revision","render_quality",
                "max_tickets"}:
            raise ValueError("One bounded next 01S source shot-group request")
        pid=self._wo5_project(request["project_id"])
        profile=reviewed_quality(request["render_quality"])
        token=object()
        host=self._film01t_host(
            profile["name"],lambda event,scope:
                event is token and scope==preflight)
        preflight=host.preview_next_group(
            pid,request["edit_id"],request["revision"],
            max_tickets=request["max_tickets"])
        if preflight.get("format")!=GROUP_FORMAT:
            return preflight
        # OS consent is obtained BEFORE placing anything on the native
        # executor; the executable worker thread never creates an OS dialog.
        if not self._film01t_confirm(preflight):
            return {"format":"nvp.film01t.group_permission_denied.v1",
                    "state":"DENIED","render_workers_started":0}
        with self._film01r_lock:
            if any(not row["future"].done() for row in
                   list(self._film01r_jobs.values())+
                   list(self._film01t_jobs.values())):
                raise RuntimeError("NVP director already has a live source worker")
            if self._film01r_pool is None:
                self._film01r_pool=ThreadPoolExecutor(
                    max_workers=1,thread_name_prefix="NVP 01T selected film batch")
            ticket=secrets.token_urlsafe(24)
            future=self._film01r_pool.submit(
                host.advance_group,pid,request["edit_id"],request["revision"],
                director_event=token,max_tickets=request["max_tickets"])
            self._film01t_jobs[ticket]={
                "future":future,"project_id":pid,"edit_id":request["edit_id"],
                "revision":request["revision"],"quality":profile["name"],
                "edit_sha256":preflight["source_edit_sha256"]}
        return {
            "format":"nvp.film01t.native_group_ticket.v1",
            "state":"QUEUED_APPROVED_NATIVE_GROUP",
            "ticket_id":ticket,"source_edit_sha256":preflight[
                "source_edit_sha256"],
            "source_ticket_count":preflight["bounded_ticket_count"],
            "quality_stage":preflight["quality"],
            "native_blender_workers_max_parallel":1,
            "full_original_camera_rolls_required":False}

    def film01t_poll(self,ticket_id):
        self._native_window()
        if type(ticket_id) is not str or len(ticket_id)>80:
            raise ValueError("Exact source batch ticket required")
        with self._film01r_lock:
            row=self._film01t_jobs.get(ticket_id)
            if row is None:
                raise KeyError("Native source group is unknown")
            future=row["future"]
        result={
            "format":"nvp.film01t.native_group_progress.v1",
            "ticket_id":ticket_id,
            "source_edit_sha256":row["edit_sha256"],
            "quality":row["quality"]}
        if not future.done():
            return {**result,"state":"NATIVE_BATCH_IN_PROGRESS"}
        try:
            outcome=future.result()
        except (OSError,RuntimeError,ValueError,PermissionError,KeyError):
            return {**result,"state":"NATIVE_BATCH_INTERRUPTED_NEEDS_INSPECTION"}
        if (outcome.get("format")!=QUEUE_FORMAT or
            outcome.get("state")!="APPROVED_GROUP_ADVANCED"):
            return {**result,"state":outcome.get("state","NOT_ADMITTED"),
                    "reason":outcome.get("reason"),
                    "queue":outcome.get("queue"),
                    "full_film_claimed_complete":False}
        return {
            **result,"state":outcome["state"],
            "verified_shots_in_group":outcome["verified_shots_in_this_action"],
            "queue":outcome["queue"],
            "full_film_claimed_complete":False}

    def film01t_reconcile(self,request):
        """Only explicit independent receipt/custody verification; no rerun."""
        if type(request) is not dict or set(request)!={
                "project_id","edit_id","revision","render_quality",
                "quality_stage","shot_id"}:
            raise ValueError("Exact original interrupted source ticket required")
        self._wo5_project(request["project_id"])
        host=self._film01t_host(request["render_quality"],lambda *_:False)
        return host.reconcile_original_result(
            request["project_id"],request["edit_id"],request["revision"],
            quality=request["quality_stage"],shot_id=request["shot_id"])

    def film01t_conform(self,request):
        """Create verified 30-second picture+original PCM once all 90 passed.

        Entire original source and chosen output names are NVP-owned. No
        browser file path, FFmpeg executable or renderer script is accepted.
        """
        if type(request) is not dict or set(request)!={
                "project_id","edit_id","revision","render_quality"}:
            raise ValueError("Bounded approved source movie export request")
        pid=self._wo5_project(request["project_id"])
        grant=object()
        host=self._film01t_host(
            request["render_quality"],
            lambda event,scope:event is grant and self._film01t_confirm(scope))
        attempts=host.finished_source_frames(
            pid,request["edit_id"],request["revision"])
        _,_,wrapped,plan_id=host._current(
            pid,request["edit_id"],request["revision"])
        path=self._wo5_state/"original-selected-film-masters"/plan_id
        pictures=path/"verified_source_pictures"
        film=path/"film_with_original_pcm"
        for part in (self._wo5_state,path):
            if part.is_symlink():
                raise PermissionError("Source film output folder cannot be symlinked")
        if film.exists() or film.is_symlink():
            raise FileExistsError("Do not overwrite a previous verified film master")
        # A previous director refusal may have left a checked gathered
        # picture directory; 01T will independently reverify it before
        # encoding rather than silently overwriting an original frame.
        executable=shutil.which("ffmpeg")
        inspector=shutil.which("ffprobe")
        if not executable or not inspector:
            raise RuntimeError("Local installed FFmpeg/FFprobe are unavailable")
        report=host.conform(
            pid,request["edit_id"],request["revision"],
            pictures_dir=pictures,destination_dir=film,
            ffmpeg=executable,ffprobe=inspector,director_event=grant)
        return {
            "format":"nvp.film01t.native_verified_original_film.v1",
            "plan_id":plan_id,"source_edit_sha256":wrapped["plan"][
                "edit_document_sha256"],
            "finished_film_file_sha256":report[
                "final_original_picture_audio_sha256"],
            "original_pcm_verified":report[
                "decoded_film_picture_and_pcm_verified"],
            "verified_selected_frames":report[
                "native_selected_frames_verified"],
            "verified_chunk_count":len(attempts),
            "director_creative_approval":False,
            "native_master_immutable":True}
