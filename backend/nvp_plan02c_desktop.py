"""PLAN-02-C: first-party desktop-only CAMERA rail and local GGUF actions.

This mixin cannot be registered on FastAPI. Original Take/Film Time authority
is server-side; the model creates a reversible UNAPPROVED suggestion only.
Only an actual attached pywebview native OS dialog can publish a USD rail.
"""
from __future__ import annotations

from backend.nvp_film_index import _require_pid
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_time_state import OpenUSDTimeState
from backend.nvp_plan02c_rails import CanonicalSourceRails
from backend.nvp_model_service import discover_models
from backend.nvp_wo6_verified_local_model import verified_writer_for

CATALOG="nvp.plan02c.canonical_camera_source_catalog.v1"


class NativePlan02CCameraActions:
    def _plan02c(self):
        self._native_window()
        if not hasattr(self,"_plan02c_rails"):
            self._plan02c_rails=CanonicalSourceRails(
                self.index,approve=self._plan02c_approve)
        return self._plan02c_rails

    def _plan02c_approve(self,scope):
        if (scope.get("operation")!="nvp.plan02c.publish_source_rail.v1" or
                self._closing):
            return False
        return self._ask(
            "Publish ONE reviewed derivative camera rail?\n"
            "Rail: "+scope["rail_id"]+
            "\nSource Take SHA: "+scope["source_take_sha256"]+
            "\nOriginal camera timeline SHA: "+scope["camera_timeline_sha256"]+
            "\nOriginal camera: "+scope["source_camera_path"]+
            "\nSource Film Time ticks: "+str(scope["film_start_tick"])+
            " .. "+str(scope["film_end_tick"])+
            "\nVerified proposal SHA: "+scope["proposal_sha256"]+
            "\nNew USD camera layer SHA: "+scope["layer_sha256"]+
            "\nNo original PCM, ActorID or Take changes; "
            "NO renderer or film-master permission.")

    def plan02c_catalog(self,project_id):
        self._native_window()
        pid=_require_pid(project_id)
        source=ExactTimeShotSequence(self.index)
        take_reader=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda *_:False)
        choices=[]
        candidates=[]
        for row in self.index.list_objects(pid,kind="temporal")[:64]:
            try:
                plan=source.read(pid,row["object_id"],row["head_revision"])
                candidates.append(plan)
            except (ValueError,RuntimeError,KeyError,PermissionError):
                continue
        for row in self.index.list_objects(pid,kind="take")[:32]:
            try:
                receipt=take_reader.verify_take(pid,row["object_id"])
                take=self.index.read_revision(pid,row["object_id"],1)
            except (ValueError,RuntimeError,KeyError,PermissionError):
                continue
            data=take["data"]
            for plan in candidates:
                if (plan["scene_id"]!=data["scene_id"] or
                    plan["scene_revision"]!=data["scene_revision"] or
                    plan["scene_document_sha256"]!=data["scene_document_sha256"]):
                    continue
                for shot in plan["shots"][:8]:
                    start=int(shot["start_tick"])
                    end=min(int(shot["end_tick"]),
                            int(data["duration_tick"]),
                            start+2*7056000000)
                    if end<=start:continue
                    snap=OpenUSDTimeState(self.index).evaluate(
                        pid,data["scene_id"],data["scene_revision"],
                        data["timeline_id"],data["timeline_revision"],
                        tick=start,paths=[shot["camera_path"]])
                    camera=next(o for o in snap["objects"]
                                if o["path"]==shot["camera_path"])
                    pos=[float(v) for v in camera["world_translation"]]
                    target=[pos[0],pos[1]+3.0,pos[2]]
                    def node(t):
                        return {
                            "tick":t,"position_m":[0.,0.,0.],
                            "target_m":[target[i]-pos[i] for i in range(3)],
                            "tangent_in_mps":[0.,0.,0.],
                            "tangent_out_mps":[0.,0.,0.],
                            "roll_deg":0.,
                            "focal_length_mm":35.,
                            "focus_distance_m":3.,
                            "f_stop":5.6,"segment_mode":"hermite",
                            "easing":"smoothstep"}
                    spec={
                        "take_id":row["object_id"],
                        "take_document_sha256":receipt["take_document_sha256"],
                        "camera_timeline_id":plan["timeline_id"],
                        "camera_timeline_revision":plan["revision"],
                        "camera_timeline_sha256":plan["document_sha256"],
                        "source_camera_path":shot["camera_path"],
                        "camera_id":"DirectorRailCam",
                        "film_start_tick":start,"film_end_tick":end,
                        "technique":"static",
                        "rail_origin_m":pos,
                        "filmback_mm":[36.,20.25],
                        "nodes":[node(start),node(end)]}
                    choices.append({"source_take_id":row["object_id"],
                        "camera_timeline_id":plan["timeline_id"],
                        "source_camera_path":shot["camera_path"],
                        "source_film_start_tick":str(start),
                        "source_film_end_tick":str(end),
                        "suggested_unapproved_rail_spec":spec,
                        "source_sample_sha256":snap["snapshot_sha256"]})
                    if len(choices)>=32:break
                if len(choices)>=32:break
            if len(choices)>=32:break
        return {"format":CATALOG,"project_id":pid,
                "sources":choices,"original_modified":False,
                "all_suggestions_unapproved":True}

    def plan02c_preview(self,request):
        self._native_window()
        if type(request) is not dict or set(request)!={
                "project_id","rail_id","expected_revision","rail_spec"}:
            raise PermissionError("Only exact source camera rail preview")
        pid=_require_pid(request["project_id"])
        return self._plan02c().preview(
            pid,request["rail_id"],request["rail_spec"],
            expected_revision=request["expected_revision"])

    def plan02c_publish(self,request):
        self._native_window()
        if type(request) is not dict or set(request)!={
                "project_id","rail_id","expected_revision",
                "rail_spec","preview_sha256"}:
            raise PermissionError("Only pinned preview may request native rail approval")
        pid=_require_pid(request["project_id"])
        return self._plan02c().publish(
            pid,request["rail_id"],request["rail_spec"],
            request["expected_revision"],request["preview_sha256"])

    def plan02c_models(self):
        self._native_window()
        data=discover_models()
        return {"format":"nvp.plan02c.available_loopback_gguf_models.v1",
                **data,"provider_model_list_not_attestation":True}

    def plan02c_model_candidate(self,request):
        self._native_window()
        if type(request) is not dict or set(request)!={
                "project_id","rail_id","expected_revision",
                "rail_spec","model_id","direction"}:
            raise PermissionError("Only reviewed source-bound local model advice")
        pid=_require_pid(request["project_id"])
        service=self._plan02c()
        # Source must already survive a genuine 3D USD layer preview.
        preview=service.preview(
            pid,request["rail_id"],request["rail_spec"],
            expected_revision=request["expected_revision"])
        model_id=request["model_id"]
        if type(model_id) is not str or not 1<=len(model_id)<=256:
            raise ValueError("Select a verified loopback model identity")
        # This local inference authorization is NOT authorization to
        # publish a camera rail or launch an external rendering worker.
        if not self._ask(
                "Ask the selected LOCAL model for UNAPPROVED camera advice?\n"
                "Model: "+model_id+
                "\nOriginal Take SHA: "+preview["take_document_sha256"]+
                "\nFilm Time camera SHA: "+preview["camera_timeline_sha256"]+
                "\nProposal SHA: "+preview["proposal_sha256"]+
                "\nThe model may not edit any source or approve a rail."):
            raise PermissionError("Human refused local GGUF camera proposal")
        self._native_window()
        from backend.nvp_plan02c_model_advice import generate_source_camera_advice
        writer=verified_writer_for(model_id)
        outcome=generate_source_camera_advice(
            service,pid,request["rail_spec"],
            direction=request["direction"],model_id=model_id,
            writer=writer)
        self._native_window()
        # A new model-derived rail must be reviewed via plan02c_preview
        # and a FRESH separate OS approval for plan02c_publish.
        return {**outcome,"model_request_human_approved":True,
                "rail_publication_human_approved":False}
