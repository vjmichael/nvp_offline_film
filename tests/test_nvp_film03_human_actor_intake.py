"""FILM03-09B: real first-party PCM audition custody and independent human rights.

Fixture waveforms are physical PCM samples, not actual speech or evidence of
performance quality. No microphone device, generator, voice cloning or final
Take acceptance is inferred from successful sample readback.
"""
from __future__ import annotations

from hashlib import sha256
from math import sin, pi
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film_index import FilmIndex
from backend.nvp_film03_human_actor_intake import (
    FORMAT, RIGHTS, checked_rights, original_signal_measurement,
    VoiceActorPerformanceIntake,
)
from backend.nvp_studio import Studio
from test_nvp_film03_actor_native_workers import prepared_source


def fake_real_pcm(peak=8500, length=24000):
    # Deterministic non-speech oscillation, not a human voice actor recording.
    out = bytearray()
    for i in range(length):
        number = round(peak * sin(2 * pi * 220 * i / 48000))
        out.extend(int(number).to_bytes(2, "little", signed=True))
    return bytes(out)


def permitted(use_conversion=False, train=False):
    evidence = sha256(b"test-only-unsigned-not-legal-rights-document").hexdigest()
    allow = {
        "recorded_line_use": True, "voice_conversion": use_conversion,
        "voice_cloning": False, "model_training": train,
        "distribution": False,
    }
    return {
        name: {
            "consented": allow[name],
            "evidence_sha256": evidence if allow[name] else None,
        }
        for name in RIGHTS
    }


def setup(root):
    s = prepared_source(root)
    signal = RecordedSoundSources(s["index"]).publish(
        s["pid"], "OriginalHumanVoiceSessionPCM", [fake_real_pcm()])
    return s, signal


def native_performer(event, scope):
    return (event == "HUMAN_ATTEST" and
            scope["operation"] == "film03_attest_original_human_voice_performance"
            and scope["contributor_id"] == "Performer_A")


def native_director(event, scope):
    return (event == "DIRECTOR_APPROVE" and
            scope["operation"] == "film03_admit_human_actor_voice_performance")


def kwargs():
    return {
        "session_id": "HumanDonutVoiceSessionA",
        "profile_revision": 1, "audio_id": "OriginalHumanVoiceSessionPCM",
        "audio_revision": 1, "performer_id": "Performer_A",
        "performer_role": "voice_actor",
        "credit_line": "The contributing human voice artist",
        "rights": permitted(use_conversion=True),
        "performer_consent_event": "HUMAN_ATTEST",
        "director_event": "DIRECTOR_APPROVE",
        "director_note": "Actor performance offered for audition only, not a selected take",
    }


