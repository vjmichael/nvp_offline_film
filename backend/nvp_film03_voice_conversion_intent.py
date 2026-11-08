"""FILM03-08: source-authoritative speech-to-speech acting direction.

This module DOES NOT perform voice conversion or grant a model permission to
act. A recorded guide performance and a separate ActorID/VoiceID reference
are two different immutable original signals. The guide supplies *intended*
timing/prosody; a future reviewed voice converter may produce an alternate
timbre. Whether the conversion preserves those things is an audio/human test,
not an inference one can make from metadata or the existence of a WAV.
"""
from __future__ import annotations

from hashlib import sha256

from backend.nvp_data_av_source import RecordedSoundSources, SAMPLE_RATE
from backend.nvp_film03_actor_identity_core import (
    ActorIdentityCore, bounded, digest,
)
from backend.nvp_film03_voice_performance_lab import frozen_case
from backend.nvp_film_index import FilmIndex, _id, _sha, _require_pid

FORMAT = "nvp.film03.actorid_guide_voice_conversion_intent.v1"
MODES = frozenset({"tone_color_transfer", "performance_to_target_voice"})
ORIGINS = frozenset({"human_acted_guide", "tts_acted_guide"})
MAX_GUIDE_SECONDS = 180
MIN_GUIDE_SECONDS = 0.20


def verified_guide_signal(index: FilmIndex, project_id, audio_id, revision):
    """Read every actual original PCM chunk, bounded in RAM, fail on tamper."""
    _require_pid(project_id)
    _id(audio_id, "immutable guide source")
    if type(revision) is not int or revision < 1:
        raise ValueError("Positive original guide audio revision required")
    original = RecordedSoundSources(index).describe(project_id, audio_id, revision)
    source = original["data"]
    count = source["sample_count"]
    if type(count) is not int or not (
        MIN_GUIDE_SECONDS * SAMPLE_RATE <= count <= MAX_GUIDE_SECONDS * SAMPLE_RATE
    ):
        raise ValueError("Guide acting duration outside the reviewed audition bounds")
    positions = 0
    hasher = sha256()
    for chunk in source["chunks"]:
        if type(chunk) is not dict or set(chunk) != {
            "first_sample", "sample_count", "blob_sha256", "byte_count"
        }:
            raise RuntimeError("Actual recorded guide has an altered PCM chunk manifest")
        n = chunk["sample_count"]
        if type(n) is not int or n <= 0 or chunk["first_sample"] != positions or \
           chunk["byte_count"] != n * 2:
            raise RuntimeError("Source guide PCM chunks have discontinuous coordinates")
        data = index.get_blob(project_id, chunk["blob_sha256"])
        if len(data) != chunk["byte_count"]:
            raise RuntimeError("Guide signal failed independent sample readback")
        hasher.update(data)
        positions += n
    if positions != count:
        raise RuntimeError("Truncated guide recording or invalid end-of-source")
    return {
        "source_id": audio_id,
        "revision": revision,
        "source_document_sha256": original["document_sha256"],
        "pcm16le_sha256": hasher.hexdigest(),
        "sample_rate": SAMPLE_RATE,
        "sample_count": count,
        "duration_ms": count * 1000 // SAMPLE_RATE,
        "actual_source_integrity_verified": True,
        "original_guide_contains_correct_spoken_words_verified": False,
        "original_guide_emotion_and_prosody_verified": False,
    }


