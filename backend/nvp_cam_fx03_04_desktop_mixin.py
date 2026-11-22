"""CAM-FX-03/04 existing installed NVP trusted WebView2 director entrypoints.

No second app, model endpoint, renderer, or permission broker. All requests
cross the existing exact-origin WO5 window bridge, revalidate original USD
and use separate one-shot native approvals for immutable publication.
"""
from __future__ import annotations

from hashlib import sha256
import secrets
import threading

from backend.nvp_cam_fx03_durable_drafts import DurableOriginalCameraDrafts
from backend.nvp_cam_fx03_source_guidance import guided_camera_scene
from backend.nvp_cam_fx01_camera_rails import OriginalCameraRails

class CameraRailDirectorMixin:
    def _camfx03_service(self,pid):
        self._wo5_project(pid)
        root=self._wo5_state/"camfx-durable-director-camera-rail-drafts"
        if root.is_symlink():
            raise PermissionError("No symlinkable director camera journal")
        if not hasattr(self,"_camfx04_host_session"):
            self._camfx04_host_session=secrets.token_hex(32)
        return DurableOriginalCameraDrafts(
            self.index,root,host_session_id=self._camfx04_host_session)

    def camfx03_scene_guidance(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","rail_spec","actor_id","district_binding_id"}:
            raise PermissionError("Source-only ActorID/district framing query")
        pid=self._wo5_project(request["project_id"])
        return guided_camera_scene(
            self.index,pid,request["rail_spec"],
            actor_id=request["actor_id"],
            district_binding_id=request["district_binding_id"])

    def camfx03_draft_catalog(self,project_id):
        pid=self._wo5_project(project_id)
        return self._camfx03_service(pid).catalog(pid)

    def camfx03_draft_create(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","rail_id","expected_revision","rail_spec"}:
            raise PermissionError("Only bounded first-party original camera rail draft")
        pid=self._wo5_project(request["project_id"])
        return self._camfx03_service(pid).create(
            pid,request["rail_id"],request["expected_revision"],
            request["rail_spec"])

    def camfx03_draft_reopen(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id"}:
            raise PermissionError("Only exact project-local original camera draft")
        pid=self._wo5_project(request["project_id"])
        return self._camfx03_service(pid).reopen(
            pid,request["draft_id"])

    def camfx03_draft_save(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version","rail_spec"}:
            raise PermissionError("Atomic camera rail draft update required")
        pid=self._wo5_project(request["project_id"])
        return self._camfx03_service(pid).save(
            pid,request["draft_id"],request["version"],request["rail_spec"])

    def camfx03_draft_undo(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version"}:
            raise PermissionError("Exact durable camera-rail undo required")
        pid=self._wo5_project(request["project_id"])
        return self._camfx03_service(pid).undo(
            pid,request["draft_id"],request["version"])

    def camfx03_draft_discard(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version"}:
            raise PermissionError("Only unapproved current camera draft may discard")
        pid=self._wo5_project(request["project_id"])
        return self._camfx03_service(pid).discard(
            pid,request["draft_id"],request["version"])

    def camfx03_draft_publish(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version","preview_sha256"}:
            raise PermissionError("Only exact durable director camera draft may publish")
        pid=self._wo5_project(request["project_id"])
        journal=self._camfx03_service(pid)
        current=journal.begin_publish(
            pid,request["draft_id"],request["version"],
            request["preview_sha256"])
        try:
            # Fresh reviewed OS action reuses the existing exact source
            # publication method, but supplies ONLY persisted draft bytes.
            accepted=self.camfx02_publish({
                "project_id":pid,"rail_id":current["rail_id"],
                "rail_spec":current["rail_spec"],
                "expected_revision":current["base_revision"],
                "preview_sha256":current["proposal_sha256"]})
        except Exception:
            # A process crash here cannot infer that the OS dialog consented;
            # reconciliation checks native FilmIndex, but NEVER retries.
            journal.complete_publish(
                pid,request["draft_id"],request["version"],None)
            raise
        state=journal.complete_publish(
            pid,request["draft_id"],request["version"],accepted)
        return {"format":"nvp.cam_fx03.durable_published_director_rail.v1",
                "rail_receipt":accepted,"draft":state,
                "native_worker_authorized":False,
                "actor_pcm_modified":False}

    def camfx03_draft_recover_publish(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id"}:
            raise PermissionError("Only read-only original rail commit reconciliation")
        pid=self._wo5_project(request["project_id"])
        return self._camfx03_service(pid).recover_published(
            pid,request["draft_id"])

    def _camfx04_jobs_host(self):
        if not hasattr(self,"_camfx04_lock"):
            self._camfx04_lock=threading.RLock()
            self._camfx04_active={}
        return self._camfx04_lock

    def camfx04_start_candidate(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version","model_id","direction",
                "actor_id","district_binding_id"}:
            raise PermissionError("Only host-scoped typed local model camera proposal")
        pid=self._wo5_project(request["project_id"])
        if getattr(self,"_wo6_closed",False):
            raise PermissionError("Local model host already closed")
        factory=getattr(self,"_wo6_director_writer_factory",None)
        if not callable(factory):
            raise PermissionError("Existing WO6 selected model host is unavailable")
        direction=request["direction"]
        if type(direction) is not str or not 1<=len(direction.strip())<=1200:
            raise ValueError("Plain bounded film-director intent required")
        lock=self._camfx04_jobs_host()
        with lock:
            if self._camfx04_active:
                raise RuntimeError("Another camera suggestion must finish or cancel")
            service=self._camfx03_service(pid)
            draft=service.reopen(pid,request["draft_id"])
            if draft["state"]!="DRAFT" or draft["version"]!=request["version"]:
                raise RuntimeError("Camera model can only propose against current saved draft")
            guide=guided_camera_scene(
                self.index,pid,draft["rail_spec"],
                actor_id=request["actor_id"],
                district_binding_id=request["district_binding_id"])
            aid=service.start_model(
                pid,request["draft_id"],request["version"],
                request["model_id"],guide["guidance_sha256"],
                sha256(direction.strip().encode("utf8")).hexdigest())
            stop=threading.Event()
            self._camfx04_active[aid]={
                "project_id":pid,"service":service,"stop":stop}
            try:
                worker=threading.Thread(
                    target=self._camfx04_generate,
                    args=(dict(request),guide,aid,stop),
                    name="NVP-CAMFX-read-only-local-model-to-durable-draft",
                    daemon=True)
                worker.start()
            except Exception:
                self._camfx04_active.pop(aid,None)
                service.fail_model(pid,aid,"model_failed")
                raise
        return service.model_status(pid,aid)

    def _camfx04_generate(self,request,initial,aid,stop):
        pid=request["project_id"]
        service=self._camfx03_service(pid)
        try:
            if stop.is_set() or getattr(self,"_wo6_closed",False):
                raise PermissionError("Director cancelled local model proposal")
            model=self._wo6_director_writer_factory(request["model_id"])
            from backend.nvp_cam_fx04_model_camera_candidate import (
                generate_camera_candidate)
            draft=service.reopen(pid,request["draft_id"])
            if draft["state"]!="DRAFT" or draft["version"]!=request["version"]:
                raise RuntimeError("Director source changed during model selection")
            candidate=generate_camera_candidate(
                draft["rail_spec"],initial,
                direction=request["direction"],
                model_id=request["model_id"],writer=model)
            if stop.is_set() or getattr(self,"_wo6_closed",False):
                raise PermissionError("Late model output cannot save after cancellation")
            # Real OpenUSD actor/district source readback must remain identical
            # after generation. A modified original scene requires new advice.
            next_source=guided_camera_scene(
                self.index,pid,draft["rail_spec"],
                actor_id=request["actor_id"],
                district_binding_id=request["district_binding_id"])
            if next_source["guidance_sha256"]!=initial["guidance_sha256"]:
                raise RuntimeError("Source ActorID/district framing changed during generation")
            service.complete_model(
                pid,aid,request["version"],initial["guidance_sha256"],
                candidate["proposed_rail_spec"],candidate)
        except Exception as exc:
            service.fail_model(
                pid,aid,"host_shutdown" if getattr(self,"_wo6_closed",False)
                else "source_changed" if isinstance(exc,RuntimeError)
                else "model_failed")
        finally:
            with self._camfx04_jobs_host():
                self._camfx04_active.pop(aid,None)

    def camfx04_candidate_status(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","attempt_id"}:
            raise PermissionError("One exact host-owned camera model attempt")
        pid=self._wo5_project(request["project_id"])
        return self._camfx03_service(pid).model_status(
            pid,request["attempt_id"])

    def camfx04_cancel_candidate(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","attempt_id"}:
            raise PermissionError("Only explicit camera model attempt cancellation")
        pid=self._wo5_project(request["project_id"])
        with self._camfx04_jobs_host():
            entry=self._camfx04_active.get(request["attempt_id"])
            if entry and entry["project_id"]==pid:
                entry["stop"].set()
            return self._camfx03_service(pid).cancel_model(
                pid,request["attempt_id"])

    def _camfx04_shutdown(self):
        with self._camfx04_jobs_host():
            for aid,job in list(self._camfx04_active.items()):
                job["stop"].set()
                job["service"].cancel_model(job["project_id"],aid)
