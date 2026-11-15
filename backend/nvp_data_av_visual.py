"""DA-04: bounded, exact-time 3D geometry data for native WebGL viewing.

Exports *scene primitives and transforms*, never rendered pictures or
a frame grid. This currently supports the actual verified NVP OpenUSD
procedural cube/sphere assets; other scene object types are drawn only
as location/role gizmos, not falsely represented as accepted character
geometry. The React/Three.js renderer owns ephemeral GPU buffers.
"""
from __future__ import annotations

from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry

FORMAT="nvp.data_av.native_visual_state.v1"
MAX_OBJECTS=64


def visual_state(index:FilmIndex,project_id,scene_snapshot):
    if not isinstance(index,FilmIndex):
        raise TypeError("Actual FilmIndex is required for source geometry")
    if (type(scene_snapshot) is not dict or
        not isinstance(scene_snapshot.get("objects"),list) or
        len(scene_snapshot["objects"])>MAX_OBJECTS):
        raise ValueError("Invalid bounded USD world-state snapshot")
    visual=[]
    assets=OpenUSDAssetRegistry(index)
    for obj in scene_snapshot["objects"]:
        role=obj["semantic_role"]
        shape="gizmo"
        size=0.4
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
            if shape not in ("cube","sphere"):
                raise RuntimeError("Unsupported native procedural geometry")
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
        })
    return {"format":FORMAT,
            "time_tick":str(scene_snapshot["time_tick"]),
            "scene_document_sha256":scene_snapshot["scene_document_sha256"],
            "timeline_document_sha256":scene_snapshot["timeline_document_sha256"],
            "objects":visual,"image_samples_rendered":False,
            "frame_grid_authority":False,"source_modified":False}
