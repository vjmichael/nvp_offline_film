"""DA-04: bounded, exact-time 3D geometry data for native WebGL viewing.

Exports *scene primitives and transforms*, never rendered pictures or
a frame grid. This supports source-verified NVP procedural cubes/spheres and bounded
original triangle-mesh topology. Unbound actor positions remain only
explicit scene-location gizmos, never synthetic character geometry. The React/Three.js renderer owns ephemeral GPU buffers.
"""
from __future__ import annotations

from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry

FORMAT="nvp.data_av.native_visual_state.v1"
MAX_OBJECTS=64
MAX_MESH_POINTS_TOTAL=4096
MAX_MESH_TRIANGLES_TOTAL=8192


def visual_state(index:FilmIndex,project_id,scene_snapshot,*,
                 scene_id=None,scene_revision=None):
    if not isinstance(index,FilmIndex):
        raise TypeError("Actual FilmIndex is required for source geometry")
    if (type(scene_snapshot) is not dict or
        not isinstance(scene_snapshot.get("objects"),list) or
        len(scene_snapshot["objects"])>MAX_OBJECTS):
        raise ValueError("Invalid bounded USD world-state snapshot")
    if (scene_id is None)!=(scene_revision is None):
        raise ValueError("Live skin requires both scene identity and exact revision")
    skins={}
    if scene_id is not None:
        from backend.nvp_data_av_skinning import verified_live_skins
        skins=verified_live_skins(index,project_id,scene_snapshot,
            scene_id=scene_id,scene_revision=scene_revision)
    visual=[]
    mesh_points_total=0
    mesh_triangles_total=0
    assets=OpenUSDAssetRegistry(index)
    for obj in scene_snapshot["objects"]:
        role=obj["semantic_role"]
        shape="gizmo"
        size=0.4
        mesh_points=None
        mesh_triangles=None
        binding=obj.get("asset")
        skin=skins.get(obj["path"])
        if skin is not None and binding is not None:
            raise RuntimeError("Ambiguous original actor mesh and reusable asset")
        if binding is not None:
            source,_layer=assets.open(
                project_id,binding["asset_id"],
                binding["asset_revision"])
            if (source["document_sha256"]!=binding["asset_document_sha256"] or
                source["data"]["layer_sha256"]!=binding["asset_layer_sha256"]):
                raise RuntimeError("Live geometry does not match frozen USD asset SHA")
            shape=source["data"]["shape"]
            size=source["data"]["size_m"]
            if shape not in ("cube","sphere","mesh"):
                raise RuntimeError("Unsupported original OpenUSD geometry")
            if shape=="mesh":
                mesh_points=source["data"]["points"]
                mesh_triangles=source["data"]["triangles"]
                mesh_points_total+=len(mesh_points)
                mesh_triangles_total+=len(mesh_triangles)
                if (mesh_points_total>MAX_MESH_POINTS_TOTAL or
                        mesh_triangles_total>MAX_MESH_TRIANGLES_TOTAL):
                    raise RuntimeError("Live original USD mesh budget exceeded")
        if skin is not None:
            shape=skin["shape"]
            size=skin["size_m"]
            mesh_points=skin["mesh_points"]
            mesh_triangles=skin["mesh_triangles"]
            if shape=="skinned_mesh":
                mesh_points_total+=len(mesh_points)
                mesh_triangles_total+=len(mesh_triangles)
                if (mesh_points_total>MAX_MESH_POINTS_TOTAL or
                        mesh_triangles_total>MAX_MESH_TRIANGLES_TOTAL):
                    raise RuntimeError("Live source character mesh budget exceeded")
            elif shape!="missing_rig_geometry":
                raise RuntimeError("Unknown original rigged actor presentation")
        matrix=obj["world_matrix"]
        if (type(matrix) is not list or len(matrix)!=4 or
            any(type(row) is not list or len(row)!=4 for row in matrix)):
            raise RuntimeError("Invalid native USD object transform")
        visual.append({
            "path":obj["path"],"semantic_role":role,
            "shape":shape,"size_m":size,
            "world_matrix":matrix,
            "world_translation":obj["world_translation"],
            "geometry_asset_sha256":(
                binding["asset_document_sha256"] if binding else
                skin["geometry_asset_sha256"] if skin else None),
            "gizmo_only":binding is None and skin is None,
            "mesh_points":mesh_points,
            "mesh_triangles":mesh_triangles,
            "source_skinning":shape=="skinned_mesh",
            "source_rigged_actor":skin is not None,
            "source_skinning_tick":skin["source_skinning_tick"] if skin else None,
            "source_color_rgb":skin["source_color_rgb"] if skin else None,
            "native_geometry_status":(
                "MISSING_BOUND_USD_MESH" if shape=="missing_rig_geometry"
                else "VERIFIED_SKINNED" if shape=="skinned_mesh"
                else "VERIFIED_STATIC" if binding else "UNMESHED_SCENE_MARKER"),
            "facial_animation_evaluated":False,
        })
    return {"format":FORMAT,
            "time_tick":str(scene_snapshot["time_tick"]),
            "scene_document_sha256":scene_snapshot["scene_document_sha256"],
            "timeline_document_sha256":scene_snapshot["timeline_document_sha256"],
            "objects":visual,"image_samples_rendered":False,
            "frame_grid_authority":False,"source_modified":False}
