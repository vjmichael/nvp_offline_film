"""CONV-01/06: exact-original UsdSkel audition inside the existing DataAV.

Reconciles the historical DA-04B source mesh behavior with the newer native
OpenUSD skin/facial evaluator. No second renderer, arbitrary USD, HTTP, GPU
worker, original Take revision or generated character geometry is admitted.
Only an already authorized native DataAV Take session may call this with the
immutable scene ID/revision that was pinned by that Take.
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
MAX_LIVE_ACTORS=8


def verified_live_skins(index:FilmIndex,project_id,scene_snapshot,*,
                        scene_id,scene_revision):
    """Return only source-reopened, bounded original USD skin at exact tick.

    Preview positions and facial weights are disposable derivatives of the
    original immutable scene. They do not prove Cycles rendering quality.
    """
    if not isinstance(index,FilmIndex) or type(scene_snapshot) is not dict:
        raise TypeError("Actual FilmIndex and exact source snapshot required")
    tick=_int(scene_snapshot.get("time_tick"),"native actor Film Time",
              maximum=MAX_USD_EXACT_TICK)
    original,stage=OpenUSDSceneBridge(index).open(
        project_id,scene_id,scene_revision)
    if original["document_sha256"]!=scene_snapshot.get("scene_document_sha256"):
        raise RuntimeError("Native skinned preview source scene SHA changed")
    observed={o["path"]:o for o in scene_snapshot["objects"]}
    if len(observed)!=len(scene_snapshot["objects"]):
        raise RuntimeError("Original native scene contains duplicate actor paths")
    declared=original["data"]["prim_roles"]
    rigs=original["data"].get("skeleton_rigs",[])
    if type(rigs) is not list or len(rigs)>MAX_LIVE_ACTORS:
        raise RuntimeError("Original native scene exceeds bounded UsdSkel actor count")
    if not rigs:
        return {}
    from pxr import UsdGeom,UsdShade
    result={}
    total_verts=0
    total_triangles=0
    layer_sha=_sha(original["data"]["skeleton_layer_sha256"])
    cast={a["path"]:a for a in original["data"].get("actor_bindings",[])}
    for rig in rigs:
        path=rig["path"]
        if path not in observed:
            continue
        actor=observed[path]
        if (declared.get(path)!="actor" or
            actor.get("semantic_role")!="actor" or
            actor.get("asset") is not None):
            raise RuntimeError("Original skinned actor was replaced or is not an actor")
        if path in cast and (
            actor.get("actor_id")!=cast[path]["actor_id"] or
            actor.get("actor_document_sha256")!=
                cast[path]["actor_document_sha256"]):
            raise RuntimeError("Original StoryBible ActorID binding changed")
        if not rig.get("skin_weighted"):
            result[path]={
                "shape":"missing_rig_geometry","size_m":0.4,
                "mesh_points":None,"mesh_triangles":None,
                "mesh_uvs":None,"mesh_face_uvs":None,
                "geometry_asset_sha256":None,
                "source_skinning":False,"source_skinning_tick":str(tick),
                "source_color_rgb":None,"source_material":None,
                "original_blend_shape_count":0,
                "facial_animation_evaluated":False,
                "source_facial_shapes":[],
                "native_geometry_status":"MISSING_BOUND_USD_MESH"}
            continue
        mesh_path=path+SKIN_MESH_SUFFIX
        if rig.get("skin_mesh_path")!=mesh_path:
            raise RuntimeError("Original skinned USD mesh path changed")
        prim=stage.GetPrimAtPath(mesh_path)
        if not prim or not prim.IsA(UsdGeom.Mesh):
            raise RuntimeError("Original skinned actor mesh is missing")
        mesh=UsdGeom.Mesh(prim)
        counts=list(mesh.GetFaceVertexCountsAttr().Get() or [])
        indices=list(mesh.GetFaceVertexIndicesAttr().Get() or [])
        vertex_count=rig.get("skin_vertex_count")
        if (type(vertex_count) is not int or
            not 3<=vertex_count<=MAX_SKIN_VERTICES or
            len(counts)!=rig.get("skin_face_count") or
            not 1<=len(counts)<=MAX_SKIN_FACES or
            any(type(count) is not int or not 3<=count<=8
                for count in counts) or sum(counts)!=len(indices)):
            raise RuntimeError("Original bounded UsdSkel mesh topology changed")
        groups=[]
        offset=0
        for count in counts:
            face=indices[offset:offset+count]
            offset+=count
            if any(int(i)<0 or int(i)>=vertex_count for i in face) or (
                len(set(face))!=len(face)):
                raise RuntimeError("Original skinned mesh has invalid face indices")
            for j in range(1,count-1):
                groups.append([int(face[0]),int(face[j]),int(face[j+1])])
        total_verts+=vertex_count
        total_triangles+=len(groups)
        if (total_verts>MAX_LIVE_SKIN_VERTICES or
            total_triangles>MAX_LIVE_SKIN_TRIANGLES):
            raise RuntimeError("Original live UsdSkel preview geometry exceeds bound")
        primvar=UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
        uv=None
        face_uv=None
        if primvar:
            values=primvar.Get()
            if values is None:
                raise RuntimeError("Original skinned mesh UV source is unavailable")
            interpolation=str(primvar.GetInterpolation())
            if interpolation=="vertex" and len(values)==vertex_count:
                uv=[[float(u),float(v)] for u,v in values]
            elif interpolation=="faceVarying" and len(values)==sum(counts):
                corner=[[float(u),float(v)] for u,v in values]
                face_uv=[]
                offset=0
                for count in counts:
                    corners=corner[offset:offset+count]
                    offset+=count
                    for j in range(1,count-1):
                        face_uv.append([corners[0],corners[j],corners[j+1]])
            else:
                raise RuntimeError("Original skinned USD UV topology changed")
            if any(not math.isfinite(v) or abs(v)>1024
                   for item in (uv if uv is not None else face_uv)
                   for coords in (item if face_uv is not None else [item])
                   for v in coords):
                raise RuntimeError("Original actor USD UV values are unbounded")
        pose=evaluate_skin(stage,prim,path,tick)
        points=pose["deformed_points"]
        if (not pose["usd_skin_binding_verified"] or
            not pose["skinning_evaluated"] or
            len(points)!=vertex_count or
            any(not math.isfinite(v) or abs(v)>1e8
                for pt in points for v in pt)):
            raise RuntimeError("Original native joint/morph source was not evaluated")
        colors=mesh.GetDisplayColorPrimvar().Get()
        if colors is None or len(colors)!=1:
            raise RuntimeError("Original actor preview color is not authored")
        color=[float(v) for v in colors[0]]
        if any(not math.isfinite(v) or not 0<=v<=1 for v in color):
            raise RuntimeError("Original authored preview color invalid")
        # Imported original GLB source includes an independently authored
        # material and SHA. Refuse rewritten or fabricated GLB material data.
        original_glb=rig.get("original_glb_sha256")
        surface=None
        if original_glb is not None:
            glb_sha=_sha(original_glb)
            attr=prim.GetAttribute("nvp:sourceGLBSHA256")
            if not attr or attr.Get()!=glb_sha:
                raise RuntimeError("Original GLB skin source SHA differs")
            material,_=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
            expected=path+"/Rig/OriginalGLBMaterial"
            if not material or str(material.GetPath())!=expected:
                raise RuntimeError("Original imported actor material binding changed")
            shader=UsdShade.Shader(stage.GetPrimAtPath(
                expected+"/PreviewSurface"))
            if not shader or shader.GetIdAttr().Get()!="UsdPreviewSurface":
                raise RuntimeError("Original imported GLB material shader missing")
            rgb=shader.GetInput("diffuseColor").GetAttr().Get()
            rough=shader.GetInput("roughness").GetAttr().Get()
            metallic=shader.GetInput("metallic").GetAttr().Get()
            if (rgb is None or any(abs(float(a)-b)>1e-5
                                    for a,b in zip(rgb,color)) or
                rough is None or metallic is None or
                not 0<=float(rough)<=1 or not 0<=float(metallic)<=1):
                raise RuntimeError("Imported original GLB PBR source changed")
            surface={
                "format":"nvp.conv06.native_imported_original_glb_surface.v1",
                "original_glb_sha256":glb_sha,
                "base_color_rgb":color,
                "roughness":float(rough),"metallic":float(metallic),
                "source_modified":False,
                "texture_pixels_exposed":False}
        facial=pose.get("source_facial_shapes",[])
        if type(facial) is not list:
            raise RuntimeError("Original native facial morph evidence invalid")
        result[path]={
            "shape":"skinned_mesh",
            "size_m":max(.01,max(abs(v) for pt in points for v in pt)),
            "mesh_points":points,"mesh_triangles":groups,
            "mesh_uvs":uv,"mesh_face_uvs":face_uv,
            "geometry_asset_sha256":layer_sha,
            "source_skinning":True,"source_skinning_tick":str(tick),
            "source_color_rgb":color,"source_material":surface,
            "bound_usd_joint_count":pose["joint_count"],
            "facial_animation_evaluated":
                pose["facial_deformation_evaluated"],
            "original_blend_shape_count":len(facial),
            "source_facial_shapes":facial,
            "native_geometry_status":"VERIFIED_SKINNED"}
    return result
