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
import os
from pathlib import Path

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_temporal_ledger import TICKS_PER_SECOND, _int

FORMAT = "nvp.scene.openusd.composition.v1"
LAYER_TYPE = "application/vnd.pixar.usd.ascii"
MAX_PRIMS = 256
MAX_CURVES = 512
MAX_ASSET_BINDINGS = 64
MAX_SAMPLES_PER_CURVE = 4096
MAX_USD_LAYER_BYTES = 8 * 1024 * 1024
# All integer ticks in this range round-trip exactly through OpenUSD's
# IEEE-754 double Usd.TimeCode. This spans ~14.8 days at our tick rate.
MAX_USD_EXACT_TICK = 2**53 - 1
ROLES = frozenset({"actor", "camera", "prop", "environment", "light", "anchor"})


def _native_publish_checkpoint(stage):
    """Opt-in, durable native crash locator; never writes scene/source content."""
    target = os.environ.get("NVP_SMOKE_DIAGNOSTIC_PATH")
    if not target:
        return
    path = Path(target)
    if path.is_symlink():
        raise RuntimeError("Refusing symlink diagnostic target")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("NVP_SMOKE_STAGE usd_publish_" + stage + "\n")
        stream.flush()
        os.fsync(stream.fileno())


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


def _compose(base, motion, Sdf, Usd, parameters=None, skeletons=None):
    # Strongest first: animation opinions supersede the layout layer.
    root = Sdf.Layer.CreateAnonymous("nvp_composed.usda")
    root.subLayerPaths = (
        ([skeletons.identifier] if skeletons is not None else []) +
        ([parameters.identifier] if parameters is not None else []) +
        [motion.identifier, base.identifier])
    stage = Usd.Stage.Open(root, Usd.Stage.LoadNone)
    if not stage:
        raise RuntimeError("Native OpenUSD composition returned no scene")
    stage.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
    # The composed root is a new stronger anonymous layer. It must copy
    # the immutable layout's authored global stage units/up-axis rather
    # than returning the generic USD defaults (centimeters/Y-up). Keep
    # the layout SHA unmodified; all statements are in-memory metadata.
    from pxr import UsdGeom
    original=Usd.Stage.Open(base,Usd.Stage.LoadNone)
    if not original:
        raise RuntimeError("Frozen layout stage cannot be reopened")
    UsdGeom.SetStageMetersPerUnit(stage,UsdGeom.GetStageMetersPerUnit(original))
    UsdGeom.SetStageUpAxis(stage,UsdGeom.GetStageUpAxis(original))
    return stage


