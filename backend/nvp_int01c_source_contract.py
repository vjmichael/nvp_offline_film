"""INT-01C: read-only identity contract between Studio/G06, FilmIndex and film renders.

G06 Studio/LiveFilmStore Takes and canonical DA-03 FilmIndex Takes are two
distinct ORIGINAL source namespaces. Similar scene IDs, matching duration or
model claims do not establish the same frozen source. This module contains no
source exporter, mutating SQL, OS approval or plaintext fallback.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT = "nvp.int01c.g06_frozen_source_binding.v1"
G06_TAKE = "nvp.g06.immutable_openusd_take.v1"
DA_TAKE = "nvp.openusd.take.v1"
RATE = 48_000
SAMPLE_TICKS = TICKS_PER_SECOND // RATE
HEXDIGEST = re.compile(r"[0-9a-f]{64}\Z")
HEXID = re.compile(r"[0-9a-f]{32}\Z")
MAX_TAKE_TICKS = 1800 * TICKS_PER_SECOND


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf8")


def _sha(value):
    return sha256(value).hexdigest()


def _sha_field(value):
    return type(value) is str and HEXDIGEST.fullmatch(value) is not None


def _check_identity(value, what):
    if type(value) is not str or not HEXID.fullmatch(value):
        raise RuntimeError("Original " + what + " identity is invalid")


def g06_binding(project_id, take_id, row, document, audio):
    """Independently check exact source identity and all sound/actor/clock bindings.

    Does not read/decrypt PCM and MUST NOT be used to certify media bytes.
    G06 validates actual SQLite/SealedPCM media separately. The binding is
    derived from verified immutable Take metadata; never from an edit request.
    """
    _check_identity(project_id, "project")
    _check_identity(take_id, "Take")
    if (row["project_id"] != project_id or row["take_id"] != take_id or
            type(row["scene_id"]) is not str or not row["scene_id"] or
            type(document) is not dict or document.get("format") != G06_TAKE or
            document.get("project_id") != project_id or
            document.get("scene_id") != row["scene_id"] or
            document.get("source_stage_revision") != row["source_stage_revision"] or
            document.get("source_is_original_openusd") is not True or
            document.get("immutable") is not True or
            document.get("camera_tracks_frozen") is not False or
            document.get("tick_rate") != TICKS_PER_SECOND or
            document.get("scene_source_sha256") != row["source_sha256"] or
            document.get("original_usd_sha256") != row["original_usd_sha256"] or
            document.get("performance_usd_sha256") != row["performance_usd_sha256"] or
            not _sha_field(row["take_sha256"]) or
            _sha(_canon(document)) != row["take_sha256"]):
        raise RuntimeError("Studio Digital Take source identity diverged")
    duration = document.get("duration_tick")
    if (type(duration) is not int or not 0 < duration <= MAX_TAKE_TICKS or
            type(row["source_stage_revision"]) is not int or
            row["source_stage_revision"] < 1):
        raise RuntimeError("Frozen source is not bounded integer Film Time")
    objects = document.get("stage_objects")
    events = document.get("events")
    setting = document.get("stage_setting")
    if (type(setting) is not dict or
            type(objects) is not list or type(events) is not list or
            len(objects) > 256 or len(events) > 512):
        raise RuntimeError("Original 3D performance source manifest is invalid")
    actors = {}
    stage_ids = set()
    for obj in objects:
        if type(obj) is not dict:
            raise RuntimeError("Original stage object has invalid identity")
        oid = obj.get("id")
        if type(oid) is not str or not oid or oid in stage_ids:
            raise RuntimeError("Duplicate original stage object")
        stage_ids.add(oid)
        actor = obj.get("actor_id")
        role = obj.get("role")
        if role == "actor":
            if (type(actor) is not str or not actor.startswith("ACT_") or
                    actor in actors):
                raise RuntimeError("Original performer ActorID is invalid or reused")
            actors[actor] = oid
        elif actor is not None:
            raise RuntimeError("A non-actor object was given a performer ActorID")
    for event in events:
        if type(event) is not dict:
            raise RuntimeError("Frozen event is not a typed source event")
        start, end = event.get("start_tick"), event.get("end_tick")
        if (type(start) is not int or type(end) is not int or
                not 0 <= start < end <= duration):
            raise RuntimeError("Original source event does not fit Film Time")
        actor = event.get("actor_id")
        oid = event.get("object_id")
        if actor is not None and actors.get(actor) != oid:
            raise RuntimeError("Frozen performer event has an incorrect ActorID")
        if oid is not None and oid not in stage_ids:
            raise RuntimeError("Frozen event references a missing stage object")
    if (type(audio) is not list or audio != document.get("audio") or
            len(audio) > 32):
        raise RuntimeError("Frozen original microphone manifest is incomplete")
    clips = set()
    source_audio = []
    for entry in audio:
        if type(entry) is not dict:
            raise RuntimeError("Original audio identity is malformed")
        cid = entry.get("clip_id")
        if type(cid) is not str or not HEXID.fullmatch(cid) or cid in clips:
            raise RuntimeError("Original microphone source was duplicated")
        clips.add(cid)
        actor = entry.get("actor_id")
        expected_path = "/World"
        if actor is not None:
            if actor not in actors:
                raise RuntimeError("Original sound emitter has a foreign ActorID")
            expected_path = "/World/Objects/" + actors[actor]
        if (entry.get("emitter_path") != expected_path or
                not _sha_field(entry.get("pcm_sha256")) or
                entry.get("sample_rate") != RATE or
                entry.get("channels") != 1):
            raise RuntimeError("Original PCM emitter or source format changed")
        samples = entry.get("sample_count")
        start = entry.get("start_tick")
        length = entry.get("duration_tick")
        if (type(samples) is not int or not 1 <= samples <= RATE * 1800 or
                type(start) is not int or not 0 <= start or
                type(length) is not int or
                length != samples * SAMPLE_TICKS or
                start + length > duration):
            raise RuntimeError("Source PCM samples do not fit exact Film Time")
        position = entry.get("emitter_position")
        if (type(position) is not list or len(position) != 3 or
                any(type(v) not in (int,float) or
                    not -100_000 <= v <= 100_000 for v in position)):
            raise RuntimeError("Original spatial sound emitter has an invalid position")
        source_audio.append({
            "clip_id": cid,
            "actor_id": actor,
            "emitter_position": position,
            "pcm_sha256": entry["pcm_sha256"],
            "sample_count": samples,
            "start_tick": start,
            "duration_tick": length,
            "emitter_path": expected_path,
            "original_recording_id": entry.get("original_recording_id"),
            "recording_sha256": entry.get("recording_sha256"),
            "recording_manifest_sha256": entry.get("recording_manifest_sha256"),
            "recording_source_start_sample":
                entry.get("recording_source_start_sample"),
        })
    binding = {
        "format": FORMAT,
        "namespace": "g06-studio-or-live",
        "project_id": project_id,
        "scene_id": row["scene_id"],
        "take_id": take_id,
        "take_sha256": row["take_sha256"],
        "original_stage_revision": row["source_stage_revision"],
        "scene_source_sha256": row["source_sha256"],
        "original_usd_sha256": row["original_usd_sha256"],
        "performance_usd_sha256": row["performance_usd_sha256"],
        "events_sha256": _sha(_canon(events)),
        "stage_objects_sha256": _sha(_canon(objects)),
        "stage_setting_sha256": _sha(_canon(setting)),
        "duration_tick": duration,
        "tick_rate": TICKS_PER_SECOND,
        "sample_rate": RATE,
        "sample_ticks": SAMPLE_TICKS,
        "audio": source_audio,
    }
    binding["binding_sha256"] = _sha(_canon(binding))
    return binding


def check_render_take(project_id, take_id, take, binding):
    """Reject a relabeled, edited, cross-project or tampered source reel.

    Called by G07/G08/G09 on immutable render-source data. The source
    bytes/PCM readers are verified at their actual host boundary; this
    binding additionally prevents combining another scene's source/ActorID
    with a valid but unrelated edit decision.
    """
    _check_identity(project_id, "project")
    _check_identity(take_id, "Take")
    if (type(binding) is not dict or binding.get("format") != FORMAT or
            binding.get("namespace") != "g06-studio-or-live" or
            binding.get("project_id") != project_id or
            binding.get("take_id") != take_id or
            not _sha_field(binding.get("binding_sha256"))):
        raise RuntimeError("Original renderer Take provenance is missing")
    fields = {key: value for key, value in binding.items()
              if key != "binding_sha256"}
    if _sha(_canon(fields)) != binding["binding_sha256"]:
        raise RuntimeError("Frozen Take binding was modified after readback")
    if (binding.get("tick_rate") != TICKS_PER_SECOND or
            binding.get("sample_rate") != RATE or
            binding.get("sample_ticks") != SAMPLE_TICKS):
        raise RuntimeError("Original Film Time or audio sample clock was replaced")
    for key, source_key in (
        ("scene_id", "scene_id"),
        ("take_sha256", "take_sha256"),
        ("original_usd_sha256", "original_sha256"),
        ("performance_usd_sha256", "performance_sha256"),
        ("duration_tick", "duration_tick")
    ):
        if binding[key] != take[source_key]:
            raise RuntimeError("A render Take is not bound to its source")
    if (take.get("project_id") != project_id or
            take.get("take_id") != take_id or
            _sha(_canon(take["events"])) != binding["events_sha256"] or
            _sha(_canon(take["stage_objects"])) != binding["stage_objects_sha256"] or
            _sha(_canon(take["stage_setting"])) != binding["stage_setting_sha256"]):
        raise RuntimeError("The source world, actor roster or event history was changed")
    if (_sha(take["original_usd"]) != binding["original_usd_sha256"] or
            _sha(take["performance_usd"]) != binding["performance_usd_sha256"]):
        raise RuntimeError("The original OpenUSD bytes were modified")
    audio = take["audio"]
    if type(audio) is not list or len(audio) != len(binding["audio"]):
        raise RuntimeError("Original render sound manifest was changed")
    from backend.nvp_g09e_pcm import verified_pcm_digest
    for item, recorded in zip(audio, binding["audio"]):
        if (item.get("clip_id") != recorded["clip_id"] or
                item.get("actor_id") != recorded["actor_id"] or
                item.get("pcm_sha256") != recorded["pcm_sha256"] or
                item.get("sample_count") != recorded["sample_count"] or
                item.get("start_tick") != recorded["start_tick"] or
                item.get("duration_tick") != recorded["duration_tick"] or
                item.get("emitter_path") != recorded["emitter_path"] or
                item.get("emitter_position") != recorded["emitter_position"] or
                any(item.get(key) != recorded[key] for key in (
                    "original_recording_id","recording_sha256",
                    "recording_manifest_sha256",
                    "recording_source_start_sample")) or
                len(item["pcm16le"]) != recorded["sample_count"]*2 or
                verified_pcm_digest(item["pcm16le"]) != recorded["pcm_sha256"]):
            raise RuntimeError("Rendered original PCM or ActorID changed")
    return True


def canonical_film_index_evidence(index, project_id, canonical_take_id):
    """Read canonical DA-03 identity WITHOUT equating it with a G06 Take.

    FilmIndex uses separately versioned scene, timeline and source blobs.
    No direct G03 LiveFilmStore/locked movie may be opened through this
    ordinary-file source index. A host MUST authorize the caller separately.
    """
    from backend.nvp_film_index import FilmIndex
    from backend.nvp_openusd_take import OpenUSDTakeCapture
    if not isinstance(index, FilmIndex):
        raise TypeError("An ordinary trusted FilmIndex is required")
    _check_identity(project_id, "project")
    verified = OpenUSDTakeCapture(index, verify_creator_action=lambda *_: False
                                 ).verify_take(project_id, canonical_take_id)
    source = index.read_revision(project_id, canonical_take_id, 1)
    data = source["data"]
    if (verified["status"] != "VERIFIED_FROZEN_DATA_TAKE" or
            data.get("host_creator_action_verified") is not True or
            data.get("frozen") is not True):
        raise RuntimeError("Canonical FilmIndex Take was not frozen")
    return {"namespace": "da-filmindex",
            "project_id": project_id, "take_id": canonical_take_id,
            "scene_id": data["scene_id"],
            "scene_revision": data["scene_revision"],
            "scene_document_sha256": data["scene_document_sha256"],
            "timeline_document_sha256": data["timeline_document_sha256"],
            "duration_tick": data["duration_tick"],
            "take_document_sha256": source["document_sha256"],
            "independently_verified": True,
            "equivalent_to_g06_take": False}


def verify_render_assembly(assembly, *, require_bindings=False):
    """Check all G06 source identities for G08/G09 native source readers.

    Historic synthetic test fixtures lack a source-provenance map and may
    remain usable in isolated codec tests; a trusted host-delivery path
    SHOULD call with require_bindings=True, never accept missing bindings
    from an actual G07 source window.
    """
    if type(assembly) is not dict:
        raise RuntimeError("Film render assembly is malformed")
    manifest = assembly.get("source_provenance")
    if manifest is None:
        if require_bindings:
            raise RuntimeError("An actual film reel requires G06 source provenance")
        return False
    pid = assembly.get("project_id")
    _check_identity(pid, "project")
    if (type(manifest) is not dict or
            manifest.get("format") != "nvp.int01c.source_provenance.v1" or
            manifest.get("project_id") != pid):
        raise RuntimeError("Original film index provenance was replaced")
    hashes = manifest.get("take_binding_hashes")
    if type(hashes) is not dict or not hashes or len(hashes) > 250:
        raise RuntimeError("Missing original source identities")
    for tid, digest in hashes.items():
        _check_identity(tid, "Take")
        if not _sha_field(digest):
            raise RuntimeError("Original Take reference digest is invalid")
    if (_sha(_canon(hashes)) != manifest.get("take_bindings_sha256") or
            manifest.get("all_source_take_count") != len(hashes) or
            assembly.get("all_source_take_count") != len(hashes)):
        raise RuntimeError("Original film source ledger was modified")
    loaded = assembly.get("original_takes")
    if type(loaded) is not dict or not loaded:
        raise RuntimeError("No reviewed original Take was loaded")
    if ("loaded_source_take_count" in assembly and
            assembly["loaded_source_take_count"] != len(loaded)):
        raise RuntimeError("Original source window omitted a reviewed Take")
    segments = assembly.get("segments")
    if segments is not None:
        if type(segments) is not list or len(segments) > 250:
            raise RuntimeError("Original source edit segments are invalid")
        window = assembly.get("window")
        if window is not None and (type(window) is not list or
                len(window) != 2 or
                any(type(t) is not int for t in window) or
                not 0 <= window[0] < window[1]):
            raise RuntimeError("Original render Film Time window is invalid")
        for seg in segments:
            if type(seg) is not dict:
                raise RuntimeError("An edit segment has no original identity")
            if (type(seg.get("start_tick")) is not int or
                    type(seg.get("end_tick")) is not int or
                    not 0 <= seg["start_tick"] < seg["end_tick"]):
                raise RuntimeError("An edit segment has invalid exact Film Time")
            tid = seg.get("take_id")
            if tid not in hashes or seg.get("take_sha256") is None:
                raise RuntimeError("An edit references a foreign original Take")
            overlaps = (window is None or
                        (seg["start_tick"] < window[1] and
                         seg["end_tick"] > window[0]))
            if overlaps:
                original = loaded.get(tid)
                if (original is None or
                        original.get("scene_id") != seg.get("scene_id") or
                        original.get("take_sha256") != seg.get("take_sha256")):
                    raise RuntimeError("An edit window substituted a scene or Take")
                start, end = seg.get("source_in_tick"), seg.get("source_out_tick")
                if (type(start) is not int or type(end) is not int or
                        not 0 <= start < end <= original["duration_tick"]):
                    raise RuntimeError("A render trim escapes its immutable Take")
    for tid, source in loaded.items():
        if tid not in hashes or type(source) is not dict:
            raise RuntimeError("Original render Take was substituted")
        binding = source.get("source_binding")
        if type(binding) is not dict or binding.get("binding_sha256") != hashes[tid]:
            raise RuntimeError("Original source binding was substituted")
        check_render_take(pid, tid, source, binding)
    return True
