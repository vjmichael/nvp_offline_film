"""P1-B/C: project-authoritative ActorID, native USD rig and original dialogue.

ActorID is one FilmIndex 'actor' source; scene bindings are exact-versioned
dependencies. Dialogue references ORIGINAL immutable PCM/timeline, never a
generated voice, inferred speaker, implicit rig, or rewritten frozen Take.
"""
from __future__ import annotations

import hashlib
import json
import re

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_temporal_ledger import TemporalLedger, _int
from backend.nvp_data_av_source import RecordedSoundSources

ACTOR_FORMAT = "nvp.p1bc.actor_identity.v1"
DIALOGUE_FORMAT = "nvp.p1bc.actor_original_dialogue.v1"
MAX_ACTORS = 8
MAX_CUES = 128
LABEL = re.compile(r"[\w][\w .,'()-]{0,119}\Z", re.UNICODE)


def _canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


class ActorDirectory:
    def __init__(self, index: FilmIndex, *, verify_director_action):
        if not isinstance(index, FilmIndex) or not callable(verify_director_action):
            raise TypeError("Trusted FilmIndex and native director authorization required")
        self.index = index
        self.authorize = verify_director_action

    def register(self, project_id, actor_id, *, display_name, creator_event):
        """Register a stable ActorID before attaching it to a USD prim."""
        _require_pid(project_id)
        _id(actor_id, "canonical ActorID")
        if type(display_name) is not str or not LABEL.fullmatch(display_name):
            raise ValueError("Actor display label must be a bounded human label")
        doc = {"format": ACTOR_FORMAT, "actor_id": actor_id,
               "display_name": display_name,
               "voice_identity": "not_yet_assigned",
               "original_voice_recorded": False,
               "geometry_and_rig_attached": False,
               "synthetic_voice_generated": False}
        exact = {"operation": "nvp.p1bc.register_actor.v1",
                 "project_id": project_id, "actor_id": actor_id,
                 "profile_sha256": hashlib.sha256(_canonical(doc)).hexdigest()}
        if self.authorize(creator_event, dict(exact)) is not True:
            raise PermissionError("Director did not approve canonical ActorID")
        return self.index.register_revision(project_id, actor_id, "actor", doc,
                                            expected_revision=0)

    def open(self, project_id, actor_id, revision=1):
        _require_pid(project_id)
        _id(actor_id, "canonical ActorID")
        record = self.index.read_revision(project_id, actor_id, revision)
        data = record["data"]
        if (record["kind"] != "actor" or
            data.get("format") != ACTOR_FORMAT or
            data.get("actor_id") != actor_id or
            type(data.get("display_name")) is not str or
            not LABEL.fullmatch(data["display_name"]) or
            data.get("synthetic_voice_generated") is not False):
            raise RuntimeError("ActorID is not an independently pinned original actor")
        return record


def resolve_scene_actor_bindings(index: FilmIndex, project_id, paths, rigs,
                                 bindings, *, verify_manifest=False):
    """Exact ActorID ↔ authored UsdSkel-bound mesh; no name-based guessing."""
    if type(bindings) is not list or len(bindings) > MAX_ACTORS:
        raise ValueError("Scene actor cast exceeds bounded native rig capacity")
    rig_by_path = {}
    for rig in rigs:
        if type(rig) is not dict or type(rig.get("path")) is not str:
            raise ValueError("Native skeleton source does not identify an actor path")
        rig_by_path[rig["path"]] = rig
    seen_ids, seen_paths, result = set(), set(), []
    directory = ActorDirectory(index, verify_director_action=lambda *_: False)
    for item in bindings:
        required = ({"actor_id", "actor_revision", "path",
                     "actor_document_sha256", "rig_joints", "skin_mesh_path"}
                    if verify_manifest else {"actor_id", "actor_revision", "path"})
        if type(item) is not dict or set(item) != required:
            raise ValueError("Actor-to-USD scene binding requires exact typed identities")
        aid = _id(item["actor_id"], "scene ActorID")
        path = item["path"]
        rev = item["actor_revision"]
        if (path in seen_paths or aid in seen_ids or paths.get(path) != "actor" or
            type(rev) is not int or rev < 1 or path not in rig_by_path):
            raise ValueError("Scene ActorID must uniquely bind a genuine skinned actor")
        rig = rig_by_path[path]
        joints = rig.get("joints")
        if (type(joints) is not list or not joints or
            ("skin" not in rig and rig.get("skin_weighted") is not True)):
            raise ValueError("ActorID requires an actual bounded UsdSkel skin, not a proxy label")
        record = directory.open(project_id, aid, rev)
        descriptor = {"actor_id": aid, "actor_revision": rev, "path": path,
                      "actor_document_sha256": record["document_sha256"],
                      "rig_joints": list(joints),
                      "skin_mesh_path": path + "/Rig/CharacterMesh"}
        if verify_manifest and descriptor != item:
            raise RuntimeError("Original actor/rig identity changed during native reopen")
        seen_paths.add(path)
        seen_ids.add(aid)
        result.append(descriptor)
    return sorted(result, key=lambda item: item["path"])


