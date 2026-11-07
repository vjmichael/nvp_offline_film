"""DA-04B: source-bound, disposable skinned geometry for live 3D preview.

Reuse the actual NVP UsdSkel bound mesh and verified joint animation; do
not infer actors from gizmos, create video frames or alter source layers.
A FilmIndex SHA-pinned USD scene is reopened only at the requested exact
Film Time tick. The bounded deformed vertices are disposable GPU inputs,
not a second performance/source or pre-rendered proxy.
"""
from __future__ import annotations

import math

from backend.nvp_film_index import FilmIndex, _sha
from backend.nvp_openusd_scene import OpenUSDSceneBridge, MAX_USD_EXACT_TICK
from backend.nvp_openusd_skinning import (
    evaluate_skin, MAX_SKIN_VERTICES, MAX_SKIN_FACES, SKIN_MESH_SUFFIX)
from backend.nvp_temporal_ledger import _int

MAX_LIVE_SKIN_VERTICES=4096
MAX_LIVE_SKIN_TRIANGLES=8192


def verified_live_skins(index:FilmIndex,project_id,scene_snapshot, *,
                        scene_id,scene_revision):
    """Map authored actor paths to native, source-verified skinned geometry.

    Never use this on untrusted arbitrary USD paths: OpenUSDSceneBridge
    owns the original project-scoped, SHA-verified USD layers and source
    reference resolution. No fallback to guessed character geometry.
    """
    if not isinstance(index,FilmIndex) or type(scene_snapshot) is not dict:
        raise TypeError("A real FilmIndex and exact source snapshot are required")
    tick=_int(scene_snapshot.get("time_tick"),"live skin Film Time",
              maximum=MAX_USD_EXACT_TICK)
    original,stage=OpenUSDSceneBridge(index).open(
        project_id,scene_id,scene_revision)
    if original["document_sha256"]!=scene_snapshot.get("scene_document_sha256"):
        raise RuntimeError("Live skin cannot change the original OpenUSD scene identity")
    declared=original["data"]["prim_roles"]
    observed={obj["path"]:obj for obj in scene_snapshot["objects"]}
    rigs=original["data"].get("skeleton_rigs",[])
    if len(rigs)>8:
        raise RuntimeError("Live native actor count exceeds bounded UsdSkel scene")
    # Every authored rig must produce either a real bound mesh or an
    # explicit missing-geometry status. Treating an unmeshed rig as an
    # anonymous actor sphere misrepresents the captured performance.
    from pxr import UsdGeom
    result={}
    vertices=0
    triangles=0
    layer_sha=_sha(original["data"]["skeleton_layer_sha256"])
    for rig in rigs:
        path=rig["path"]
        if path not in observed:
            # Snapshot can be a subset selected for audio or inspection.
            continue
        if not rig.get("skin_weighted"):
            result[path]={
                "shape":"missing_rig_geometry",
                "size_m":0.4,
                "mesh_points":None,"mesh_triangles":None,
                "geometry_asset_sha256":None,
                "source_skinning":False,
                "source_skinning_tick":str(tick),
                "source_color_rgb":None,"source_material":None,
                "original_blend_shape_count":0,
                "reason":"Rigged original USD actor has no bound UsdSkel mesh",
                "facial_animation_evaluated":False,
            }
            continue
        if declared.get(path)!="actor" or observed[path]["semantic_role"]!="actor":
            raise RuntimeError("Bound live skin has no matching original actor")
        if observed[path].get("asset") is not None:
            raise RuntimeError("A skinned actor cannot silently override another USD asset")
        mesh_path=path+SKIN_MESH_SUFFIX
        if rig.get("skin_mesh_path")!=mesh_path:
            raise RuntimeError("Native skeleton mesh identity changed")
        prim=stage.GetPrimAtPath(mesh_path)
        if not prim or not prim.IsA(UsdGeom.Mesh):
            raise RuntimeError("Original USD bound actor mesh is unavailable")
        geometry=UsdGeom.Mesh(prim)
        faces=list(geometry.GetFaceVertexCountsAttr().Get() or [])
        indices=list(geometry.GetFaceVertexIndicesAttr().Get() or [])
        points_count=rig["skin_vertex_count"]
        if (type(points_count) is not int or
            not 4<=points_count<=MAX_SKIN_VERTICES or
            len(faces)!=rig["skin_face_count"] or
            not 1<=len(faces)<=MAX_SKIN_FACES or
            any(type(n) is not int or not 3<=n<=8 for n in faces) or
            sum(faces)!=len(indices)):
            raise RuntimeError("Original USD skinned geometry topology is invalid")
        groups=[]
        offset=0
        for count in faces:
            face=indices[offset:offset+count]
            offset+=count
            if (any(type(i) is not int or not 0<=i<points_count for i in face)
                or len(set(face))!=count):
                raise RuntimeError("Invalid original USD actor face")
            groups.extend([[face[0],face[j],face[j+1]]
                           for j in range(1,count-1)])
        pose=evaluate_skin(stage,prim,path,tick)
        points=pose["deformed_points"]
        if (len(points)!=points_count or
            not pose["usd_skin_binding_verified"] or
            not pose["skinning_evaluated"]):
            raise RuntimeError("Native USD skinning is not source verified")
        vertices+=len(points)
        triangles+=len(groups)
        if (vertices>MAX_LIVE_SKIN_VERTICES or
                triangles>MAX_LIVE_SKIN_TRIANGLES):
            raise RuntimeError("Live skinned USD source exceeds GPU audition bounds")
        colors=geometry.GetDisplayColorPrimvar().Get()
        if colors is None or len(colors)!=1:
            raise RuntimeError("Original USD actor requires one authored preview color")
        color=[float(x) for x in colors[0]]
        if any(not math.isfinite(x) or not 0<=x<=1 for x in color):
            raise RuntimeError("Original USD actor has untrusted display color")
        material=pose["source_preview_material"]
        if (any(abs(x-y)>1e-5 for x,y in
                zip(material["base_color_rgb"],color)) or
            material["original_source_modified"] is not False):
            raise RuntimeError("Source USD material and mesh color provenance disagree")
        size=max(0.01,max(abs(value) for point in points for value in point))
        result[path]={
            "shape":"skinned_mesh",
            "size_m":size,
            "mesh_points":points,
            "mesh_triangles":groups,
            "geometry_asset_sha256":layer_sha,
            "source_skinning":True,
            "source_skinning_tick":str(tick),
            "source_color_rgb":material["base_color_rgb"],
            "source_material":material,
            "bound_usd_joint_count":pose["joint_count"],
            "facial_animation_evaluated":pose["facial_deformation_evaluated"],
            "original_blend_shape_count":pose["original_blend_shape_count"],
        }
    return result
