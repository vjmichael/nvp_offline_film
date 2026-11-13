"""USD-02D: bounded native UsdSkel joint hierarchy and timed animation.

This encodes an actual USD skeleton and its joint-local animation, not merely
a custom joint-angle label. SLATE-07 optionally adds a native UsdSkel-bound
typed character mesh with bounded per-vertex influences in the SAME source
layer. Facial deformation and general-purpose rest/bind pose authoring remain
future tasks. NVP controls source identities and exact native Film Time ticks.
"""
from __future__ import annotations
import math
import re
from backend.nvp_openusd_scene import _usd, _vector, MAX_USD_EXACT_TICK
from backend.nvp_temporal_ledger import _int, TICKS_PER_SECOND

MAX_RIGS=8
MAX_JOINTS=32
MAX_KEYS=256


def _source_matrix(value):
    # Original GLB 4x4 source/bind transform, not a guessed pelvis offset.
    from pxr import Gf
    if (type(value) is not list or len(value)!=16 or any(
        type(x) not in (float,int) or not math.isfinite(x)
        or abs(x)>1e6 for x in value)):
        raise ValueError("Native rig source transform must be sixteen finite numbers")
    matrix=Gf.Matrix4d(*[float(x) for x in value])
    if not math.isfinite(matrix.GetDeterminant()) or abs(matrix.GetDeterminant())<1e-8:
        raise ValueError("Native rig source transform is singular")
    return matrix

JOINT = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:/[A-Za-z][A-Za-z0-9_]*)*\Z")


def _skel():
    try:
        from pxr import UsdSkel, Vt
    except ImportError as exc:
        raise RuntimeError("Real native USD Skel library required") from exc
    return UsdSkel, Vt


def validate_rigs(roles, rigs):
    if type(rigs) is not list or len(rigs)>MAX_RIGS:
        raise ValueError("Too many animated skeletons")
    seen=set()
    result=[]
    for rig in rigs:
        if (type(rig) is not dict or
            not {"path","joints","samples"}<=set(rig) or
            not set(rig)<= {"path","joints","samples","skin",
                            "rest_transforms","bind_transforms"}):
            raise ValueError("Invalid exact USD rig descriptor")
        path=rig["path"]
        if roles.get(path)!="actor" or path in seen:
            raise ValueError("Native skeleton must attach to one declared actor")
        seen.add(path)
        joints=rig["joints"]
        if (type(joints) is not list or
            not 1 <= len(joints) <= MAX_JOINTS or
            any(type(j) is not str or not JOINT.fullmatch(j) for j in joints) or
            len(set(joints))!=len(joints)):
            raise ValueError("Invalid bounded joint names")
        for i,j in enumerate(joints):
            if "/" in j and j.rsplit("/",1)[0] not in joints[:i]:
                raise ValueError("Skeleton must define each parent before its children")
        if ("rest_transforms" in rig)!=("bind_transforms" in rig):
            raise ValueError("Original GLB rest and bind matrices must be paired")
        if "rest_transforms" in rig:
            for key in ("rest_transforms","bind_transforms"):
                transforms=rig[key]
                if type(transforms) is not list or len(transforms)!=len(joints):
                    raise ValueError("Every imported joint requires an exact rest/bind matrix")
                for source in transforms:
                    _source_matrix(source)
        samples=rig["samples"]
        if type(samples) is not list or not 2<=len(samples)<=MAX_KEYS:
            raise ValueError("Native joint animation needs bounded time keys")
        previous=-1
        for entry in samples:
            if type(entry) is not dict or set(entry) not in (
                    {"tick","translations"},{"tick","joint_transforms"}):
                raise ValueError("Unsupported joint key schema")
            tick=_int(entry["tick"],"joint sample time",maximum=MAX_USD_EXACT_TICK)
            if tick<=previous:
                raise ValueError("Joint time keys must strictly increase")
            previous=tick
            if "translations" in entry:
                translations=entry["translations"]
                if type(translations) is not list or len(translations)!=len(joints):
                    raise ValueError("Joint animation keys must cover every joint")
                for position in translations:
                    _vector(position)
            else:
                transforms=entry["joint_transforms"]
                if type(transforms) is not list or len(transforms)!=len(joints):
                    raise ValueError("Imported GLB joint samples must cover every joint")
                for matrix in transforms:
                    _source_matrix(matrix)
        descriptor={"path":path,"joints":list(joints),
                    "sample_count":len(samples)}
        if "skin" in rig:
            from backend.nvp_openusd_skinning import normalize_skin,SKIN_MESH_SUFFIX
            skin=normalize_skin(rig["skin"],len(joints))
            descriptor.update({
                "skin_mesh_path":path+SKIN_MESH_SUFFIX,
                "skin_vertex_count":len(skin["points"]),
                "skin_face_count":len(skin["faces"]),
                "skin_weighted":True,
                "facial_animation_rendered":False,
            })
            if "source_glb_sha256" in skin:
                descriptor.update({
                    "original_glb_sha256":skin["source_glb_sha256"],
                    "actual_imported_glb_vertices":True,
                })
        result.append(descriptor)
    return result


