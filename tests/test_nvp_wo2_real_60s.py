"""WO2 genuine sixty-second frozen USD scene acceptance on native Linux.

Unlike the synthetic 600-sample unit test, this executes 60 actual 640x360
source-authoritative float32 CPU renders spanning all 60 seconds of Film
Time. It measures total wall seconds, p95 latency and Python allocations.
It is NOT a 60-fps real-time GPU/installed Windows certification.
"""
import unittest
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_wo2_continuity import measure_native_frozen_take
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
import test_nvp_openusd_reusable_assets as fixture


class WO2RealSixtySecondNativeContinuity(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        self.scene.publish(
            self.pid,"wo2_60sec_scene",
            prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Light","role":"light","position":[1,2,3]},
            ],
            curves=[],native_schemas=True,
            asset_bindings=[{
                "path":"/World/Actor","asset_id":"body_geometry",
                "asset_revision":1,
            }])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"wo2_60sec_timeline",
            scene_id="wo2_60sec_scene",scene_revision=1,
            duration_tick=str(60*T),
            shots=[{
                "shot_id":"continuity",
                "camera_path":"/World/Camera",
                "start_tick":"0","end_tick":str(60*T),
                "pattern":"continuous",
            }])
        self.take=self.takes.freeze(
            self.pid,"wo2_60sec_take",
            scene_id="wo2_60sec_scene",scene_revision=1,
            timeline_id="wo2_60sec_timeline",timeline_revision=1,
            sample_ticks=[0,30*T,59*T],
            creator_event="director_confirms")

    def test_actual_sixty_second_frozen_scene_renders_60_native_frames(self):
        receipt=measure_native_frozen_take(
            self.index,self.pid,"wo2_60sec_take",
            self.take["document_sha256"],"/World/Camera",
            duration_seconds=60,sample_hz=1)
        self.assertEqual(receipt["status"],"COMPLETE")
        self.assertEqual(receipt["requested_frames"],60)
        self.assertEqual(receipt["processed_frames"],60)
        self.assertTrue(receipt["real_source_rendering_proven"])
        self.assertTrue(receipt["source_immutable_take_reopened"])
        self.assertTrue(receipt["within_memory_budget"])
        self.assertFalse(receipt["gpu_hardware_verified"])
        self.assertFalse(receipt["physical_display_calibrated"])
        self.assertRegex(receipt["sample_receipts_sha256"],
                         r"^[0-9a-f]{64}$")
        self.assertGreater(receipt["actual_wall_seconds"],0)
        self.assertGreaterEqual(receipt["latency_p95_ms"],0)
        # Machine-readable CI artifact is a measured source receipt, not
        # a synthesized GPU/Hydra or physical color calibration pass.
        import json
        from pathlib import Path
        output=Path("wo2-native-60s-receipt.json")
        output.write_text(
            json.dumps(receipt,sort_keys=True,indent=2)+"\\n",
            encoding="utf-8")
        print("WO2_REAL_60S_NATIVE_CPU_RECEIPT:",
              json.dumps(receipt,sort_keys=True),flush=True)


if __name__=="__main__":
    unittest.main()
