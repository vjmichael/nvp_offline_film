"""FILM03-09D: ACTUAL native OpenUSD mesh/UsdSkel facial-shape acceptance.

USD library is required. These tests author genuine source mesh geometry,
genuine UsdSkel.BlendShape offsets and a separate native USD animation layer.
Phoneme events in the fixture are manually chosen *test-only* labels; they
do NOT establish that MFA ran, lips look believable, or a real film was made.
"""
from __future__ import annotations

from copy import deepcopy
import unittest

from pxr import Sdf, Usd, UsdSkel

import test_nvp_slate07_skinned_camera as fixture
from backend.nvp_film03_facial_rig_compositor import (
    FORMAT, inspect_original_rig, compose_usd_facial_overlay,
    publish_verified_alignment_overlay, validate_stored_acoustic_output,
)
from backend.nvp_film03_phoneme_alignment import import_mfa_json
from test_nvp_film03_phoneme_alignment import example_json, encoded
from backend.nvp_film03_phoneme_alignment import FORMAT as PHONEME_FORMAT
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T


def offsets(count, index, delta):
    values = [[0., 0., 0.] for _ in range(count)]
    values[index] = list(delta)
    return values


class RealActorFacialRigAcceptance(fixture.RealCharacterAndLens):
    def setUp(self):
        super().setUp()
        rig = deepcopy(self.rigs[0])
        n = len(self.skin["points"])
        rig["skin"]["blend_shapes"] = [
            {"name": "MouthClosed",
             "offsets": offsets(n, 4, [-0.1, 0.0, 0.0])},
            {"name": "MouthOpen",
             "offsets": offsets(n, 5, [0.0, -0.2, 0.0])},
            {"name": "Sad",
             "offsets": offsets(n, 6, [0.0, 0.0, -0.17])},
            {"name": "Smile",
             "offsets": offsets(n, 7, [0.0, 0.0, 0.23])},
            {"name": "Inactive",
             "offsets": offsets(n, 1, [0., 0., 0.])},
        ]
        self.source_rig = deepcopy(rig)
        for t, key in enumerate(rig["samples"]):
            key["face_weights"] = {
                "MouthClosed": 0., "MouthOpen": 0.,
                "Sad": 0., "Smile": 0.3 + t * 0.1, "Inactive": 0.,
            }
        self.scene.publish(
            self.pid, "real_face_scene",
            prims=[
                {"path": "/World/Actor", "role": "actor",
                 "position": [0, 0, 0]},
                {"path": "/World/Camera", "role": "camera",
                 "position": [0, 0, 8]},
                {"path": "/World/Key", "role": "light",
                 "position": [0, 5, 5]},
            ], curves=[], skeletal_rigs=[rig])
        self.takes.freeze(
            self.pid, "real_face_take",
            scene_id="real_face_scene", scene_revision=1,
            timeline_id="acting", timeline_revision=1,
            sample_ticks=[0, T, 2 * T],
            creator_event="freeze_take")
        self.take = self.index.read_revision(self.pid, "real_face_take", 1)
        self.rig = inspect_original_rig(
            self.index, self.pid, "real_face_take", "/World/Actor",
            self.take["document_sha256"])
        self.controls = {
            "visemes": {"MBP": "MouthClosed", "AA": "MouthOpen"},
            "emotions": {"sad": "Sad", "happy": "Smile"},
            "emotion_reset_targets": ["Sad", "Smile"],
        }
        self.phonemes = [
            {"start_sample": 0, "end_sample": 4000,
             "phoneme": "M", "viseme": "MBP", "weight": 1.0},
            {"start_sample": 4000, "end_sample": 9500,
             "phoneme": "AA1", "viseme": "AA", "weight": 1.0},
        ]
        self.face = [
            {"sample": 0, "value": "sad", "intensity": 0.8},
            {"sample": 14000, "value": "happy", "intensity": 0.6},
        ]

    def compile(self, *, controls=None, phonemes=None,
                face=None, body=None):
        return compose_usd_facial_overlay(
            self.index, self.rig,
            phonemes=self.phonemes if phonemes is None else phonemes,
            face_track=self.face if face is None else face,
            body_track=([{"sample": 0, "value": "relaxed", "intensity": 1.0}]
                        if body is None else body),
            controls=self.controls if controls is None else controls,
            source_start_tick=0, sample_count=48000)

    def test_actual_original_shape_geometry_and_blendshape_sources(self):
        rig = self.rig
        self.assertTrue(rig["real_usd_mesh_and_shape_offsets_verified"])
        self.assertEqual(rig["mesh_path"],
                         "/World/Actor/Rig/CharacterMesh")
        self.assertEqual(rig["shape_names"], [
            "MouthClosed", "MouthOpen", "Sad", "Smile", "Inactive"])
        self.assertEqual(set(rig["nonzero_offset_shapes"]),
                         {"MouthClosed", "MouthOpen", "Sad", "Smile"})
        self.assertEqual(rig["shape_deformed_vertices"]["MouthClosed"], [4])
        self.assertEqual(rig["shape_deformed_vertices"]["Smile"], [7])
        self.assertEqual(rig["shape_deformed_vertices"]["Inactive"], [])
        self.assertEqual(rig["source_scene_sha256"],
                         self.index.read_revision(
                             self.pid, "real_face_scene", 1)["document_sha256"])
        self.assertFalse(rig["artistic_mouth_semantics_verified_by_human"])
        with self.assertRaises(PermissionError):
            inspect_original_rig(
                self.index, self.pid, "real_face_take", "/World/Actor",
                "0" * 64)
        with self.assertRaises(PermissionError):
            inspect_original_rig(
                self.index, self.pid, "real_face_take", "/World/Key",
                self.take["document_sha256"])
        # Actual original actor may have no facial rig; NEVER invent lips.
        self.freeze()
        with self.assertRaises(ValueError):
            inspect_original_rig(
                self.index, self.pid, "take", "/World/Actor",
                self.index.read_revision(
                    self.pid, "take", 1)["document_sha256"])

    def test_true_usd_overlay_animates_mouth_and_distinct_director_face(self):
        original, original_stage = self.scene.open(
            self.pid, "real_face_scene", 1)
        source_anim = UsdSkel.Animation(original_stage.GetPrimAtPath(
            self.rig["animation_path"]))
        before = list(source_anim.GetBlendShapeWeightsAttr().Get(
            Usd.TimeCode(0)))
        self.assertAlmostEqual(before[3], 0.3, places=5)
        result = self.compile()
        self.assertEqual(result["format"], FORMAT)
        self.assertTrue(result["real_native_usd_blendshape_layer_authored"])
        self.assertTrue(result["all_original_joint_body_animation_untouched"])
        self.assertTrue(result["human_shape_semantic_review_open"])
        self.assertTrue(result["rigged_visual_lip_sync_not_rendered"])
        self.assertGreater(result["keyframe_count"], 5)
        overlay = Sdf.Layer.CreateAnonymous("test_real_derived_face.usda")
        self.assertTrue(overlay.ImportFromString(
            result["usd_layer_bytes"].decode("utf8")))
        stage = Usd.Stage.Open(overlay, Usd.Stage.LoadNone)
        anim = UsdSkel.Animation(stage.GetPrimAtPath(
            self.rig["animation_path"]))
        names = list(anim.GetBlendShapesAttr().Get())
        self.assertEqual([str(x) for x in names], self.rig["shape_names"])
        at = lambda sample: list(anim.GetBlendShapeWeightsAttr().Get(
            Usd.TimeCode(float(sample * 147000))))
        first = at(2000)
        self.assertGreater(first[0], 0.5)
        self.assertAlmostEqual(first[2], 0.8, places=5)
        self.assertAlmostEqual(first[3], 0., places=5)
        second = at(7000)
        self.assertGreater(second[1], 0.5)
        self.assertAlmostEqual(second[2], 0.8, places=5)
        happy = at(14000)
        self.assertAlmostEqual(happy[2], 0., places=5)
        self.assertAlmostEqual(happy[3], 0.6, places=5)
        # Only a facial animation override: no joint translations authored.
        self.assertIsNone(anim.GetTranslationsAttr().Get())
        self.assertEqual(original["document_sha256"],
                         self.index.read_revision(
                             self.pid, "real_face_scene", 1)["document_sha256"])
        self.assertEqual(list(source_anim.GetBlendShapeWeightsAttr().Get(
            Usd.TimeCode(0))), before)

    def test_wrong_shape_fake_mouth_conflicting_face_rig_and_time_refused(self):
        failures = [
            dict(controls=dict(self.controls,
                visemes={"MBP": "MouthClosed"})),
            dict(controls=dict(self.controls,
                visemes={"MBP": "Inactive", "AA": "MouthOpen"})),
            dict(controls=dict(self.controls,
                visemes={"MBP": "MouthClosed", "AA": "Smile"})),
            dict(controls=dict(self.controls,
                emotion_reset_targets=["Sad"])),
            dict(phonemes=[{
                "start_sample": 0, "end_sample": 100000,
                "phoneme": "M", "viseme": "MBP", "weight": 1.,
            }]),
            dict(phonemes=[self.phonemes[1], self.phonemes[0]]),
        ]
        for case in failures:
            with self.subTest(case=case), self.assertRaises(
                (ValueError, PermissionError)):
                self.compile(**case)

    def test_actual_shared_mesh_vertices_require_corrective_face_rig(self):
        overlap = deepcopy(self.source_rig)
        smile = overlap["skin"]["blend_shapes"][3]["offsets"]
        smile[7] = [0., 0., 0.]
        smile[4] = [0., 0., 0.23]
        for t, key in enumerate(overlap["samples"]):
            key["face_weights"] = {
                "MouthClosed": 0., "MouthOpen": 0.,
                "Sad": 0., "Smile": 0.3 + t * 0.1, "Inactive": 0.,
            }
        self.scene.publish(
            self.pid, "overlap_face_scene",
            prims=[
                {"path": "/World/Actor", "role": "actor", "position": [0, 0, 0]},
                {"path": "/World/Camera", "role": "camera", "position": [0, 0, 8]},
                {"path": "/World/Key", "role": "light", "position": [0, 5, 5]},
            ], curves=[], skeletal_rigs=[overlap])
        self.takes.freeze(
            self.pid, "overlap_face_take", scene_id="overlap_face_scene",
            scene_revision=1, timeline_id="acting", timeline_revision=1,
            sample_ticks=[0, T, 2 * T], creator_event="freeze_take")
        frozen = self.index.read_revision(self.pid, "overlap_face_take", 1)
        actual_rig = inspect_original_rig(
            self.index, self.pid, "overlap_face_take", "/World/Actor",
            frozen["document_sha256"])
        self.assertEqual(actual_rig["shape_deformed_vertices"]["Smile"], [4])
        with self.assertRaises(PermissionError):
            compose_usd_facial_overlay(
                self.index, actual_rig, phonemes=self.phonemes,
                face_track=self.face, body_track=[],
                controls=self.controls, source_start_tick=0,
                sample_count=48000)

    def test_source_rig_descriptor_tampering_is_not_allowed(self):
        forged = deepcopy(self.rig)
        forged["shape_deformed_vertices"]["Smile"] = [4]
        with self.assertRaises(PermissionError):
            compose_usd_facial_overlay(
                self.index, forged, phonemes=self.phonemes,
                face_track=self.face, body_track=[],
                controls=self.controls, source_start_tick=0,
                sample_count=48000)

    def test_actual_stored_mfa_json_must_reproduce_every_phoneme(self):
        # The byte source is an explicit MFA *format fixture* and does not
        # pretend a speech model ran. The validation tests data integrity.
        source = encoded(example_json())
        model_sha = self.index.put_blob(
            self.pid, source, media_type="application/json")
        parsed = import_mfa_json(
            source, exact_script_text="Hello world!",
            pcm_sample_count=48000)
        candidate = {
            **parsed,
            "source_plan": {
                "exact_script_text": "Hello world!",
                "sample_count": 48000,
            },
            "native_output_sha256": model_sha,
            "native_output_blob_sha256": model_sha,
            "native_acoustic_model_executed": False,
        }
        self.assertEqual(
            validate_stored_acoustic_output(self.index, self.pid, candidate),
            parsed)
        corrupt = deepcopy(candidate)
        corrupt["viseme_candidates"][0]["viseme"] = "TH"
        with self.assertRaises(PermissionError):
            validate_stored_acoustic_output(self.index, self.pid, corrupt)
        missing = deepcopy(candidate)
        missing["native_output_blob_sha256"] = "0" * 64
        with self.assertRaises(PermissionError):
            validate_stored_acoustic_output(self.index, self.pid, missing)
        different = deepcopy(candidate)
        different["source_plan"]["exact_script_text"] = "Different spoken words"
        with self.assertRaises(PermissionError):
            validate_stored_acoustic_output(self.index, self.pid, different)

    def test_no_unverified_acoustic_source_may_publish_as_real_animation(self):
        self.index.register_revision(
            self.pid, "FakeAcoustic", "performance",
            {"format": PHONEME_FORMAT, "native_acoustic_model_executed": False})
        self.index.register_revision(
            self.pid, "FakeFace", "performance",
            {"format": "nvp.film03.independent_face_body_voice_direction.v1"})
        with self.assertRaises(PermissionError):
            publish_verified_alignment_overlay(
                self.index, self.pid, "FakeAcoustic", "FakeFace",
                "/World/Actor", controls=self.controls,
                candidate_id="FakeMouthGeneratedTake")
        with self.assertRaises(KeyError):
            self.index.read_revision(
                self.pid, "FakeMouthGeneratedTake", 1)


if __name__ == "__main__":
    unittest.main()
