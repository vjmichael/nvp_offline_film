"""P1-F single original-frame source pack: cast + full body + PBR + voice.

This collects already independently re-opened immutable FilmIndex sources for
an exact original source camera/Take, never authorizes a Blender worker or
pretends it created genuine pictures. Host must separately review licensed
quality, transfer and render the exact sources inside an OS-owned sandbox.
"""
from __future__ import annotations

from hashlib import sha256
import json

from backend.nvp_film_index import FilmIndex
from backend.nvp_p1f_production_character_assets import P1FReviewedProductionCharacters
from backend.nvp_p1f_shot_material_binding import P1FOriginalShotMaterialBinding
from backend.nvp_p1f_actor_dialogue_evidence import original_actor_dialogue_frame


def review_original_character_scene_frame(
    index, pid, *, plan_id, reel_index, frame_offset,
    cast_id, reviewed_look_id, require_complete_body=True
):
    if not isinstance(index, FilmIndex) or type(require_complete_body) is not bool:
        raise TypeError("Trusted canonical FilmIndex and explicit body policy required")
    materials = P1FOriginalShotMaterialBinding(index).for_frame(
        pid, reviewed_look_id, plan_id, reel_index, frame_offset)
    characters = P1FReviewedProductionCharacters(index)
    actor = characters.for_frame(pid, cast_id, plan_id, reel_index, frame_offset)
    speech = original_actor_dialogue_frame(
        index, pid, cast_id, plan_id, reel_index, frame_offset)
    cast = characters.open_cast(pid, cast_id)["data"]
    package = characters.open(pid, cast["package_id"])["data"]
    if (cast["scene_document_sha256"] != materials["scene_document_sha256"] or
            actor["source_take_sha256"] != materials["take_document_sha256"] or
            actor["source_tick"] != materials["source_tick"] or
            actor["output_tick"] != materials["output_tick"] or
            speech["source_tick"] != materials["source_tick"] or
            speech["take_document_sha256"] != actor["source_take_sha256"] or
            speech["actor_id"] != actor["actor_id"] or
            speech["cast_document_sha256"] != actor["cast_document_sha256"]):
        raise RuntimeError("Combined original scene ActorID/look/voice source clocks disagree")
    rest = actor.get("glb_full_body_rest_axes")
    if require_complete_body and (not isinstance(rest, dict) or
                                  rest.get("glb_inverse_bind_rest_verified") is not True):
        raise RuntimeError("Original shot has no complete reviewed full-body GLB rest source")
    observation = {
        "format": "nvp.p1f.original_character_scene_source_bundle.v1",
        "status": "REVIEWED_ORIGINAL_SOURCES_NOT_RENDERED",
        "project_id": pid, "plan_id": plan_id,
        "reel_index": reel_index, "frame_offset": frame_offset,
        "scene_document_sha256": materials["scene_document_sha256"],
        "source_take_document_sha256": materials["take_document_sha256"],
        "original_source_tick": actor["source_tick"],
        "original_output_tick": actor["output_tick"],
        "actor_id": actor["actor_id"],
        "actor_path": actor["actor_path"],
        "actor_cast_document_sha256": actor["cast_document_sha256"],
        "original_glb_sha256": actor["glb_sha256"],
        "actor_rights_evidence_sha256": actor["source_rights_evidence_sha256"],
        "glb_full_body_rest_axes": rest,
        "glb_decoded_skinned_vertices": package["decoded_geometry"]["decoded_skinned_vertices"],
        "original_shape_weights": actor["facial_weights"],
        "source_voice_event_id": speech["dialogue_event_id"],
        "source_pcm_window_sha256": speech["voice_pcm_sha256"],
        "original_material_look_id": materials["look_id"],
        "original_material_look_sha256": materials["look_document_sha256"],
        "original_material_source_sha256": materials["material_set_document_sha256"],
        "original_texture_sha256": {
            slot: data["sha256"]
            for slot, data in materials["texture_sources"].items()
        },
        "full_body_original_usd_animation_verified": False,
        "actor_lipsync_deformation_verified": False,
        "original_mesh_terrain_contact_verified": False,
        "detailed_asset_rights_independently_cleared": False,
        "cycles_rendered": False, "worker_authorized": False,
        "filmmaker_film_master_approved": False,
    }
    encoded = json.dumps(observation,sort_keys=True,separators=(",",":"),
                         ensure_ascii=True,allow_nan=False).encode("ascii")
    return {**observation, "source_review_sha256": sha256(encoded).hexdigest()}
