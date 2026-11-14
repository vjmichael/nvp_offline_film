"""USD-01D: bounded, style-bound presentation plan from ONE frozen Digital Take.

This is structured world-state data for conventional or future AI renderers.
It does not render pixels, start workers, or infer motion beyond native USD
time samples and declared composition. No final presentation is approved.
"""
from __future__ import annotations

from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_openusd_take import OpenUSDTakeCapture, canonical, sha
from backend.nvp_openusd_scene import OpenUSDSceneBridge, _evaluate, _usd
from backend.nvp_temporal_ledger import TemporalLedger
from backend.nvp_temporal_projection import TemporalProjection
from backend.nvp_openusd_channels import evaluate_parameter_channels

FORMAT = "nvp.openusd.presentation_plan.v1"
MAX_PRIMS = 64


class OpenUSDPresentationPlanner:
    def __init__(self, index: FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("FilmIndex is required for presentation planning")
        self.index=index
        self.scene=OpenUSDSceneBridge(index)
        self.temporal=TemporalLedger(index)
        self.projection=TemporalProjection(self.temporal)

    def prepare(self, project_id, take_id, *, style_id, style_revision,
                start_tick, end_tick, fps_num, fps_den,
                shot_id=None, shot_revision=None):
        _id(take_id,"frozen Digital Take ID")
        _id(style_id,"presentation style ID")
        take=self.index.read_revision(project_id,take_id,1)
        info=take["data"]
        if (take["kind"]!="take" or
            info.get("format")!="nvp.digital_take.openusd_temporal.v1" or
            info.get("frozen") is not True):
            raise RuntimeError("Presentation requires exact frozen OpenUSD Digital Take")
        style=self.index.read_revision(project_id,style_id,style_revision)
        if style["kind"]!="style":
            raise RuntimeError("Presentation style must be an exact FilmIndex style revision")
        scene,stage=self.scene.open(
            project_id,info["scene_id"],info["scene_revision"])
        timeline=self.temporal._revision(
            project_id,info["timeline_id"],info["timeline_revision"])
        if (shot_id is None)!=(shot_revision is None):
            raise ValueError("Shot ID and exact revision must be selected together")
        shot_record=None
        shot_opinions=set()
        if shot_id is not None:
            from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
            reader=OpenUSDShotOverrides(
                self.index,verify_director_action=lambda *_:False)
            shot_record,shot_scene,stage=reader.open_shot(
                project_id,shot_id,shot_revision,tick=start_tick)
            sd=shot_record["data"]
            if (sd["take_id"]!=take_id or
                sd["take_document_sha256"]!=take["document_sha256"] or
                sd["scene_document_sha256"]!=scene["document_sha256"] or
                end_tick>sd["end_tick"]):
                raise RuntimeError("Shot override not scoped to selected frozen Take/time")
            shot_opinions={(item["path"],item["property"])
                           for item in sd["opinions"]}
        if (scene["document_sha256"]!=info["scene_document_sha256"] or
            timeline["document_sha256"]!=info["timeline_document_sha256"]):
            raise RuntimeError("Frozen performance source changed")
        # FilmIndex revisions and OpenUSD layer blob hashes are checked above.
        # Do NOT stream the entire feature-length event ledger or re-evaluate
        # all frozen checkpoints for each interactive preview window.
        # verify_take() is a deliberate full-integrity acceptance operation.
        plan=self.projection.prepare(
            project_id,info["timeline_id"],info["timeline_revision"],
            start_tick=start_tick,end_tick=end_tick,
            fps_num=fps_num,fps_den=fps_den)
        paths=sorted(scene["data"]["prim_roles"])
        if not paths or len(paths)>MAX_PRIMS:
            raise RuntimeError("Requested scene exceeds bounded first USD presentation evaluator")
        _,Sdf,Usd,UsdGeom=_usd()
        samples=[]
        for sample in plan["presentation_samples"]:
            t=sample["time_tick"]
            positions=[_evaluate(stage,path,t,Sdf,Usd,UsdGeom)
                       for path in paths]
            channels=evaluate_parameter_channels(
                stage,scene["data"].get("performance_channels",[]),
                scene["data"]["prim_roles"],t)
            item={
                "output_frame_zero":sample["presentation_frame_zero"],
                "time_tick":t,
                "world_state":positions,
                "performance_channels":channels,
            }
            if scene["data"].get("native_schema_version"):
                from backend.nvp_openusd_native_schemas import evaluate_native_schema
                item["native_scene_schemas"]=[
                    value for path in paths
                    if (value:=evaluate_native_schema(
                        stage,path,scene["data"]["prim_roles"][path],t,
                        [entry for entry in channels
                         if (entry["path"],"camera_focal_length_mm"
                             if entry["property"]=="camera.focal_length_mm"
                             else "light_intensity"
                             if entry["property"]=="light.intensity"
                             else entry["property"]) not in shot_opinions]
                        )) is not None]
            if scene["data"].get("skeleton_rigs"):
                from backend.nvp_openusd_skeleton import evaluate_skeletons
                item["skeletal_pose"]=evaluate_skeletons(
                    stage,scene["data"]["skeleton_rigs"],t)
            samples.append(item)
        result={
            "format":FORMAT,"project_id":project_id,
            "frozen_take_id":take_id,
            "frozen_take_document_sha256":take["document_sha256"],
            "scene_document_sha256":scene["document_sha256"],
            "timeline_document_sha256":timeline["document_sha256"],
            "style_id":style_id,"style_revision":style_revision,
            "style_document_sha256":style["document_sha256"],
            "fps_num":fps_num,"fps_den":fps_den,
            "presentation_samples":samples,
            "source_state_sha256":sha(samples),
            "source_full_audit_this_operation":False,
            "revision_metadata_bound":True,
            "creator_approved_for_render":False,
            "frames_rendered":False,"output":"DATA_ONLY_NOT_RENDERED",
        }
        if shot_record is not None:
            result["director_shot_id"]=shot_id
            result["director_shot_revision"]=shot_revision
            result["director_shot_document_sha256"]=shot_record["document_sha256"]
            result["director_shot_source_layer_sha256"]=(
                shot_record["data"]["usd_layer_sha256"])
            result["intentional_continuity_cheat"]=(
                shot_record["data"]["continuity_policy"]=="intentional_cheat")
            result["shot_data_approved"]=True
            result["render_approved"]=False
        return result
