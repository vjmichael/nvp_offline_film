"""WO6-03: exact-source, bounded film context for a trusted AI crew reader.

This is not model inference, a creator approval, a picture render, or a
new database. OpenUSD/FilmIndex/TemporalLedger/recorded PCM are reopened
from EXISTING project storage and checked before preparing a read-only
context. Everything is exact-revision and time-scoped, with omissions and
limits visible to the model. A human/host still decides what is shared.
"""
from __future__ import annotations

import hashlib
import json

from backend.nvp_ai_context import assemble_task_context
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_scene import OpenUSDSceneBridge, _evaluate, _usd
from backend.nvp_openusd_take import OpenUSDTakeCapture, FORMAT as TAKE_FORMAT
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND, _int
from backend.nvp_studio import Studio

FORMAT = "nvp.wo6.verified_scene_crew_context.v1"
MAX_PRIMS = 64
MAX_EVENTS = 48
MAX_AUDIO_SOURCES = 16
MAX_PACKET_BYTES = 240000
CAPABILITY = {
    "id": "nvp.film.read_scene_crew_context.v1",
    "description": "Reopen an exact frozen Take, native OpenUSD actor/camera/"
                   "light transforms, event-time dialogue/music/sound, recorded "
                   "audio source SHA and optional exact screenplay scene",
    "effect": "read",
    "input_schema": {
        "project_id": "current authorized film project",
        "take_id": "existing immutable OpenUSD Digital Take ID",
        "take_revision": "exact revision 1",
        "tick": "integer authoritative Film Time tick within Take",
        "source_revision": "optional exact current screenplay revision",
        "screenplay_scene_id": "optional scene ID, requires source_revision",
        "max_prims": "integer 1..64",
        "max_events": "integer 1..48",
    },
    "result_schema": FORMAT,
    "requires_host_authorization": True,
    "executable_by_model": False,
    "new_take_authorized": False,
}


