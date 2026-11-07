"""WO2 independent Hydra execution is required, never simulated as accepted."""
import unittest
import shutil
from unittest.mock import patch
import test_nvp_openusd_reusable_assets as fixture
from backend.nvp_wo2_hydra_probe import capture_hydra_evidence


class WO2IndependentHydraGate(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        self.scene.publish(
            self.pid,"hydra_scene",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
            ],curves=[],native_schemas=True,
            asset_bindings=[{
                "path":"/World/Actor","asset_id":"body_geometry",
                "asset_revision":1}])

    def test_missing_independent_renderer_is_not_fabricated_success(self):
        with patch("backend.nvp_wo2_hydra_probe.shutil.which",
                   return_value=None):
            receipt=capture_hydra_evidence(
                self.index,self.pid,"hydra_scene",1,
                camera_path="/World/Camera")
        self.assertEqual(receipt["status"],"HYDRA_BINARY_UNAVAILABLE")
        self.assertFalse(receipt["real_independent_frame_rendered"])
        self.assertFalse(receipt["physical_gpu_accepted"])
        self.assertFalse(receipt["hydra_shader_parity_accepted"])
        self.assertFalse(receipt["physical_display_calibrated"])
        self.assertFalse(receipt["original_modified"])

    @unittest.skipUnless(shutil.which("usdrecord"),
                         "Independent Hydra usdrecord is not installed")
    def test_actual_hydra_frame_is_rendered_by_external_binary(self):
        receipt=capture_hydra_evidence(
            self.index,self.pid,"hydra_scene",1,
            camera_path="/World/Camera",renderer="Embree",
            require_gpu=False,timeout_seconds=60)
        self.assertEqual(receipt["status"],"HYDRA_FRAME_RENDERED",
                         receipt)
        self.assertTrue(receipt["real_independent_frame_rendered"])
        self.assertRegex(receipt["rendered_rgb_sha256"],r"^[0-9a-f]{64}$")
        self.assertGreater(receipt["rendered_width"],0)
        self.assertFalse(receipt["hydra_shader_parity_accepted"])
        self.assertFalse(receipt["physical_gpu_accepted"])

    def test_paired_image_requires_real_exact_frozen_take_identity(self):
        with self.assertRaises(ValueError):
            capture_hydra_evidence(
                self.index,self.pid,"hydra_scene",1,
                camera_path="/World/Camera",native_take={
                    "take_id":"some_take","take_sha256":"a"*64,
                    "tick":1})
        with self.assertRaises(ValueError):
            capture_hydra_evidence(
                self.index,self.pid,"hydra_scene",1,
                camera_path="/World/Camera",native_take={
                    "take_id":"some_take","take_sha256":"not a SHA",
                    "tick":0})
        with patch("backend.nvp_wo2_hydra_probe.shutil.which",
                   return_value=None):
            result=capture_hydra_evidence(
                self.index,self.pid,"hydra_scene",1,
                camera_path="/World/Camera",native_take={
                    "take_id":"some_take","take_sha256":"a"*64,
                    "tick":0})
        self.assertEqual(result["status"],"HYDRA_BINARY_UNAVAILABLE")
        self.assertFalse(result["hydra_shader_parity_accepted"])

    def test_unapproved_camera_and_arbitrary_renderer_refused(self):
        with self.assertRaises(PermissionError):
            capture_hydra_evidence(
                self.index,self.pid,"hydra_scene",1,
                camera_path="/World/Actor")
        with self.assertRaises(ValueError):
            capture_hydra_evidence(
                self.index,self.pid,"hydra_scene",1,
                camera_path="/World/Camera",renderer="evil;rm -rf /")
        with self.assertRaises(ValueError):
            capture_hydra_evidence(
                self.index,self.pid,"hydra_scene",1,
                camera_path="/World/Camera",
                renderer="Storm",require_gpu=False)
        with self.assertRaises(ValueError):
            capture_hydra_evidence(
                self.index,self.pid,"hydra_scene",1,
                camera_path="/World/Camera",
                renderer="Embree",require_gpu=True)


if __name__=="__main__":
    unittest.main()
