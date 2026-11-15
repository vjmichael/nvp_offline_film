"""USD-02B: data-only native scene state at an authored event-time tick.

Native OpenUSD resolves composed transforms, including references to bounded,
project-owned USD asset blobs. Semantic actions come from the immutable
Temporal Ledger, not from generated frames or an AI guess.
"""
from __future__ import annotations

import hashlib
import json
import math

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_scene import (
    OpenUSDSceneBridge, _path, _usd, MAX_USD_EXACT_TICK)
from backend.nvp_temporal_ledger import TemporalLedger, _int
from backend.nvp_openusd_channels import evaluate_parameter_channels

FORMAT = "nvp.usd.scene_state.v1"
MAX_SCENE_OBJECTS = 128
MAX_ACTIVE_EVENTS = 250


def _canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",",":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


class OpenUSDTimeState:
    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Temporal scene state requires trusted FilmIndex")
        self.index = index
        self.scene = OpenUSDSceneBridge(index)
        self.ledger = TemporalLedger(index)

    def evaluate(self, project_id, scene_id, scene_revision,
                 timeline_id, timeline_revision, *, tick, paths=None):
        _require_pid(project_id)
        _id(scene_id,"source USD scene ID")
        _id(timeline_id,"source event timeline ID")
        _int(tick,"film time",maximum=MAX_USD_EXACT_TICK)
        scene,stage=self.scene.open(project_id,scene_id,scene_revision)
        timeline=self.ledger._revision(
            project_id,timeline_id,timeline_revision)
        if tick>=timeline["data"]["duration_tick"]:
            raise ValueError("Scene state sample exceeds authored take duration")
        declared=scene["data"]["prim_roles"]
        Gf,Sdf,Usd,UsdGeom=_usd()
        wanted=sorted(declared) if paths is None else sorted(paths)
        if (not wanted or len(wanted)>MAX_SCENE_OBJECTS or
            len(wanted)!=len(set(wanted)) or
            any(p not in declared for p in wanted)):
            raise ValueError("Invalid bounded scene-state evaluation scope")
        objects=[]
        for path in wanted:
            _path(path,Sdf)
            prim=stage.GetPrimAtPath(path)
            if not prim or not prim.IsDefined() or not prim.IsA(UsdGeom.Xformable):
                raise RuntimeError("Composed scene object is missing or not spatial")
            matrix=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
                Usd.TimeCode(float(tick)))
            values=[[float(matrix.GetRow(i)[j]) for j in range(4)]
                    for i in range(4)]
            if any(not math.isfinite(x) or abs(x)>1e12 for row in values
                   for x in row):
                raise RuntimeError("Nonfinite or unreasonable USD scene transform")
            position=[float(x) for x in matrix.ExtractTranslation()]
            objects.append({
                "path":path,"semantic_role":declared[path],
                "world_matrix":values,"world_translation":position,
                "asset":next((entry for entry in
                    scene["data"].get("asset_bindings",[])
                    if entry["path"]==path),None),
            })
        # Bound the result; do not run a full 3-hour film manifest audit per
        # interactive query. Final take publication runs verify() separately.
        active=self.ledger.events_at(project_id,timeline_id,timeline_revision,
                                     tick=tick,limit=MAX_ACTIVE_EVENTS+1)
        if len(active)>MAX_ACTIVE_EVENTS:
            raise RuntimeError("Authored event density exceeds bounded preview")
        for event in active:
            target=event["payload"].get("usd_prim_path")
            if target is not None and target not in declared:
                raise RuntimeError("Timed authored action targets an absent USD prim")
            source=self.index.read_revision(
                project_id,event["source_id"],event["source_revision"])
            if source["document_sha256"]!=event["source_document_sha256"]:
                raise RuntimeError("Timed event source revision no longer matches")
        native_schemas=[]
        if scene["data"].get("native_schema_version"):
            from backend.nvp_openusd_native_schemas import evaluate_native_schema
            sampled=evaluate_parameter_channels(
                stage,scene["data"].get("performance_channels",[]),declared,tick)
            for path in wanted:
                observation=evaluate_native_schema(
                    stage,path,declared[path],tick,sampled)
                if observation is not None:
                    native_schemas.append(observation)
        snapshot={
            "format":FORMAT,"time_tick":tick,
            "scene_document_sha256":scene["document_sha256"],
            "timeline_document_sha256":timeline["document_sha256"],
            "objects":objects,"active_events":active,
            "performance_channels":[p for p in evaluate_parameter_channels(
                stage,scene["data"].get("performance_channels",[]),
                declared,tick) if p["path"] in wanted],
            "rendered_frames":False,"source_full_audit":False,
        }
        if scene["data"].get("native_schema_version"):
            snapshot["native_scene_schemas"]=native_schemas
            snapshot["native_schema_version"]=scene["data"]["native_schema_version"]
        if scene["data"].get("skeleton_rigs"):
            from backend.nvp_openusd_skeleton import evaluate_skeletons
            snapshot["skeletal_pose"]=[
                item for item in evaluate_skeletons(
                    stage,scene["data"]["skeleton_rigs"],tick)
                if item["path"] in wanted]
        snapshot["snapshot_sha256"]=hashlib.sha256(
            _canonical(snapshot)).hexdigest()
        return snapshot
