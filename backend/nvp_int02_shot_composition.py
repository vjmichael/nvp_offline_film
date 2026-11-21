"""INT-02C: compose approved shot-local USD opinions at exact original Film Time.

No editing of the original USD layers. The result is an ephemeral view of an
approved SHOT-01 layer over the frozen Take; it is not a fallback image or a
render authorization. Unknown or unimplemented director intention fails closed.
"""
from __future__ import annotations

import hashlib
import json
import math

from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import _usd
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_openusd_native_schemas import evaluate_native_schema
from backend.nvp_temporal_ledger import _int

SUPPORTED_OPINIONS = frozenset((
    "translation_offset", "visibility", "camera_focal_length_mm",
    "camera_f_stop", "camera_focus_distance_m",
    "camera_sensor_width_mm", "camera_sensor_height_mm", "light_intensity",
))


def validate_source_shot(index: FilmIndex, project_id, *,
                         take_id, take_sha256, shot_id, shot_revision,
                         shot_sha256, source_in, source_out, listener_path=None):
    """Pin exactly one director layer, refusing unrendered sound/actor intent."""
    if not isinstance(index, FilmIndex):
        raise TypeError("Original FilmIndex required for shot composition")
    shot = index.read_revision(project_id, shot_id, shot_revision)
    doc = shot["data"]
    if (shot["kind"] != "presentation" or
        shot["document_sha256"] != shot_sha256 or
        doc.get("format") != "nvp.usd.director_shot_override.v1" or
        doc.get("take_id") != take_id or
        doc.get("take_document_sha256") != take_sha256 or
        doc.get("director_shot_change_approved") is not True or
        doc.get("original_scene_modified") is not False or
        not doc["start_tick"] <= source_in < source_out <= doc["end_tick"]):
        raise RuntimeError("Committed shot is not pinned to the original Take/interval")
    scene = index.read_revision(project_id, doc["scene_id"], doc["scene_revision"])
    if (scene["document_sha256"] != doc["scene_document_sha256"] or
        scene["kind"] != "scene"):
        raise RuntimeError("Director shot original scene revision changed")
    roles = scene["data"]["prim_roles"]
    for opinion in doc["opinions"]:
        prop, path = opinion["property"], opinion["path"]
        if prop not in SUPPORTED_OPINIONS:
            raise RuntimeError("Unimplemented director opinion cannot be silently rendered: " + prop)
        if prop == "translation_offset" and (
                path == listener_path or roles.get(path) != "camera"):
            # Original PCM still uses frozen listener and emitter positions.
            # No shot-local audio retiming or spatial adjustment may be guessed.
            raise RuntimeError("Shot motion requires a composed acoustic mixer before delivery")
    return shot


def compose_shot_snapshot(index: FilmIndex, project_id, *,
                          take_id, take_sha256, shot_id, shot_revision,
                          shot_sha256, tick, source_snapshot, listener_path):
    """Re-evaluate the actual composed USD stage, not just a JSON opinion list."""
    _int(tick, "composed original Film Time")
    if source_snapshot.get("time_tick") != tick:
        raise RuntimeError("Shot visual state is not at the original source moment")
    shot = validate_source_shot(
        index, project_id, take_id=take_id, take_sha256=take_sha256,
        shot_id=shot_id, shot_revision=shot_revision,
        shot_sha256=shot_sha256, source_in=tick, source_out=tick+1,
        listener_path=listener_path)
    compositor = OpenUSDShotOverrides(
        index, verify_director_action=lambda event, scope: False)
    reopened, scene, stage = compositor.open_shot(
        project_id, shot_id, shot_revision, tick=tick)
    if reopened["document_sha256"] != shot_sha256:
        raise RuntimeError("Composed shot changed while its USD layer was reopened")
    if source_snapshot.get("scene_document_sha256") != scene["document_sha256"]:
        raise RuntimeError("Shot USD stage belongs to a different scene revision")
    _, _, Usd, UsdGeom = _usd()
    objects = []
    schemas = []
    for obj in source_snapshot["objects"]:
        path = obj["path"]
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsDefined() or not prim.IsA(UsdGeom.Xformable):
            raise RuntimeError("Shot-composed USD object disappeared from original stage")
        visibility = UsdGeom.Imageable(prim).ComputeVisibility(
            Usd.TimeCode(float(tick)))
        if str(visibility) == "invisible":
            if path == listener_path:
                raise RuntimeError("Shot hides the authored original soundtrack listener")
            continue
        matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
            Usd.TimeCode(float(tick)))
        values = [[float(matrix.GetRow(i)[j]) for j in range(4)]
                  for i in range(4)]
        if any(not math.isfinite(x) or abs(x) > 1e12
               for row in values for x in row):
            raise RuntimeError("Non-finite director-composed USD geometry")
        changed = dict(obj)
        changed["world_matrix"] = values
        changed["world_translation"] = [float(v) for v in matrix.ExtractTranslation()]
        objects.append(changed)
        # Reevaluate real camera and light schema values from the composed
        # USD stage. Intention-only opinions are rejected in preflight.
        if source_snapshot.get("native_schema_version"):
            obs = evaluate_native_schema(
                stage, path, obj["semantic_role"], tick, [])
            if obs is not None:
                schemas.append(obs)
    combined = dict(source_snapshot)
    combined["objects"] = objects
    combined["native_scene_schemas"] = schemas
    combined["shot_composed"] = True
    combined["shot_id"] = shot_id
    combined["shot_revision"] = shot_revision
    combined["shot_document_sha256"] = shot_sha256
    combined["shot_layer_sha256"] = shot["data"]["usd_layer_sha256"]
    combined["canonical_scene_unchanged"] = True
    combined["source_performance_modified"] = False
    combined["snapshot_sha256"] = hashlib.sha256(json.dumps(
        {k:v for k,v in combined.items() if k != "snapshot_sha256"},
        sort_keys=True, separators=(",", ":"),allow_nan=False).encode("ascii")).hexdigest()
    return combined
