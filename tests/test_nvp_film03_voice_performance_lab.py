"""FILM03-07 real PCM audition contract; fixtures are NON-SPEECH test signals."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from backend.nvp_film03_voice_performance_lab import (
    FORMAT, RUBRIC, compare_auditions, frozen_case, inspect_real_wav,
    record_candidate, record_listening_review,
)
from backend.nvp_film03_expressive_voice_direction import FilmActorVoiceDirection
from test_nvp_film03_expressive_voice_direction import direction
from test_nvp_film03_actor_native_workers import prepared_source


def sound(root, name="candidate.wav", *, amp=8000, seconds=0.4):
    """Only a deterministic non-speech signal for PCM parser regression."""
    path = root / name
    sample_rate = 24000
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        data = bytearray()
        for i in range(int(sample_rate * seconds)):
            n = int(amp * math.sin(2 * math.pi * 220 * i / sample_rate))
            data += n.to_bytes(2, "little", signed=True)
        wav.writeframes(bytes(data))
    return path, sha256(path.read_bytes()).hexdigest()


def producer(case, *, model="ExperimentalModel"):
    pending = sha256(b"test-only receipt not validated").hexdigest()
    return {
        "provider_id": "LabProvider",
        "model_id": model, "model_revision": "v2026_test",
        "model_execution_receipt_sha256": pending,
        "original_reference_sha256": case["voice_reference_sha256"],
    }


class FilmVoiceLabTests(unittest.TestCase):
    def source(self, root):
        s = prepared_source(root)
        director = FilmActorVoiceDirection(
            s["index"], verify_creator_action=lambda event, _: event == "DIRECTOR")
        saved = director.publish(
            s["pid"], s["request"], profile_revision=1,
            directions=direction(), expected_revision=0,
            director_note="Original explicitly approved whisper delivery",
            creator_event="DIRECTOR")
        case = frozen_case(
            s["index"], s["pid"], s["request"], profile_revision=1,
            direction_id=saved["direction_id"],
            direction_revision=saved["direction_revision"])
        return s, saved, case

    def test_frozen_case_preserves_original_actor_voice_script_and_take(self):
        with TemporaryDirectory() as temp:
            s, saved, case = self.source(Path(temp))
            self.assertEqual(case["format"], FORMAT)
            self.assertEqual(case["actor_id"], s["people"]["DONUT"])
            self.assertEqual(case["voice_id"], "Voice_Donut_ActorIdentity")
            self.assertEqual(case["source_take_sha256"],
                             s["original_take"]["document_sha256"])
            self.assertEqual(case["direction_document_sha256"],
                             saved["direction_document_sha256"])
            self.assertEqual(case["delivery"], "whisper")
            self.assertTrue(case["lab_only_not_permission_to_generate_or_approve"])
            self.assertEqual(case["profile_model_id"], "TestModelNotInstalled")
            for wrong in (
                dict(s["request"], actor_id=s["people"]["BOX"]),
                dict(s["request"], exact_text="Changed original spoken words"),
            ):
                with self.assertRaises((ValueError, KeyError, PermissionError)):
                    frozen_case(s["index"], s["pid"], wrong,
                                profile_revision=1,
                                direction_id=saved["direction_id"],
                                direction_revision=1)
            with self.assertRaises((KeyError, ValueError, PermissionError)):
                frozen_case(s["index"], s["pid"], s["request"],
                            profile_revision=1, direction_id="WrongDirection",
                            direction_revision=1)
            self.assertEqual(s["index"].read_revision(
                s["pid"], "RelayRekindleTake", 1)["document_sha256"],
                s["original_take"]["document_sha256"])

    def test_real_pcm_audit_is_not_claimed_as_acting_quality(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            path, sha = sound(root)
            audio = inspect_real_wav(root, path.name)
            self.assertEqual(audio["actual_file_sha256"], sha)
            self.assertEqual(audio["sample_frames"], 9600)
            self.assertEqual(audio["sample_rate"], 24000)
            self.assertGreater(audio["rms_dbfs"], -22.0)
            for key in ("pronunciation_verified", "emotion_verified",
                        "speaker_identity_verified", "whisper_verified"):
                self.assertFalse(audio[key])
            self.assertTrue(audio["real_human_review_required"])

    def test_tampering_wrong_reference_and_untrusted_paths_fail_closed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            s, _, case = self.source(root)
            path, original_sha = sound(root)
            audition = record_candidate(
                case, root, path.name, producer=producer(case),
                declared_wav_sha256=original_sha)
            self.assertFalse(audition["director_take_approved"])
            self.assertFalse(audition["run_receipt_independently_verified"])
            with self.assertRaises(PermissionError):
                record_candidate(case, root, path.name,
                                 producer=producer(case),
                                 declared_wav_sha256="0"*64)
            wrong = producer(case)
            wrong["original_reference_sha256"] = "f"*64
            with self.assertRaises(PermissionError):
                record_candidate(case, root, path.name, producer=wrong,
                                 declared_wav_sha256=original_sha)
            for name in ("../candidate.wav", "C:\\candidate.wav",
                         "candidate.wav/../x.wav"):
                with self.assertRaises((ValueError, PermissionError)):
                    inspect_real_wav(root, name)
            path.write_bytes(path.read_bytes()[:80])
            with self.assertRaises((EOFError, ValueError, wave.Error)):
                inspect_real_wav(root, path.name)
            self.assertIsNone(s["index"].read_revision(
                s["pid"], "DonutAuthoredOriginalLine", 1)["data"][
                "recorded_voice_source"])

    def test_audition_review_is_a_comparison_not_model_permission(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, case = self.source(root)
            path, sha = sound(root)
            audition = record_candidate(
                case, root, path.name,
                producer=producer(case, model="UnapprovedExperimentalModel"),
                declared_wav_sha256=sha)
            self.assertEqual(audition["case"]["profile_model_id"],
                             "TestModelNotInstalled")
            self.assertEqual(audition["review_state"], "UNREVIEWED_EXPERIMENT")
            scores = {criterion: 3 for criterion in RUBRIC}
            note = "The actual reviewer must compare breath, prosody and emotional meaning."
            review = record_listening_review(
                audition, reviewer_id="Auditor01", ratings=scores, notes=note)
            self.assertFalse(review["reviewer_identity_authenticated"])
            self.assertFalse(review["qualified_provider"])
            self.assertFalse(review["approved_cinematic_take"])
            with self.assertRaises(ValueError):
                record_listening_review(
                    audition, reviewer_id="Auditor01",
                    ratings={"naturalness": 5}, notes=note)
            corrupt = deepcopy(audition)
            corrupt["readback"]["actual_file_sha256"] = "f"*64
            with self.assertRaises(PermissionError):
                record_listening_review(
                    corrupt, reviewer_id="Auditor01", ratings=scores, notes=note)
            comparison = compare_auditions([audition], [review])
            self.assertEqual(comparison["rows"][0]["review_count"], 1)
            self.assertEqual(comparison["rows"][0]["descriptive_mean_rubric"], 3.0)
            self.assertTrue(comparison[
                "provider_qualification_and_human_director_approval_remain_open"])
            with self.assertRaises(ValueError):
                compare_auditions([audition, audition], [review])


if __name__ == "__main__":
    unittest.main()
