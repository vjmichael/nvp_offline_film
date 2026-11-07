"""WO2 independent Hydra execution is required, never simulated as accepted."""
import unittest
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

    def test_unapproved_camera_and_arbitrary_renderer_refused(self):
        with self.assertRaises(PermissionError):
            capture_hydra_evidence(
                self.index,self.pid,"hydra_scene",1,
                camera_path="/World/Actor")
        with self.assertRaises(ValueError):
            capture_hydra_evidence(
                self.index,self.pid,"hydra_scene",1,
                camera_path="/World/Camera",renderer="evil;rm -rf /")


if __name__=="__main__":
    unittest.main()
