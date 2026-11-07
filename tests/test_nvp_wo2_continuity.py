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


class WO2RealUSDContinuity(unittest.TestCase):
    def setUp(self):
        import test_nvp_openusd_reusable_assets as fixture
        fixture.NativeUSD02Integration.setUp(self)
        self.scene.publish(
            self.pid,"continuity_scene",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Light","role":"light","position":[1,2,3]},
            ],curves=[],native_schemas=True,asset_bindings=[{
                "path":"/World/Actor","asset_id":"body_geometry",
                "asset_revision":1}])
        self.take=self.takes.freeze(
            self.pid,"continuity_take",scene_id="continuity_scene",
            scene_revision=1,timeline_id="event_timeline",
            timeline_revision=1,sample_ticks=[0],
            creator_event="director_confirms")

    def test_one_real_native_usd_raster_has_independent_source_receipt(self):
        from backend.nvp_wo2_continuity import measure_native_frozen_take
        report=measure_native_frozen_take(
            self.index,self.pid,"continuity_take",
            self.take["document_sha256"],"/World/Camera",
            duration_seconds=1,sample_hz=1)
        self.assertEqual(report["status"],"COMPLETE")
        self.assertEqual(report["processed_frames"],1)
        self.assertTrue(report["real_source_rendering_proven"])
        self.assertTrue(report["source_immutable_take_reopened"])
        self.assertFalse(report["gpu_hardware_verified"])
        self.assertFalse(report["physical_display_calibrated"])
        with self.assertRaises(RuntimeError):
            measure_native_frozen_take(
                self.index,self.pid,"continuity_take",
                self.take["document_sha256"],"/World/Camera",
                duration_seconds=60,sample_hz=1)


if __name__=="__main__":
    unittest.main()
