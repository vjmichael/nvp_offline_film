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
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_story_bible import sha_scene
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_scene import OpenUSDSceneBridge, _evaluate, _usd
from backend.nvp_openusd_take import OpenUSDTakeCapture, FORMAT as TAKE_FORMAT
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND, _int
from backend.nvp_studio import Studio

FORMAT = "nvp.wo6.verified_scene_crew_context.v1"
MAX_PRIMS = 64
MAX_EVENTS = 48
MAX_AUDIO_SOURCES = 16
MAX_APPROVED_FACTS = 32
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
        "shot_sequence_id": "optional authored camera shot timeline",
        "shot_sequence_revision": "exact revision, required with shot_sequence_id",
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
    shot_sequence_id=None, shot_sequence_revision=None,
    dialogue_selection_id=None, dialogue_selection_revision=None,
    dialogue_route_request=None,
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
    if (shot_sequence_id is None) != (shot_sequence_revision is None):
        raise ValueError("Shot timeline ID and exact revision must be selected together")
    if (dialogue_selection_id is None) != (dialogue_selection_revision is None):
        raise ValueError("Selected dialogue requires exact source ID and revision")
    if dialogue_route_request is not None:
        if (type(dialogue_route_request) is not dict or
                dialogue_selection_id is None or dialogue_selection_revision is None):
            raise ValueError("Acted dialogue needs a selected source revision and exact actor request")
        if (dialogue_route_request.get("selection_id") != dialogue_selection_id or
                dialogue_route_request.get("selection_revision") != dialogue_selection_revision or
                dialogue_route_request.get("source_take_id") != take_id or
                dialogue_route_request.get("film_time_tick") != tick):
            raise PermissionError("AI dialogue request does not match the chosen Take, time and selection")
    if dialogue_selection_id is not None:
        _id(dialogue_selection_id, "creator-selected object-actor dialogue")
        if (type(dialogue_selection_revision) is not int or
                dialogue_selection_revision < 1):
            raise ValueError("Exact approved dialogue revision required")
    if shot_sequence_id is not None:
        _id(shot_sequence_id, "shot timeline")
        if type(shot_sequence_revision) is not int or shot_sequence_revision < 1:
            raise ValueError("Shot timeline revision must be an exact positive integer")
    take = index.read_revision(project_id, take_id, take_revision)
    doc = take["data"]
    if (take["kind"] != "take" or doc.get("format") != TAKE_FORMAT or
            doc.get("frozen") is not True or
            type(doc.get("duration_tick")) is not int):
        raise PermissionError("Not a valid frozen OpenUSD Take")
    if tick >= doc["duration_tick"]:
        raise ValueError("Requested Film Time exceeds frozen source duration")
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
            "sample_window_pcm_verified": False,
            "full_recorded_audio_verified": False,
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
                "sample_window_pcm_verified": True,
                "verified_sample_count": min(samples, 64),
                "sample_rate": rec["data"]["sample_rate"],
                "channels": rec["data"]["channels"],
                "sample_count": samples,
            })
        known_sound.append(item)
    shot_selection = None
    if shot_sequence_id is not None:
        authored = ExactTimeShotSequence(index).read(
            project_id, shot_sequence_id, shot_sequence_revision)
        if (authored["scene_id"] != doc["scene_id"] or
                authored["scene_revision"] != doc["scene_revision"] or
                authored["scene_document_sha256"] != doc["scene_document_sha256"]):
            raise PermissionError("Selected authored shots belong to a different OpenUSD scene")
        if tick >= int(authored["duration_tick"]):
            raise ValueError("Selected authored camera shots do not cover this Take time")
        selected_shots = [
            shot for shot in authored["shots"]
            if int(shot["start_tick"]) <= tick < int(shot["end_tick"])
        ]
        if len(selected_shots) > 1:
            raise RuntimeError("Conflicting creator shots overlap at this Film Time")
        shot_selection = {
            "shot_timeline_id": shot_sequence_id,
            "shot_timeline_revision": shot_sequence_revision,
            "shot_timeline_document_sha256": authored["document_sha256"],
            "authored_shot_count": len(authored["shots"]),
            "camera_coverage_status": ("SELECTED_AUTHORED_CAMERA"
                if selected_shots else "INTENTIONAL_CAMERA_GAP"),
            "selected_shot": selected_shots[0] if selected_shots else None,
            "camera_selected_by_source_not_ai_guess": True,
            "rendered_output_proven": False,
        }
    selected_dialogue = None
    if dialogue_selection_id is not None:
        from backend.nvp_film03_object_dialogue import read_scene_dialogue_selection
        selected_dialogue = read_scene_dialogue_selection(
            index, project_id, dialogue_selection_id,
            dialogue_selection_revision, tick=tick, expected_take_id=take_id)
        if selected_dialogue["source_take_sha256"] != take["document_sha256"]:
            raise PermissionError("Scene crew received a dialogue selection from another frozen Take")
    canonical_dialogue_route = None
    if dialogue_route_request is not None:
        from backend.nvp_film03_dialogue_manager import ActorDialogueManager
        canonical_dialogue_route = ActorDialogueManager(index).route(
            project_id, dialogue_route_request)
        if canonical_dialogue_route["source_take_sha256"] != take["document_sha256"]:
            raise PermissionError("AI dialogue route points to another real frozen Take")
    screenplay = None
    approved_facts = []
    bible_status = "NO_SCREENPLAY_SCENE_SELECTED"
    approved_fact_omitted = 0
    if source_revision is not None:
        if type(source_revision) is not int or source_revision < 0:
            raise ValueError("Select an exact nonnegative screenplay revision")
        screenplay = assemble_task_context(
            index.studio, project_id, source_revision, "scene_coverage",
            scene_id=screenplay_scene_id, max_lines=50)
        # The Story Bible is *optional* and creator-owned. A read must not
        # initialize it (which would CREATE TABLEs), turn proposals into canon,
        # or match a character merely by a similar USD prim name.
        project = index.studio.get_project(project_id)
        if project["revision"] != source_revision:
            raise RuntimeError("Screenplay changed while collecting actor canon")
        selected_story_scene = next(
            (row for row in project["scenes"]
             if row["id"] == screenplay_scene_id), None)
        if selected_story_scene is None:
            raise RuntimeError("Selected screenplay scene disappeared")
        scene_sha = sha_scene(selected_story_scene)
        with index.studio._connection() as db:
            present = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND "
                "name IN ('bible_entities','bible_scene_links','bible_facts')")}
            if len(present) != 3:
                bible_status = "STORY_BIBLE_NOT_CREATED"
            else:
                accepted = db.execute("""
                    SELECT e.id AS entity_id,e.name AS entity_name,
                      e.kind AS entity_kind,e.revision AS entity_revision,
                      f.id AS fact_id,f.fact_key,f.fact_value,f.story_scope,
                      l.scene_sha,l.screenplay_revision
                    FROM bible_entities e
                    JOIN bible_scene_links l ON
                      l.project_id=e.project_id AND l.entity_id=e.id
                    JOIN bible_facts f ON
                      f.project_id=e.project_id AND f.entity_id=e.id
                    WHERE e.project_id=? AND l.scene_id=?
                      AND f.status='accepted'
                    ORDER BY e.kind,e.name,e.id,f.fact_key,f.id
                    LIMIT ?
                """,(project_id,screenplay_scene_id,MAX_APPROVED_FACTS+1)).fetchall()
                stale_links = 0
                for row in accepted:
                    fact = dict(row)
                    if (fact["scene_sha"] != scene_sha or
                            fact["screenplay_revision"] != source_revision):
                        stale_links += 1
                        continue
                    if len(approved_facts) < MAX_APPROVED_FACTS:
                        approved_facts.append({
                            "entity_id":fact["entity_id"],
                            "entity_name":fact["entity_name"],
                            "entity_kind":fact["entity_kind"],
                            "entity_revision":fact["entity_revision"],
                            "fact_id":fact["fact_id"],
                            "key":fact["fact_key"],
                            "value":fact["fact_value"],
                            "scope":fact["story_scope"],
                            "screenplay_scene_id":screenplay_scene_id,
                            "scene_text_sha256":scene_sha,
                            "creator_accepted":True,
                            "usd_actor_binding_proven":False,
                        })
                approved_fact_omitted = max(
                    0,len(accepted)-stale_links-len(approved_facts))
                bible_status = ("HAS_STALE_SCENE_LINKS_OMITTED"
                    if stale_links else "SCENE_LINKED_ACCEPTED_FACTS_ONLY")
        # A matching character name is not a proven binding to a rig or
        # OpenUSD actor. The actor/scene semantic link requires separate
        # source-authorized registry data.
    # An immutable Take can remain historically valid when a new scene
    # revision exists; never describe an old Take as the current edit.
    # O(1) exact-object head checks. Long films can have millions of
    # assets; never materialize the whole production catalog to report
    # whether these two trusted source revisions are still the heads.
    heads = {
        doc["scene_id"]: index.read_revision(project_id,doc["scene_id"])["revision"],
        doc["timeline_id"]: index.read_revision(project_id,doc["timeline_id"])["revision"],
    }
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
        "authored_camera_selection": shot_selection,
        "authored_object_actor_dialogue_selection": selected_dialogue,
        "authoritative_actorid_dialogue_route": canonical_dialogue_route,
        "dialogue_source_inspection_is_not_permission_to_speak":
            canonical_dialogue_route is None,
        "screenplay_scene_context": screenplay,
        "approved_story_facts": approved_facts,
        "approved_story_facts_omitted_at_least": approved_fact_omitted,
        "story_bible_status": bible_status,
        "screenplay_to_usd_actor_identity_verified": False,
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
