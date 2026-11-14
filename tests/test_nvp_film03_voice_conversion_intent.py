"""FILM03-08 speech-to-speech source custody tests.

A zero-valued PCM fixture exercises actual chunk hashing and source revision
without ever pretending the silence contains a performed screenplay line.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film03_voice_conversion_intent import (
    FORMAT, FilmGuideVoiceConversion, verified_guide_signal,
)
from backend.nvp_film03_expressive_voice_direction import FilmActorVoiceDirection
from test_nvp_film03_actor_native_workers import prepared_source
from test_nvp_film03_expressive_voice_direction import direction


def prepared_guide(root):
    source = prepared_source(root)
    pid = source["pid"]
    editor = FilmActorVoiceDirection(
        source["index"],
        verify_creator_action=lambda event, _: event == "DIRECTOR")
    performance = editor.publish(
        pid, source["request"], profile_revision=1,
        directions=direction(), expected_revision=0,
        director_note="Director approved a separate original spoken performance direction",
        creator_event="DIRECTOR")
    # RecordedSoundSources is immutable, native 48k PCM. These bytes are a
    # SILENCE TEST FIXTURE, NOT an acting sample or successful voice conversion.
    guide = RecordedSoundSources(source["index"]).publish(
        pid, "GuideDonutPerformanceSource", [b"\0" * 48000])
    return source, performance, guide


def plan_args(performance):
    return dict(
        profile_revision=1,
        direction_id=performance["direction_id"],
        direction_revision=1,
        guide_audio_id="GuideDonutPerformanceSource",
        guide_audio_revision=1,
        mode="tone_color_transfer",
        guide_origin="human_acted_guide",
    )


def authorize(event, scope):
    return event == "DIRECTOR" and scope["operation"] == \
        "film03_publish_source_locked_guide_conversion_intent"


class FilmGuideConversionContracts(unittest.TestCase):
    def test_guide_and_actor_voice_reference_are_not_interchangeable(self):
        with TemporaryDirectory() as temp:
            source, performance, guide = prepared_guide(Path(temp))
            pid = source["pid"]
            host = FilmGuideVoiceConversion(
                source["index"], verify_creator_action=authorize)
            plan = host.plan(pid, source["request"], **plan_args(performance))
            self.assertEqual(plan["actor_id"], source["people"]["DONUT"])
            self.assertEqual(plan["voice_id"], "Voice_Donut_ActorIdentity")
            self.assertEqual(
                plan["approved_target_voice_reference_sha256"],
                source["core"].prepare_generated_voice(
                    pid, source["request"], profile_revision=1)[
                        "voice_reference_sha256"])
            self.assertEqual(
                plan["guide_source"]["source_document_sha256"],
                guide["document_sha256"])
            self.assertEqual(
                plan["guide_source"]["pcm16le_sha256"],
                sha256(b"\0" * 48000).hexdigest())
            self.assertEqual(plan["performance_mode"], "tone_color_transfer")
            self.assertEqual(plan["guide_source"]["sample_count"], 24000)
            self.assertTrue(plan["source_script_unchanged"])
            self.assertFalse(plan["guide_script_and_emotion_independently_verified"])
            self.assertFalse(plan["converted_pcm_generated"])
            self.assertTrue(plan["unreviewed_model_must_not_run"])
            self.assertFalse(plan["creator_film_approval"])

    def test_wrong_actor_wrong_direction_and_wrong_audio_refused(self):
        with TemporaryDirectory() as temp:
            source, performance, _ = prepared_guide(Path(temp))
            host = FilmGuideVoiceConversion(
                source["index"], verify_creator_action=authorize)
            for wrong in (
                dict(plan_args(performance), guide_audio_id="WrongGuide"),
                dict(plan_args(performance), direction_id="WrongDirection"),
                dict(plan_args(performance), guide_audio_revision=99),
                dict(plan_args(performance), mode="voice_impersonation"),
                dict(plan_args(performance), guide_origin="unauthenticated_mic"),
                dict(plan_args(performance), guide_origin="tts_acted_guide"),
            ):
                with self.subTest(wrong=wrong), self.assertRaises(
                    (ValueError, PermissionError, KeyError, RuntimeError)):
                    host.plan(source["pid"], source["request"], **wrong)
            wrong_actor = dict(source["request"], actor_id=source["people"]["BOX"])
            with self.assertRaises((ValueError, PermissionError, KeyError)):
                host.plan(source["pid"], wrong_actor, **plan_args(performance))
            # A different NVP recording cannot be passed as the target
            # voice reference; its only role is an unapproved acting guide.
            self.assertEqual(
                source["index"].read_revision(
                    source["pid"], "RelayRekindleTake", 1)["document_sha256"],
                source["original_take"]["document_sha256"])

    def test_native_director_approval_writes_immutable_plan_without_execution(self):
        with TemporaryDirectory() as temp:
            source, performance, _ = prepared_guide(Path(temp))
            pid = source["pid"]
            host = FilmGuideVoiceConversion(
                source["index"], verify_creator_action=authorize)
            kwargs = dict(
                **plan_args(performance), intent_id="DonutGuideToVoiceCandidate",
                expected_revision=0,
                director_note="Test-only director intent for Donut tone-color performance candidate")
            with self.assertRaises(PermissionError):
                host.publish_intent(pid, source["request"],
                    **kwargs, creator_event="MODEL_OR_UNAPPROVED_CLICK")
            result = host.publish_intent(
                pid, source["request"], **kwargs, creator_event="DIRECTOR")
            self.assertEqual(result["format"], FORMAT)
            self.assertTrue(result["no_conversion_model_executed"])
            self.assertFalse(result["film_take_approval"])
            saved = source["index"].read_revision(
                pid, "DonutGuideToVoiceCandidate", 1)
            self.assertEqual(saved["kind"], "performance")
            self.assertEqual(saved["data"]["voice_id"], "Voice_Donut_ActorIdentity")
            self.assertFalse(saved["data"]["voice_conversion_run_authorized"])
            self.assertEqual(saved["data"]["guide_source"]["duration_ms"], 500)
            self.assertEqual(
                {(v["object_id"], v["role"]) for v in saved["dependencies"]},
                {
                    ("GuideDonutPerformanceSource", "audio"),
                    (performance["direction_id"], "performance"),
                    ("RelayRekindleTake", "source_take"),
                })
            self.assertEqual(source["index"].read_revision(
                pid, "RelayRekindleTake", 1)["document_sha256"],
                source["original_take"]["document_sha256"])
            with self.assertRaises(RuntimeError):
                host.publish_intent(pid, source["request"], **kwargs,
                                    creator_event="DIRECTOR")
            revised = dict(kwargs)
            revised["expected_revision"] = 1
            revised["mode"] = "performance_to_target_voice"
            second = host.publish_intent(
                pid, source["request"], **revised, creator_event="DIRECTOR")
            self.assertEqual(second["intent_revision"], 2)
            self.assertEqual(source["index"].read_revision(
                pid, "DonutGuideToVoiceCandidate", 1)["document_sha256"],
                result["intent_document_sha256"])
            self.assertFalse(source["index"].read_revision(
                pid, "DonutGuideToVoiceCandidate", 2)["data"][
                    "voice_conversion_run_authorized"])

    def test_reject_short_recording_and_avoid_guessing_any_speech_content(self):
        with TemporaryDirectory() as temp:
            source, performance, _ = prepared_guide(Path(temp))
            pid = source["pid"]
            RecordedSoundSources(source["index"]).publish(
                pid, "TooShortGuide", [b"\0" * 800])
            with self.assertRaises(ValueError):
                verified_guide_signal(source["index"], pid, "TooShortGuide", 1)
            evidence = verified_guide_signal(
                source["index"], pid, "GuideDonutPerformanceSource", 1)
            self.assertTrue(evidence["actual_source_integrity_verified"])
            self.assertFalse(
                evidence["original_guide_contains_correct_spoken_words_verified"])
            self.assertFalse(evidence["original_guide_emotion_and_prosody_verified"])


if __name__ == "__main__":
    unittest.main()
