"""INT-02 derived 30-second source-bound delivery contracts.

Uses a tiny test-only PNG renderer. Passing this is not proof of production
Cycles, installed desktop authorization, or a conventional movie master.
"""
from pathlib import Path
import unittest

from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_int02_film_delivery import (
    deliver_approved_30s_take, verify_original_30s_derivative,
)
from test_nvp_final_2d_native import NativeDataFirstOutputTests, T


class ThirtySecondDerivativeTests(unittest.TestCase):
    _render = NativeDataFirstOutputTests._render

    def setUp(self):
        NativeDataFirstOutputTests.setUp(self)

    def _frozen_30s(self):
        ExactTimeShotSequence(self.index).publish(
            self.pid, "ThirtySecCameraTimeline",
            scene_id="spatial_world", scene_revision=1,
            duration_tick=str(30*T),
            shots=[{
                "shot_id": "Full30Seconds",
                "camera_path": "/World/ListenerLeft",
                "pattern": "continuous",
                "start_tick": "0", "end_tick": str(30*T),
            }])
        frozen = OpenUSDTakeCapture(
            self.index, verify_creator_action=lambda event, scope:
            event == "native_approved"
        ).freeze(
            self.pid, "ThirtySecTake",
            scene_id="spatial_world", scene_revision=1,
            timeline_id="ThirtySecCameraTimeline", timeline_revision=1,
            sample_ticks=[0], creator_event="native_approved")
        return frozen["document_sha256"]

    def test_reopen_all_720_samples_pcm_and_immutable_take(self):
        digest = self._frozen_30s()
        result = deliver_approved_30s_take(
            self.exporter, self.pid, "ThirtySecTake", digest,
            "ThirtySecondsA", self.out, listener_path="/World/ListenerLeft")
        self.assertEqual(result["status"], "VERIFIED_30S_DERIVED_PICTURE_AND_PCM")
        self.assertEqual(result["picture_count"], 720)
        self.assertEqual(result["pcm_samples"], 1440000)
        self.assertFalse(result["single_file_master"])
        folder = Path(result["directory"])
        picture = folder/"pictures"/"0000042.png"
        original = picture.read_bytes()
        picture.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaisesRegex(RuntimeError, "SHA mismatch"):
            verify_original_30s_derivative(
                self.index, self.pid, "ThirtySecTake", digest, folder)
        picture.write_bytes(original)
        wav = folder/"soundtrack.wav"
        with wav.open("ab") as stream:
            stream.write(b"tamper")
        with self.assertRaisesRegex(RuntimeError, "soundtrack SHA mismatch"):
            verify_original_30s_derivative(
                self.index, self.pid, "ThirtySecTake", digest, folder)
        self.assertEqual(
            self.index.read_revision(self.pid, "ThirtySecTake", 1)["document_sha256"],
            digest)

    def test_one_second_take_cannot_be_accepted_as_30_second_film(self):
        digest = NativeDataFirstOutputTests.create(self)
        produced = self.exporter.export(
            self.pid, "OutputTake", digest, "OnlyOneSecond",
            self.out, listener_path="/World/ListenerLeft")
        with self.assertRaisesRegex(RuntimeError, "30-second contract"):
            verify_original_30s_derivative(
                self.index, self.pid, "OutputTake", digest, produced["directory"])


if __name__ == "__main__":
    unittest.main()
