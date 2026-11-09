"""USD-FILM-02M-F — only the installed NVP director bridge can save USD.

AI proposals and director drafts are data, never a user/AI OS grant.
The existing WO5→WO6 exact-origin bridge is the sole writer. No HTTP
source mutation and no alternate PyWebView/Blender instance is created.
"""
from __future__ import annotations

import re
import secrets
import threading
from hashlib import sha256
from pathlib import Path

from backend.nvp_usd_film02m_f_authoring import OriginalDistrictDrafts

SHA=re.compile(r"[0-9a-f]{64}\Z")


class OriginalDistrictDesktopMixin:
    def _film02mf_confirm(self,scope):
        window=self._native_window()
        if (type(scope) is not dict or
            scope.get("operation")!=
                "nvp.film02m_f.commit_exact_original_district.v1" or
            type(scope.get("project_id")) is not str or
            type(scope.get("district_id")) is not str or
            not all(type(scope.get(k)) is str and SHA.fullmatch(scope[k])
                for k in ("original_source_plan_sha256",
                          "native_original_layer_source_sha256")) or
            type(scope.get("version")) is not int or
            type(scope.get("base_revision")) is not int or
            type(scope.get("generated_instances")) is not int or
            type(scope.get("manual_opinion_count")) is not int or
            type(scope.get("source_triangles_estimated")) is not int):
            return False
        message=(
            "NVP — Publish this original 3D film world revision?\n\n"
            "Project: "+scope["project_id"]+"\n"
            "Original district: "+scope["district_id"]+"\n"
            "Proposal ID: "+str(scope.get("draft_id"))+"\n"
            "Proposal version: "+str(scope["version"])+"\n"
            "Current approved base revision: "+str(scope["base_revision"])+"\n"
            "Existing source SHA: "+str(scope.get("base_source_sha256"))+"\n"
            "Exact proposed plan SHA: "+
                scope["original_source_plan_sha256"]+"\n"
            "Exact proposed native USD SHA: "+
                scope["native_original_layer_source_sha256"]+"\n"
            "Generated source buildings: "+
                str(scope["generated_instances"])+"\n"
            "Director edit opinions: "+
                str(scope["manual_opinion_count"])+"\n"
            "Budgeted source triangles: "+
                str(scope["source_triangles_estimated"])+"\n\n"
            "An AI draft is NOT an approval. This operation publishes ONE "
            "immutable original FilmIndex revision, preserves prior world "
            "revisions, and does NOT render or change actor Takes.\n\n"
            "Approve this exact current source and its director changes?")
        return window.create_confirmation_dialog(
            "NVP — Approve Original Building World",message) is True

    def _film02mf_service(self,pid):
        self._wo5_project(pid)
        workspace=self._wo5_state/"original-film02m-director-proposals"
        if workspace.is_symlink():
            raise PermissionError("Installed NVP original proposal store is not symlinkable")
        if not hasattr(self,"_film02mg_host_session"):
            self._film02mg_host_session=secrets.token_hex(16)
        return OriginalDistrictDrafts(
            self.index,workspace,confirm=self._film02mf_confirm,
            model_session_id=self._film02mg_host_session)

    def _film02mg_begin(self,request):
        """Admit exact source/model intent before starting generation."""
        if (type(request) is not dict or set(request)!={
                "project_id","district_id","expected_revision",
                "direction","model_id"}):
            raise PermissionError("Only bounded local-model world advice request")
        pid=self._wo5_project(request["project_id"])
        if getattr(self,"_wo6_closed",False):
            raise PermissionError("Original world model session is closed")
        factory=getattr(self,"_wo6_director_writer_factory",None)
        if not callable(factory):
            raise PermissionError("Installed WO6 local provider is unavailable")
        from backend.nvp_usd_film02m_f_authoring import _json
        direction=request["direction"]
        if (type(direction) is not str or not 1<=len(direction.strip())<=1200):
            raise ValueError("Bounded director intent required")
        service=self._film02mf_service(pid)
        catalog=service.catalog(pid)
        catalog_key=_json([
            [(b["building_id"],b["revision"],b["document_sha256"])
             for b in catalog["source_buildings"]],
            [(d["district_id"],d["revision"],d["document_sha256"])
             for d in catalog["approved_districts"]]]).encode("ascii")
        attempt=service.start_model_attempt(
            pid,request["district_id"],request["expected_revision"],
            request["model_id"],sha256(direction.strip().encode("utf8")).hexdigest(),
            sha256(catalog_key).hexdigest())
        return pid,service,catalog,catalog_key,direction,attempt

    def _film02mg_complete(self,request,begun,cancel_event=None):
        """The single source-locked implementation for sync and background work."""
        pid,service,catalog,catalog_key,direction,attempt=begun
        from backend.nvp_usd_film02m_g_model_world_candidate import (
            generate_model_world_candidate)
        from backend.nvp_usd_film02m_f_authoring import _json
        def require_live():
            if (getattr(self,"_wo6_closed",False) or
                (cancel_event is not None and cancel_event.is_set())):
                raise PermissionError("Original world generation was stopped")
        try:
            require_live()
            # Provider is selected by the existing trusted host, never by
            # browser-supplied endpoint, script, URL, or executable path.
            model=self._wo6_director_writer_factory(request["model_id"])
            require_live()
            result=generate_model_world_candidate(
                catalog,project_id=pid,district_id=request["district_id"],
                expected_revision=request["expected_revision"],
                direction=direction,model_id=request["model_id"],model=model)
            require_live()
            newest=service.catalog(pid)
            new_key=_json([
                [(b["building_id"],b["revision"],b["document_sha256"])
                 for b in newest["source_buildings"]],
                [(d["district_id"],d["revision"],d["document_sha256"])
                 for d in newest["approved_districts"]]]).encode("ascii")
            if sha256(catalog_key).digest()!=sha256(new_key).digest():
                raise RuntimeError("Original source catalog changed during generation")
            require_live()
            # Atomic SQLite state transition GENERATING -> DRAFT_SAVED. If
            # cancellation won while native USD source was being validated,
            # create() rolls its draft/evidence INSERTs back in one transaction.
            draft=service.create(
                pid,request["district_id"],
                expected_revision=request["expected_revision"],
                params=result["params"],proposed_by="ai",
                model_evidence=result,model_attempt_id=attempt)
        except Exception as exc:
            service.fail_model_attempt(
                pid,attempt,"session_closed" if getattr(self,"_wo6_closed",False)
                else "source_changed" if isinstance(exc,RuntimeError)
                else "model_response_denied")
            raise
        return {
            "format":"nvp.usd_film02m_g.model_saved_original_draft.v1",
            "proposal":draft,
            "attempt_id":attempt,
            "model_evidence":result,
            "director_approval_granted":False,
            "actor_takes_modified":False,
        }

    def film02mg_generate_candidate(self,request):
        """Synchronous compatibility path; host-owned, never a browser grant."""
        return self._film02mg_complete(request,self._film02mg_begin(request))

    def _film02mg_run_background(self,request,begun,stop):
        attempt=begun[-1]
        try:
            self._film02mg_complete(request,begun,stop)
        except Exception:
            # Durable failure classification is retained by the host-owned
            # attempt table. Never echo model text or local source paths to UI.
            pass
        finally:
            with self._film02mg_async_lock:
                self._film02mg_active.pop(attempt,None)

    def film02mg_start_candidate(self,request):
        """Nonblocking installed-WebView generation, without OS authorization."""
        if not hasattr(self,"_film02mg_async_lock"):
            raise PermissionError("Trusted native desktop model host unavailable")
        with self._film02mg_async_lock:
            if getattr(self,"_wo6_closed",False):
                raise PermissionError("Local model host already closed")
            if self._film02mg_active:
                raise RuntimeError("Previous installed world model job still running")
            begun=self._film02mg_begin(request)
            pid,service,_,_,_,attempt=begun
            stop=threading.Event()
            self._film02mg_active[attempt]={
                "project_id":pid,"stop":stop,"service":service}
            try:
                threading.Thread(
                    target=self._film02mg_run_background,
                    args=(dict(request),begun,stop),
                    name="NVP-FILM02M-read-only-model-to-draft",
                    daemon=True).start()
            except Exception:
                self._film02mg_active.pop(attempt,None)
                service.fail_model_attempt(pid,attempt,"provider_failed")
                raise
        return {
            "format":"nvp.usd_film02m_g.durable_model_attempt_status.v1",
            "attempt_id":attempt,"project_id":pid,
            "state":"GENERATING",
            "director_approval_granted":False,
            "native_worker_authorized":False,
            "actor_takes_modified":False,
        }

    def film02mg_candidate_status(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","attempt_id"}:
            raise PermissionError("Only exact original model attempt status")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).model_attempt_status(
            pid,request["attempt_id"])

    def film02mg_cancel_candidate(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","attempt_id"}:
            raise PermissionError("Only exact original model attempt cancellation")
        pid=self._wo5_project(request["project_id"])
        attempt=request["attempt_id"]
        if type(attempt) is not str or not (
            len(attempt)==24 and all(x in "0123456789abcdef" for x in attempt)):
            raise PermissionError("Only host-minted model attempt may be cancelled")
        with self._film02mg_async_lock:
            active=self._film02mg_active.get(attempt)
            if active is not None and active["project_id"]==pid:
                active["stop"].set()
            return self._film02mf_service(pid).cancel_model_attempt(pid,attempt)

    def _film02mg_shutdown(self):
        """Revokes in-flight draft admission before the native host closes."""
        with self._film02mg_async_lock:
            for attempt,job in list(self._film02mg_active.items()):
                job["stop"].set()
                job["service"].cancel_model_attempt(job["project_id"],attempt)

    def _film02mh_confirm(self,scope):
        if (type(scope) is not dict or
            scope.get("operation")!=
                "nvp.film02m_h.approve_original_district_shot_binding.v1" or
            not all(type(scope.get(k)) is str and SHA.fullmatch(scope[k])
                for k in ("district_document_sha256","district_usd_root_sha256",
                          "world_take_sha256","original_camera_shot_sha256",
                          "source_preview_sha256")) or
            type(scope.get("actor_count")) is not int or
            type(scope.get("film_tick")) is not int):
            return False
        message=(
            "Approve one immutable original 3D building world in this FILM shot?\n\n"
            "Film project: "+str(scope["project_id"])+"\n"
            "Binding: "+str(scope["binding_id"])+"\n"
            "Approved world: "+str(scope["district_id"])+" rev "+
            str(scope["district_revision"])+"\n"
            "Original building source SHA: "+scope["district_document_sha256"]+"\n"
            "Actual OpenUSD layer SHA: "+scope["district_usd_root_sha256"]+"\n"
            "Immutable actor world Take: "+str(scope["world_take_id"])+"\n"
            "Original actor Take SHA: "+scope["world_take_sha256"]+"\n"
            "Original camera shot SHA: "+scope["original_camera_shot_sha256"]+"\n"
            "Exact source preview SHA: "+scope["source_preview_sha256"]+"\n"
            "Film tick: "+str(scope["film_tick"])+"\n"
            "Verified original actors: "+str(scope["actor_count"])+"\n\n"
            "This binds existing approved sources. It does NOT alter actors, "
            "camera, dialogue, original PCM, USD building layers or source Takes. "
            "It is NOT approval of a rendered film or native render worker.\n"
            "Publish this one immutable original source binding?")
        return self._native_window().create_confirmation_dialog(
            "NVP — Original Actor/Camera World Binding",message) is True

    def _film02mh_host(self):
        from backend.nvp_usd_film02m_h_actor_camera_binding import (
            OriginalDistrictShotBinding)
        token=object()
        used=[False]
        def approve(event,scope):
            if event is not token or used[0]:
                return False
            used[0]=True
            return self._film02mh_confirm(scope)
        return OriginalDistrictShotBinding(
            self.index,confirm=approve),token

    def film02mh_preview_shot(self,request):
        if (type(request) is not dict or set(request)!={
                "project_id","district_id","district_revision",
                "world_take_id","film_tick"}):
            raise PermissionError("Only immutable 01D/01E source shot preview")
        pid=self._wo5_project(request["project_id"])
        host,_=self._film02mh_host()
        return host.preview(
            pid,request["district_id"],request["district_revision"],
            request["world_take_id"],request["film_tick"])

    def film02mh_commit_shot_binding(self,request):
        if (type(request) is not dict or set(request)!={
                "project_id","binding_id","district_id","district_revision",
                "world_take_id","film_tick","source_preview_sha256"}):
            raise PermissionError("Only exact-native-approved original shot binding")
        pid=self._wo5_project(request["project_id"])
        if (type(request["source_preview_sha256"]) is not str or
            not SHA.fullmatch(request["source_preview_sha256"])):
            raise PermissionError("Current source-locked preview SHA required")
        host,token=self._film02mh_host()
        return host.publish(
            pid,request["binding_id"],
            district_id=request["district_id"],
            district_revision=request["district_revision"],
            world_take_id=request["world_take_id"],
            film_tick=request["film_tick"],
            creator_event=token,
            expected_preview_sha256=request["source_preview_sha256"])

    def film02mh_reopen_shot_binding(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","binding_id"}:
            raise PermissionError("Only immutable source shot binding reopen")
        pid=self._wo5_project(request["project_id"])
        host,_=self._film02mh_host()
        return host.reopen(pid,request["binding_id"])

    def film02mf_catalog(self,project_id):
        return self._film02mf_service(project_id).catalog(project_id)

    def film02mf_propose(self,request):
        if (type(request) is not dict or set(request)!={
                "project_id","district_id","expected_revision",
                "params","proposed_by"}):
            raise PermissionError("Original 02M AI/director draft must be typed")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).create(
            pid,request["district_id"],
            expected_revision=request["expected_revision"],
            params=request["params"],proposed_by=request["proposed_by"])

    def film02mf_reopen(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id"}:
            raise PermissionError("Exact NVP original source draft reopen request")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).reopen(pid,request["draft_id"])

    def film02mf_preview(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id"}:
            raise PermissionError("Only original source scene draft preview")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).preview(pid,request["draft_id"])

    def film02mf_edit(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version","action"}:
            raise PermissionError("Source director layer accepts only one typed proposed action")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).edit(
            pid,request["draft_id"],request["version"],request["action"])

    def film02mf_undo(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version"}:
            raise PermissionError("Only exact proposal-version undo")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).undo(
            pid,request["draft_id"],request["version"])

    def film02mf_discard(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version"}:
            raise PermissionError("Only exact proposal-version discard")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).discard(
            pid,request["draft_id"],request["version"])

    def film02mf_commit(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version",
                "source_plan_sha256","usd_layer_root_sha256"}:
            raise PermissionError("Only exact verified source-locked native approval")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).approve_and_commit(
            pid,request["draft_id"],request["version"],
            request["source_plan_sha256"],
            request["usd_layer_root_sha256"])
