"""CAM-FX-03: verified native ActorID framing and conservative 3D ray guidance.

This is scene evidence for director choices, not a renderer, a screenshot,
a hidden global ray-mask, nor authority for an AI model. Exact source
provenance is read through 01E/01M/02M-H; geometry is bounded and never
modified. A single center-ray check is NOT a proof of full picture visibility.
"""
from __future__ import annotations

from hashlib import sha256
from contextlib import ExitStack
import json
import math

from backend.nvp_film_index import FilmIndex,_require_pid,_id
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_cam_fx01_camera_rails import (
    normalize_rail,evaluate_rail,_hash)
from backend.nvp_cam_fx02_usd_camera_layer import camera_matrix_rows
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_usd_film01e_world_take import OpenUSDWorldTakeCapture
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T

FORMAT="nvp.cam_fx03.source_grounded_actor_framing_and_occlusion.v1"
MAX_ACTORS=24
MAX_SOURCE_PRIMS=2000
MAX_TRIANGLES=12000
MAX_SAMPLES=5

def _dot(a,b):
    return sum(x*y for x,y in zip(a,b))

def _sub(a,b):
    return [x-y for x,y in zip(a,b)]

def _cross(a,b):
    return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0]]

def _hit(origin,direction,length,triangle):
    """Bounded Möller–Trumbore ray hit against real USD triangle vertices."""
    a,b,c=triangle
    edge1=_sub(b,a);edge2=_sub(c,a)
    q=_cross(direction,edge2)
    determinant=_dot(edge1,q)
    if abs(determinant)<1e-10:
        return None
    inv=1/determinant
    t=_sub(origin,a)
    u=_dot(t,q)*inv
    if u<0 or u>1:return None
    v=_dot(direction,_cross(t,edge1))*inv
    if v<0 or u+v>1:return None
    distance=_dot(edge2,_cross(t,edge1))*inv
    return distance if .01<distance<length-.05 else None

def _bbox(prim,tick):
    from pxr import Usd,UsdGeom
    cache=UsdGeom.BBoxCache(Usd.TimeCode(float(tick)),
            [UsdGeom.Tokens.default_,UsdGeom.Tokens.render,
             UsdGeom.Tokens.proxy],useExtentsHint=False)
    bounds=cache.ComputeWorldBound(prim).ComputeAlignedRange()
    low=bounds.GetMin();high=bounds.GetMax()
    numbers=[[float(low[i]) for i in range(3)],
             [float(high[i]) for i in range(3)]]
    if any(not math.isfinite(x) or abs(x)>1000000
           for row in numbers for x in row):
        raise RuntimeError("Original actor USD bound has nonfinite world coordinates")
    if any(a>b for a,b in zip(*numbers)):
        raise RuntimeError("ActorID geometry has no actual native USD extent")
    return numbers

def _corners(bounds):
    low,high=bounds
    return [[x,y,z] for x in (low[0],high[0])
            for y in (low[1],high[1])
            for z in (low[2],high[2])]

def _framing(sample,bounds):
    basis=camera_matrix_rows(sample)
    right,up,back=(row[:3] for row in basis[:3])
    place=sample["position_m"]
    xcoords=[];ycoords=[];depths=[]
    for point in _corners(bounds):
        delta=_sub(point,place)
        depth=-_dot(delta,back)
        if depth<=.02:
            continue
        xcoords.append(.5+_dot(delta,right)*sample[
            "focal_length_mm"]/(depth*sample["filmback_mm"][0]))
        ycoords.append(.5-_dot(delta,up)*sample[
            "focal_length_mm"]/(depth*sample["filmback_mm"][1]))
        depths.append(depth)
    if not depths:return {
        "state":"BEHIND_CAMERA","bounds_uv":None,"coverage":0.0,
        "center_uv":None,"near_depth_m":None}
    extent=[min(xcoords),min(ycoords),max(xcoords),max(ycoords)]
    center=[(extent[0]+extent[2])/2,(extent[1]+extent[3])/2]
    visible=(extent[2]>0 and extent[0]<1 and
             extent[3]>0 and extent[1]<1)
    area=max(0,min(1,extent[2])-max(0,extent[0]))*max(
        0,min(1,extent[3])-max(0,extent[1]))
    return {"state":"PARTLY_IN_FRAME" if visible else "OUT_OF_FRAME",
            "bounds_uv":extent,"center_uv":center,
            "coverage":area,"near_depth_m":min(depths)}

