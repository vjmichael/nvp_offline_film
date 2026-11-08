"""FILM01: independent geometric shadow / reflection reference paths.

The first-party native NVP preview has a Z depth buffer and local
GGX/Schlick USD materials, but DOES NOT cast inter-object shadows or
trace another actor into a reflection. This small reference tracer
tests whether our actual three-actor USD scene requires those effects.

A positive blocker or mirror-ray intersection is a geometric *target*
for future renderer work, not a claim that the current image depicts
that shadow or reflected green box. It uses the source-authored torus
mesh and trusted frozen original USD positions, no arbitrary assets.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from tools.nvp_film01_donut_light_probe import (
    DONUT_PATH,BOX_PATH,SPHERE_PATH)

FORMAT="nvp.film01.donut_interobject_shadow_reflection_reference.v1"


def _sub(a,b):
    return tuple(a[i]-b[i] for i in range(3))


def _add(a,b):
    return tuple(a[i]+b[i] for i in range(3))


def _scale(a,k):
    return tuple(k*v for v in a)


def _dot(a,b):
    return sum(a[i]*b[i] for i in range(3))


def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],
            a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def _unit(a):
    k=math.sqrt(_dot(a,a))
    if k<1.e-10:
        raise RuntimeError("Degenerate original geometry light path")
    return _scale(a,1./k)


def _ray_triangle(start,direction,a,b,c,*,max_t):
    """Two-sided native reference triangle, Moller-Trumbore distance."""
    e1=_sub(b,a);e2=_sub(c,a)
    p=_cross(direction,e2)
    determinant=_dot(e1,p)
    if abs(determinant)<1e-10:
        return None
    inv=1./determinant
    tvec=_sub(start,a)
    u=_dot(tvec,p)*inv
    if not -1e-9<=u<=1.+1e-9:
        return None
    q=_cross(tvec,e1)
    v=_dot(direction,q)*inv
    if v< -1e-9 or u+v>1.+1e-9:
        return None
    t=_dot(e2,q)*inv
    if not 1.e-6<t<max_t-1.e-6:
        return None
    return t


def _ray_box(start,direction,center,half,*,max_t):
    lo=0.
    hi=max_t
    for axis in range(3):
        minimum=center[axis]-half
        maximum=center[axis]+half
        if abs(direction[axis])<1.e-10:
            if not minimum<=start[axis]<=maximum:
                return None
        else:
            aa=(minimum-start[axis])/direction[axis]
            bb=(maximum-start[axis])/direction[axis]
            if aa>bb:aa,bb=bb,aa
            lo=max(lo,aa);hi=min(hi,bb)
            if hi<lo:
                return None
    return lo if hi>=max(lo,1e-5) else None


def reference_real_original_light_paths(source):
    """At 1s the green box passes BEHIND the torus mesh.

    The actual source scene, torus UV/triangles, original light position,
    camera position and source Take SHA are mandatory. Return measurable
    *expected* blockers and reflected-object intersections, leaving
    unsupported native shader capabilities OPEN.
    """
    idx=source["index"];pid=source["project_id"]
    native=FrozenSceneAV(
        idx,pid,"DonutLightingTake",
        expected_take_sha256=source["take_sha256"],
        listener_path="/World/Camera")
    try:
        snap=native.snapshot(TICKS_PER_SECOND)
    finally:
        native.close()
    observed={x["path"]:tuple(x["world_translation"])
              for x in snap["objects"]}
    for path in (DONUT_PATH,BOX_PATH,SPHERE_PATH,
                 "/World/Camera","/World/KeyLight"):
        if path not in observed:
            raise RuntimeError("Reference physical light path missing original source prim")
    donut=observed[DONUT_PATH]
    box=observed[BOX_PATH]
    camera=observed["/World/Camera"]
    light=observed["/World/KeyLight"]
    mesh=source["geometry"]
    vertices=[_add(tuple(p),donut) for p in mesh["mesh_points"]]
    faces=mesh["mesh_triangles"]
    # Evaluate actual box source front face against its real key light.
    # A crossing box may have SOME shadowed and SOME illuminated points.
    # No shadowed samples should be silently interpreted as a computed
    # hard shadow in the current NVP color image.
    probe_samples=[(0.,0.),(.2,.2),(-.2,-.2),(.1,0.),(.3,0.)]
    shadows=[]
    for dx,dy in probe_samples:
        pos=(box[0]+dx,box[1]+dy,box[2]+.4)
        light_vector=_sub(light,pos)
        distance=math.sqrt(_dot(light_vector,light_vector))
        direction=_unit(light_vector)
        hits=[]
        for index,(ia,ib,ic) in enumerate(faces):
            t=_ray_triangle(pos,direction,vertices[ia],
                            vertices[ib],vertices[ic],max_t=distance)
            if t is not None:
                hits.append((t,index))
        shadows.append({
            "box_surface_point_world":list(pos),
            "native_usd_key_light_world":list(light),
            "physical_reference_donut_blocks_key":bool(hits),
            "first_intercept_torus_face":(
                min(hits)[1] if hits else None),
        })
    if not any(x["physical_reference_donut_blocks_key"] for x in shadows):
        raise RuntimeError("Three-actor scene lacks a ray-reference donut cast-shadow test")
    if not any(not x["physical_reference_donut_blocks_key"] for x in shadows):
        raise RuntimeError("Three-actor scene lacks a reference illuminated comparison")

    # Source USD torus can also reflect the green box IN PRINCIPLE.
    # Trace ideal mirror rays from its camera-visible triangle centers
    # against the actual rear box AABB. Native shade will not render
    # these secondary paths until renderer integration implements them.
    mirror_hits=[]
    for index,(ia,ib,ic) in enumerate(faces):
        a,b,c=(vertices[i] for i in (ia,ib,ic))
        point=tuple((a[i]+b[i]+c[i])/3 for i in range(3))
        try:
            normal=_unit(_cross(_sub(b,a),_sub(c,a)))
            view=_unit(_sub(camera,point))
        except RuntimeError:
            continue
        incidence=_dot(normal,view)
        if incidence<=0:
            continue
        reflected=_sub(_scale(normal,2*incidence),view)
        t=_ray_box(point,reflected,box,.4,max_t=100.)
        if t is not None and t>1.e-5:
            mirror_hits.append({
                "torus_face_index":index,
                "mirror_ray_box_entry_distance_m":round(t,6),
                "reflection_surface_xyz":[round(v,6) for v in point],
            })
    if not mirror_hits:
        raise RuntimeError("Original three-actor donut scene has no reflected box ray")
    return {
        "format":FORMAT,
        "source_take_sha256":source["take_sha256"],
        "source_scene_sha256":source["scene_sha256"],
        "source_torus_mesh_sha256":source["torus_source_mesh_sha256"],
        "original_film_tick":str(TICKS_PER_SECOND),
        "true_source_usd_scene_object_positions":{
            path:list(observed[path]) for path in
            (DONUT_PATH,BOX_PATH,SPHERE_PATH,
             "/World/Camera","/World/KeyLight")},
        "original_box_ray_samples":shadows,
        "physically_expected_shadowed_sample_count":sum(
            x["physical_reference_donut_blocks_key"] for x in shadows),
        "physically_expected_unshadowed_sample_count":sum(
            not x["physical_reference_donut_blocks_key"] for x in shadows),
        "ideal_camera_mirror_rays_that_hit_original_box":len(mirror_hits),
        "first_ideal_mirror_ray_hits":mirror_hits[:12],
        "native_current_renderer_depth_occlusion_present":True,
        "native_current_renderer_cast_shadows_present":False,
        "native_current_renderer_interobject_reflections_present":False,
        "reference_is_secondary_light_transport_not_raster_acceptance":True,
        "artist_quality_or_DCI_approved":False,
    }