def author_skeleton_layer(roles, rigs):
    descriptors=validate_rigs(roles,rigs)
    Gf,Sdf,Usd,_=_usd()
    UsdSkel,Vt=_skel()
    layer=Sdf.Layer.CreateAnonymous("nvp_skeletons.usda")
    stage=Usd.Stage.Open(layer)
    # Match exact native Film Time across every composited Sdf sublayer.
    # The default 24 tps would distort genuine joint keys on composition.
    stage.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
    for rig in rigs:
        root_path=rig["path"]+"/Rig"
        root=UsdSkel.Root.Define(stage,root_path)
        if not root:
            raise RuntimeError("Could not define native USD skeleton root")
        skel=UsdSkel.Skeleton.Define(stage,root_path+"/Skeleton")
        joints=Vt.TokenArray(rig["joints"])
        topology=UsdSkel.Topology(joints)
        valid,reason=topology.Validate()
        if not valid:
            raise RuntimeError("Native USD skeleton topology invalid: "+str(reason))
        skel.GetJointsAttr().Set(joints)
        identity=Vt.Matrix4dArray([Gf.Matrix4d(1.0) for _ in rig["joints"]])
        bind_matrices=Vt.Matrix4dArray([
            _source_matrix(mat) for mat in rig["bind_transforms"]
        ]) if "bind_transforms" in rig else identity
        rest_matrices=Vt.Matrix4dArray([
            _source_matrix(mat) for mat in rig["rest_transforms"]
        ]) if "rest_transforms" in rig else identity
        if (not skel.GetBindTransformsAttr().Set(bind_matrices) or
            not skel.GetRestTransformsAttr().Set(rest_matrices)):
            raise RuntimeError("Actual imported GLB joint bind/rest transforms missing")
        animation=UsdSkel.Animation.Define(
            stage,root_path+"/Skeleton/Animation")
        animation.GetJointsAttr().Set(joints)
        bind=UsdSkel.BindingAPI.Apply(skel.GetPrim())
        if not bind:
            raise RuntimeError("Unable to apply native USD skeleton binding")
        if not bind.CreateAnimationSourceRel().SetTargets([
            animation.GetPrim().GetPath()]):
            raise RuntimeError("Cannot bind native USD skeleton animation")
        if "skin" in rig:
            from backend.nvp_openusd_skinning import author_skin_mesh
            source=author_skin_mesh(
                stage,rig["path"],skel.GetPrim().GetPath(),
                rig["skin"],len(rig["joints"]))
            if source["mesh_path"]!=rig["path"]+"/Rig/CharacterMesh":
                raise RuntimeError("Author did not preserve canonical skeleton mesh path")
        for sample in rig["samples"]:
            matrices=[]
            if "joint_transforms" in sample:
                matrices=[_source_matrix(x) for x in sample["joint_transforms"]]
            else:
                for point in sample["translations"]:
                    m=Gf.Matrix4d(1.0)
                    m.SetTranslate(Gf.Vec3d(*_vector(point)))
                    matrices.append(m)
            if not animation.SetTransforms(
                Vt.Matrix4dArray(matrices),
                Usd.TimeCode(float(sample["tick"]))):
                raise RuntimeError("Native skeleton transform sample failed")
    return layer,descriptors


def evaluate_skeletons(stage, descriptors, tick):
    _int(tick,"skeleton film time",maximum=MAX_USD_EXACT_TICK)
    UsdSkel,_=_skel()
    _,_,Usd,_=_usd()
    if type(descriptors) is not list or len(descriptors)>MAX_RIGS:
        raise RuntimeError("Invalid frozen rig source manifest")
    cache=UsdSkel.Cache()
    results=[]
    for info in descriptors:
        path=info["path"]
        skel=UsdSkel.Skeleton(
            stage.GetPrimAtPath(path+"/Rig/Skeleton"))
        if not skel or not skel.GetPrim().IsA(UsdSkel.Skeleton):
            raise RuntimeError("Native USD skeleton missing from composed scene")
        joints=[str(j) for j in skel.GetJointsAttr().Get()]
        if joints!=info["joints"]:
            raise RuntimeError("Frozen skeletal joint hierarchy changed")
        query=cache.GetSkelQuery(skel)
        if not query:
            raise RuntimeError("Native USD skeleton cannot resolve animation")
        matrices=query.ComputeJointSkelTransforms(
            Usd.TimeCode(float(tick)))
        if matrices is None or len(matrices)!=len(joints):
            raise RuntimeError("Incomplete evaluated USD joint transform array")
        positions=[]
        for joint,transform in zip(joints,matrices):
            xyz=[float(v) for v in transform.ExtractTranslation()]
            if any(not math.isfinite(v) or abs(v)>1e8 for v in xyz):
                raise RuntimeError("Nonfinite native USD skeletal evaluation")
            positions.append({"joint":joint,"skeleton_translation":xyz})
        results.append({"path":path,"time_tick":tick,
                        "joint_count":len(joints),
                        "joints":positions,
                        "mesh_deformation_rendered":False})
    return results
