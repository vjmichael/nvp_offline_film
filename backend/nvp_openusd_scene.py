"""USD-01A: NVP-owned, composable OpenUSD scenes evaluated in authored film time.

Native USD is intentionally imported only inside this adapter. No external
USD paths, references, payloads, asset resolver or renderer are accepted in
this first trusted, typed authoring path. USD is scene data, NOT FilmIndex
authority, media access authorization or creator approval.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_temporal_ledger import TICKS_PER_SECOND, _int

FORMAT = "nvp.scene.openusd.composition.v1"
LAYER_TYPE = "application/vnd.pixar.usd.ascii"
MAX_PRIMS = 256
MAX_CURVES = 512
MAX_SAMPLES_PER_CURVE = 4096
MAX_USD_LAYER_BYTES = 8 * 1024 * 1024
# All integer ticks in this range round-trip exactly through OpenUSD's
# IEEE-754 double Usd.TimeCode. This spans ~14.8 days at our tick rate.
MAX_USD_EXACT_TICK = 2**53 - 1
ROLES = frozenset({"actor", "camera", "prop", "environment", "light", "anchor"})


def _usd():
    try:
        from pxr import Gf, Sdf, Usd, UsdGeom
    except ImportError as exc:
        raise RuntimeError("Native OpenUSD (usd-core / pxr) is required") from exc
    return Gf, Sdf, Usd, UsdGeom


def _path(value, Sdf):
    if (type(value) is not str or len(value) > 240 or
        not value.startswith("/World/")):
        raise ValueError("A scene object needs an absolute /World/ prim path")
    path = Sdf.Path(value)
    if (not path.IsAbsolutePath() or not path.IsPrimPath() or
        path.ContainsPrimVariantSelection() or path.name in ("", "World")):
        raise ValueError("Invalid or ambiguous OpenUSD scene prim path")
    return value


def _vector(value):
    if (type(value) is not list or len(value) != 3 or
        any(type(x) not in (float, int) or not math.isfinite(x)
            or abs(x) > 1_000_000 for x in value)):
        raise ValueError("Expected finite 3D position")
    return [float(x) for x in value]


def _digest(doc):
    return hashlib.sha256(json.dumps(
        doc,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()


def _layer_from_text(text, label, Sdf):
    layer = Sdf.Layer.CreateAnonymous(label)
    if not layer.ImportFromString(text):
        raise RuntimeError("Frozen OpenUSD layer could not be imported")
    return layer


def _compose(base, motion, Sdf, Usd):
    # Strongest first: animation opinions supersede the layout layer.
    root = Sdf.Layer.CreateAnonymous("nvp_composed.usda")
    root.subLayerPaths = [motion.identifier, base.identifier]
    stage = Usd.Stage.Open(root, Usd.Stage.LoadNone)
    if not stage:
        raise RuntimeError("Native OpenUSD composition returned no scene")
    stage.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
    return stage


def _evaluate(stage, path, tick, Sdf, Usd, UsdGeom):
    _int(tick, "film time", maximum=MAX_USD_EXACT_TICK)
    _path(path,Sdf)
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsDefined() or not prim.IsA(UsdGeom.Xform):
        raise KeyError("Composed OpenUSD prim is missing or not a transform")
    transform = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
        Usd.TimeCode(float(tick)))
    pos = transform.ExtractTranslation()
    xyz = [float(pos[i]) for i in range(3)]
    if not all(math.isfinite(x) for x in xyz):
        raise RuntimeError("OpenUSD scene transform was nonfinite")
    return {"prim_path":path,"time_tick":tick,
            "world_translation":xyz,"frames_rendered":False}


class OpenUSDSceneBridge:
    def __init__(self, index: FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("A trusted FilmIndex is required")
        self.index=index

    def publish(self, project_id, scene_id, *, prims, curves,
                expected_revision=0):
        """Create immutable world+motion layer blobs and an exact scene revision.

        A failed FilmIndex publication may leave *orphan blobs*, not an approved
        scene. Only NVP-typed material is allowed, no arbitrary USD import.
        """
        _require_pid(project_id)
        _id(scene_id,"scene ID")
        _int(expected_revision,"expected scene revision")
        if (type(prims) is not list or not 1<=len(prims)<=MAX_PRIMS or
            type(curves) is not list or len(curves)>MAX_CURVES):
            raise ValueError("Scene prim/curve authoring budget exceeded")
        Gf,Sdf,Usd,UsdGeom=_usd()
        base=Sdf.Layer.CreateAnonymous("nvp_layout.usda")
        layout=Usd.Stage.Open(base)
        layout.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
        UsdGeom.Xform.Define(layout,"/World")
        paths={}
        for value in prims:
            if type(value) is not dict or set(value)!={"path","role","position"}:
                raise ValueError("Invalid typed scene prim")
            path=_path(value["path"],Sdf)
            role=value["role"]
            if role not in ROLES or path in paths:
                raise ValueError("Duplicate scene path or invalid semantic role")
            pos=_vector(value["position"])
            prim=UsdGeom.Xform.Define(layout,path)
            prim.GetPrim().CreateAttribute(
                "nvp:semanticRole",Sdf.ValueTypeNames.String).Set(role)
            UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(*pos))
            paths[path]=role
        motion=Sdf.Layer.CreateAnonymous("nvp_performance.usda")
        moving=Usd.Stage.Open(motion)
        moving.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
        animated=set()
        for curve in curves:
            if type(curve) is not dict or set(curve)!={"path","samples"}:
                raise ValueError("Invalid typed OpenUSD animation curve")
            path=_path(curve["path"],Sdf)
            if path not in paths or path in animated:
                raise ValueError("Curve must target one declared scene object")
            samples=curve["samples"]
            if (type(samples) is not list or
                not 2<=len(samples)<=MAX_SAMPLES_PER_CURVE):
                raise ValueError("Motion curve needs at least two bounded samples")
            # Authored overrides are composed above immutable layout.
            xform=UsdGeom.Xform.Define(moving,path)
            api=UsdGeom.XformCommonAPI(xform)
            previous=-1
            for sample in samples:
                if type(sample) is not dict or set(sample)!={"tick","position"}:
                    raise ValueError("Invalid exact-time motion key")
                tick=_int(sample["tick"],"motion tick",
                          maximum=MAX_USD_EXACT_TICK)
                if tick<=previous:
                    raise ValueError("Motion sample ticks must strictly increase")
                previous=tick
                api.SetTranslate(Gf.Vec3d(*_vector(sample["position"])),
                                 time=Usd.TimeCode(float(tick)))
            animated.add(path)
        composed=_compose(base,motion,Sdf,Usd)
        for path in paths:
            _evaluate(composed,path,0,Sdf,Usd,UsdGeom)
        base_bytes=base.ExportToString().encode("utf-8")
        motion_bytes=motion.ExportToString().encode("utf-8")
        if (len(base_bytes)>MAX_USD_LAYER_BYTES or
            len(motion_bytes)>MAX_USD_LAYER_BYTES):
            raise ValueError("Authored OpenUSD layer exceeded blob policy")
        # The immutable scene references the layer *bytes*, not temp paths.
        bsha=self.index.put_blob(project_id,base_bytes,media_type=LAYER_TYPE)
        msha=self.index.put_blob(project_id,motion_bytes,media_type=LAYER_TYPE)
        manifest={"format":FORMAT,
                  "layer_order":["motion","layout"],
                  "layout_layer_sha256":bsha,
                  "motion_layer_sha256":msha,
                  "ticks_per_second":TICKS_PER_SECOND,
                  "usd_timecode_limit":MAX_USD_EXACT_TICK,
                  "prim_roles":paths,
                  "animated_paths":sorted(animated),
                  "contains_external_references":False,
                  "rendered":False,
                  "creator_approved":False}
        def guard(db):
            for sha in (bsha,msha):
                if db.execute("""SELECT 1 FROM film_blob_refs
                    WHERE project_id=? AND sha256=?""",
                    (project_id,sha)).fetchone() is None:
                    raise RuntimeError("Composed OpenUSD source layer lost before commit")
        return self.index.register_revision(
            project_id,scene_id,"scene",manifest,
            expected_revision=expected_revision,dependencies=[],
            precommit_guard=guard)

    def open(self, project_id, scene_id, revision):
        record=self.index.read_revision(project_id,scene_id,revision)
        doc=record["data"]
        if (record["kind"]!="scene" or doc.get("format")!=FORMAT or
            doc.get("layer_order")!=["motion","layout"] or
            doc.get("contains_external_references") is not False or
            doc.get("ticks_per_second")!=TICKS_PER_SECOND):
            raise RuntimeError("Scene is not an accepted typed OpenUSD source")
        Gf,Sdf,Usd,UsdGeom=_usd()
        base=_layer_from_text(
            self.index.get_blob(project_id,doc["layout_layer_sha256"]).decode(),
            "reopen_layout.usda",Sdf)
        motion=_layer_from_text(
            self.index.get_blob(project_id,doc["motion_layer_sha256"]).decode(),
            "reopen_motion.usda",Sdf)
        composed=_compose(base,motion,Sdf,Usd)
        for p,role in doc["prim_roles"].items():
            _evaluate(composed,p,0,Sdf,Usd,UsdGeom)
            observed=composed.GetPrimAtPath(p).GetAttribute("nvp:semanticRole").Get()
            if observed!=role:
                raise RuntimeError("Composed OpenUSD semantics changed")
        return record,composed

    def evaluate(self, project_id, scene_id, revision, *, path, tick):
        rec,stage=self.open(project_id,scene_id,revision)
        _,Sdf,Usd,UsdGeom=_usd()
        result=_evaluate(stage,path,tick,Sdf,Usd,UsdGeom)
        return {**result,"scene_id":scene_id,"scene_revision":revision,
                "scene_document_sha256":rec["document_sha256"],
                "usd_timecodes_per_second":TICKS_PER_SECOND}
