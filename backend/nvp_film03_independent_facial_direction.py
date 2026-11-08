"""FILM03-09: independent speech articulation, face, and body direction.

The director may intentionally pair a sad voice with a happy face, or the
opposite. AI speech alignment proposes mouth timing ONLY; it has no authority
to rewrite facial emotion or body acting. Actor, cast, script, guide audio
and director intention remain preserved as source, not generated film output.

Source-only stage: NO phoneme aligner or animation model is executed, and
NO facial rig has been proven able to realize the requested mouth shapes.
"""
from __future__ import annotations

from backend.nvp_film_index import FilmIndex, _id, _sha, _require_pid
from backend.nvp_film03_voice_performance_lab import frozen_case
from backend.nvp_film03_voice_conversion_intent import verified_guide_signal
from backend.nvp_film03_actor_identity_core import (
    ActorIdentityCore, bounded, digest,
)
from backend.nvp_data_av_source import SAMPLE_RATE

FORMAT = "nvp.film03.independent_face_body_voice_direction.v1"
TICKS_PER_SECOND = 7056000000
assert TICKS_PER_SECOND % SAMPLE_RATE == 0
TICKS_PER_SAMPLE = TICKS_PER_SECOND // SAMPLE_RATE
INT64_MAX = (1 << 63) - 1
ARTICULATION = frozenset({"mouth_visemes", "abstract_reaction", "no_mouth"})
VISEMES = frozenset({
    "rest", "silence", "MBP", "FV", "TH", "DD", "KG", "CH", "SS",
    "NN", "RR", "AA", "E", "IH", "OH", "OU", "WQ", "L",
})
FACES = frozenset({
    "neutral", "happy", "sad", "angry", "calm", "nonchalant", "afraid",
    "surprised", "confused", "wry", "determined", "smiling", "crying",
    "disgusted", "ironic", "custom",
})
BODIES = frozenset({
    "neutral", "still", "relaxed", "tense", "lean_forward", "lean_back",
    "shrug", "fold_arms", "gesture", "turn_away", "custom",
})
INTENT = frozenset({
    "independent", "intentional_contrast", "director_chosen_alignment",
})
CONTRIBUTORS = frozenset({"consenting_voice_actor", "consenting_director_guide"})
MAX_EVENTS = 240


def _exact_sample(value, total, *, allow_endpoint=False):
    if type(value) is not int or not 0 <= value <= total or (
        value == total and not allow_endpoint
    ):
        raise ValueError("Facial direction needs actual original PCM sample positions")
    return value


def _number(value, label):
    if type(value) not in (int, float) or not 0.0 <= value <= 1.0:
        raise ValueError("Invalid " + label + " blending amount")
    return float(value)


def _time_events(items, total, choices, field):
    """Independent expression/body keyframes; NOT inferred from vocal emotion."""
    if type(items) is not list or len(items) > MAX_EVENTS:
        raise ValueError(field + " track must be a bounded list")
    previous = -1
    result = []
    for item in items:
        if type(item) is not dict or set(item) != {
            "sample", "value", "intensity"
        }:
            raise ValueError(field + " event must have exact sample/value/intensity")
        sample = _exact_sample(item["sample"], total)
        if sample <= previous or item["value"] not in choices:
            raise ValueError("Unsorted, duplicated, or unsupported " + field + " keyframe")
        previous = sample
        result.append({
            "sample": sample, "value": item["value"],
            "intensity": _number(item["intensity"], field + " intensity"),
        })
    return result


