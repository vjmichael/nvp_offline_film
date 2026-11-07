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


def visual_state(index:FilmIndex,project_id,scene_snapshot):
    if not isinstance(index,FilmIndex):
        raise TypeError("Actual FilmIndex is required for source geometry")
    if (type(scene_snapshot) is not dict or
        not isinstance(scene_snapshot.get("objects"),list) or
        len(scene_snapshot["objects"])>MAX_OBJECTS):
        raise ValueError("Invalid bounded USD world-state snapshot")
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
                binding["asset_document_sha256"] if binding else None),
            "gizmo_only":binding is None,
            "mesh_points":mesh_points,
            "mesh_triangles":mesh_triangles,
        })
    return {"format":FORMAT,
            "time_tick":str(scene_snapshot["time_tick"]),
            "scene_document_sha256":scene_snapshot["scene_document_sha256"],
            "timeline_document_sha256":scene_snapshot["timeline_document_sha256"],
            "objects":visual,"image_samples_rendered":False,
            "frame_grid_authority":False,"source_modified":False}