def _canonical(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def assemble_film_crew_context(
    index: FilmIndex, project_id: str, take_id: str, take_revision: int,
    tick: int, *, source_revision=None, screenplay_scene_id=None,
    max_prims: int = 32, max_events: int = 24,
) -> dict:
    if not isinstance(index, FilmIndex):
        raise TypeError("Trusted existing FilmIndex is required")
    _require_pid(project_id)
    _id(take_id, "Digital Take identity")
    if type(take_revision) is not int or take_revision != 1:
        raise ValueError("Digital Take is single-commit; exact revision 1 required")
    _int(tick, "exact Film Time tick", maximum=2**53-1)
    if (type(max_prims) is not int or not 1 <= max_prims <= MAX_PRIMS or
            type(max_events) is not int or not 1 <= max_events <= MAX_EVENTS):
        raise ValueError("Bounded scene prim/event limits required")
    if (source_revision is None) != (screenplay_scene_id is None):
        raise ValueError("Screenplay scene and exact revision must be selected together")
    take = index.read_revision(project_id, take_id, take_revision)
    doc = take["data"]
    if (take["kind"] != "take" or doc.get("format") != TAKE_FORMAT or
            doc.get("frozen") is not True or
            type(doc.get("duration_tick")) is not int or
            not 0 <= tick < doc["duration_tick"]):
        raise PermissionError("Not a valid frozen OpenUSD Take at selected Film Time")
    # Reopens the actual native layers, temporal source references and
    # saved Take checkpoints. This must not silently accept plausible
    # metadata from an unreopened source.
    freezer = OpenUSDTakeCapture(index, verify_creator_action=lambda *_: False)
    proof = freezer.verify_take(project_id, take_id)
    if (proof["status"] != "VERIFIED_FROZEN_DATA_TAKE" or
            proof["take_document_sha256"] != take["document_sha256"] or
            proof["scene_document_sha256"] != doc["scene_document_sha256"] or
            proof["timeline_document_sha256"] != doc["timeline_document_sha256"]):
        raise PermissionError("Original Digital Take source evidence not verified")
    bridge = OpenUSDSceneBridge(index)
    src, stage = bridge.open(
        project_id, doc["scene_id"], doc["scene_revision"])
    if src["document_sha256"] != doc["scene_document_sha256"]:
        raise PermissionError("Original scene revision SHA changed")
    timeline = TemporalLedger(index)
    timeline_record = timeline._revision(
        project_id, doc["timeline_id"], doc["timeline_revision"])
    if timeline_record["document_sha256"] != doc["timeline_document_sha256"]:
        raise PermissionError("Original temporal revision SHA changed")
    roles = src["data"]["prim_roles"]
    ordered = sorted(roles)
    if not ordered:
        raise RuntimeError("OpenUSD scene has no identifiable prim roles")
    _, Sdf, Usd, UsdGeom = _usd()
    selected = ordered[:max_prims]
    schema_controls = []
    if src["data"].get("performance_channels"):
        from backend.nvp_openusd_channels import evaluate_parameter_channels
        schema_controls = evaluate_parameter_channels(
            stage, src["data"]["performance_channels"], roles, tick)
    visible = []
    for path in selected:
        pose = _evaluate(stage, path, tick, Sdf, Usd, UsdGeom)
        item = {
            "prim_path": path,
            "role": roles[path],
            "world_translation": pose["world_translation"],
            "authored_scene_revision_sha256": src["document_sha256"],
            "at_tick": tick,
            "source_pose_not_finished_frame": True,
        }
        if roles[path] in ("camera", "light") and src["data"].get("native_schema_version"):
            from backend.nvp_openusd_native_schemas import evaluate_native_schema
            item["native_schema"] = evaluate_native_schema(
                stage, path, roles[path], tick, schema_controls)
        visible.append(item)
    # Query one extra event to know whether the active-time packet is
    # incomplete. The event ledger verifies *all* source hashes at
    # frozen-Take reopening; do not invent missing dialogue text.
    active = timeline.events_at(
        project_id, doc["timeline_id"], doc["timeline_revision"],
        tick=tick, limit=max_events+1)
    truncated_events = len(active) > max_events
    active = active[:max_events]
    relevant_sound = [
        event for event in active
        if event["event_kind"] in ("sound", "music", "dialogue")
    ]
    known_sound = []
    for event in relevant_sound[:MAX_AUDIO_SOURCES]:
        source = index.read_revision(
            project_id, event["source_id"], event["source_revision"])
        if source["document_sha256"] != event["source_document_sha256"]:
            raise PermissionError("Sound event source identity changed")
        item = {
            "event_id": event["event_id"],
            "event_kind": event["event_kind"],
            "source_id": event["source_id"],
            "source_revision": event["source_revision"],
            "source_kind": source["kind"],
            "source_document_sha256": source["document_sha256"],
            "recorded_sound_pcm_verified": False,
            "mastered_final_audio_verified": False,
        }
        if source["kind"] == "audio":
            rec = RecordedSoundSources(index).describe(
                project_id, event["source_id"], event["source_revision"])
            samples = rec["data"]["sample_count"]
            # Evidence is from actual saved PCM bytes, not just a manifest.
            if samples < 1:
                raise PermissionError("Recorded source contains no samples")
            RecordedSoundSources(index).read(
                project_id, event["source_id"], event["source_revision"],
                0, min(samples, 64))
            item.update({
                "recorded_sound_pcm_verified": True,
                "sample_rate": rec["data"]["sample_rate"],
                "channels": rec["data"]["channels"],
                "sample_count": samples,
            })
        known_sound.append(item)
    screenplay = None
    if source_revision is not None:
        if type(source_revision) is not int or source_revision < 0:
            raise ValueError("Select an exact nonnegative screenplay revision")
        screenplay = assemble_task_context(
            index.studio, project_id, source_revision, "scene_coverage",
            scene_id=screenplay_scene_id, max_lines=50)
    # An immutable Take can remain historically valid when a new scene
    # revision exists; never describe an old Take as the current edit.
    heads = {r["object_id"]: r["head_revision"]
             for r in index.list_objects(project_id)}
    anchored = [
        {"object_id": doc["scene_id"], "revision": doc["scene_revision"],
         "document_sha256": doc["scene_document_sha256"],
         "head_revision_observed": heads.get(doc["scene_id"]),
         "is_current_head": heads.get(doc["scene_id"]) == doc["scene_revision"]},
        {"object_id": doc["timeline_id"], "revision": doc["timeline_revision"],
         "document_sha256": doc["timeline_document_sha256"],
         "head_revision_observed": heads.get(doc["timeline_id"]),
         "is_current_head": heads.get(doc["timeline_id"]) == doc["timeline_revision"]},
    ]
    if index.read_revision(project_id, take_id, 1)["document_sha256"] != take["document_sha256"]:
        raise RuntimeError("Original Take revision changed during context assembly")
    result = {
        "format": FORMAT,
        "project_id": project_id,
        "source_take": {"take_id": take_id, "take_revision": 1,
                        "document_sha256": take["document_sha256"],
                        "frozen": True, "independently_reopened": True},
        "film_time_tick": tick,
        "ticks_per_second": TICKS_PER_SECOND,
        "duration_tick": doc["duration_tick"],
        "scene_id": doc["scene_id"],
        "scene_revision": doc["scene_revision"],
        "scene_document_sha256": doc["scene_document_sha256"],
        "temporal_id": doc["timeline_id"],
        "temporal_revision": doc["timeline_revision"],
        "temporal_document_sha256": doc["timeline_document_sha256"],
        "source_heads": anchored,
        "historical_take_not_current_scene": any(
            not x["is_current_head"] for x in anchored),
        "visible_scene_prims": visible,
        "scene_prim_count": len(ordered),
        "scene_prim_count_omitted": len(ordered)-len(visible),
        "active_events": active,
        "active_events_truncated": truncated_events,
        "sound_events": known_sound,
        "sound_events_omitted": max(0, len(relevant_sound)-len(known_sound)),
        "screenplay_scene_context": screenplay,
        "no_unlisted_actors_or_sound_assumed": True,
        "visual_frames_rendered": False,
        "mastered_soundtrack_replayed": False,
        "human_artist_approval": False,
        "authorization_provided": False,
        "effect": "read",
        "side_effects_performed": False,
    }
    raw = _canonical(result)
    if len(raw) > MAX_PACKET_BYTES:
        raise ValueError("Source context exceeded bounded model context packet")
    result["context_sha256"] = hashlib.sha256(raw).hexdigest()
    return result
