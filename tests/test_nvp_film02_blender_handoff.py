"""FILM02-01 native original 30s Blender handoff regression.

These assert data/source planning only; they MUST NOT be used to
claim a completed real Blender film, 30-minute pilot or creator approval.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_film01_original_30s import write_original_30s_source
from tools.nvp_film02_blender_handoff import (
    ASSETS, CHIRP, CUTS, FORMAT, FRAMES, SOURCE_IDS,
    _digest, build_handoff, validate_handoff, write_handoff,
)


class Original30sBlenderHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.source = cls.root / "original-frozen-film"
        cls.report = write_original_30s_source(
            cls.source, approve_test_only=True)
        cls.source_before = (cls.source / "original-source-report.json").read_bytes()
        cls.plan = build_handoff(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_720_exact_film_time_frames_with_three_real_cuts(self):
        plan = self.plan
        self.assertEqual(plan["format"], FORMAT)
        self.assertEqual(plan["cut_output_frames"], list(CUTS))
        self.assertEqual(len(plan["frames"]), FRAMES)
        self.assertEqual(plan["source_edit_sha256"], self.report["edit_sha256"])
        self.assertEqual([shot["take_id"] for shot in plan["shots"]],
                         list(SOURCE_IDS))
        self.assertEqual(len(set(shot["take_sha256"] for shot in plan["shots"])), 3)
        for i in (0, 1, 239, 240, 241, 479, 480, 481, 623, 624, 635, 636, 719):
            frame = plan["frames"][i]
            self.assertEqual(frame["output_frame_zero"], i)
            self.assertEqual(frame["output_film_tick"], str(294000000 * i))
            self.assertEqual(frame["source_film_tick"], str(294000000 * (i % 240)))
            self.assertEqual(frame["source_take_sha256"],
                             plan["shots"][i // 240]["take_sha256"])
            self.assertEqual(len(frame["world_matrices"]), 7)
        self.assertEqual(
            validate_handoff(plan, self.report)["chirp_start_frame"], 624)
        self.assertEqual(
            validate_handoff(plan, self.report)["chirp_end_exclusive"], 636)
        self.assertEqual(plan["manifest_sha256"],
                         _digest({k: v for k, v in plan.items()
                                  if k != "manifest_sha256"}))

    def test_real_camera_light_and_all_object_actor_source_primitives(self):
        plan = self.plan
        self.assertEqual(len(plan["assets"]), 5)
        self.assertEqual(set(plan["frames"][0]["world_matrices"]),
                         set(ASSETS) | {"/World/Camera", "/World/PracticalLight"})
        donut = plan["assets"]["EngineerDonut"]
        source = donut["source_data"]
        self.assertEqual(source["shape"], "mesh")
        self.assertEqual(len(source["points"]), 504)
        self.assertEqual(len(source["triangles"]), 1008)
        self.assertEqual(len(source["face_uvs"]), 1008)
        self.assertTrue(source["layer_sha256"])
        self.assertIn("/World/Engineer", donut["bound_scene_paths"])
        self.assertEqual(plan["assets"]["CrossingBox"]["source_data"]["shape"], "cube")
        self.assertEqual(plan["assets"]["PassingSphere"]["source_data"]["shape"], "sphere")
        # Performer path semantics are preserved, not mapped to fake human rigs.
        self.assertIn("/World/PassingSphere", plan["frames"][672]["world_matrices"])
        self.assertEqual(plan["frames"][624]["source_sound_event_ids"].count(CHIRP), 1)
        self.assertNotIn(CHIRP, plan["frames"][636]["source_sound_event_ids"])

    def test_tampered_frames_rejected_even_when_attacker_recomputes_manifest_digest(self):
        for mutate in (
            lambda doc: doc["frames"][240].__setitem__(
                "segment_id", doc["shots"][0]["segment_id"]),
            lambda doc: doc["frames"][480].__setitem__(
                "source_take_sha256", doc["shots"][1]["take_sha256"]),
            lambda doc: doc["frames"][624].__setitem__(
                "source_sound_event_ids", ["SoundRekindle"]),
            lambda doc: doc["frames"][719]["world_matrices"].pop(
                "/World/Camera"),
        ):
            changed = deepcopy(self.plan)
            mutate(changed)
            changed["manifest_sha256"] = _digest(
                {k: v for k, v in changed.items() if k != "manifest_sha256"})
            with self.assertRaises((RuntimeError, PermissionError)):
                validate_handoff(changed, self.report)

    def test_immutable_source_and_no_premature_blender_or_final_film_acceptance(self):
        self.assertEqual((self.source / "original-source-report.json").read_bytes(),
                         self.source_before)
        self.assertTrue(self.plan["source_takes_unchanged"])
        self.assertTrue(self.plan["test_only_source_fixture"])
        self.assertTrue(self.plan["renderer_handoff_pending"])
        self.assertFalse(self.plan["production_creator_approval_obtained"])
        self.assertFalse(self.plan["picture_rendered"])
        self.assertFalse(self.plan["mixed_audio_exported"])
        self.assertTrue(self.plan["source_pcm_reference_only"])

    def test_output_is_created_once_and_cannot_overwrite(self):
        path = self.root / "source-handoff.json"
        result = write_handoff(self.source, path)
        self.assertEqual(result["manifest_sha256"], self.plan["manifest_sha256"])
        self.assertEqual(json.loads(path.read_text())["manifest_sha256"],
                         self.plan["manifest_sha256"])
        with self.assertRaises(PermissionError):
            write_handoff(self.source, path)
        with self.assertRaises(PermissionError):
            write_handoff(self.source, self.source / "illegal-source-side-output.json")


if __name__ == "__main__":
    unittest.main()
