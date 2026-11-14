"""Original ActorID face/PCM dialogue evidence, bound to the frozen Take clock.

No generated phonemes, lip-sync claim, extra TTS, soundtrack replacement,
source edits, or sandbox/renderer authorization. This pairs actual timed
UsdSkel facial weights with independently re-read original PCM16LE.
"""
from __future__ import annotations

from hashlib import sha256
import math
import struct

from backend.nvp_data_av_source import RecordedSoundSources, SAMPLE_RATE
from backend.nvp_p1de_edit_audio import _sound_events
from backend.nvp_p1f_production_character_assets import P1FReviewedProductionCharacters
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

SAMPLE_TICK = TICKS_PER_SECOND // SAMPLE_RATE
MAX_WINDOW = 4096


def original_actor_dialogue_frame(index, pid, cast_id, plan_id,
                                  reel_index, frame_offset, *, window_samples=2000):
    """Read verified original actor scene/Take, facial pose and bounded source PCM.

    All data are genuine from original source. Timing association is not a
    claim that the physical actor's lips match speech (requires a multi-frame,
    professionally rigged Blender measurement and creator acceptance).
    """
    if type(window_samples) is not int or not 1 <= window_samples <= MAX_WINDOW:
        raise ValueError("Bounded native dialogue source sample window required")
    registry = P1FReviewedProductionCharacters(index)
    face = registry.for_frame(pid, cast_id, plan_id, reel_index, frame_offset)
    cast = registry.open_cast(pid, cast_id)["data"]
    # for_frame already checks exact original source scene, Take, ActorID,
    # GLB bytes and source Film Time against the frozen cast.
    from backend.nvp_p1f_cycles_source_admission import admit_original_frame
    original = admit_original_frame(index, pid, plan_id, reel_index, frame_offset)
    take = index.read_revision(pid, original["take_id"], 1)
    tick = face["source_tick"]
    if type(tick) is not int or tick != original["source_tick"]:
        raise RuntimeError("Original facial and sound clocks diverged")
    events = _sound_events(index, pid, take)
    active = [e for e in events if e["event_kind"] == "dialogue"
              and e["start_tick"] <= tick < e["end_tick"]
              and e["subject_id"] == face["actor_id"]]
    if len(active) > 1:
        raise RuntimeError("Overlapping original actor speech needs explicit review")
    if not active:
        return {
            "format": "nvp.p1f.original_actor_face_dialogue.v1",
            "status": "ORIGINAL_ACTOR_NO_ACTIVE_DIALOGUE",
            "actor_id": face["actor_id"], "cast_id": cast_id,
            "cast_document_sha256": face["cast_document_sha256"],
            "take_document_sha256": face["source_take_sha256"],
            "source_tick": tick, "facial_weights": face["facial_weights"],
            "dialogue_event_id": None, "voice_pcm_sha256": None,
            "speech_motion_correlation_verified": False,
            "genuine_cycles_output": False,
        }
    event = active[0]
    if (event["payload"].get("usd_prim_path") != cast["actor_path"] or
            event["source_id"] is None or
            type(event["source_revision"]) is not int):
        raise RuntimeError("Original dialogue emitter/ActorID source does not match cast")
    offset = tick - event["start_tick"]
    if offset < 0 or offset % SAMPLE_TICK:
        raise RuntimeError("Original dialogue sample clock cannot be exactly represented")
    source = RecordedSoundSources(index)
    record = source.describe(pid, event["source_id"], event["source_revision"])
    if record["document_sha256"] != event["source_document_sha256"]:
        raise RuntimeError("Original dialogue PCM revision/hash changed")
    first = offset // SAMPLE_TICK
    available = record["data"]["sample_count"]-first
    event_remaining = (event["end_tick"]-tick) // SAMPLE_TICK
    count = min(window_samples, available, event_remaining)
    if count <= 0:
        raise RuntimeError("Original actor speech event exceeds recorded PCM")
    pcm = source.read(pid, event["source_id"], event["source_revision"], first, count)
    actual = struct.unpack("<" + str(count) + "h", pcm)
    rms = math.sqrt(sum(float(s)*s for s in actual)/count)/32768.
    peak = max(abs(int(s)) for s in actual)/32768.
    return {
        "format": "nvp.p1f.original_actor_face_dialogue.v1",
        "status": "ORIGINAL_ACTOR_FACE_PCM_PAIR_NOT_LIPSYNC_VERIFIED",
        "actor_id": face["actor_id"], "cast_id": cast_id,
        "cast_document_sha256": face["cast_document_sha256"],
        "take_document_sha256": face["source_take_sha256"],
        "source_tick": tick, "facial_weights": face["facial_weights"],
        "dialogue_event_id": event["event_id"],
        "original_source_id": event["source_id"],
        "original_source_document_sha256": record["document_sha256"],
        "voice_pcm_sha256": sha256(pcm).hexdigest(),
        "first_original_sample": first, "sample_count": count,
        "mono_pcm_rms": round(rms, 9), "mono_pcm_peak": round(peak, 9),
        "speech_motion_correlation_verified": False,
        "rendered_face_deformation_verified": False,
        "genuine_cycles_output": False,
        "new_voice_synthesized": False,
    }
