"""WO5 installed desktop director review IPC; NO HTTP or browser approvals.

This is a pywebview js_api subclass of NVP's existing trusted desktop bridge.
No independent worker, alternate scene viewer or production supervisor is
created. Actual OpenUSD sound/picture audition reuses data_av_* on this bridge.
The finished DCP's independently decoded video+sound playback is NOT yet
implemented by this desktop feature.
"""
from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os
import secrets
import threading
import json

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_usd_film01t_desktop_mixin import OriginalSelectedFilmDesktopMixin
from backend.nvp_usd_film02m_f_desktop_mixin import OriginalDistrictDesktopMixin
from backend.nvp_wo4_feature_journal import FeatureJournal, ASSEMBLY_FORMAT
from backend.nvp_wo5_original_feature import inspect_original_feature_readiness
from backend.nvp_wo5_director_review import (
    INTENT_FORMAT, REVIEW_FORMAT,
    register_director_intent, record_director_review)

FORMAT = "nvp.wo5.trusted_desktop_director_review.v1"
MAX_CATALOG = 256


class TrustedDesktopWO5Bridge(OriginalDistrictDesktopMixin,OriginalSelectedFilmDesktopMixin,TrustedDesktopCameraBridge):
    """Use the actual OS-confirmed WebView2 bridge; not FastAPI routes."""

    def __init__(self, index: FilmIndex, *, origin, production_root=None,
                 host_factory=None, finished_codec_provider=None):
        super().__init__(index, origin=origin, host_factory=host_factory)
        if production_root is None:
            home = Path(os.environ.get("NVP_HOME", str(
                Path(index.studio.db_path).parent)))
            production_root = home / ".native-production-runtime"
        root = Path(production_root)
        if not root.is_absolute() or root.is_symlink():
            raise PermissionError("Host-owned native production state root required")
        self._wo5_state = root.resolve()
        self._wo5_journal = None
        self._finished_codec_provider = finished_codec_provider
        self._finished_player = None
        # Same trusted installed native WebView; source-linked 01R editor
        # never creates a browser-side privileged write/render endpoint.
        self._film01r_lock = threading.RLock()
        self._film01r_jobs = {}
        self._film01t_jobs = {}
        self._film01r_pool = None

    def _wo5_project(self, project_id):
        self._native_window()  # exact current first-party pywebview origin
        _require_pid(project_id)
        self.index.studio.get_project(project_id)
        return project_id

    def _wo5_journal_for_review(self):
        self._native_window()
        if self._wo5_journal is None:
            # Identical durable FeatureJournal backing store used by
            # NativeProductionHost, never an alternate job/supervisor.
            self._wo5_journal = FeatureJournal(self._wo5_state)
        return self._wo5_journal

    def _wo5_approve(self, scope):
        """Native OS confirmation, over the EXACT source-hashed operation."""
        if type(scope) is not dict:
            return False
        allowed = {
            "nvp.wo5.creator_confirm_director_intent.v1",
            "nvp.wo5.creator_confirm_film_observations.v1",
        }
        if scope.get("operation") not in allowed:
            return False
        message = (
            "Director-only immutable film review record.\n"
            "Operation: " + scope["operation"] + "\n"
            "Film project: " + str(scope.get("project_id", "")) + "\n"
            "Original FilmIndex source SHA: " +
                str(scope.get("assembly_sha256") or
                    scope.get("feature_filmindex_sha256") or "") + "\n"
            "Review/intent SHA: " + str(scope.get("intent_shots_sha256") or
                                      scope.get("observations_sha256") or "") +
            "\nNo worker, exported film or original Take will be modified.\n"
            "Your report is NOT theatrical certification or AI approval.\n"
            "Approve this exact operation?")
        return self._native_window().create_confirmation_dialog(
            "NVP — Approve Director Review", message) is True

    def wo5_review_catalog(self, project_id):
        """Return safe, project-bound durable feature/edit/intent/review metadata."""
        self._wo5_project(project_id)
        index = self.index
        assemblies, intents, reviews = [], [], []
        for kind in ("edit", "presentation"):
            for entry in index.list_objects(project_id, kind=kind)[:MAX_CATALOG]:
                object_id = entry["object_id"]
                revision = entry["head_revision"]
                record = index.read_revision(project_id, object_id, revision)
                data = record["data"]
                fmt = data.get("format")
                if fmt == ASSEMBLY_FORMAT:
                    assemblies.append({
                        "assembly_id": object_id,
                        "assembly_revision": revision,
                        "assembly_sha256": record["document_sha256"],
                        "end_tick": data.get("end_tick"),
                        "reel_count": len(data.get("ordered_reel_job_ids", [])),
                    })
                elif fmt == INTENT_FORMAT:
                    intents.append({
                        "intent_id": object_id,
                        "source_assembly_id": data["source_assembly_id"],
                        "source_assembly_revision": data["source_assembly_revision"],
                        "source_assembly_sha256": data["source_assembly_sha256"],
                        "shot_count": len(data["shots"]),
                        "intent_sha256": record["document_sha256"],
                    })
                elif fmt == REVIEW_FORMAT:
                    reviews.append({
                        "review_id": object_id,
                        "source_director_intent_id": data["source_director_intent_id"],
                        "original_feature_id": data["original_feature_id"],
                        "director_requests_revisions": data["director_requests_revisions"],
                        "production_acceptance": False,
                    })
        journal = self._wo5_journal_for_review()
        with journal._read() as db:
            entries = [dict(row) for row in db.execute(
                """SELECT feature_id,assembly_id,assembly_revision,
                   assembly_sha256,project_id,state,updated_at FROM
                   production_features WHERE project_id=?
                   ORDER BY created_at DESC LIMIT ?""",
                (project_id, MAX_CATALOG))]
        features = [{
            "feature_id": r["feature_id"],
            "assembly_id": r["assembly_id"],
            "assembly_revision": r["assembly_revision"],
            "assembly_sha256": r["assembly_sha256"],
            "state": r["state"],
            "updated_at": r["updated_at"],
            "production_accepted": False,
        } for r in entries]
        return {
            "format": FORMAT, "status": "NATIVE_PROJECT_SCOPED_READ_ONLY",
            "project_id": project_id, "assemblies": assemblies,
            "features": features, "director_intents": intents,
            "director_reviews": reviews,
            "native_source_preview_available": True,
            "full_finished_dcp_playback_verified": False,
            "smpte_bv21_validated": False,
            "production_accepted": False,
            "host_native_only": True, "source_paths_exposed": False,
        }

    def wo5_review_read_intent(self, project_id, intent_id):
        self._wo5_project(project_id)
        _id(intent_id, "director intent")
        record = self.index.read_revision(project_id, intent_id, 1)
        if record["kind"] != "presentation" or (
                record["data"].get("format") != INTENT_FORMAT):
            raise PermissionError("Only the exact frozen creator intent may be read")
        return {"format": INTENT_FORMAT, "intent_id": intent_id,
                "intent_sha256": record["document_sha256"],
                "data": record["data"], "source_paths_exposed": False}

    def wo5_review_save_intent(self, payload):
        self._native_window()
        required = {"project_id", "assembly_id", "assembly_revision",
                    "intent_id", "shots"}
        if type(payload) is not dict or set(payload) != required:
            raise PermissionError("Exactly scoped creator intent request required")
        self._wo5_project(payload["project_id"])
        return register_director_intent(
            self.index, payload["project_id"],
            assembly_id=payload["assembly_id"],
            assembly_revision=payload["assembly_revision"],
            intent_id=payload["intent_id"], shots=payload["shots"],
            approve=self._wo5_approve)

    def wo5_review_inspect_feature(self, project_id, feature_id):
        """A real, possibly slow native hash audit. Never mark film passed."""
        self._wo5_project(project_id)
        return inspect_original_feature_readiness(
            self.index, self._wo5_journal_for_review(),
            project_id, feature_id)

    def wo5_review_save_observations(self, payload):
        self._native_window()
        required = {"project_id", "feature_id", "intent_id", "review_id",
                    "observations", "watched_entire_film",
                    "heard_entire_sound"}
        if type(payload) is not dict or set(payload) != required:
            raise PermissionError("Exactly scoped native film review request required")
        self._wo5_project(payload["project_id"])
        return record_director_review(
            self.index, self._wo5_journal_for_review(),
            payload["project_id"], feature_id=payload["feature_id"],
            intent_id=payload["intent_id"], review_id=payload["review_id"],
            observations=payload["observations"],
            watched_entire_film=payload["watched_entire_film"],
            heard_entire_sound=payload["heard_entire_sound"],
            approve=self._wo5_approve)


    def wo5_film_capabilities(self):
        """Desktop only; native binaries must be verified by installed host."""
        self._native_window()
        return {
            "format":"nvp.wo5.finished_dcp_pcm24_picture_review.v1",
            "native_finished_mxf_decode_configured":
                callable(self._finished_codec_provider),
            "FFmpeg_used":False,
            "source_take_only":False,
            "finished_picture_and_sound_from_published_mxf":True,
            "actual_sustained_24fps_verified":False,
            "installed_codec_bundle_verified":
                self._finished_player is not None,
            "production_accepted":False,
        }

    def _wo5_finished(self):
        self._native_window()
        if self._finished_player is None:
            if not callable(self._finished_codec_provider):
                raise RuntimeError(
                    "Native finished-DCP viewer requires installed, build-SHA-pinned "
                    "OpenJPEG/asdcplib codec bundle; no fallback to FFmpeg")
            from backend.nvp_wo5_finished_playback import FinishedFilmPlayer
            unwrap,decoder=self._finished_codec_provider()
            self._finished_player=FinishedFilmPlayer(
                self.index,self._wo5_journal_for_review(),
                unwrap=unwrap,decoder=decoder,
                private_root=self._wo5_state/".review-scratch",
                native_window=self._native_window,
                ask_native=self._wo5_confirm_finished_viewing)
        return self._finished_player

    def _wo5_confirm_finished_viewing(self,scope):
        self._native_window()
        if scope.get("operation")!="nvp.wo5.approve_readonly_finished_mxf_playback.v1":
            return False
        message=(
            "Review published FINISHED picture MXF and mastered PCM24 sound.\n"
            "This is NOT the original Take's live 3D scene.\n"
            "Feature: "+str(scope["feature_id"])+"\n"
            "FilmIndex SHA: "+str(scope["feature_filmindex_sha256"])+"\n"
            "Approved picture SHA: "+str(scope["picture_custody_sha256"])+"\n"
            "Frame count: "+str(scope["frames"])+"\n"
            "Verified CineCert decoder: "+str(scope["unwrap_binary_sha256"])+"\n"
            "Verified OpenJPEG decoder: "+str(scope["openjpeg_binary_sha256"])+"\n"
            "No file or original Take will be modified.\n"
            "Screen-preview color, 2-channel monitoring and cinema compliance "
            "are NOT independently certified.\n"
            "Authorize read-only playback of this exact published film?")
        return self._native_window().create_confirmation_dialog(
            "NVP — Authorize Finished-Film Playback",message) is True

    def wo5_film_begin(self,project_id,feature_id):
        self._wo5_project(project_id)
        return self._wo5_finished().begin(project_id,feature_id)

    def wo5_film_frame(self,session_id,frame_index):
        self._native_window()
        return self._wo5_finished().frame(session_id,frame_index)

    def wo5_film_window(self,session_id,first_frame,count=4):
        self._native_window()
        return self._wo5_finished().window(session_id,first_frame,count)

    def wo5_film_stop(self,session_id):
        self._native_window()
        return self._wo5_finished().stop(session_id)

    # USD-FILM-01R — source-first director edit in the ORIGINAL desktop
    # bridge inherited by TrustedDesktopWO6Bridge. No new HTTP writer.
    def _film01r_confirm(self, scope):
        window=self._native_window()
        allowed={
            "nvp.film.director_camera_bank_revision.v1",
            "nvp.film01q.publish_selected_view_edit.v1",
            "nvp.render.usd_film01q_selected_source_chunk.v1",
        }
        if type(scope) is not dict or scope.get("operation") not in allowed:
            return False
        identity=(scope.get("proposed_camera_bank_sha256") or
                  scope.get("proposed_edit_sha256") or
                  scope.get("selected_source_frames_sha256"))
        if type(identity) is not str or len(identity)!=64:
            return False
        detail=(
            "NVP native original-world director action.\\n"
            "Operation: "+str(scope["operation"])+"\\n"
            "Project: "+str(scope.get("project_id",""))+"\\n"
            "Exact source edit/view SHA: "+identity+"\\n"
            "World/performance SHA: "+str(scope.get(
                "original_performance_sha256") or scope.get(
                "source_performance_sha256") or "")+"\\n"
            "Source camera IDs: "+str(scope.get(
                "camera_ids") or scope.get("selected_viewpoint_ids") or [])[:300]+"\\n"
            "Film frame: "+str(scope.get("start_frame","not applicable"))+"\\n"
            "Render and edit permission is limited to this exact action.\\n"
            "Existing actors and world Take cannot be rewritten.\\n"
            "Approve this operation?")
        return window.create_confirmation_dialog(
            "NVP — Approve Original Director View/Edit",detail) is True

    def film01r_catalog(self,project_id):
        self._wo5_project(project_id)
        from backend.nvp_usd_film01r_lowfi_source import SourceViewpointWorkspace
        return SourceViewpointWorkspace(self.index).catalog(project_id)

    def film01r_preview(self,request):
        if type(request) is not dict or set(request)!={
            "project_id","camera_bank_id","revision","camera_id","frame"}:
            raise ValueError("Only exact source original camera preview request")
        self._wo5_project(request["project_id"])
        from backend.nvp_usd_film01r_lowfi_source import SourceViewpointWorkspace
        return SourceViewpointWorkspace(self.index).snapshot(
            request["project_id"],request["camera_bank_id"],
            request["revision"],camera_id=request["camera_id"],
            frame=request["frame"])

    def film01r_create_bank(self,request):
        if type(request) is not dict or set(request)!={
            "project_id","camera_bank_id","world_take_id","cameras"}:
            raise PermissionError("Only exactly bounded native source rig creation")
        pid=self._wo5_project(request["project_id"])
        from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
        grant=object()
        host=DirectorCameraBank(
            self.index,verify_director_action=lambda event,scope:
                event is grant and self._film01r_confirm(scope))
        record=host.create(
            pid,request["camera_bank_id"],
            world_take_id=request["world_take_id"],
            cameras=request["cameras"],director_event=grant)
        return {"format":"nvp.film01r.authenticated_camera_bank_saved.v1",
                "camera_bank_id":record["object_id"],
                "revision":record["revision"],
                "document_sha256":record["document_sha256"],
                "source_take_modified":False}

    def film01r_revise_bank(self,request):
        if type(request) is not dict or set(request)!={
            "project_id","camera_bank_id","expected_revision","changes"}:
            raise PermissionError("Only exact native original camera revision edits")
        pid=self._wo5_project(request["project_id"])
        from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
        grant=object()
        host=DirectorCameraBank(
            self.index,verify_director_action=lambda event,scope:
                event is grant and self._film01r_confirm(scope))
        record=host.revise(
            pid,request["camera_bank_id"],
            expected_revision=request["expected_revision"],
            changes=request["changes"],director_event=grant)
        return {"format":"nvp.film01r.authenticated_camera_bank_saved.v1",
                "camera_bank_id":record["object_id"],
                "revision":record["revision"],
                "document_sha256":record["document_sha256"],
                "source_take_modified":False}

    def film01r_save_edit(self,request):
        expected={"project_id","edit_id","expected_revision",
                  "camera_bank_id","camera_bank_revision","cuts"}
        if type(request) is not dict or set(request)!=expected:
            raise PermissionError("Exact original director EDL revision required")
        pid=self._wo5_project(request["project_id"])
        from backend.nvp_usd_film01q_selected_view_edit import OriginalSelectedViewEdit
        grant=object()
        host=OriginalSelectedViewEdit(
            self.index,verify_director_action=lambda event,scope:
                event is grant and self._film01r_confirm(scope))
        if request["expected_revision"]==0:
            record=host.create(
                pid,request["edit_id"],
                camera_bank_id=request["camera_bank_id"],
                camera_bank_revision=request["camera_bank_revision"],
                cuts=request["cuts"],director_event=grant)
        else:
            previous=host.verify(
                pid,request["edit_id"],request["expected_revision"])
            if previous["camera_bank_id"]!=request["camera_bank_id"]:
                raise PermissionError("Cannot silently change original camera source bank")
            record=host.revise(
                pid,request["edit_id"],
                expected_revision=request["expected_revision"],
                camera_bank_revision=request["camera_bank_revision"],
                cuts=request["cuts"],director_event=grant)
        return {"format":"nvp.film01r.authenticated_source_edit_saved.v1",
                "edit_id":record["object_id"],
                "revision":record["revision"],
                "document_sha256":record["document_sha256"],
                "original_performance_modified":False,
                "native_render_jobs_started":0}

    def film01r_render_next(self,request):
        """One explicit click => one bounded original 8-frame OS worker only."""
        fields={"project_id","edit_id","revision","render_quality",
                "shots_per_batch","parallel_worker_limit"}
        if type(request) is not dict or set(request)!=fields:
            raise PermissionError("Only native source-verified selected-render request")
        pid=self._wo5_project(request["project_id"])
        from backend.nvp_usd_film01r_quality import reviewed_quality
        from backend.nvp_usd_film01q_selected_view_edit import OriginalSelectedViewEdit
        from backend.nvp_usd_film01s_adaptive_batch import (
            BatchPreferences,safe_parallelism,FINAL)
        from backend.nvp_usd_film01s_resource_service import usable_cpu_threads
        from backend.nvp_resource_guard import collect_resources
        profile=reviewed_quality(request["render_quality"])
        edit=OriginalSelectedViewEdit(
            self.index,verify_director_action=lambda *_:False).verify(
                pid,request["edit_id"],request["revision"])
        worker=self._get_host().supervisor
        if not worker.blender_version.startswith("Blender 5.2."):
            raise RuntimeError("Original source Cycles worker needs verified Blender 5.2")
        prefs=BatchPreferences(
            shots_per_batch=request["shots_per_batch"],
            parallel_worker_limit=request["parallel_worker_limit"],
            renderer="cpu",
            final_worker_ram_mb=profile["max_worker_ram_mb"])
        ledger=worker.activity
        reserves=(ledger.snapshot().get("reservations") or {}) if ledger else {}
        capacity=safe_parallelism(
            collect_resources(),prefs,quality=FINAL,
            reserved_ram_mb=reserves.get("ram_mb",0),
            reserved_gpu_mb=reserves.get("gpu_mb",0),
            cpu_threads=usable_cpu_threads())
        if capacity["safe_workers"]<1:
            return {"format":"nvp.film01r.native_selected_frame_ticket.v1",
                    "state":"QUEUED_FOR_RESOURCES","reason":capacity["reason"],
                    "worker_started":False,"camera_rolls_required":False}
        with self._film01r_lock:
            if any(not item["future"].done()
                   for item in self._film01r_jobs.values()):
                raise RuntimeError("Original director editor already has one active worker")
            if self._film01r_pool is None:
                self._film01r_pool=ThreadPoolExecutor(
                    max_workers=1,thread_name_prefix="NVP 01R original selected view")
            token=secrets.token_urlsafe(18)
            grant=object()
            def native_one():
                from backend.nvp_usd_film01q_selected_view_host import ReviewedSelectedViewFilm
                host=ReviewedSelectedViewFilm(
                    self.index,worker,
                    verify_director_action=lambda event,scope:
                        event is grant and self._film01r_confirm(scope),
                    prove_process_custody=lambda *_:False,
                    render_quality=profile["name"])
                return host.run_next(
                    pid,request["edit_id"],revision=request["revision"],
                    director_event=grant)
            future=self._film01r_pool.submit(native_one)
            self._film01r_jobs[token]={
                "future":future,"project_id":pid,
                "edit_id":request["edit_id"],"revision":request["revision"],
                "quality":profile["name"],
                "original_performance_sha256":edit[
                    "original_performance_sha256"]}
        return {
            "format":"nvp.film01r.native_selected_frame_ticket.v1",
            "state":"QUEUED_NATIVE_APPROVAL","ticket_id":token,
            "quality":profile["name"],"worker_started":False,
            "camera_rolls_required":False,
            "safe_parallel_workers_at_admission":capacity["safe_workers"],
            "actual_editor_worker_parallelism":1}

    def film01r_render_poll(self,ticket_id):
        self._native_window()
        if type(ticket_id) is not str or len(ticket_id)>64:
            raise ValueError("Bounded native render ticket required")
        with self._film01r_lock:
            item=self._film01r_jobs.get(ticket_id)
            if item is None:
                raise KeyError("No active source-selected render ticket")
            future=item["future"]
        identity={
            "format":"nvp.film01r.native_selected_frame_status.v1",
            "ticket_id":ticket_id,"edit_id":item["edit_id"],
            "revision":item["revision"],"quality":item["quality"],
            "original_performance_sha256":item[
                "original_performance_sha256"],
            "source_camera_rolls_required":False}
        if not future.done():
            return {**identity,"state":"NATIVE_JOB_OR_APPROVAL_PENDING"}
        try:
            answer=future.result()
        except PermissionError:
            return {**identity,"state":"DENIED_OR_RECOVERY_REQUIRED"}
        except (RuntimeError,ValueError,OSError,KeyError):
            return {**identity,"state":"NATIVE_FAILED_NEEDS_INSPECTION"}
        if answer.get("state")=="BLOCKED_NEEDS_OS_CUSTODY_PROOF_AND_NEW_APPROVAL":
            return {**identity,"state":"RECOVERY_REQUIRED"}
        return {**identity,"state":"REVERIFIED_SELECTED_FRAMES",
                "native_result":answer,"original_film_complete":False}

    def film01r_render_image(self,ticket_id,frame):
        """Read one native Cycles PNG only after independent worker verification.

        No arbitrary path or file opener is ever exposed to the WebView.
        The native ticket and source edit determine the exact allowed PNG.
        """
        self._native_window()
        if (type(ticket_id) is not str or len(ticket_id)>64 or
            type(frame) is not int or not 0<=frame<720):
            raise ValueError("One exact completed source frame and ticket required")
        with self._film01r_lock:
            row=self._film01r_jobs.get(ticket_id)
            if row is None or not row["future"].done():
                raise PermissionError("Only a completed original render ticket can show pixels")
            data=dict(row)
        result=data["future"].result()
        start=result.get("start_frame")
        job_id=result.get("job_id")
        if (result.get("state")!="REVERIFIED_NATIVE_SELECTED_FRAMES" or
            type(start) is not int or not start<=frame<start+8 or
            type(job_id) is not str):
            raise PermissionError("Native output has no accepted source camera frame")
        from backend.nvp_usd_film01q_selected_view_host import ReviewedSelectedViewFilm
        from backend.nvp_blender_worker import sha_file
        import base64
        host=ReviewedSelectedViewFilm(
            self.index,self._get_host().supervisor,
            verify_director_action=lambda *_:False,
            prove_process_custody=lambda *_:False,
            render_quality=data["quality"])
        source_dir,source,plan=host.source_plan(
            data["project_id"],data["edit_id"],data["revision"])
        host._verify_completed(job_id,source_dir,source,plan,start,
                               int(job_id[-2:]))
        selected=plan["plan"]["frames"][frame]
        filename="frame_"+str(frame).zfill(4)+".png"
        image=self._get_host().supervisor.root/job_id/filename
        if image.is_symlink() or not image.is_file() or image.stat().st_size>12*1024*1024:
            raise RuntimeError("Native selected camera picture is missing or too large for inspection")
        sha=sha_file(image)
        audit=json.loads((self._get_host().supervisor.root/job_id/"audit.json").read_text("utf8"))
        receipt=audit["selected_view_frames"][frame-start]
        if (receipt["rendered_png_sha256"]!=sha or
            receipt["selected_camera_id"]!=selected["camera_id"] or
            receipt["view_cache_sha256"]!=selected["view_cache_sha256"]):
            raise RuntimeError("Native picture does not match actual original camera/edit")
        return {
            "format":"nvp.film01r.verified_native_cycles_picture.v1",
            "source_edit_document_sha256":plan["plan"]["edit_document_sha256"],
            "original_performance_sha256":source["original_performance_sha256"],
            "source_frame":frame,
            "source_camera_id":selected["camera_id"],
            "render_profile_sha256":plan["plan"]["render_profile_sha256"],
            "image_sha256":sha,
            "image_data_url":"data:image/png;base64,"+
                base64.b64encode(image.read_bytes()).decode("ascii"),
            "actual_blender_cycles_pixels":True,
            "director_picture_approved":False}
 
    def _close(self):
        if self._film01r_pool is not None:
            # No new grant survives closing this window. The existing
            # native supervisor owns termination/recovery of live workers.
            self._film01r_pool.shutdown(wait=False,cancel_futures=True)
        if self._finished_player is not None:
            self._finished_player.close()
        super()._close()