class HumanVoiceActorAdmission(unittest.TestCase):
    def test_two_independent_approvals_original_pcm_and_durable_restart(self):
        with TemporaryDirectory() as temp:
            s, original = setup(Path(temp))
            host = VoiceActorPerformanceIntake(
                s["index"], verify_performer_consent=native_performer,
                verify_creator_action=native_director)
            published = host.publish(s["pid"], s["request"], **kwargs())
            self.assertEqual(published["format"], FORMAT)
            self.assertEqual(published["actor_id"], s["people"]["DONUT"])
            self.assertEqual(published["voice_id"], "Voice_Donut_ActorIdentity")
            self.assertEqual(published["contributor_id"], "Performer_A")
            self.assertFalse(published["film_take_approved"])
            self.assertFalse(published["generated_voice_or_model_executed"])
            self.assertTrue(published["separate_performer_and_director_attestations"])
            doc = s["index"].read_revision(s["pid"], published["session_id"], 1)
            self.assertEqual(doc["kind"], "performance")
            self.assertEqual(doc["data"]["recorded_original_signal"]["source_document_sha256"],
                             original["document_sha256"])
            self.assertTrue(doc["data"]["consent_scopes"]["voice_conversion"]["consented"])
            self.assertFalse(doc["data"]["consent_scopes"]["voice_cloning"]["consented"])
            self.assertFalse(doc["data"]["consent_scopes"]["model_training"]["consented"])
            self.assertFalse(doc["data"]["voice_conversion_worker_authorized"])
            self.assertFalse(doc["data"]["model_training_authorized"])
            self.assertFalse(doc["data"]["director_voice_timbre_reviewed"])
            self.assertEqual(
                {(x["object_id"], x["role"]) for x in doc["dependencies"]},
                {
                    ("OriginalHumanVoiceSessionPCM", "audio"),
                    (s["request"]["selected_performance_id"], "performance"),
                    (s["request"]["selection_id"], "presentation"),
                    ("RelayRekindleTake", "source_take"),
                })
            # Full restart of native SQLite/FilmIndex and independent source readback.
            new_index = FilmIndex(
                Studio(s["index"].studio.db_path), s["index"].blob_root)
            recovered = VoiceActorPerformanceIntake(
                new_index, verify_performer_consent=native_performer,
                verify_creator_action=native_director).reopen(
                    s["pid"], "HumanDonutVoiceSessionA")
            self.assertTrue(recovered["reopened_and_source_verified"])
            self.assertEqual(recovered["document_sha256"], published["session_document_sha256"])
            self.assertEqual(recovered["contributor_id"], "Performer_A")
            self.assertTrue(recovered["filmmaking_performance_not_yet_approved"])
            self.assertEqual(s["index"].read_revision(
                s["pid"], "RelayRekindleTake", 1)["document_sha256"],
                s["original_take"]["document_sha256"])

    def test_real_permission_flags_are_independent_and_recorded_use_required(self):
        accepted = checked_rights(permitted(use_conversion=True))
        self.assertTrue(accepted["recorded_line_use"]["consented"])
        self.assertTrue(accepted["voice_conversion"]["consented"])
        self.assertFalse(accepted["voice_cloning"]["consented"])
        self.assertFalse(accepted["model_training"]["consented"])
        for damaged in (
            {**permitted(), "recorded_line_use": {
                "consented": False, "evidence_sha256": None}},
            {**permitted(), "voice_cloning": {
                "consented": True, "evidence_sha256": None}},
            {**permitted(), "model_training": {
                "consented": False, "evidence_sha256": "a"*64}},
            {**permitted(), "distribution": {
                "consented": "yes", "evidence_sha256": "b"*64}},
        ):
            with self.assertRaises((ValueError, PermissionError)):
                checked_rights(damaged)

    def test_no_assumed_script_verification_or_legal_clearance(self):
        with TemporaryDirectory() as temp:
            s, _ = setup(Path(temp))
            host = VoiceActorPerformanceIntake(
                s["index"], verify_performer_consent=native_performer,
                verify_creator_action=native_director)
            proposed = host.plan(
                s["pid"], s["request"], **{
                    k: v for k, v in kwargs().items()
                    if k in {"profile_revision", "audio_id", "audio_revision",
                             "performer_id", "performer_role", "credit_line",
                             "rights"}
                })
            self.assertFalse(proposed["recorded_original_signal"]["speech_transcript_verified"])
            self.assertFalse(proposed["legal_reuse_clearance_completed"])
            self.assertFalse(proposed["actor_voice_similarity_verified"]
                             if "actor_voice_similarity_verified" in proposed else
                             proposed["recorded_original_signal"]["actor_voice_similarity_verified"])
            self.assertGreater(proposed["recorded_original_signal"]["nonquiet_sample_fraction"], 0)
            self.assertTrue(proposed["recorded_original_signal"]["human_listening_pending"])

    def test_missing_either_human_or_director_consent_leaves_no_session(self):
        with TemporaryDirectory() as temp:
            s, _ = setup(Path(temp))
            host = VoiceActorPerformanceIntake(
                s["index"], verify_performer_consent=native_performer,
                verify_creator_action=native_director)
            for field, wrong in (
                ("performer_consent_event", "MODEL_FORGED_HUMAN_CONSENT"),
                ("director_event", "VOICE_ACTOR_IS_NOT_THE_DIRECTOR"),
            ):
                opts = kwargs()
                opts[field] = wrong
                with self.assertRaises(PermissionError):
                    host.publish(s["pid"], s["request"], **opts)
                with self.assertRaises(KeyError):
                    s["index"].read_revision(s["pid"], opts["session_id"], 1)

    def test_wrong_actor_retake_audio_silence_clipping_and_reuse_fail(self):
        with TemporaryDirectory() as temp:
            s, _ = setup(Path(temp))
            host = VoiceActorPerformanceIntake(
                s["index"], verify_performer_consent=native_performer,
                verify_creator_action=native_director)
            bad_route = dict(s["request"], actor_id=s["people"]["BOX"])
            with self.assertRaises((ValueError, PermissionError, KeyError)):
                host.publish(s["pid"], bad_route, **kwargs())
            bad = kwargs()
            bad["audio_id"] = "MissingSource"
            with self.assertRaises((ValueError, PermissionError, KeyError)):
                host.publish(s["pid"], s["request"], **bad)
            RecordedSoundSources(s["index"]).publish(
                s["pid"], "SilentActorSample", [bytes(48000)])
            with self.assertRaises(ValueError):
                original_signal_measurement(
                    s["index"], s["pid"], "SilentActorSample", 1)
            RecordedSoundSources(s["index"]).publish(
                s["pid"], "DistortedActorSample",
                [int(32767).to_bytes(2, "little", signed=True) * 24000])
            with self.assertRaises(ValueError):
                original_signal_measurement(
                    s["index"], s["pid"], "DistortedActorSample", 1)
            first = host.publish(s["pid"], s["request"], **kwargs())
            with self.assertRaises((RuntimeError, ValueError)):
                host.publish(s["pid"], s["request"], **kwargs())
            # A second source ID containing IDENTICAL samples must not be
            # silently assigned as an independent artist's original recording.
            RecordedSoundSources(s["index"]).publish(
                s["pid"], "AliasedAudioDifferentSource", [fake_real_pcm()])
            second = dict(kwargs(), session_id="DifferentPerformerClaim",
                          audio_id="AliasedAudioDifferentSource")
            with self.assertRaises((ValueError, RuntimeError)):
                host.publish(s["pid"], s["request"], **second)
            with self.assertRaises(KeyError):
                s["index"].read_revision(s["pid"], "DifferentPerformerClaim", 1)
            self.assertTrue(first["recording_source_preserved"])


if __name__ == "__main__":
    unittest.main()