def _meshes(stage,*,excluded,translation=(0.,0.,0.),time=0):
    """Only real, independently loaded USD meshes; bounded deterministic list."""
    from pxr import Usd,UsdGeom,Gf
    candidates=[]
    prim_count=0
    total=0
    unsupported=0
    for prim in stage.Traverse():
        prim_count+=1
        if prim_count>MAX_SOURCE_PRIMS:
            raise MemoryError("Native actor/world occlusion geometry is not bounded")
        path=str(prim.GetPath())
        if any(path==root or path.startswith(root+"/") for root in excluded):
            continue
        if not prim.IsA(UsdGeom.Mesh):
            if prim.IsA(UsdGeom.Boundable) and (
                    prim.IsA(UsdGeom.Cube) or
                    prim.IsA(UsdGeom.Cylinder) or
                    prim.IsA(UsdGeom.Sphere) or
                    prim.IsA(UsdGeom.Cone) or
                    prim.IsA(UsdGeom.Capsule)):
                unsupported+=1
            continue
        mesh=UsdGeom.Mesh(prim)
        points=mesh.GetPointsAttr().Get(Usd.TimeCode(float(time)))
        counts=mesh.GetFaceVertexCountsAttr().Get()
        indices=mesh.GetFaceVertexIndicesAttr().Get()
        if not points or not counts or not indices:
            unsupported+=1
            continue
        transform=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
            Usd.TimeCode(float(time)))
        world=[]
        for p in points:
            xyz=transform.Transform(Gf.Vec3d(*[float(v) for v in p]))
            world.append([float(xyz[i])+translation[i] for i in range(3)])
        at=0
        for size in counts:
            if size<3:
                unsupported+=1;at+=size;continue
            face=list(indices[at:at+size]);at+=size
            if any(i<0 or i>=len(world) for i in face):
                raise RuntimeError("Native USD original mesh has invalid topology")
            for corner in range(1,len(face)-1):
                candidates.append((
                    path,[world[face[0]],world[face[corner]],
                          world[face[corner+1]]]))
                total+=1
                if total>MAX_TRIANGLES:
                    raise MemoryError("Reviewed native source triangle ray budget exceeded")
    return candidates,unsupported