class FilmGuideVoiceConversion:
    """Director-reviewed guide → approved target VoiceID; model still blocked."""

    def __init__(self, index: FilmIndex, *, verify_creator_action):
        if not isinstance(index, FilmIndex) or not callable(verify_creator_action):
            raise TypeError("Native FilmIndex and trusted director approval required")
        self.index = index
        self._approve = verify_creator_action

    def plan(self, project_id, source_route, *, profile_revision,
             direction_id, direction_revision, guide_audio_id,
             guide_audio_revision, mode, guide_origin):
        if mode not in MODES or guide_origin not in ORIGINS:
            raise ValueError("Unknown reviewed voice-conversion performance mode")
        if guide_origin == "tts_acted_guide":
            raise PermissionError(
                "TTS acting guide is derived audio, not an original microphone source; "
                "requires a separately verified source-to-derived provenance adapter")
        case = frozen_case(
            self.index, project_id, source_route,
            profile_revision=profile_revision,
            direction_id=direction_id, direction_revision=direction_revision)
        actor = ActorIdentityCore(self.index, verify_creator_action=lambda *_: False)
        source = actor.prepare_generated_voice(
            project_id, source_route, profile_revision=profile_revision)
        guide = verified_guide_signal(
            self.index, project_id, guide_audio_id, guide_audio_revision)
        packet = {
            "format": FORMAT, "project_id": project_id,
            "actor_id": case["actor_id"], "voice_id": case["voice_id"],
            "approved_target_voice_reference_sha256": case["voice_reference_sha256"],
            "original_script_line_id": case["script_line_id"],
            "exact_original_script_text_sha256": case["script_text_sha256"],
            "source_take_id": source["source_take_id"],
            "source_take_sha256": case["source_take_sha256"],
            "source_generation_contract_sha256": case["source_generation_contract_sha256"],
            "actor_profile_revision": profile_revision,
            "actor_profile_document_sha256": source["actor_identity_profile_sha256"],
            "original_director_direction_id": direction_id,
            "original_director_direction_revision": direction_revision,
            "original_director_direction_document_sha256": case["direction_document_sha256"],
            "original_director_direction_sha256": case["direction_sha256"],
            "director_emotion": case["emotion"], "director_delivery": case["delivery"],
            "performance_mode": mode, "guide_origin": guide_origin,
            "guide_source": guide,
            "guide_script_and_emotion_independently_verified": False,
            "converted_voice_identity_verified": False,
            "conversion_preserves_guide_prosody_verified": False,
            "converted_pcm_generated": False,
            "unreviewed_model_must_not_run": True,
            "creator_film_approval": False,
            "source_script_unchanged": True,
            "original_guide_pcm_preserved": True,
            "original_target_voice_reference_preserved": True,
        }
        return {**packet, "plan_sha256": digest(packet)}

    def publish_intent(self, project_id, source_route, *, profile_revision,
                       direction_id, direction_revision, guide_audio_id,
                       guide_audio_revision, mode, guide_origin,
                       intent_id, expected_revision, director_note,
                       creator_event):
        _id(intent_id, "guide conversion intent ID")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected guide conversion revision must be explicit")
        note = bounded(director_note, "human director guide comparison note", max_length=1400)
        plan_kwargs = {
            "profile_revision": profile_revision,
            "direction_id": direction_id,
            "direction_revision": direction_revision,
            "guide_audio_id": guide_audio_id,
            "guide_audio_revision": guide_audio_revision,
            "mode": mode, "guide_origin": guide_origin,
        }
        packet = self.plan(project_id, source_route, **plan_kwargs)
        if intent_id in (guide_audio_id, direction_id, packet["source_take_id"]):
            raise ValueError("Conversion intent cannot shadow original audio/direction/Take")
        scope = {
            "operation": "film03_publish_source_locked_guide_conversion_intent",
            "project_id": project_id, "actor_id": packet["actor_id"],
            "voice_id": packet["voice_id"],
            "guide_source_document_sha256": packet["guide_source"]["source_document_sha256"],
            "guide_pcm16le_sha256": packet["guide_source"]["pcm16le_sha256"],
            "original_direction_sha256": packet["original_director_direction_sha256"],
            "source_take_sha256": packet["source_take_sha256"],
            "intent_id": intent_id,
            "expected_revision": expected_revision,
            "plan_sha256": packet["plan_sha256"],
            "director_note": note,
        }
        if not self._approve(creator_event, scope):
            raise PermissionError("Director has not approved the exact guide-performance binding")
        if self.plan(project_id, source_route, **plan_kwargs) != packet:
            raise PermissionError("Guide, actor, script, or voice source changed before approval")
        def guard(db):
            latest = db.execute(
                """SELECT document_sha256,voice_id,voice_reference_sha256
                   FROM nvp_bible_actor_identity_profiles
                   WHERE project_id=? AND actor_id=?
                   ORDER BY profile_revision DESC LIMIT 1""",
                (project_id, packet["actor_id"])).fetchone()
            if not latest or (
                latest["document_sha256"] != packet["actor_profile_document_sha256"]
                or latest["voice_id"] != packet["voice_id"]
                or latest["voice_reference_sha256"] !=
                   packet["approved_target_voice_reference_sha256"]
            ):
                raise PermissionError("Character or VoiceID recast before intent publication")
        result = self.index.register_revision(
            project_id, intent_id, "performance",
            {**packet, "director_note": note,
             "voice_conversion_run_authorized": False,
             "voice_conversion_result_approved": False},
            expected_revision=expected_revision,
            dependencies=[
                {"object_id": guide_audio_id, "revision": guide_audio_revision, "role": "audio"},
                {"object_id": direction_id, "revision": direction_revision, "role": "performance"},
                {"object_id": packet["source_take_id"], "revision": 1, "role": "source_take"},
            ],
            precommit_guard=guard,
        )
        return {
            "format": FORMAT, "project_id": project_id,
            "actor_id": packet["actor_id"], "voice_id": packet["voice_id"],
            "intent_id": intent_id, "intent_revision": result["revision"],
            "intent_document_sha256": result["document_sha256"],
            "source_take_sha256": packet["source_take_sha256"],
            "guide_pcm16le_sha256": packet["guide_source"]["pcm16le_sha256"],
            "no_conversion_model_executed": True,
            "film_take_approval": False,
            "previous_film_and_guide_revisions_preserved": True,
        }
