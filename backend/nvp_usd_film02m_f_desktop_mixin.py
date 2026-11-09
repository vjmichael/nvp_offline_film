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

    def _film02mh_confirm_render(self,scope):
        """One fresh native Windows dialog; historical binding is not a grant."""
        if (type(scope) is not dict or scope.get("operation")!=
                "nvp.render.usd_film02m_h.original_district_actor_shot.v1" or
            type(scope.get("project_id")) is not str or
            type(scope.get("binding_id")) is not str or
            type(scope.get("original_film_tick")) is not int or
            type(scope.get("actual_district_meshes")) is not int or
            type(scope.get("original_actor_count")) is not int or
            not all(type(scope.get(key)) is str and SHA.fullmatch(scope[key])
                    for key in ("binding_sha256","approved_district_sha256",
                                "original_world_take_sha256",
                                "original_camera_shot_sha256",
                                "source_usd_sha256"))):
            return False
        message=(
            "NVP — Render one original actor and building-world camera frame?\\n\\n"
            "Project: "+scope["project_id"]+"\\n"
            "Exact approved film shot binding: "+scope["binding_id"]+"\\n"
            "Binding SHA: "+scope["binding_sha256"]+"\\n"
            "Approved district SHA: "+scope["approved_district_sha256"]+"\\n"
            "Frozen actor World Take SHA: "+scope[
                "original_world_take_sha256"]+"\\n"
            "Original camera shot SHA: "+scope[
                "original_camera_shot_sha256"]+"\\n"
            "Derived render-only USD SHA: "+scope["source_usd_sha256"]+"\\n"
            "Exact original film tick: "+str(scope["original_film_tick"])+"\\n"
            "Original actors: "+str(scope["original_actor_count"])+"\\n"
            "Native approved building meshes: "+str(scope[
                "actual_district_meshes"])+"\\n\\n"
            "This authorizes ONE bounded supervised Blender/Cycles render. "
            "The original ActorID Takes, camera, district source layers and "
            "PCM remain immutable. The image is NOT approved film content.\\n"
            "Approve this exact render operation?")
        return self._native_window().create_confirmation_dialog(
            "NVP — Render Original Actor and District Shot",message) is True

    def film02mh_render_begin(self,request):
        """Nonblocking one-frame real Cycles, with a one-use native OS gate."""
        if type(request) is not dict or set(request)!={
                "project_id","binding_id","binding_sha256"}:
            raise PermissionError("Only source-bound original shot render request")
        pid=self._wo5_project(request["project_id"])
        from backend.nvp_usd_film02m_h_actor_camera_binding import (
            OriginalDistrictShotBinding)
        from backend.nvp_usd_film02m_h_render_handoff import (
            ReviewedDistrictShotCyclesHost)
        from concurrent.futures import ThreadPoolExecutor
        source=OriginalDistrictShotBinding(
            self.index,confirm=lambda *_:False).reopen(
                pid,request["binding_id"])
        if (source["binding_document_sha256"]!=request["binding_sha256"] or
            not SHA.fullmatch(request["binding_sha256"])):
            raise PermissionError("Rendered shot requires the current approved binding SHA")
        worker=self._get_host().supervisor
        if not worker.blender_version.startswith("Blender 5.2."):
            raise RuntimeError("Verified original shot requires Blender 5.2")
        with self._film01r_lock:
            if any(not x["future"].done() for x in
                   list(self._film01r_jobs.values())+
                   list(self._film02mh_jobs.values())):
                raise RuntimeError("Another original film render already in progress")
            if self._film01r_pool is None:
                self._film01r_pool=ThreadPoolExecutor(
                    max_workers=1,thread_name_prefix="NVP original source shot")
            token=secrets.token_hex(12)
            job_id="shot02mh_"+secrets.token_hex(12)
            one_use=object()
            used=[False]
            def authorize(event,scope):
                if event is not one_use or used[0]:
                    return False
                used[0]=True
                return self._film02mh_confirm_render(scope)
            def native_one():
                host=ReviewedDistrictShotCyclesHost(
                    self.index,worker,verify_director_action=authorize)
                return host.render(pid,request["binding_id"],
                                   job_id=job_id,director_event=one_use)
            future=self._film01r_pool.submit(native_one)
            self._film02mh_jobs[token]={
                "future":future,"project_id":pid,
                "binding_id":request["binding_id"],
                "binding_sha256":source["binding_document_sha256"],
                "job_id":job_id}
        return {
            "format":"nvp.usd_film02m_h.native_render_ticket.v1",
            "state":"PENDING_FRESH_NATIVE_APPROVAL",
            "ticket_id":token,"binding_id":request["binding_id"],
            "binding_sha256":source["binding_document_sha256"],
            "worker_verified":False,"director_picture_approved":False,
            "original_actor_takes_modified":False}

    def film02mh_render_poll(self,ticket_id):
        self._native_window()
        if (type(ticket_id) is not str or len(ticket_id)!=24 or
            any(x not in "0123456789abcdef" for x in ticket_id)):
            raise PermissionError("Exact installed original-render ticket required")
        with self._film01r_lock:
            item=self._film02mh_jobs.get(ticket_id)
        if item is None:
            raise KeyError("Unknown installed original-shot render ticket")
        base={
            "format":"nvp.usd_film02m_h.native_render_status.v1",
            "ticket_id":ticket_id,"binding_id":item["binding_id"],
            "binding_sha256":item["binding_sha256"],
            "original_actor_takes_modified":False,
            "director_picture_approved":False}
        if not item["future"].done():
            return {**base,"state":"NATIVE_JOB_OR_APPROVAL_PENDING"}
        try:
            result=item["future"].result()
            from backend.nvp_usd_film02m_h_render_handoff import (
                ReviewedDistrictShotCyclesHost)
            verified=ReviewedDistrictShotCyclesHost(
                self.index,self._get_host().supervisor,
                verify_director_action=lambda *_:False).reopen_verified_render(
                    item["project_id"],item["binding_id"],item["job_id"])
            if (result["state"]!=
                    "RENDERED_REAL_ORIGINAL_DISTRICT_ACTOR_CAMERA_SHOT" or
                result["binding_sha256"]!=item["binding_sha256"] or
                verified["picture_sha256"]!=result["png_sha256"] or
                verified["native_worker_and_independent_reopen_verified"] is not True):
                raise RuntimeError("Native reviewed source frame differs from completed job")
        except PermissionError:
            return {**base,"state":"NATIVE_DENIED_OR_REQUIRES_NEW_APPROVAL"}
        except (RuntimeError,ValueError,OSError,KeyError,TypeError):
            return {**base,"state":"NATIVE_FAILED_NEEDS_INDEPENDENT_INSPECTION"}
        return {**base,"state":"SOURCE_VERIFIED_CYCLES_PICTURE",
                "job_id":item["job_id"],
                "picture_sha256":verified["picture_sha256"],
                "world_take_sha256":verified["world_take_sha256"],
                "district_document_sha256":verified["district_document_sha256"],
                "native_worker_and_independent_reopen_verified":True}

    def film02mh_render_image(self,request):
        """Only exact journal-verified source picture; supports restart readback."""
        if type(request) is not dict or set(request)!={
                "project_id","binding_id","binding_sha256","job_id"}:
            raise PermissionError("Only pinned completed 02M-H Cycles preview")
        pid=self._wo5_project(request["project_id"])
        if (type(request["binding_sha256"]) is not str or
            not SHA.fullmatch(request["binding_sha256"])):
            raise PermissionError("Exact immutable render source SHA required")
        from backend.nvp_usd_film02m_h_render_handoff import (
            ReviewedDistrictShotCyclesHost)
        from backend.nvp_blender_worker import sha_file
        import base64
        supervisor=self._get_host().supervisor
        proof=ReviewedDistrictShotCyclesHost(
            self.index,supervisor,verify_director_action=lambda *_:False
            ).reopen_verified_render(
                pid,request["binding_id"],request["job_id"])
        if (proof["binding_sha256"]!=request["binding_sha256"] or
            proof["original_actor_takes_and_pcm_unchanged"] is not True):
            raise PermissionError("Render image no longer matches source binding")
        image=supervisor.root/request["job_id"]/"frame.png"
        if image.is_symlink() or sha_file(image)!=proof["picture_sha256"]:
            raise RuntimeError("Native render PNG changed after journal verification")
        return {**proof,"image_data_url":"data:image/png;base64,"+
                base64.b64encode(image.read_bytes()).decode("ascii")}

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

    def _camfx01_source(self,pid):
        from backend.nvp_cam_fx01_camera_rails import OriginalCameraRails
        return OriginalCameraRails(self.index,verify_director_action=lambda *_:False)

    def camfx01_catalog(self,project_id):
        """Existing 01M director banks + bounded native approved rail history."""
        pid=self._wo5_project(project_id)
        from backend.nvp_usd_film01m_director_camera_bank import (
            FORMAT as BANK_FORMAT,DirectorCameraBank)
        from backend.nvp_cam_fx01_camera_rails import FORMAT as RAIL_FORMAT
        rows=self.index.list_objects(pid,kind="presentation")
        if len(rows)>512:
            raise RuntimeError("Browse scoped camera source objects, not unbounded film history")
        banks,rails=[],[]
        for row in rows:
            record=self.index.read_revision(
                pid,row["object_id"],row["head_revision"])
            doc=record["data"]
            if doc.get("format")==BANK_FORMAT:
                # Film bank revisions are immutable. Expose the old exact
                # source bank as well, otherwise editing an old rail after
                # camera-bank revision 2 would silently select revision 2.
                if row["head_revision"]>32:
                    raise RuntimeError("Camera history too large for one scoped catalog")
                for revision in range(1,row["head_revision"]+1):
                    original=self.index.read_revision(
                        pid,row["object_id"],revision)
                    verified=DirectorCameraBank(
                        self.index,verify_director_action=lambda *_:False).verify(
                            pid,row["object_id"],revision)
                    banks.append({
                        "bank_id":row["object_id"],
                        "revision":revision,
                        "document_sha256":original["document_sha256"],
                        "world_take_id":verified["world_take_id"],
                        "world_take_sha256":verified["world_take_sha256"],
                        "duration_ticks":verified["source_duration_ticks"],
                        "cameras":[{"camera_id":x["camera_id"],
                                    "position_m":x["position_m"],
                                    "focal_length_mm":x["focal_length_mm"],
                                    "focus_distance_m":x["focus_distance_m"]}
                                   for x in verified["cameras"][:96]]})
            elif doc.get("format")==RAIL_FORMAT:
                rails.append({
                    "rail_id":row["object_id"],
                    "revision":row["head_revision"],
                    "document_sha256":record["document_sha256"],
                    "camera_bank_id":doc["camera_bank_id"],
                    "world_take_sha256":doc["world_take_sha256"],
                    "camera_id":doc["rail_spec"]["camera_id"],
                    "film_start_tick":doc["rail_spec"]["film_start_tick"],
                    "film_end_tick":doc["rail_spec"]["film_end_tick"],
                    "layer_sha256":doc["rail_layer_sha256"],
                    "technique":doc["rail_spec"]["technique"]})
        if len(banks)>96 or len(rails)>128:
            raise RuntimeError("Scoped rail catalog must remain bounded")
        return {
            "format":"nvp.cam_fx01.trusted_director_rail_catalog.v1",
            "project_id":pid,
            "camera_banks":banks[:96],"rails":rails[:128],
            "frozen_actor_takes_modified":False,
            "native_worker_started":False}

    def camfx01_preview(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","rail_id","rail_spec","expected_revision"}:
            raise PermissionError("Only reviewed original director camera rail proposal")
        pid=self._wo5_project(request["project_id"])
        return self._camfx01_source(pid).preview(
            pid,request["rail_id"],request["rail_spec"],
            expected_revision=request["expected_revision"])

    def _camfx02_confirm(self,scope):
        if (type(scope) is not dict or scope.get("operation")!=
                "nvp.cam_fx02.publish_exact_director_camera_rail.v1" or
            type(scope.get("project_id")) is not str or
            type(scope.get("rail_id")) is not str or
            type(scope.get("source_camera_id")) is not str or
            type(scope.get("expected_revision")) is not int or
            type(scope.get("film_start_tick")) is not int or
            type(scope.get("film_end_tick")) is not int or
            not all(type(scope.get(key)) is str and SHA.fullmatch(scope[key])
                for key in ("world_take_sha256",
                            "source_performance_sha256","camera_bank_sha256",
                            "proposed_rail_sha256","stronger_usd_layer_sha256"))):
            return False
        message=(
            "NVP — Approve an exact original film camera rail revision?\\n\\n"
            "Project: "+scope["project_id"]+"\\n"
            "Rail: "+scope["rail_id"]+"\\n"
            "Original source camera: "+scope["source_camera_id"]+"\\n"
            "Shot technique: "+str(scope["shot_technique"])+"\\n"
            "Exact original Film Time ticks: "+str(scope["film_start_tick"])+
                " → "+str(scope["film_end_tick"])+"\\n"
            "Source camera bank SHA: "+scope["camera_bank_sha256"]+"\\n"
            "Original ActorID/performance SHA: "+scope[
                "source_performance_sha256"]+"\\n"
            "Frozen world Take SHA: "+scope["world_take_sha256"]+"\\n"
            "Director rail proposal SHA: "+scope["proposed_rail_sha256"]+"\\n"
            "Stronger OpenUSD layer SHA: "+scope["stronger_usd_layer_sha256"]+"\\n"
            "Previous rail revision: "+str(scope["expected_revision"])+"\\n\\n"
            "This publishes ONE immutable director camera-layer revision. "
            "It neither moves original actors nor alters the frozen PCM. "
            "No render worker is authorized and no Cycles picture is approved.\\n"
            "Approve this exact director-edited virtual rail?")
        return self._native_window().create_confirmation_dialog(
            "NVP — Approve Virtual Camera Rail",message) is True

    def camfx02_publish(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","rail_id","rail_spec","expected_revision",
                "preview_sha256"}:
            raise PermissionError("Only current source-pinned camera path publication")
        pid=self._wo5_project(request["project_id"])
        from backend.nvp_cam_fx01_camera_rails import OriginalCameraRails
        nonce=object()
        used=[False]
        def confirm(event,scope):
            if event is not nonce or used[0]:
                return False
            used[0]=True
            return self._camfx02_confirm(scope)
        return OriginalCameraRails(
            self.index,verify_director_action=confirm).publish(
            pid,request["rail_id"],request["rail_spec"],
            expected_revision=request["expected_revision"],
            preview_sha256=request["preview_sha256"],director_event=nonce)

    def camfx02_reopen(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","rail_id","revision"}:
            raise PermissionError("Only exact authored virtual rail reopen")
        pid=self._wo5_project(request["project_id"])
        from backend.nvp_cam_fx02_usd_camera_layer import (
            open_approved_camera_layer)
        from backend.nvp_cam_fx01_camera_rails import OriginalCameraRails
        from backend.nvp_film_index import _id
        _id(request["rail_id"],"approved director rail")
        rail=OriginalCameraRails(
            self.index,verify_director_action=lambda *_:False).verify(
            pid,request["rail_id"],request["revision"])
        with open_approved_camera_layer(
                self.index,pid,request["rail_id"],request["revision"]) as native:
            sample_count=len(native["native_verified_time_samples"])
            if not native["source_world_root_layer_unchanged"]:
                raise RuntimeError("Original source was modified by rail recompose")
        return {
            "format":"nvp.cam_fx02.trusted_native_director_rail_reopen.v1",
            "project_id":pid,"rail_id":request["rail_id"],
            "revision":request["revision"],"rail_spec":rail["rail_spec"],
            "layer_sha256":rail["rail_layer_sha256"],
            "world_take_sha256":rail["world_take_sha256"],
            "camera_bank_sha256":rail["camera_bank_sha256"],
            "native_camera_path":native["camera_path"],
            "native_reopened_sample_count":sample_count,
            "native_stronger_layer_verified":True,
            "frozen_actor_takes_and_pcm_unchanged":True,
            "creative_render_approved":False}

    def camfx02_sample(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","rail_id","revision","film_tick"}:
            raise PermissionError("Exact original film-timed rail readback only")
        pid=self._wo5_project(request["project_id"])
        from backend.nvp_cam_fx01_camera_rails import (
            OriginalCameraRails,evaluate_rail)
        from backend.nvp_cam_fx02_usd_camera_layer import (
            open_approved_camera_layer)
        rail=OriginalCameraRails(
            self.index,verify_director_action=lambda *_:False).verify(
            pid,request["rail_id"],request["revision"])
        sample=evaluate_rail(rail["rail_spec"],request["film_tick"])
        # Recompose the real native layer before exposing source-derived
        # controls; do not allow browser-selected USD paths.
        with open_approved_camera_layer(
                self.index,pid,request["rail_id"],request["revision"]) as native:
            if native["rail_layer_sha256"]!=rail["rail_layer_sha256"]:
                raise RuntimeError("Stronger original camera layer changed")
        return {"format":"nvp.cam_fx02.native_rail_film_tick_pose.v1",
                "project_id":pid,"rail_id":request["rail_id"],
                "revision":request["revision"],
                "rail_layer_sha256":rail["rail_layer_sha256"],
                "film_tick":request["film_tick"],"sample":sample,
                "source_actor_pcm_changed":False,
                "native_worker_started":False}