class ActorDialogueDirector:
    def __init__(self, index: FilmIndex, *, verify_director_action):
        if not isinstance(index, FilmIndex) or not callable(verify_director_action):
            raise TypeError("Trusted FilmIndex and native dialogue approval required")
        self.index = index
        self.authorize = verify_director_action

    def _original_event(self, project_id, take_id, actor_id, event_id):
        _require_pid(project_id)
        for value in (take_id, actor_id, event_id):
            _id(value, "original source ActorID/dialogue identity")
        take = self.index.read_revision(project_id, take_id, 1)
        doc = take["data"]
        if (take["kind"] != "take" or doc.get("frozen") is not True or
            doc.get("format") != "nvp.digital_take.openusd_temporal.v1"):
            raise RuntimeError("Dialogue must reference an immutable original USD Take")
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        OpenUSDTakeCapture(self.index,
            verify_creator_action=lambda *_: False).verify_take(project_id, take_id)
        from backend.nvp_openusd_scene import OpenUSDSceneBridge
        scene, _ = OpenUSDSceneBridge(self.index).open(
            project_id, doc["scene_id"], doc["scene_revision"])
        if scene["document_sha256"] != doc["scene_document_sha256"]:
            raise RuntimeError("Dialogue source scene SHA was changed")
        matched = [v for v in scene["data"].get("actor_bindings", [])
                   if v["actor_id"] == actor_id]
        if len(matched) != 1:
            raise RuntimeError("Original dialogue ActorID has no unique rigged scene binding")
        binding = matched[0]
        event = TemporalLedger(self.index).events_in(
            project_id, doc["timeline_id"], doc["timeline_revision"],
            start_tick=0, end_tick=int(doc["duration_tick"]),
            limit=500)
        if event.get("next_cursor") is not None:
            raise RuntimeError("Cannot bind dialogue from partial original timeline")
        matches = [e for e in event["events"] if e["event_id"] == event_id]
        if len(matches) != 1 or matches[0]["event_kind"] != "dialogue":
            raise RuntimeError("Original dialogue event does not exist exactly once")
        original = matches[0]
        if (original["subject_id"] != actor_id or
            original["payload"].get("usd_prim_path") != binding["path"] or
            not 0 <= original["start_tick"] < original["end_tick"] <=
                        int(doc["duration_tick"])):
            raise PermissionError("Dialogue subject, emitter or Film Time is not the pinned ActorID")
        audio = RecordedSoundSources(self.index).describe(
            project_id, original["source_id"], original["source_revision"])
        if audio["document_sha256"] != original["source_document_sha256"]:
            raise RuntimeError("Original recorded dialogue source SHA mismatch")
        return take, scene, binding, original, audio

    def bind(self, project_id, dialogue_id, *, actor_id, take_id, event_id,
             creator_event):
        """One actor, one original speaker event; no invented transcript/voice."""
        _id(dialogue_id, "original dialogue attribution ID")
        take, scene, binding, event, audio = self._original_event(
            project_id, take_id, actor_id, event_id)
        data = {"format": DIALOGUE_FORMAT, "actor_id": actor_id,
                "actor_revision": binding["actor_revision"],
                "actor_document_sha256": binding["actor_document_sha256"],
                "actor_usd_prim_path": binding["path"],
                "rig_joints": binding["rig_joints"],
                "skin_mesh_path": binding["skin_mesh_path"],
                "scene_id": scene["object_id"],
                "scene_revision": scene["revision"],
                "scene_document_sha256": scene["document_sha256"],
                "source_take_id": take_id,
                "source_take_sha256": take["document_sha256"],
                "event_id": event_id,
                "timeline_id": take["data"]["timeline_id"],
                "timeline_revision": take["data"]["timeline_revision"],
                "original_recorded_source_id": event["source_id"],
                "original_recorded_source_revision": event["source_revision"],
                "original_pcm_document_sha256": audio["document_sha256"],
                "start_tick": event["start_tick"],
                "end_tick": event["end_tick"],
                "voice_synthesized": False,
                "lip_sync_generated": False,
                "original_take_modified": False}
        scope = {"operation": "nvp.p1bc.bind_original_dialogue.v1",
                 "project_id": project_id, "dialogue_id": dialogue_id,
                 "actor_id": actor_id, "source_take_sha256": take["document_sha256"],
                 "dialogue_intent_sha256": hashlib.sha256(_canonical(data)).hexdigest()}
        if self.authorize(creator_event, dict(scope)) is not True:
            raise PermissionError("Director refused exact original speaker attribution")
        if self._original_event(project_id, take_id, actor_id, event_id)[3] != event:
            raise RuntimeError("Dialogue source changed during creator authorization")
        return self.index.register_revision(
            project_id, dialogue_id, "dialogue", data, expected_revision=0,
            dependencies=[
                {"object_id": actor_id, "revision": binding["actor_revision"], "role": "actor"},
                {"object_id": scene["object_id"], "revision": scene["revision"], "role": "scene"},
                {"object_id": take_id, "revision": 1, "role": "source_take"},
                {"object_id": event["source_id"], "revision": event["source_revision"], "role": "audio"},
                {"object_id": take["data"]["timeline_id"],
                 "revision": take["data"]["timeline_revision"], "role": "temporal"},
            ])

    def at(self, project_id, dialogue_id, revision, tick):
        """Read-only original dialogue at Film Time; no playback synthesis."""
        _int(tick, "actor dialogue Film Time")
        rec = self.index.read_revision(project_id, dialogue_id, revision)
        doc = rec["data"]
        if rec["kind"] != "dialogue" or doc.get("format") != DIALOGUE_FORMAT:
            raise RuntimeError("Not a native original-dialogue actor binding")
        take, scene, binding, event, audio = self._original_event(
            project_id, doc["source_take_id"], doc["actor_id"], doc["event_id"])
        expected = {"actor_document_sha256": binding["actor_document_sha256"],
                    "scene_document_sha256": scene["document_sha256"],
                    "source_take_sha256": take["document_sha256"],
                    "original_pcm_document_sha256": audio["document_sha256"],
                    "original_recorded_source_id": event["source_id"],
                    "actor_usd_prim_path": binding["path"],
                    "start_tick": event["start_tick"],
                    "end_tick": event["end_tick"]}
        if (any(doc.get(k) != v for k, v in expected.items()) or
            doc.get("voice_synthesized") is not False or
            doc.get("lip_sync_generated") is not False):
            raise RuntimeError("Original actor dialogue attribution lost source identity")
        active = doc["start_tick"] <= tick < doc["end_tick"]
        return {"actor_id": doc["actor_id"],
                "usd_prim_path": doc["actor_usd_prim_path"],
                "rig_joints": doc["rig_joints"],
                "source_take_sha256": doc["source_take_sha256"],
                "original_pcm_sha256": doc["original_pcm_document_sha256"],
                "source_event_id": doc["event_id"],
                "time_tick": tick, "dialogue_active": active,
                "native_scene_rig_binding_verified": True,
                "voice_synthesized": False, "lip_sync_generated": False}
