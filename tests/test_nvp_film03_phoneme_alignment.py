"""FILM03-09C: strict MFA JSON/phoneme timing source contracts.

MFA output here is a structural fixture; no native acoustic model has run.
The separate real-model CI job must demonstrate that independently.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_film03_independent_facial_direction import FilmIndependentActingDirection
from backend.nvp_film03_phoneme_alignment import (
    FORMAT, import_mfa_json, source_alignment_plan, run_reviewed_mfa_one,
)
from test_nvp_film03_independent_facial_direction import prepared


def example_json():
    return {
        "start": 0, "end": 1,
        "tiers": {
            "words": {"type": "interval", "entries": [
                [0, 0.22, "Hello"],
                [0.24, 0.55, "world"],
            ]},
            "phones": {"type": "interval", "entries": [
                [0, 0.06, "HH"],
                [0.06, 0.14, "AH0"],
                [0.14, 0.22, "L"],
                [0.24, 0.29, "W"],
                [0.29, 0.40, "ER1"],
                [0.40, 0.48, "L"],
                [0.48, 0.55, "D"],
            ]},
        },
    }


def encoded(doc):
    return json.dumps(doc, separators=(",", ":"), allow_nan=False).encode("utf8")


class MFARealAudioImporterContracts(unittest.TestCase):
    def test_real_timing_units_canonical_visemes_and_words(self):
        parsed = import_mfa_json(
            encoded(example_json()), exact_script_text="Hello world!",
            pcm_sample_count=48000)
        self.assertEqual(parsed["format"], FORMAT)
        self.assertEqual(parsed["sample_rate_hz"], 48000)
        self.assertEqual(parsed["source_sample_count"], 48000)
        self.assertEqual(parsed["ticks_per_sample"], 147000)
        self.assertEqual(
            [x["normalized"] for x in parsed["word_intervals"]],
            ["hello", "world"])
        self.assertEqual(parsed["viseme_candidates"][0]["start_sample"], 0)
        self.assertEqual(parsed["viseme_candidates"][0]["viseme"], "rest")
        self.assertEqual(parsed["viseme_candidates"][1]["viseme"], "AA")
        self.assertEqual(parsed["viseme_candidates"][4]["viseme"], "RR")
        self.assertEqual(parsed["viseme_candidates"][-1]["end_sample"], 26400)
        self.assertFalse(parsed["source_audio_automatically_transcribed"])
        self.assertFalse(parsed["audio_to_phoneme_timing_independently_accuracy_scored"])
        self.assertFalse(parsed["rigged_mouth_motion_rendered"])

    def test_wrong_script_unsupported_phone_gap_and_overlap_fail_closed(self):
        for mutation in (
            lambda o: o["tiers"]["words"]["entries"][1].__setitem__(2, "another"),
            lambda o: o["tiers"]["phones"]["entries"][1].__setitem__(2, "HACK"),
            lambda o: o["tiers"]["phones"]["entries"][1].__setitem__(0, .01),
            lambda o: o["tiers"]["phones"]["entries"][1].__setitem__(1, .05),
            lambda o: o["tiers"]["phones"]["entries"][2].__setitem__(1, 2.0),
            lambda o: o["tiers"].update({"speaker - phones": {}}),
            lambda o: o["tiers"]["words"]["entries"].pop(),
            lambda o: o["tiers"]["phones"]["entries"].clear(),
        ):
            obj = example_json()
            mutation(obj)
            with self.subTest(obj=obj), self.assertRaises(
                    (ValueError, PermissionError)):
                import_mfa_json(
                    encoded(obj), exact_script_text="Hello world!",
                    pcm_sample_count=48000)
        with self.assertRaises(PermissionError):
            import_mfa_json(
                encoded(example_json()), exact_script_text="This is a different scene.",
                pcm_sample_count=48000)
        with self.assertRaises(ValueError):
            import_mfa_json(
                encoded(example_json()), exact_script_text="Hello world!",
                pcm_sample_count=16000)
        with self.assertRaises(ValueError):
            import_mfa_json(
                b"{" + b"x" * 600000 + b"}", exact_script_text="Hello world!",
                pcm_sample_count=48000)

    def test_facial_source_and_original_audio_bound_to_actual_actorid(self):
        with TemporaryDirectory() as temp:
            state, original, args = prepared(Path(temp))
            host = FilmIndependentActingDirection(
                state["index"],
                verify_creator_action=lambda event, scope:
                    event == "DIRECTOR" and
                    scope["operation"] == "film03_publish_independent_acted_face_voice_body")
            receipt = host.publish(
                state["pid"], state["request"],
                performance_id="DonutSourceFaceForRealMFA",
                expected_revision=0,
                director_note="Only a candidate for independently aligned original actor audio",
                creator_event="DIRECTOR", **args)
            plan = source_alignment_plan(
                state["index"], state["pid"], state["request"],
                receipt["performance_id"], receipt["revision"])
            self.assertEqual(plan["actor_id"], state["people"]["DONUT"])
            self.assertEqual(plan["voice_id"], "Voice_Donut_ActorIdentity")
            self.assertEqual(plan["audio_source_document_sha256"],
                             original["document_sha256"])
            self.assertEqual(plan["sample_count"], 24000)
            self.assertFalse(plan["phoneme_model_already_executed"])
            self.assertFalse(plan["speech_is_final_selected_film_audio"])
            self.assertEqual(plan["source_take_id"], "RelayRekindleTake")
            with self.assertRaises((ValueError, KeyError, PermissionError)):
                source_alignment_plan(
                    state["index"], state["pid"],
                    dict(state["request"], actor_id=state["people"]["BOX"]),
                    receipt["performance_id"], 1)
            with self.assertRaises((ValueError, KeyError, PermissionError)):
                source_alignment_plan(
                    state["index"], state["pid"], state["request"],
                    "WrongFacialSource", 1)
            # A derived performance cannot overwrite the original guide/Takes.
            with self.assertRaises(ValueError):
                run_reviewed_mfa_one(
                    state["index"], plan,
                    work_root=Path(temp).resolve(),
                    mfa_binary=Path(temp) / "nonexistent-mfa",
                    mfa_sha256="0" * 64,
                    dictionary_file=Path(temp) / "nonexistent.dict",
                    dictionary_sha256="0" * 64,
                    acoustic_model_file=Path(temp) / "nonexistent.model",
                    acoustic_model_sha256="0" * 64,
                    candidate_object_id="RelayRekindleTake")
            # No unreviewed binary may execute, even if a source plan exists.
            with self.assertRaises((ValueError, PermissionError)):
                run_reviewed_mfa_one(
                    state["index"], plan,
                    work_root=Path(temp).resolve(),
                    mfa_binary=Path(temp) / "nonexistent-mfa",
                    mfa_sha256="0" * 64,
                    dictionary_file=Path(temp) / "nonexistent.dict",
                    dictionary_sha256="0" * 64,
                    acoustic_model_file=Path(temp) / "nonexistent.model",
                    acoustic_model_sha256="0" * 64)
            self.assertEqual(
                state["index"].read_revision(
                    state["pid"], "RelayRekindleTake", 1)["document_sha256"],
                state["original_take"]["document_sha256"])


if __name__ == "__main__":
    unittest.main()
