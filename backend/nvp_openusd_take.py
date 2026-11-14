"""USD-01B/C: exact temporal-ledger/scene binding and immutable Digital Take.

The scene layers and authored events stay DATA. A Digital Take freezes exact
source revision hashes, semantic event manifest, and evidence sampled at
authored time. No frames, final presentation, or AI-model outputs are made.
A trusted host must supply an explicit creator-action verifier.
"""
from __future__ import annotations

import hashlib
import json

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_temporal_ledger import TemporalLedger, _int
from backend.nvp_openusd_channels import evaluate_parameter_channels
from backend.nvp_openusd_scene import (
    OpenUSDSceneBridge, _evaluate, _usd, MAX_USD_EXACT_TICK, FORMAT as SCENE_FORMAT)

FORMAT = "nvp.digital_take.openusd_temporal.v1"
MAX_CHECKPOINTS = 32


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",",":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def sha(data):
    return hashlib.sha256(canonical(data)).hexdigest()


class OpenUSDTakeCapture:
    def __init__(self, index: FilmIndex, *, verify_creator_action):
        if not isinstance(index,FilmIndex) or not callable(verify_creator_action):
            raise TypeError("Trusted FilmIndex and creator authorization required")
        self.index = index
        self.scene = OpenUSDSceneBridge(index)
        self.temporal = TemporalLedger(index)
        self._approve = verify_creator_action

    def _sources(self, project_id, scene_id, scene_revision,
                 timeline_id, timeline_revision):
        source,stage=self.scene.open(project_id,scene_id,scene_revision)
        timeline=self.temporal._revision(project_id,timeline_id,timeline_revision)
        evidence=self.temporal.verify(project_id,timeline_id,timeline_revision)
        if evidence["document_sha256"]!=timeline["document_sha256"]:
            raise RuntimeError("Timed authored source manifest is not stable")
        duration=timeline["data"]["duration_tick"]
        if duration>MAX_USD_EXACT_TICK:
            raise RuntimeError("Authoring tick exceeds exact OpenUSD timecode domain")
        with self.index.studio._connection() as db:
            rows=db.execute("""SELECT event_id,payload_json FROM nvp_temporal_events
                WHERE project_id=? AND timeline_id=? AND revision=?""",
                (project_id,timeline_id,timeline_revision))
            paths={r["event_id"]:json.loads(r["payload_json"]).get("usd_prim_path")
                   for r in rows}
        roles=source["data"]["prim_roles"]
        for eid,path in paths.items():
            if path is not None and path not in roles:
                raise RuntimeError("Timed event "+eid+" targets an absent scene prim")
        return source,timeline,stage,duration

    def sample(self, project_id, scene_id, scene_revision,
               timeline_id, timeline_revision, *, tick, paths=None):
        """Evaluate one DATA checkpoint without frames or frame-rate choice."""
        src,timeline,stage,duration=self._sources(
            project_id,scene_id,scene_revision,timeline_id,timeline_revision)
        _int(tick,"capture tick",maximum=MAX_USD_EXACT_TICK)
        if tick>=duration:
            raise ValueError("Checkpoint outside frozen source duration")
        _,Sdf,Usd,UsdGeom=_usd()
        requested=(sorted(src["data"]["prim_roles"]) if paths is None
                   else sorted(paths))
        if not requested or len(requested)>256:
            raise ValueError("Invalid bounded OpenUSD sample scope")
        if len(set(requested))!=len(requested) or any(
            p not in src["data"]["prim_roles"] for p in requested):
            raise ValueError("Requested prim path is not part of source scene")
        transforms=[_evaluate(stage,p,tick,Sdf,Usd,UsdGeom)
                    for p in requested]
        events=self.temporal.events_at(
            project_id,timeline_id,timeline_revision,tick=tick,limit=500)
        values=evaluate_parameter_channels(
            stage,src["data"].get("performance_channels",[]),
            src["data"]["prim_roles"],tick)
        native=[]
        if src["data"].get("native_schema_version"):
            from backend.nvp_openusd_native_schemas import evaluate_native_schema
            for p in requested:
                item=evaluate_native_schema(
                    stage,p,src["data"]["prim_roles"][p],tick,values)
                if item is not None:
                    native.append(item)
        result={"format":"nvp.usd_time_checkpoint.v1",
                "tick":tick,"scene_document_sha256":src["document_sha256"],
                "performance_channels":values,
                "timeline_document_sha256":timeline["document_sha256"],
                "transforms":transforms,"active_events":events,
                "rendered_frames":False}
        if src["data"].get("native_schema_version"):
            result["native_scene_schemas"]=native
        if src["data"].get("skeleton_rigs"):
            from backend.nvp_openusd_skeleton import evaluate_skeletons
            result["skeletal_pose"]=evaluate_skeletons(
                stage,src["data"]["skeleton_rigs"],tick)
        return result

    def freeze(self, project_id, take_id, *,
               scene_id, scene_revision, timeline_id, timeline_revision,
               sample_ticks, creator_event):
        """Publish a single-commit take by freezing exact existing source data.

        Authorization is checked against the fully evaluated source scope;
        no user-supplied booleans can grant creator approval.
        """
        _require_pid(project_id)
        for oid in (take_id,scene_id,timeline_id):
            _id(oid,"take/source ID")
        if take_id in (scene_id,timeline_id) or scene_id==timeline_id:
            raise ValueError("Digital Take and its sources need distinct identities")
        if (type(sample_ticks) is not list or
            not 1<=len(sample_ticks)<=MAX_CHECKPOINTS):
            raise ValueError("Digital Take needs bounded selected event times")
        if sorted(set(sample_ticks))!=sample_ticks:
            raise ValueError("Take sample ticks must be sorted and unique")
        source,timeline,stage,duration=self._sources(
            project_id,scene_id,scene_revision,timeline_id,timeline_revision)
        _,Sdf,Usd,UsdGeom=_usd()
        prims=sorted(source["data"]["prim_roles"])
        checkpoints=[]
        for tick in sample_ticks:
            _int(tick,"capture checkpoint",maximum=MAX_USD_EXACT_TICK)
            if tick>=duration:
                raise ValueError("Take checkpoint beyond scene duration")
            positions=[_evaluate(stage,p,tick,Sdf,Usd,UsdGeom)
                       for p in prims]
            active=self.temporal.events_at(
                project_id,timeline_id,timeline_revision,tick=tick,limit=500)
            checkpoint={"tick":tick,"poses":positions,
                        "active_event_ids":[x["event_id"] for x in active]}
            if source["data"].get("performance_channels"):
                checkpoint["performance_channels"]=evaluate_parameter_channels(
                    stage,source["data"]["performance_channels"],
                    source["data"]["prim_roles"],tick)
            if source["data"].get("native_schema_version"):
                from backend.nvp_openusd_native_schemas import evaluate_native_schema
                values=evaluate_parameter_channels(
                    stage,source["data"].get("performance_channels",[]),
                    source["data"]["prim_roles"],tick)
                checkpoint["native_scene_schemas"]=[
                    value for p in prims
                    if (value:=evaluate_native_schema(
                        stage,p,source["data"]["prim_roles"][p],tick,
                        values)) is not None]
            if source["data"].get("skeleton_rigs"):
                from backend.nvp_openusd_skeleton import evaluate_skeletons
                checkpoint["skeletal_pose"]=evaluate_skeletons(
                    stage,source["data"]["skeleton_rigs"],tick)
            checkpoints.append(checkpoint)
        snapshot_sha=sha(checkpoints)
        scoped={
            "operation":"nvp.freeze.usd_temporal_take.v1",
            "project_id":project_id,"take_id":take_id,
            "scene_id":scene_id,"scene_revision":scene_revision,
            "scene_document_sha256":source["document_sha256"],
            "timeline_id":timeline_id,"timeline_revision":timeline_revision,
            "timeline_document_sha256":timeline["document_sha256"],
            "duration_tick":duration,"checkpoint_sha256":snapshot_sha,
            "checkpoint_ticks":sample_ticks,
        }
        if self._approve(creator_event,dict(scoped)) is not True:
            raise PermissionError("Creator did not authorize exact Digital Take freeze")
        # Metadata dependency versions are immutable and validated again in
        # FilmIndex's transactional edge checks. Source blobs are reverified
        # on reopen; no external USD asset path is implicitly trusted.
        check_scene=self.index.read_revision(project_id,scene_id,scene_revision)
        check_time=self.index.read_revision(project_id,timeline_id,timeline_revision)
        if (check_scene["document_sha256"]!=source["document_sha256"] or
            check_time["document_sha256"]!=timeline["document_sha256"]):
            raise RuntimeError("Frozen take source revision changed")
        manifest={
            "format":FORMAT,
            "scene_id":scene_id,"scene_revision":scene_revision,
            "scene_document_sha256":source["document_sha256"],
            "timeline_id":timeline_id,"timeline_revision":timeline_revision,
            "timeline_document_sha256":timeline["document_sha256"],
            "duration_tick":duration,
            "ticks_per_second":timeline["data"]["ticks_per_second"],
            "layout_layer_sha256":source["data"]["layout_layer_sha256"],
            "motion_layer_sha256":source["data"]["motion_layer_sha256"],
            "asset_bindings":source["data"].get("asset_bindings",[]),
            "parameter_layer_sha256":source["data"].get("parameter_layer_sha256"),
            "performance_channels":source["data"].get("performance_channels",[]),
            "sample_ticks":sample_ticks,"sample_digest_sha256":snapshot_sha,
            "native_schema_version":source["data"].get("native_schema_version"),
            "skeleton_layer_sha256":source["data"].get("skeleton_layer_sha256"),
            "skeleton_rigs":source["data"].get("skeleton_rigs",[]),
            "host_creator_action_verified":True,
            "artist_presentation_approved":False,
            "frozen":True,"rendered_frames":False,
        }
        return self.index.register_revision(
            project_id,take_id,"take",manifest,expected_revision=0,
            dependencies=[
                {"object_id":scene_id,"revision":scene_revision,"role":"scene"},
                {"object_id":timeline_id,"revision":timeline_revision,"role":"temporal"},
            ])

    def verify_take(self, project_id, take_id):
        # A journaled filming Take is not readable while its multi-object
        # publication is incomplete. Historical Takes without a filming
        # receipt retain their existing independent creator-approval checks.
        # Import locally to avoid making the capture publisher a dependency
        # of the ordinary immutable Take reader.
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        publication=FilmingPublicationJournal(self.index).visibility(project_id,take_id)
        if publication["journaled"] and not publication["visible"]:
            raise PermissionError("Filming Take publication unavailable: "+publication["reason"])
        take=self.index.read_revision(project_id,take_id,1)
        manifest=take["data"]
        if (take["kind"]!="take" or manifest.get("format")!=FORMAT or
            manifest.get("frozen") is not True or
            manifest.get("artist_presentation_approved") is not False):
            raise RuntimeError("Not a frozen scene + temporal Digital Take")
        src,timeline,stage,duration=self._sources(
            project_id,manifest["scene_id"],manifest["scene_revision"],
            manifest["timeline_id"],manifest["timeline_revision"])
        if (src["document_sha256"]!=manifest["scene_document_sha256"] or
            timeline["document_sha256"]!=manifest["timeline_document_sha256"] or
            duration!=manifest["duration_tick"] or
            src["data"]["layout_layer_sha256"]!=manifest["layout_layer_sha256"] or
            src["data"]["motion_layer_sha256"]!=manifest["motion_layer_sha256"] or
            src["data"].get("asset_bindings",[])!=manifest.get("asset_bindings",[]) or
            src["data"].get("parameter_layer_sha256")!=manifest.get("parameter_layer_sha256") or
            src["data"].get("performance_channels",[])!=manifest.get("performance_channels",[]) or
            src["data"].get("native_schema_version")!=manifest.get("native_schema_version") or
            src["data"].get("skeleton_layer_sha256")!=manifest.get("skeleton_layer_sha256") or
            src["data"].get("skeleton_rigs",[])!=manifest.get("skeleton_rigs",[])):
            raise RuntimeError("Frozen scene/timed film source changed")
        _,Sdf,Usd,UsdGeom=_usd()
        poses=[]
        for tick in manifest["sample_ticks"]:
            positions=[_evaluate(stage,p,tick,Sdf,Usd,UsdGeom)
                       for p in sorted(src["data"]["prim_roles"])]
            events=self.temporal.events_at(
                project_id,manifest["timeline_id"],manifest["timeline_revision"],
                tick=tick,limit=500)
            checkpoint={"tick":tick,"poses":positions,
                        "active_event_ids":[x["event_id"] for x in events]}
            if src["data"].get("performance_channels"):
                checkpoint["performance_channels"]=evaluate_parameter_channels(
                    stage,src["data"]["performance_channels"],
                    src["data"]["prim_roles"],tick)
            if src["data"].get("native_schema_version"):
                from backend.nvp_openusd_native_schemas import evaluate_native_schema
                values=evaluate_parameter_channels(
                    stage,src["data"].get("performance_channels",[]),
                    src["data"]["prim_roles"],tick)
                checkpoint["native_scene_schemas"]=[
                    value for p in sorted(src["data"]["prim_roles"])
                    if (value:=evaluate_native_schema(
                        stage,p,src["data"]["prim_roles"][p],tick,
                        values)) is not None]
            if src["data"].get("skeleton_rigs"):
                from backend.nvp_openusd_skeleton import evaluate_skeletons
                checkpoint["skeletal_pose"]=evaluate_skeletons(
                    stage,src["data"]["skeleton_rigs"],tick)
            poses.append(checkpoint)
        if sha(poses)!=manifest["sample_digest_sha256"]:
            raise RuntimeError("Frozen Digital Take sampled state digest changed")
        return {"status":"VERIFIED_FROZEN_DATA_TAKE",
                "take_id":take_id,"take_document_sha256":take["document_sha256"],
                "scene_document_sha256":src["document_sha256"],
                "timeline_document_sha256":timeline["document_sha256"],
                "checkpoint_count":len(poses),
                "rendered_frames":False,"presentation_approved":False}
