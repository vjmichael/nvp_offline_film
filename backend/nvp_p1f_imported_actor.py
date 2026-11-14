"""P1-F reviewed, immutable imported facially rigged OpenUSD actor assets.

Accepts a SINGLE self-contained USDA actor with real triangle/polygon mesh,
UsdSkel skin, four separate facial domains and two exact Film Time expression
keys. Nothing from an external USD/texture path or an arbitrary user script is
ever resolved. Source bytes remain immutable and SHA-addressed in FilmIndex.
This does not grant Blender, distribution or generative-video authorization.
"""
from __future__ import annotations

from hashlib import sha256
import math
import re

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_scene import _usd, _layer_from_text, LAYER_TYPE, MAX_USD_LAYER_BYTES
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT="nvp.asset.openusd.imported_rigged_actor.v1"
MAX_ACTOR_POINTS=250_000
MAX_ACTOR_FACES=250_000
MAX_JOINTS=128
MAX_EXPRESSION_KEYS=4096
SHAPES=("jawOpen","lipClose","eyeBlink","browRaise")
# These are USDA composition operators, not permitted source data.
FORBIDDEN = re.compile(
    r"\b(?:references|payload|subLayers|inherits|specializes|variantSets|clips|"
    r"assetInfo|relocates)\s*=",re.I)


def _valid_stage(source, actor_id):
    if type(source) is not bytes or not 100 <= len(source) <= MAX_USD_LAYER_BYTES:
        raise ValueError("Imported actor must be a finite self-contained USDA asset")
    if (not source.lstrip().startswith(b"#usda 1.0") or b"@" in source or
            b"\x00" in source):
        raise ValueError("An imported actor cannot resolve files or external assets")
    text=source.decode("utf-8","strict")
    if FORBIDDEN.search(text):
        raise ValueError("Imported actor cannot author USD composition arcs")
    Gf,Sdf,Usd,UsdGeom=_usd()
    from pxr import UsdSkel
    layer=_layer_from_text(text,"nvp_imported_rigged_actor.usda",Sdf)
    if layer.subLayerPaths or layer.GetExternalReferences():
        raise ValueError("Imported character has external layer references")
    stage=Usd.Stage.Open(layer,Usd.Stage.LoadNone)
    if not stage or stage.GetDefaultPrim().GetPath()!=Sdf.Path("/Asset"):
        raise ValueError("Character must contain the /Asset default prim")
    if float(stage.GetTimeCodesPerSecond())!=float(TICKS_PER_SECOND):
        raise ValueError("Character animation must use the exact original Film Time base")
    root=stage.GetPrimAtPath("/Asset")
    mesh_prim=stage.GetPrimAtPath("/Asset/Geometry")
    skel_prim=stage.GetPrimAtPath("/Asset/Skeleton")
    anim_prim=stage.GetPrimAtPath("/Asset/Animation")
    if (not root.IsA(UsdSkel.Root) or not mesh_prim.IsA(UsdGeom.Mesh)
            or not skel_prim.IsA(UsdSkel.Skeleton)
            or not anim_prim.IsA(UsdSkel.Animation)):
        raise ValueError("Imported actor requires mesh, skeleton and facial performance animation")
    if root.GetAttribute("nvp:actorID").Get()!=actor_id:
        raise ValueError("Rigged asset is not owned by the declared ActorID")
    mesh=UsdGeom.Mesh(mesh_prim)
    positions=mesh.GetPointsAttr().Get()
    counts=mesh.GetFaceVertexCountsAttr().Get()
    indices=mesh.GetFaceVertexIndicesAttr().Get()
    if (positions is None or not 3<=len(positions)<=MAX_ACTOR_POINTS or
            counts is None or not 1<=len(counts)<=MAX_ACTOR_FACES or
            indices is None or sum(counts)!=len(indices) or
            any(n<3 or n>128 for n in counts) or
            any(i<0 or i>=len(positions) for i in indices) or
            any(not math.isfinite(float(v)) or abs(float(v))>1_000_000
                for point in positions for v in point)):
        raise ValueError("Imported mesh topology or point coordinates are invalid")
    skel=UsdSkel.Skeleton(skel_prim)
    rig_binding=UsdSkel.BindingAPI(skel_prim)
    if list(rig_binding.GetAnimationSourceRel().GetTargets()) != [
            Sdf.Path("/Asset/Animation")]:
        raise ValueError("Original skeleton must own the timed actor facial animation")
    joints=skel.GetJointsAttr().Get()
    bind=skel.GetBindTransformsAttr().Get()
    rest=skel.GetRestTransformsAttr().Get()
    if (not joints or not 1<=len(joints)<=MAX_JOINTS or
            len(set(str(j) for j in joints))!=len(joints) or
            bind is None or rest is None or
            len(bind)!=len(joints) or len(rest)!=len(joints)):
        raise ValueError("Imported actor lacks a complete bounded skeleton")
    binding=UsdSkel.BindingAPI(mesh_prim)
    if list(binding.GetSkeletonRel().GetTargets()) != [Sdf.Path("/Asset/Skeleton")]:
        raise ValueError("Actor mesh is not skinned to its own immutable skeleton")
    joint_indices=binding.GetJointIndicesPrimvar().Get()
    joint_weights=binding.GetJointWeightsPrimvar().Get()
    if (joint_indices is None or joint_weights is None or
            len(joint_indices)!=len(joint_weights) or
            len(joint_indices)<len(positions) or
            any(i<0 or i>=len(joints) for i in joint_indices) or
            any(not math.isfinite(float(w)) or w<0 or w>1
                for w in joint_weights)):
        raise ValueError("Imported skin weights or joint indices are invalid")
    names=tuple(str(x) for x in (binding.GetBlendShapesAttr().Get() or []))
    if names!=SHAPES:
        raise ValueError("Imported actor requires explicit jaw/lip/eye/brow shape controls")
    expected=[Sdf.Path("/Asset/Face/"+name) for name in SHAPES]
    if list(binding.GetBlendShapeTargetsRel().GetTargets())!=expected:
        raise ValueError("Facial targets are not bound to the original mesh")
    for path in expected:
        prim=stage.GetPrimAtPath(path)
        if not prim.IsA(UsdSkel.BlendShape):
            raise ValueError("Missing genuine native facial blendshape")
        shape=UsdSkel.BlendShape(prim)
        offsets=shape.GetOffsetsAttr().Get()
        affected=shape.GetPointIndicesAttr().Get()
        if (offsets is None or affected is None or not offsets or
                len(offsets)!=len(affected) or
                any(i<0 or i>=len(positions) for i in affected) or
                any(not math.isfinite(float(v)) for p in offsets for v in p)):
            raise ValueError("Facial blendshape offsets are missing or malformed")
    animation=UsdSkel.Animation(anim_prim)
    if tuple(str(x) for x in animation.GetBlendShapesAttr().Get() or [])!=SHAPES:
        raise ValueError("Facial performance track differs from original rig")
    weights=animation.GetBlendShapeWeightsAttr()
    times=weights.GetTimeSamples()
    if not 2<=len(times)<=MAX_EXPRESSION_KEYS:
        raise ValueError("Imported facial performance requires genuine timed expression keys")
    for t in times:
        if not float(t).is_integer() or not 0<=t<=2**53-1:
            raise ValueError("Facial keys must use exact integral source Film Time")
        v=weights.Get(Usd.TimeCode(t))
        if v is None or len(v)!=len(SHAPES) or any(
                not math.isfinite(float(x)) or x<0 or x>1 for x in v):
            raise ValueError("Malformed facial animation weights")
    allowed={
        "/Asset","/Asset/Geometry","/Asset/Skeleton","/Asset/Animation",
        "/Asset/Face",*(str(x) for x in expected),
    }
    for prim in stage.TraverseAll():
        if not prim.GetPath().pathString in allowed:
            raise ValueError("Unexpected imported prim or executable/auxiliary payload")
    return layer,{
        "actor_id":actor_id,
        "point_count":len(positions),
        "face_count":len(counts),
        "joint_count":len(joints),
        "face_shapes":list(SHAPES),
        "facial_keys":len(times),
        "start_tick":int(times[0]),
        "end_tick":int(times[-1]),
    }