def guided_camera_scene(index:FilmIndex,pid,rail_spec,*,
                        actor_id=None,district_binding_id=None):
    """Read the actual original ActorID and optional approved district USD."""
    if not isinstance(index,FilmIndex):
        raise TypeError("Only original FilmIndex for camera scene context")
    _require_pid(pid)
    if actor_id is not None:_id(actor_id,"approved source ActorID")
    if district_binding_id is not None:
        _id(district_binding_id,"approved original district shot")
    if type(rail_spec) is not dict:
        raise ValueError("Only exact first-party camera rail proposal")
    bank=DirectorCameraBank(index,verify_director_action=lambda *_:False
                            ).verify(pid,rail_spec["camera_bank_id"],
                                     rail_spec["camera_bank_revision"])
    clean=normalize_rail(rail_spec,bank["source_duration_ticks"])
    if not any(c["camera_id"]==clean["camera_id"] for c in bank["cameras"]):
        raise PermissionError("Unknown source camera cannot gain scene guidance")
    frozen=OpenUSDWorldTakeCapture(index,verify_creator_action=lambda *_:False)
    receipt=frozen.verify_take(pid,bank["world_take_id"])
    if (receipt["status"]!="VERIFIED_ORIGINAL_WORLD_SOURCE_DATA_TAKE"
        or receipt["original_actor_source_unchanged"] is not True):
        raise RuntimeError("Original world Take / ActorID authority is invalid")
    take=index.read_revision(pid,bank["world_take_id"],1)
    if take["document_sha256"]!=bank["world_take_sha256"]:
        raise RuntimeError("Original performance Take changed during rail planning")
    doc=take["data"]
    actors=doc["canonical_original_actors"]
    if not 1<=len(actors)<=MAX_ACTORS:
        raise ValueError("Source-verified cinematic ActorID count is unbounded")
    if actor_id is not None and not any(a["actor_id"]==actor_id for a in actors):
        raise PermissionError("Unrecognized ActorID target from another source")
    bindings=None
    if district_binding_id:
        from backend.nvp_usd_film02m_h_actor_camera_binding import (
            OriginalDistrictShotBinding)
        bindings=OriginalDistrictShotBinding(index,confirm=lambda *_:False
                            ).reopen(pid,district_binding_id)
        if bindings["source_preview"]["world_take_sha256"]!=take[
                "document_sha256"]:
            raise PermissionError("District source belongs to another original Take")
    ticks=sorted({clean["film_start_tick"],
        (clean["film_start_tick"]+clean["film_end_tick"])//2,
        clean["film_end_tick"]})
    sets=list(dict.fromkeys(x["set"] for x in doc["original_scene_takes"]))
    if not 1<=len(sets)<=8:
        raise RuntimeError("Exact original world scene set count invalid")
    snapshots=[]
    with OpenUSDWorldComposer(index).open(
            pid,doc["world_id"],doc["world_revision"]) as source:
        source.load(sets)
        stage=source.stage
        for tick in ticks:
            observed=[]
            for a in actors:
                prim=stage.GetPrimAtPath(a["composed_actor_prim"])
                if not prim or not prim.IsDefined():
                    raise RuntimeError("Original ActorID geometry missing in composed world")
                bounds=_bbox(prim,tick)
                center=[(lo+hi)/2 for lo,hi in zip(*bounds)]
                observed.append({
                    "actor_id":a["actor_id"],
                    "source_take_id":next(
                        (t["take_id"] for t in doc["original_scene_takes"]
                         if t["set"] in str(a["composed_actor_prim"])),None),
                    "source_prim":a["composed_actor_prim"],
                    "center_world_m":center,"bounds_world_m":bounds,
                })
            sample=evaluate_rail(clean,tick)
            target=next((a for a in observed if a["actor_id"]==actor_id),None)
            views=[{"actor_id":a["actor_id"],
                    "source_prim":a["source_prim"],
                    "center_world_m":a["center_world_m"],
                    "bounds_world_m":a["bounds_world_m"],
                    "frame":_framing(sample,a["bounds_world_m"])}
                   for a in observed]
            source_exclude=[a["source_prim"] for a in observed]
            triangles,unsupported=_meshes(
                stage,excluded=source_exclude,time=tick)
            district_triangles=0
            if bindings:
                from pxr import Usd
                from backend.nvp_usd_film02m_e2_district_render_view import (
                    source_district_render_view)
                d=bindings["source_preview"]
                with source_district_render_view(
                        index,pid,d["district_id"],d["district_revision"]) as approved:
                    if approved["manifest"]["original_district_document_sha256"]!=d[
                            "district_document_sha256"]:
                        raise RuntimeError("Approved district source changed during ray guidance")
                    dst=Usd.Stage.Open(str(approved["root"]/
                        "district_render_view.usda"),load=Usd.Stage.LoadAll)
                    if dst is None:
                        raise RuntimeError("Native approved building USD cannot reopen")
                    mesh,unknown=_meshes(
                        dst,excluded=[],translation=d["district_world_origin_m"],
                        time=tick)
                    district_triangles=len(mesh)
                    if len(mesh)+len(triangles)>MAX_TRIANGLES:
                        raise MemoryError("Original plus district ray budget exceeded")
                    triangles.extend(mesh);unsupported+=unknown
            ray={"state":"NO_TARGET","hit_source_prim":None,
                 "reviewed_source_triangles":len(triangles),
                 "reviewed_original_district_triangles":district_triangles,
                 "excluded_nonmesh_shapes":unsupported,
                 "full_image_visibility_proven":False}
            if target is not None:
                origin=sample["position_m"]
                delta=_sub(target["center_world_m"],origin)
                distance=math.sqrt(_dot(delta,delta))
                if distance<.02:
                    ray["state"]="CAMERA_AT_ACTOR_TARGET"
                else:
                    direction=[x/distance for x in delta]
                    hit=None
                    for path,triangle in triangles:
                        candidate=_hit(origin,direction,distance,triangle)
                        if candidate is not None and (
                                hit is None or candidate<hit[0]):
                            hit=(candidate,path)
                    ray["hit_source_prim"]=hit[1] if hit else None
                    ray["state"]=(
                        "SOURCE_CENTER_RAY_OCCLUDED" if hit else
                        "NO_MESH_HIT_WITH_UNSUPPORTED_SOURCE_SHAPES" if unsupported
                        else "NO_HIT_IN_REVIEWED_CENTER_RAY")
            snapshots.append({
                "film_tick":tick,"camera_sample":sample,
                "original_actor_views":views,"selected_actor_id":actor_id,
                "selected_actor_center_world_m":
                    target["center_world_m"] if target else None,
                "selected_actor_center_ray":ray})
    body={
        "format":FORMAT,"project_id":pid,
        "camera_bank_id":clean["camera_bank_id"],
        "camera_bank_revision":clean["camera_bank_revision"],
        "camera_bank_sha256":index.read_revision(
            pid,clean["camera_bank_id"],
            clean["camera_bank_revision"])["document_sha256"],
        "world_take_id":bank["world_take_id"],
        "world_take_sha256":take["document_sha256"],
        "source_performance_sha256":bank["source_performance_sha256"],
        "rail_spec_sha256":_hash(clean),
        "reviewed_district_binding_id":district_binding_id,
        "approved_district_sha256":(
            bindings["source_preview"]["district_document_sha256"]
            if bindings else None),
        "native_actor_count":len(actors),
        "source_guided_frames":snapshots,
        "occlusion_check_scope":"bounded native source mesh center-ray only",
        "camera_clearance_or_human_framing_approved":False,
        "source_actor_takes_and_pcm_unchanged":True,
        "native_scene_reviewed":True,
        "cycles_pixels_rendered":False}
    body["guidance_sha256"]=_hash(body)
    return body
