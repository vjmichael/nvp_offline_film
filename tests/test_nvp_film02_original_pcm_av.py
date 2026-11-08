"""FILM02-03 original PCM and real Cycles/mux authorization boundary tests.

All audio source tests use real frozen FilmIndex/OpenUSD and actual recorded
PCM chunks. No fake six-frame film may pass full 720-frame acceptance.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_wo6_07e_source_review import sample_editorial_source
from tools.nvp_film01_original_30s import write_original_30s_source
from tools.nvp_film02_blender_handoff import build_handoff
from tools.nvp_film02_original_pcm import (
    FORMAT, FRAMES, TOTAL_SAMPLES, read_original_pcm_frame,
    write_original_pcm,
)
from tools.nvp_film02_original_av_review import (
    create_original_av_review, mux_verified_av, validate_audio_proof,
)


class Film02RealOriginalSoundReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.source = cls.root / "frozen-original-30-seconds"
        cls.report = write_original_30s_source(
            cls.source, approve_test_only=True)
        cls.plan = build_handoff(cls.source)
        cls.index = FilmIndex(Studio(cls.source / "short.sqlite3"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_original_PCM_is_exact_2000_source_samples_at_cuts_and_cue(self):
        for n in (0, 1, 239, 240, 241, 479, 480, 481,
                  623, 624, 630, 635, 636, 719):
            row = read_original_pcm_frame(
                self.index, self.plan, n, verify_timeline=(n % 240 == 0))
            self.assertEqual(row["frame_zero"], n)
            self.assertEqual(row["sample_first"], n * 2000)
            self.assertEqual(row["sample_count"], 2000)
            self.assertEqual(len(row["pcm"]), 4000)
            self.assertEqual(row["original_take_sha256"],
                             self.plan["shots"][n//240]["take_sha256"])
            self.assertEqual(row["source_audio_event_ids"],
                             self.plan["frames"][n]["source_sound_event_ids"])
            self.assertEqual(sha256(row["pcm"]).hexdigest(),
                             row["original_pcm16_sha256"])
            self.assertEqual("BeaconSignalRestored" in row["source_audio_event_ids"],
                             624 <= n < 636)

    def test_original_audio_matches_existing_editorial_source_audition(self):
        for n in (0, 240, 480, 624, 635, 636):
            expected = sample_editorial_source(
                self.index, self.report["project_id"],
                self.report["edit_id"], 1, self.report["edit_sha256"],
                n, audio_window_frames=1)
            self.assertFalse(expected["original_source_modified"])
            self.assertFalse(expected["frame_spans_edit_boundary"])
            self.assertEqual(expected["source_pcm_samples"], 2000)
            self.assertTrue(expected["audio_data_url"].startswith("data:audio/wav;base64,"))
            with wave.open(BytesIO(base64.b64decode(
                    expected["audio_data_url"].split(",", 1)[1],
                    validate=True)), "rb") as sound:
                actual = sound.readframes(2000)
            from_original = read_original_pcm_frame(self.index, self.plan, n)
            self.assertEqual(actual, from_original["pcm"])

    def test_refuses_source_time_or_sound_event_spoofing(self):
        source = deepcopy(self.plan)
        source["frames"][624]["source_sound_event_ids"] = ["SoundRekindle"]
        with self.assertRaises(PermissionError):
            read_original_pcm_frame(self.index, source, 624)
        source = deepcopy(self.plan)
        source["frames"][240]["source_film_tick"] = "294000000"
        with self.assertRaises(PermissionError):
            read_original_pcm_frame(self.index, source, 240)
        with self.assertRaises(ValueError):
            read_original_pcm_frame(self.index, self.plan, 720)

    def test_export_original_complete_wav_without_inventing_a_movie(self):
        wav = self.root / "original-frozen-source-48k.wav"
        receipt = self.root / "original-frozen-source-48k.receipt.json"
        proof = write_original_pcm(self.source, self.plan, self.report,
                                   wav, receipt)
        self.assertEqual(proof["format"], FORMAT)
        self.assertEqual(proof["source_manifest_sha256"], self.plan["manifest_sha256"])
        self.assertEqual(proof["source_cut_frames"], [240, 480])
        self.assertEqual(proof["beacon_cue_frames"], [624, 636])
        self.assertEqual(proof["total_original_samples"], TOTAL_SAMPLES)
        self.assertEqual(len(proof["original_frame_pcm_receipts"]), FRAMES)
        self.assertFalse(proof["soundtrack_mastered"])
        self.assertTrue(validate_audio_proof(
            self.plan, wav, proof)["source_PCM_verified"])
        self.assertEqual(json.loads(receipt.read_text("utf8"))["pcm_wav_sha256"],
                         sha256(wav.read_bytes()).hexdigest())
        with wave.open(str(wav), "rb") as sound:
            self.assertEqual(sound.getnframes(), 1_440_000)
            self.assertEqual(sound.getframerate(), 48_000)
            self.assertEqual(sound.getnchannels(), 1)
            self.assertEqual(sound.getsampwidth(), 2)
        with self.assertRaises(PermissionError):
            write_original_pcm(self.source, self.plan, self.report, wav,
                               self.root/"duplicated-receipt.json")
        # A receipt for a different source mix must never be accepted.
        changed = dict(proof, source_edit_sha256="0"*64)
        with self.assertRaises(PermissionError):
            validate_audio_proof(self.plan, wav, changed)

    def test_missing_native_cycles_frames_cannot_produce_an_AVI(self):
        nonexistent = self.root / "missing-original-Cycles-pictures"
        out = self.root / "invalid-claimed-review"
        handoff = self.root / "original-handoff.json"
        handoff.write_text(json.dumps(self.plan), encoding="utf8")
        with self.assertRaises((PermissionError, RuntimeError, FileNotFoundError)):
            create_original_av_review(
                self.source, handoff, nonexistent, out)
        self.assertFalse(out.exists())
        with self.assertRaises((PermissionError, TypeError, KeyError)):
            mux_verified_av(self.plan, [], nonexistent, nonexistent, {}, out/"fraud.avi")
        self.assertFalse((out/"fraud.avi").exists())


if __name__ == "__main__":
    unittest.main()