def _mouth_events(items, total, articulation):
    """Typed proposals, not an assertion of genuine phoneme synchronization."""
    if type(items) is not list or len(items) > MAX_EVENTS:
        raise ValueError("Mouth animation requires bounded reviewed alignment events")
    if articulation == "no_mouth" and items:
        raise ValueError("No-mouth object actors cannot be given invented lips")
    previous_end = 0
    out = []
    for item in items:
        if type(item) is not dict or set(item) != {
            "start_sample", "end_sample", "viseme", "phoneme", "weight"
        }:
            raise ValueError("Exact phoneme/viseme candidate event is required")
        start = _exact_sample(item["start_sample"], total)
        end = _exact_sample(item["end_sample"], total, allow_endpoint=True)
        if start < previous_end or end <= start:
            raise ValueError("Overlapping, reversed or unsorted speech intervals")
        if item["viseme"] not in VISEMES:
            raise ValueError("Unknown rig-independent viseme target")
        phoneme = bounded(item["phoneme"], "phoneme observation", max_length=32)
        previous_end = end
        out.append({
            "start_sample": start, "end_sample": end,
            "viseme": item["viseme"], "phoneme": phoneme,
            "weight": _number(item["weight"], "viseme candidate weight"),
        })
    return out


class FilmIndependentActingDirection:
    """Full authorial control, with speech timing separable from emotion."""

    def __init__(self, index: FilmIndex, *, verify_creator_action):
        if not isinstance(index, FilmIndex) or not callable(verify_creator_action):
            raise TypeError("Native FilmIndex and trusted creator action are required")
        self.index = index
        self._approve = verify_creator_action

    def plan(self, project_id, route, *, profile_revision, direction_id,
             direction_revision, dialogue_audio_id, dialogue_audio_revision,
             contributor_id, contributor_role, contributor_consent_sha256,
             articulation, mouth_events, face_events, body_events,
             emotional_relationship, start_tick):
        _require_pid(project_id)
        case = frozen_case(
            self.index, project_id, route, profile_revision=profile_revision,
            direction_id=direction_id, direction_revision=direction_revision)
        source = ActorIdentityCore(
            self.index, verify_creator_action=lambda *_: False
        ).prepare_generated_voice(project_id, route, profile_revision=profile_revision)
        _id(contributor_id, "performer/contributor identity")
        if contributor_role not in CONTRIBUTORS:
            raise ValueError("A real voice actor or actual director guide must be identified")
        _sha(contributor_consent_sha256)
        _id(dialogue_audio_id, "performed dialogue source")
        if articulation not in ARTICULATION or emotional_relationship not in INTENT:
            raise ValueError("Director must explicitly select articulation and emotion relationship")
        if type(start_tick) is not int or not 0 <= start_tick <= INT64_MAX:
            raise ValueError("Original Film Time must be signed 64-bit positive ticks")
        if start_tick != source["film_time_tick"]:
            raise PermissionError("Articulation cannot move the original dialogue's Film Time")
        pcm = verified_guide_signal(
            self.index, project_id, dialogue_audio_id, dialogue_audio_revision)
        if start_tick + pcm["sample_count"] * TICKS_PER_SAMPLE > INT64_MAX:
            raise ValueError("Spoken performance exceeds the representable Film Time")
        total = pcm["sample_count"]
        mouth = _mouth_events(mouth_events, total, articulation)
        face = _time_events(face_events, total, FACES, "face")
        body = _time_events(body_events, total, BODIES, "body")
        if articulation == "mouth_visemes" and not mouth:
            raise ValueError("Mouth-driven actor requires a nonempty proposed alignment")
        doc = {
            "format": FORMAT, "project_id": project_id,
            "actor_id": case["actor_id"], "voice_id": case["voice_id"],
            "source_take_id": source["source_take_id"],
            "source_take_sha256": case["source_take_sha256"],
            "actor_profile_document_sha256": source["actor_identity_profile_sha256"],
            "voice_reference_sha256": case["voice_reference_sha256"],
            "script_line_id": case["script_line_id"],
            "exact_original_script_text_sha256": case["script_text_sha256"],
            "direction_id": direction_id, "direction_revision": direction_revision,
            "direction_document_sha256": case["direction_document_sha256"],
            "voice_direction_emotion": case["emotion"],
            "voice_direction_delivery": case["delivery"],
            "audio_source": pcm,
            "contributor_id": contributor_id, "contributor_role": contributor_role,
            "contributor_consent_evidence_sha256": contributor_consent_sha256,
            "contributor_permission_independently_verified": False,
            "voice_cloning_permission_not_inferred": True,
            "speech_start_film_tick": start_tick,
            "ticks_per_pcm_sample": TICKS_PER_SAMPLE,
            "articulation_style": articulation, "viseme_candidates": mouth,
            "facial_expression_track": face, "body_performance_track": body,
            "emotional_relationship": emotional_relationship,
            "voice_expression_can_be_deliberately_inconsistent": True,
            "ai_cannot_override_director_face_or_body": True,
            "actual_phoneme_alignment_independently_verified": False,
            "audio_transcript_matches_script_verified": False,
            "face_rig_compatibility_verified": False,
            "real_facial_animation_generated": False,
            "film_take_approved": False,
        }
        return {**doc, "direction_plan_sha256": digest(doc)}

    def publish(self, project_id, route, *, performance_id, expected_revision,
                director_note, creator_event, **kwargs):
        _id(performance_id, "facial performance direction ID")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected immutable direction revision required")
        note = bounded(director_note, "director facial acting intention", max_length=1600)
        plan = self.plan(project_id, route, **kwargs)
        if performance_id in {
            plan["audio_source"]["source_id"], plan["direction_id"],
            plan["source_take_id"],
        }:
            raise ValueError("Facial direction cannot replace original source identity")
        scope = {
            "operation": "film03_publish_independent_acted_face_voice_body",
            "project_id": project_id, "actor_id": plan["actor_id"],
            "voice_id": plan["voice_id"],
            "performance_id": performance_id,
            "expected_revision": expected_revision,
            "direction_plan_sha256": plan["direction_plan_sha256"],
            "director_note": note,
        }
        if not self._approve(creator_event, scope):
            raise PermissionError("Creator must authorize exact facial acting direction")
        if self.plan(project_id, route, **kwargs) != plan:
            raise PermissionError("Recorded audio, ActorID or acting direction changed before publish")
        def guard(db):
            current = db.execute(
                """SELECT document_sha256,voice_id,voice_reference_sha256
                   FROM nvp_bible_actor_identity_profiles
                   WHERE project_id=? AND actor_id=?
                   ORDER BY profile_revision DESC LIMIT 1""",
                (project_id, plan["actor_id"])).fetchone()
            if not current or (
                current["voice_id"] != plan["voice_id"]
                or current["voice_reference_sha256"] != plan["voice_reference_sha256"]
                or current["document_sha256"] != plan["actor_profile_document_sha256"]
            ):
                raise PermissionError("Character profile or VoiceID changed before facial performance publication")
        # The same source and cast are re-opened before submission; a worker
        # may only animate them in a subsequent separately authorized stage.
        saved = self.index.register_revision(
            project_id, performance_id, "performance",
            {**plan, "director_note": note, "articulation_worker_authorized": False},
            expected_revision=expected_revision,
            dependencies=[
                {"object_id": plan["audio_source"]["source_id"],
                 "revision": plan["audio_source"]["revision"], "role": "audio"},
                {"object_id": plan["direction_id"],
                 "revision": plan["direction_revision"], "role": "performance"},
                {"object_id": plan["source_take_id"], "revision": 1, "role": "source_take"},
            ],
            precommit_guard=guard,
        )
        return {
            "format": FORMAT, "actor_id": plan["actor_id"], "voice_id": plan["voice_id"],
            "performance_id": performance_id, "revision": saved["revision"],
            "document_sha256": saved["document_sha256"],
            "director_face_independent_of_voice": True,
            "real_lip_sync_validated": False,
            "facial_animation_executed": False,
            "film_take_approved": False,
        }
