"""WO2 measurable Film Time continuity behavior; never fake GPU acceptance."""
import unittest

from backend.nvp_wo2_continuity import measure_source_continuity

SOURCE="a"*64
FRAME="b"*64


class WO2ContinuityAcceptance(unittest.TestCase):
    def test_sixty_seconds_of_film_time_has_real_sampling_receipt(self):
        observed=[]
        def draw(tick):
            observed.append(tick)
            return {"source_sha256":SOURCE,
                    "native_preview_sha256":FRAME,
                    "original_modified":False}
        result=measure_source_continuity(
            sample=draw,source_sha256=SOURCE,
            duration_seconds=60,sample_hz=10)
        self.assertEqual(result["status"],"COMPLETE")
        self.assertEqual(result["requested_frames"],600)
        self.assertEqual(result["processed_frames"],600)
        self.assertAlmostEqual(observed[-1],59.9,places=6)
        self.assertGreaterEqual(result["actual_wall_seconds"],0)
        self.assertGreaterEqual(result["latency_p95_ms"],0)
        self.assertTrue(result["within_memory_budget"])
        self.assertFalse(result["real_source_rendering_proven"])
        self.assertFalse(result["gpu_hardware_verified"])

    def test_cancel_and_source_identity_violation_fail_closed(self):
        count=[0]
        def one(_):
            count[0]+=1
            return {"source_sha256":SOURCE,
                    "native_preview_sha256":FRAME,
                    "original_modified":False}
        receipt=measure_source_continuity(
            sample=one,source_sha256=SOURCE,duration_seconds=60,
            approved_cancel=lambda:count[0]>=3)
        self.assertEqual(receipt["status"],"CANCELLED")
        self.assertEqual(receipt["processed_frames"],3)
        with self.assertRaises(RuntimeError):
            measure_source_continuity(
                sample=lambda _:{"source_sha256":"f"*64,
                                 "native_preview_sha256":FRAME,
                                 "original_modified":False},
                source_sha256=SOURCE,duration_seconds=1)


if __name__=="__main__":
    unittest.main()
