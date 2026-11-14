"""Original ActorID + facial shape + immutable PCM sample pairing regression.

No phoneme generator and no claim of visually confirmed lip synchronization.
"""
from hashlib import sha256
import unittest

from backend.nvp_p1f_actor_dialogue_evidence import original_actor_dialogue_frame
from backend.nvp_p1f_production_character_assets import P1FReviewedProductionCharacters
from test_nvp_p1f_production_character_assets_native import OriginalProductionCharacterTests


class ActorFaceDialogueTests(unittest.TestCase):
    def setUp(self):
        original = OriginalProductionCharacterTests(
            "test_reviewed_glb_and_explicit_bone_map_survive_independent_take_reopen")
        original.setUp()
        self.addCleanup(original.doCleanups)
        original.register()
        original.cast()
        self.fixture = original

    def sample(self, frame=0, **kwargs):
        return original_actor_dialogue_frame(
            self.fixture.index, self.fixture.pid,
            "original_reviewed_cast", "rigged_reel_plan", 0, frame, **kwargs)

    def test_facial_source_clock_and_original_pcm_are_paired_not_replaced(self):
        first = self.sample()
        self.assertEqual(first["status"],
                         "ORIGINAL_ACTOR_FACE_PCM_PAIR_NOT_LIPSYNC_VERIFIED")
        self.assertEqual(first["actor_id"], "ACT_OriginalLead")
        self.assertEqual(first["dialogue_event_id"], "lead_speech")
        self.assertEqual(first["sample_count"], 2000)
        self.assertEqual(first["first_original_sample"], 0)
        self.assertGreater(first["mono_pcm_rms"], 0)
        self.assertEqual(len(first["facial_weights"]), 4)
        self.assertFalse(first["speech_motion_correlation_verified"])
        self.assertFalse(first["genuine_cycles_output"])
        self.assertFalse(first["new_voice_synthesized"])
        self.assertEqual(self.sample(), first)
        next_frame = self.sample(frame=1)
        self.assertEqual(next_frame["status"], "ORIGINAL_ACTOR_NO_ACTIVE_DIALOGUE")
        self.assertIsNone(next_frame["voice_pcm_sha256"])

    def test_tampered_original_pcm_and_out_of_scope_samples_denied(self):
        with self.assertRaises(ValueError):
            self.sample(window_samples=10000)
        source = self.fixture.index.read_revision(
            self.fixture.pid, "actor_dialogue_source", 1)
        blob = source["data"]["chunks"][0]["blob_sha256"]
        path = self.fixture.index._blob_path(self.fixture.pid, blob)
        path.write_bytes(b"changed recorded actor PCM")
        with self.assertRaises(RuntimeError):
            self.sample()


if __name__=="__main__":
    unittest.main()
