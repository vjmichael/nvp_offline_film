"""FILM03-09: default vocal-emotion matching with preserved director override.

Native PCM fixture intentionally contains silence; it validates source and
articulation timeline custody, NOT phoneme recognition, acting or animation.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film03_expressive_voice_direction import FilmActorVoiceDirection
from backend.nvp_film03_independent_facial_direction import (
    FilmIndependentActingDirection, TICKS_PER_SAMPLE, FORMAT,
)
from test_nvp_film03_actor_native_workers import prepared_source
from test_nvp_film03_expressive_voice_direction import direction



def prepared(root):
    state = prepared_source(root)
    speech = direction()
    speech["emotion"] = "sad"
    speech["delivery"] = "soft"
    approved = FilmActorVoiceDirection(
        state["index"], verify_creator_action=lambda event, _: event == "DIRECTOR"
    ).publish(
        state["pid"], state["request"], profile_revision=1,
        directions=speech, expected_revision=0,
        director_note="Separate sad spoken delivery; happy facial expression allowed",
        creator_event="DIRECTOR")
    recorded = RecordedSoundSources(state["index"]).publish(
        state["pid"], "OriginalActorGuideForFace", [b"\0" * 48000])
    tick = state["core"].prepare_generated_voice(
        state["pid"], state["request"], profile_revision=1)["film_time_tick"]
    opts = dict(
        profile_revision=1, direction_id=approved["direction_id"],
        direction_revision=1,
        dialogue_audio_id="OriginalActorGuideForFace", dialogue_audio_revision=1,
        contributor_id="VoiceActor_A", contributor_role="voice_actor",
        articulation="mouth_visemes",
        mouth_events=[
            {"start_sample": 0, "end_sample": 5500,
             "viseme": "MBP", "phoneme": "m", "weight": 0.8},
            {"start_sample": 5500, "end_sample": 19000,
             "viseme": "AA", "phoneme": "a", "weight": 0.9},
        ],
        face_events=[
            {"sample": 0, "value": "happy", "intensity": 1.0},
            {"sample": 14000, "value": "smiling", "intensity": 0.7},
        ],
        body_events=[
            {"sample": 0, "value": "relaxed", "intensity": 0.8},
            {"sample": 12000, "value": "shrug", "intensity": 0.5},
        ],
        emotional_relationship="intentional_contrast",
        start_tick=tick,
    )
    return state, recorded, opts


class FaceBodyVoiceSourceContracts(unittest.TestCase):
    def test_default_face_proposes_approved_vocal_emotion_not_acoustic_fact(self):
        with TemporaryDirectory() as temp:
            state, _, args = prepared(Path(temp))
            args.pop("emotional_relationship")
            args.pop("face_events")  # Omitted, not merely an explicit empty list
            host = FilmIndependentActingDirection(
                state["index"], verify_creator_action=lambda *_: True)
            plan = host.plan(state["pid"], state["request"], **args)
            self.assertEqual(plan["emotional_relationship"], "match_voice_default")
            self.assertEqual(plan["voice_direction_emotion"], "sad")
            self.assertEqual(plan["facial_expression_track"], [{
                "sample": 0, "value": "sad", "intensity": 0.65,
            }])
            self.assertEqual(plan["face_track_source"],
                             "approved_voice_direction_provisional")
            self.assertTrue(plan["default_match_from_approved_voice_direction"])
            self.assertFalse(plan["director_explicit_face_override_preserved"])
            self.assertFalse(plan["final_audio_emotion_acoustically_verified"])
            self.assertFalse(plan["default_emotion_arc_word_timing_verified"])
            self.assertFalse(plan["facial_match_to_final_audio_verified"])

    def test_director_face_events_override_default_even_when_mode_omitted(self):
        with TemporaryDirectory() as temp:
            state, _, args = prepared(Path(temp))
            args.pop("emotional_relationship")
            host = FilmIndependentActingDirection(
                state["index"], verify_creator_action=lambda *_: True)
            plan = host.plan(state["pid"], state["request"], **args)
            self.assertEqual(plan["emotional_relationship"], "match_voice_default")
            self.assertEqual(plan["voice_direction_emotion"], "sad")
            self.assertEqual(plan["facial_expression_track"][0]["value"], "happy")
            self.assertEqual(plan["face_track_source"], "director_explicit_keyframes")
            self.assertFalse(plan["default_match_from_approved_voice_direction"])
            self.assertTrue(plan["director_explicit_face_override_preserved"])
            self.assertEqual(plan["body_performance_track"][0]["value"], "relaxed")

    def test_sad_voice_with_happy_face_is_valid_director_decision(self):
        with TemporaryDirectory() as temp:
            state, audio, args = prepared(Path(temp))
            planner = FilmIndependentActingDirection(
                state["index"], verify_creator_action=lambda *_: True)
            plan = planner.plan(state["pid"], state["request"], **args)
            self.assertEqual(plan["format"], FORMAT)
            self.assertEqual(plan["voice_direction_emotion"], "sad")
            self.assertEqual(plan["facial_expression_track"][0]["value"], "happy")
            self.assertEqual(plan["body_performance_track"][1]["value"], "shrug")
            self.assertEqual(plan["emotional_relationship"], "intentional_contrast")
            self.assertTrue(plan["director_explicit_face_override_preserved"])
            self.assertFalse(plan["default_match_from_approved_voice_direction"])
            self.assertEqual(plan["ticks_per_pcm_sample"], 147000)
            self.assertEqual(TICKS_PER_SAMPLE, 147000)
            self.assertEqual(
                plan["audio_source"]["source_document_sha256"],
                audio["document_sha256"])
            self.assertFalse(plan["actual_phoneme_alignment_independently_verified"])
            self.assertFalse(plan["audio_transcript_matches_script_verified"])
            self.assertFalse(plan["face_rig_compatibility_verified"])
            self.assertFalse(plan["real_facial_animation_generated"])
            self.assertTrue(plan["voice_expression_can_be_deliberately_inconsistent"])

    def test_angry_face_with_happy_voice_is_not_auto_corrected(self):
        with TemporaryDirectory() as temp:
            state, _, args = prepared(Path(temp))
            new = dict(args)
            new["face_events"] = [
                {"sample": 0, "value": "angry", "intensity": 1.0}]
            new["emotional_relationship"] = "director_chosen_alignment"
            plan = FilmIndependentActingDirection(
                state["index"], verify_creator_action=lambda *_: True
            ).plan(state["pid"], state["request"], **new)
            self.assertEqual(plan["facial_expression_track"][0]["value"], "angry")
            self.assertEqual(plan["voice_direction_emotion"], "sad")
            self.assertTrue(plan["ai_cannot_override_director_face_or_body"])

    def test_nonhuman_actor_may_use_no_mouth_without_invented_lip_rig(self):
        with TemporaryDirectory() as temp:
            state, _, args = prepared(Path(temp))
            new = dict(args, articulation="no_mouth", mouth_events=[])
            plan = FilmIndependentActingDirection(
                state["index"], verify_creator_action=lambda *_: True
            ).plan(state["pid"], state["request"], **new)
            self.assertEqual(plan["articulation_style"], "no_mouth")
            self.assertEqual(plan["viseme_candidates"], [])
            with self.assertRaises(ValueError):
                FilmIndependentActingDirection(
                    state["index"], verify_creator_action=lambda *_: True
                ).plan(state["pid"], state["request"],
                       **dict(new, mouth_events=args["mouth_events"]))

    def test_wrong_source_alignment_time_role_and_recast_are_rejected(self):
        with TemporaryDirectory() as temp:
            state, _, args = prepared(Path(temp))
            host = FilmIndependentActingDirection(
                state["index"], verify_creator_action=lambda *_: True)
            bad = [
                dict(args, start_tick=args["start_tick"] + TICKS_PER_SAMPLE),
                dict(args, dialogue_audio_revision=6),
                dict(args, articulation="mouth_visemes", mouth_events=[]),
                dict(args, mouth_events=[{
                    "start_sample": 22000, "end_sample": 40000,
                    "viseme": "AA", "phoneme": "a", "weight": 1.0}]),
                dict(args, mouth_events=[
                    args["mouth_events"][0],
                    {"start_sample": 1000, "end_sample": 3000,
                     "viseme": "AA", "phoneme": "a", "weight": 1.0}]),
                dict(args, face_events=[
                    {"sample": 0, "value": "automatically_match_voice",
                     "intensity": 1.0}]),
            ]
            for case in bad:
                with self.subTest(case=case), self.assertRaises(
                        (ValueError, KeyError, RuntimeError, PermissionError)):
                    host.plan(state["pid"], state["request"], **case)
            with self.assertRaises((KeyError, ValueError, PermissionError)):
                host.plan(state["pid"],
                          dict(state["request"], actor_id=state["people"]["BOX"]),
                          **args)

    def test_creator_publishes_source_revisions_not_a_finished_facial_take(self):
        with TemporaryDirectory() as temp:
            state, audio, args = prepared(Path(temp))
            host = FilmIndependentActingDirection(
                state["index"], verify_creator_action=lambda ev, sc:
                ev == "DIRECTOR" and
                sc["operation"] == "film03_publish_independent_acted_face_voice_body")
            publish = dict(args, performance_id="DonutContrastingFacialPerformance",
                           expected_revision=0,
                           director_note="The director wants a delighted smile during a sad line")
            with self.assertRaises(PermissionError):
                host.publish(state["pid"], state["request"],
                             **publish, creator_event="UNTRUSTED_AI")
            receipt = host.publish(state["pid"], state["request"],
                                   **publish, creator_event="DIRECTOR")
            self.assertEqual(receipt["revision"], 1)
            self.assertFalse(receipt["real_lip_sync_validated"])
            self.assertFalse(receipt["facial_animation_executed"])
            doc = state["index"].read_revision(
                state["pid"], receipt["performance_id"], 1)
            self.assertFalse(doc["data"]["articulation_worker_authorized"])
            self.assertEqual(doc["data"]["voice_direction_emotion"], "sad")
            self.assertEqual(
                {(x["object_id"], x["role"]) for x in doc["dependencies"]},
                {
                    (audio["object_id"], "audio"),
                    (args["direction_id"], "performance"),
                    ("RelayRekindleTake", "source_take"),
                })
            with self.assertRaises(RuntimeError):
                host.publish(state["pid"], state["request"],
                             **publish, creator_event="DIRECTOR")
            new = dict(publish, expected_revision=1,
                       face_events=[{
                           "sample": 0, "value": "angry", "intensity": 0.6}])
            rev2 = host.publish(state["pid"], state["request"],
                                **new, creator_event="DIRECTOR")
            self.assertEqual(rev2["revision"], 2)
            first = state["index"].read_revision(
                state["pid"], receipt["performance_id"], 1)
            self.assertEqual(first["document_sha256"], receipt["document_sha256"])
            self.assertEqual(first["data"]["facial_expression_track"][0]["value"],
                             "happy")
            self.assertEqual(state["index"].read_revision(
                state["pid"], "RelayRekindleTake", 1)["document_sha256"],
                state["original_take"]["document_sha256"])


if __name__ == "__main__":
    unittest.main()