def _evaluate(stage, path, tick, Sdf, Usd, UsdGeom):
    _int(tick, "film time", maximum=MAX_USD_EXACT_TICK)
    _path(path,Sdf)
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsDefined() or not UsdGeom.Xformable(prim):
        raise KeyError("Composed OpenUSD prim is missing or not xformable")
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
                expected_revision=0, asset_bindings=None,
                performance_channels=None, native_schemas=False,
                skeletal_rigs=None, actor_bindings=None,
                imported_character_sources=None):
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
        if type(native_schemas) is not bool:
            raise ValueError("Explicit native scene schema choice required")
        _native_publish_checkpoint("before_pxr")
        Gf,Sdf,Usd,UsdGeom=_usd()
        _native_publish_checkpoint("after_pxr")
        _native_publish_checkpoint("before_layout_layer_create")
        base=Sdf.Layer.CreateAnonymous("nvp_layout.usda")
        _native_publish_checkpoint("after_layout_layer_create")
        _native_publish_checkpoint("before_stage_open")
        layout=Usd.Stage.Open(base)
        _native_publish_checkpoint("after_stage_open")
        layout.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
        if native_schemas:
            from backend.nvp_openusd_native_schemas import METERS_PER_UNIT
            UsdGeom.SetStageMetersPerUnit(layout,METERS_PER_UNIT)
            # NVP authored coordinates use Z as vertical (elevation).
            # Persist that explicitly for all newly published native
            # scenes; old frozen USD layers remain SHA-stable and untouched.
            UsdGeom.SetStageUpAxis(layout,UsdGeom.Tokens.z)
        UsdGeom.Xform.Define(layout,"/World")
        paths={}
        _native_publish_checkpoint("before_prims")
        for value in prims:
            if type(value) is not dict or set(value)!={"path","role","position"}:
                raise ValueError("Invalid typed scene prim")
            path=_path(value["path"],Sdf)
            role=value["role"]
            if role not in ROLES or path in paths:
                raise ValueError("Duplicate scene path or invalid semantic role")
            pos=_vector(value["position"])
            if native_schemas:
                _native_publish_checkpoint("before_native_prim_" + role)
                from backend.nvp_openusd_native_schemas import define_native_scene_prim
                prim=define_native_scene_prim(layout,path,role)
            else:
                prim=UsdGeom.Xform.Define(layout,path)
            prim.GetPrim().CreateAttribute(
                "nvp:semanticRole",Sdf.ValueTypeNames.String).Set(role)
            if native_schemas:
                authored=prim.GetPrim()
                # Standard USD xform attributes on typed Camera/Light prims.
                if not authored.CreateAttribute(
                    "xformOpOrder",Sdf.ValueTypeNames.TokenArray).Set(
                    ["xformOp:translate"]):
                    raise RuntimeError("Cannot author native USD transform order")
                if not authored.CreateAttribute(
                    "xformOp:translate",Sdf.ValueTypeNames.Double3).Set(
                    Gf.Vec3d(*pos)):
                    raise RuntimeError("Cannot author native USD object position")
            elif not UsdGeom.XformCommonAPI(prim).SetTranslate(
                    Gf.Vec3d(*pos)):
                raise RuntimeError("Cannot author USD layout transform")
            paths[path]=role
            _native_publish_checkpoint("after_prim_" + role)
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
            # Do not author a stronger Xform prim type above a native
            # camera/light schema; motion only contributes transform opinions.
            if native_schemas:
                # A native Camera/Light is typed in the base layer. Its
                # stronger motion opinion must remain an untyped over.
                # Author the standard USD transform-op attributes directly.
                xform=moving.OverridePrim(path)
                xform.CreateAttribute(
                    "xformOpOrder",Sdf.ValueTypeNames.TokenArray).Set(
                    ["xformOp:translate"])
                translation=xform.CreateAttribute(
                    "xformOp:translate",Sdf.ValueTypeNames.Double3)
                api=None
            else:
                xform=UsdGeom.Xform.Define(moving,path)
                api=UsdGeom.XformCommonAPI(xform)
                translation=None
            previous=-1
            for sample in samples:
                if type(sample) is not dict or set(sample)!={"tick","position"}:
                    raise ValueError("Invalid exact-time motion key")
                tick=_int(sample["tick"],"motion tick",
                          maximum=MAX_USD_EXACT_TICK)
                if tick<=previous:
                    raise ValueError("Motion sample ticks must strictly increase")
                previous=tick
                value=Gf.Vec3d(*_vector(sample["position"]))
                t=Usd.TimeCode(float(tick))
                if native_schemas:
                    if not translation.Set(value,t):
                        raise RuntimeError("Native USD timed transform op failed")
                elif not api.SetTranslate(value,time=t):
                    raise RuntimeError("Native USD transform authoring failed")
            animated.add(path)
        # Source assets are logically bound to exact FilmIndex revisions.
        # The USD session references are recreated only from trusted SHA-
        # addressed in-memory layers, never from arbitrary disk paths.
        bindings=self._resolve_assets(project_id, paths, asset_bindings or [])
        from backend.nvp_openusd_channels import author_parameter_layer
        if performance_channels:
            parameter_layer, channel_manifest=author_parameter_layer(
                paths,performance_channels,native_schemas=native_schemas)
        else:
            parameter_layer,channel_manifest=None,[]
        skeleton_layer,rig_manifest=None,[]
        if skeletal_rigs:
            from backend.nvp_openusd_skeleton import author_skeleton_layer
            skeleton_layer,rig_manifest=author_skeleton_layer(paths,skeletal_rigs)
        # P1-B: one canonical, creator-authorized ActorID per genuine
        # UsdSkel-bound mesh. The stored ActorID/record SHA lives in the
        # immutable layout USD as source data, not a renderer-only hint.
        from backend.nvp_p1bc_actor_registry import resolve_scene_actor_bindings
        cast=resolve_scene_actor_bindings(
            self.index,project_id,paths,skeletal_rigs or [],
            actor_bindings or [])
        from backend.nvp_p1bc_scene_cast import resolve_imported_character_sources
        imported=resolve_imported_character_sources(
            self.index,project_id,cast,skeletal_rigs or [],
            imported_character_sources or [])
        for actor in cast:
            prim=layout.GetPrimAtPath(actor["path"])
            prim.CreateAttribute(
                "nvp:actorId",Sdf.ValueTypeNames.String).Set(actor["actor_id"])
            prim.CreateAttribute(
                "nvp:actorRevision",Sdf.ValueTypeNames.Int).Set(
                    actor["actor_revision"])
            prim.CreateAttribute(
                "nvp:actorDocumentSHA",Sdf.ValueTypeNames.String).Set(
                    actor["actor_document_sha256"])
        _native_publish_checkpoint("before_compose")
        composed=_compose(base,motion,Sdf,Usd,parameter_layer,skeleton_layer)
        _native_publish_checkpoint("after_compose")
        _native_publish_checkpoint("before_attach_assets")
        self._attach_assets(composed,bindings)
        _native_publish_checkpoint("after_attach_assets")
        for path in paths:
            _native_publish_checkpoint("before_evaluate_" + paths[path])
            _evaluate(composed,path,0,Sdf,Usd,UsdGeom)
            _native_publish_checkpoint("after_evaluate_" + paths[path])
        _native_publish_checkpoint("before_layout_export")
        base_bytes=base.ExportToString().encode("utf-8")
        _native_publish_checkpoint("after_layout_export")
        motion_bytes=motion.ExportToString().encode("utf-8")
        _native_publish_checkpoint("after_motion_export")
        parameter_bytes=(parameter_layer.ExportToString().encode("utf-8")
                         if parameter_layer is not None else b"")
        skeleton_bytes=(skeleton_layer.ExportToString().encode("utf-8")
                        if skeleton_layer is not None else b"")
        if (len(base_bytes)>MAX_USD_LAYER_BYTES or
            len(motion_bytes)>MAX_USD_LAYER_BYTES or
            len(parameter_bytes)>MAX_USD_LAYER_BYTES or
            len(skeleton_bytes)>MAX_USD_LAYER_BYTES):
            raise ValueError("Authored OpenUSD layer exceeded blob policy")
        # The immutable scene references the layer *bytes*, not temp paths.
        _native_publish_checkpoint("before_layout_blob_commit")
        bsha=self.index.put_blob(project_id,base_bytes,media_type=LAYER_TYPE)
        _native_publish_checkpoint("after_layout_blob_commit")
        msha=self.index.put_blob(project_id,motion_bytes,media_type=LAYER_TYPE)
        _native_publish_checkpoint("after_motion_blob_commit")
        psha=(self.index.put_blob(project_id,parameter_bytes,
                                 media_type=LAYER_TYPE)
              if parameter_bytes else None)
        ssha=(self.index.put_blob(project_id,skeleton_bytes,
                                 media_type=LAYER_TYPE)
              if skeleton_bytes else None)
        manifest={"format":FORMAT,
                  "layer_order":(
                      (["skeletons"] if skeleton_layer is not None else []) +
                      (["parameters"] if parameter_layer is not None else []) +
                      ["motion","layout"]),
                  "layout_layer_sha256":bsha,
                  "motion_layer_sha256":msha,
                  "parameter_layer_sha256":psha,
                  "skeleton_layer_sha256":ssha,
                  "skeleton_rigs":rig_manifest,
                  "actor_bindings":cast,
                  "imported_characters":imported,
                  "performance_channels":channel_manifest,
                  "native_schema_version":(
                      "nvp.usd.camera_sphere_light.v1" if native_schemas
                      else None),
                  "ticks_per_second":TICKS_PER_SECOND,
                  "usd_timecode_limit":MAX_USD_EXACT_TICK,
                  "prim_roles":paths,
                  "animated_paths":sorted(animated),
                  "asset_bindings":[entry["manifest"] for entry in bindings],
                  "contains_external_references":False,
                  "rendered":False,
                  "creator_approved":False}
        def guard(db):
            for original in imported:
                source=self.index._read_revision(
                    db,project_id,original["character_asset_id"],
                    original["character_asset_revision"])
                if (source is None or
                    source["document_sha"]!=original["character_asset_document_sha256"]):
                    raise RuntimeError("Original imported GLB asset changed before USD scene commit")
            for actor in cast:
                row=self.index._read_revision(
                    db,project_id,actor["actor_id"],actor["actor_revision"])
                if row is None or row["document_sha"]!=actor["actor_document_sha256"]:
                    raise RuntimeError("ActorID source changed before original USD scene commit")
            for entry in bindings:
                record=entry["manifest"]
                row=db.execute("""SELECT document_sha FROM film_object_revisions
                    WHERE project_id=? AND object_id=? AND revision=?""",
                    (project_id,record["asset_id"],record["asset_revision"])).fetchone()
                if row is None or row["document_sha"]!=record["asset_document_sha256"]:
                    raise RuntimeError("Referenced USD asset revision changed before scene commit")
            for sha in (bsha,msha,psha,ssha):
                if sha is None:
                    continue
                if db.execute("""SELECT 1 FROM film_blob_refs
                    WHERE project_id=? AND sha256=?""",
                    (project_id,sha)).fetchone() is None:
                    raise RuntimeError("Composed OpenUSD source layer lost before commit")
        _native_publish_checkpoint("before_scene_revision_commit")
        committed = self.index.register_revision(
            project_id,scene_id,"scene",manifest,
            expected_revision=expected_revision,
            # One asset may appear at many scene paths, but FilmIndex has
            # exactly one dependency edge per immutable source revision.
            dependencies=(
                [{"object_id":aid,"revision":rev,"role":"asset"}
                 for aid,rev in sorted({
                    (e["manifest"]["asset_id"],
                     e["manifest"]["asset_revision"])
                    for e in bindings})] +
                [{"object_id":actor["actor_id"],
                  "revision":actor["actor_revision"],"role":"actor"}
                 for actor in cast] +
                [{"object_id":aid,"revision":rev,"role":"asset"}
                 for aid,rev in sorted({
                     (a["character_asset_id"],a["character_asset_revision"])
                     for a in imported
                 })]),
            precommit_guard=guard)
        _native_publish_checkpoint("after_scene_revision_commit")
        return committed

    def _resolve_assets(self, project_id, paths, asset_bindings, *,
                        verify_manifest=False):
        if (type(asset_bindings) is not list or
            len(asset_bindings)>MAX_ASSET_BINDINGS):
            raise ValueError("Too many reusable scene assets")
        from backend.nvp_openusd_assets import OpenUSDAssetRegistry
        registry=OpenUSDAssetRegistry(self.index)
        _,Sdf,_,_=_usd()
        attached=set()
        result=[]
        for item in asset_bindings:
            required=({"path","asset_id","asset_revision",
                       "asset_document_sha256","asset_layer_sha256"}
                      if verify_manifest else
                      {"path","asset_id","asset_revision"})
            if type(item) is not dict or set(item)!=required:
                raise ValueError("Invalid typed reusable scene asset binding")
            path=_path(item["path"],Sdf)
            if path not in paths or path in attached:
                raise ValueError("Reusable asset must target one declared prim")
            attached.add(path)
            aid=_id(item["asset_id"],"reusable USD asset")
            rev=item["asset_revision"]
            if type(rev) is not int or rev<1:
                raise ValueError("Reusable USD asset must use an exact revision")
            record,layer=registry.open(project_id,aid,rev)
            manifest={"path":path,"asset_id":aid,"asset_revision":rev,
                      "asset_document_sha256":record["document_sha256"],
                      "asset_layer_sha256":record["data"]["layer_sha256"]}
            if verify_manifest and manifest!=item:
                raise RuntimeError("Pinned scene asset differs from immutable source")
            result.append({"manifest":manifest,"layer":layer})
        return sorted(result,key=lambda x:x["manifest"]["path"])

    @staticmethod
    def _attach_assets(stage, entries):
        if not entries:
            return
        _,Sdf,Usd,UsdGeom=_usd()
        # USD supports references, but this first bridge only references
        # layers just reconstructed from immutable FilmIndex blobs.
        # Session-layer opinions are rebuilt from the SHA-pinned manifest on
        # every reopen. Anonymous identifiers are NEVER persisted as paths.
        old=stage.GetEditTarget()
        stage.SetEditTarget(stage.GetSessionLayer())
        try:
            for entry in entries:
                path=entry["manifest"]["path"]
                layer=entry["layer"]
                prim=stage.OverridePrim(path)
                if not prim.GetReferences().AddReference(
                    layer.identifier,Sdf.Path("/Asset")):
                    raise RuntimeError("OpenUSD asset composition failed")
                if not stage.GetPrimAtPath(path+"/Geometry").IsDefined():
                    raise RuntimeError("Composed reusable asset geometry is missing")
        finally:
            stage.SetEditTarget(old)

    def open(self, project_id, scene_id, revision):
        record=self.index.read_revision(project_id,scene_id,revision)
        doc=record["data"]
        if (record["kind"]!="scene" or doc.get("format")!=FORMAT or
            doc.get("layer_order") not in (
                ["motion","layout"],["parameters","motion","layout"],
                ["skeletons","motion","layout"],
                ["skeletons","parameters","motion","layout"]) or
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
        param=None
        if "parameters" in doc["layer_order"]:
            if (not doc.get("parameter_layer_sha256") or
                type(doc.get("performance_channels")) is not list):
                raise RuntimeError("Missing pinned authored performance layer")
            param=_layer_from_text(
                self.index.get_blob(
                    project_id,doc["parameter_layer_sha256"]).decode("utf-8"),
                "reopen_parameters.usda",Sdf)
        skeletons=None
        if doc["layer_order"][0]=="skeletons":
            if (not doc.get("skeleton_layer_sha256") or
                type(doc.get("skeleton_rigs")) is not list):
                raise RuntimeError("Missing exact frozen USD skeleton layer")
            skeletons=_layer_from_text(
                self.index.get_blob(
                    project_id,doc["skeleton_layer_sha256"]).decode("utf-8"),
                "reopen_skeleton.usda",Sdf)
        composed=_compose(base,motion,Sdf,Usd,param,skeletons)
        if doc.get("native_schema_version"):
            from backend.nvp_openusd_native_schemas import METERS_PER_UNIT
            if not math.isclose(
                    UsdGeom.GetStageMetersPerUnit(composed),METERS_PER_UNIT,
                    rel_tol=0,abs_tol=1e-12):
                raise RuntimeError("Frozen USD scene unit policy changed")
        bindings=self._resolve_assets(
            project_id,doc["prim_roles"],doc.get("asset_bindings",[]),
            verify_manifest=True)
        self._attach_assets(composed,bindings)
        # Validate archived ActorID against the original actor revision AND
        # the original USD prim after every fresh FilmIndex/SQLite reopen.
        from backend.nvp_p1bc_scene_cast import resolve_imported_character_sources
        from backend.nvp_p1bc_actor_registry import resolve_scene_actor_bindings
        cast=resolve_scene_actor_bindings(
            self.index,project_id,doc["prim_roles"],
            doc.get("skeleton_rigs",[]),doc.get("actor_bindings",[]),
            verify_manifest=True)
        resolve_imported_character_sources(
            self.index,project_id,cast,doc.get("skeleton_rigs",[]),
            doc.get("imported_characters",[]),verify_manifest=True,
            composed_stage=composed)
        for actor in cast:
            prim=composed.GetPrimAtPath(actor["path"])
            if (prim.GetAttribute("nvp:actorId").Get()!=actor["actor_id"] or
                prim.GetAttribute("nvp:actorRevision").Get()!=actor["actor_revision"] or
                prim.GetAttribute("nvp:actorDocumentSHA").Get()!=actor["actor_document_sha256"]):
                raise RuntimeError("Original scene USD ActorID metadata changed")
        if skeletons is not None:
            from backend.nvp_openusd_skeleton import evaluate_skeletons
            evaluate_skeletons(composed,doc["skeleton_rigs"],0)
        if param is not None:
            from backend.nvp_openusd_channels import evaluate_parameter_channels
            evaluate_parameter_channels(
                composed,doc["performance_channels"],doc["prim_roles"],0)
        if doc.get("native_schema_version") is not None:
            from backend.nvp_openusd_native_schemas import (
                SCHEMA,evaluate_native_schema)
            if doc["native_schema_version"]!=SCHEMA:
                raise RuntimeError("Unknown native USD scene schema version")
            from backend.nvp_openusd_channels import evaluate_parameter_channels
            values=evaluate_parameter_channels(
                composed,doc.get("performance_channels",[]),
                doc["prim_roles"],0)
            for p,role in doc["prim_roles"].items():
                evaluate_native_schema(composed,p,role,0,values)
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