def import_actor(index:FilmIndex,project_id,asset_id,source,*,actor_id,
                 approve_import,creator_event,expected_revision=0):
    if not isinstance(index,FilmIndex) or not callable(approve_import):
        raise TypeError("Trusted FilmIndex and independent creator approval required")
    _require_pid(project_id)
    _id(asset_id,"reviewed imported actor asset")
    _id(actor_id,"ActorID")
    if not actor_id.startswith("ACT_"):
        raise ValueError("Imported mesh needs authoritative ActorID identity")
    if type(expected_revision) is not int or expected_revision!=0:
        raise ValueError("Imported source identity is immutable; use a new asset ID")
    layer,observed=_valid_stage(source,actor_id)
    source_sha=sha256(source).hexdigest()
    scope={"operation":"nvp.p1f.import_rigged_usd_actor.v1",
           "project_id":project_id,"asset_id":asset_id,
           "actor_id":actor_id,"source_sha256":source_sha,
           "geometry":observed}
    if approve_import(creator_event,scope) is not True:
        raise PermissionError("Creator did not approve these exact imported actor bytes")
    blob_sha=index.put_blob(project_id,source,LAYER_TYPE)
    if blob_sha!=source_sha:
        raise RuntimeError("Imported USD bytes changed on content-addressed publication")
    document={"format":FORMAT,"actor_id":actor_id,
              "source":"reviewed_self_contained_openusd_character",
              "layer_sha256":blob_sha,"root_prim":"/Asset",
              "external_references":False,"geometry":observed}
    def guard(db):
        row=db.execute("""SELECT sha256 FROM film_blob_refs
             WHERE project_id=? AND sha256=?""",
             (project_id,source_sha)).fetchone()
        if row is None:
            raise RuntimeError("Approved rigged-character USD blob was not retained")
    return index.register_revision(
        project_id,asset_id,"asset",document,expected_revision=0,
        dependencies=[],precommit_guard=guard)


def open_actor(index:FilmIndex,project_id,asset_id,revision):
    record=index.read_revision(project_id,asset_id,revision)
    doc=record["data"]
    if (record["kind"]!="asset" or doc.get("format")!=FORMAT or
            doc.get("source")!="reviewed_self_contained_openusd_character" or
            doc.get("root_prim")!="/Asset" or
            doc.get("external_references") is not False):
        raise RuntimeError("Not an approved immutable imported actor")
    source=index.get_blob(project_id,doc["layer_sha256"])
    layer,observed=_valid_stage(source,doc["actor_id"])
    if observed!=doc["geometry"]:
        raise RuntimeError("Imported actor animation/mesh changed on reopen")
    return record,layer
