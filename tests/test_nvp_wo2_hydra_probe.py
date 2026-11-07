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



class WO2IndependentFiveChannelHydra(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)

    @unittest.skipUnless(shutil.which("usdrecord"),
                         "Independent Hydra usdrecord is not installed")
    def test_real_five_channel_hydra_frame_and_same_take_cpu_pixels(self):
        from io import BytesIO
        from PIL import Image
        from backend.nvp_exact_time_shots import ExactTimeShotSequence
        from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
        def png(color):
            source=BytesIO()
            Image.new("RGB",(2,2),color).save(source,format="PNG")
            return source.getvalue()
        self.assets.publish(
            self.pid,"hydra_pbr_actor",shape="mesh",size_m=2.,
            points=[[-1.,-1.,0.],[1.,-1.,0.],
                    [1.,1.,0.],[-1.,1.,0.]],
            triangles=[[0,1,2],[0,2,3]],
            mesh_uvs=[[0,0],[1,0],[1,1],[0,1]],
            preview_material={"base_color_rgb":[1.,1.,1.],
                              "roughness":.45,"metallic":.0},
            texture_png=png((160,130,100)),
            pbr_maps_png={
                "roughness":png((100,100,100)),
                "metallic":png((80,80,80)),
                "emission":png((20,20,50)),
                "normal":png((128,128,255)),
                "opacity":png((255,255,255)),
            })
        self.scene.publish(self.pid,"hydra_pbr_scene",
            prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Light","role":"light","position":[1,2,3]},
            ],curves=[],native_schemas=True,asset_bindings=[{
                "path":"/World/Actor",
                "asset_id":"hydra_pbr_actor","asset_revision":1}])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"hydra_pbr_timeline",
            scene_id="hydra_pbr_scene",scene_revision=1,
            duration_tick=str(T),
            shots=[{"shot_id":"hydra_reference",
                    "camera_path":"/World/Camera",
                    "start_tick":"0","end_tick":str(T),
                    "pattern":"continuous"}])
        take=self.takes.freeze(
            self.pid,"hydra_pbr_take",
            scene_id="hydra_pbr_scene",scene_revision=1,
            timeline_id="hydra_pbr_timeline",timeline_revision=1,
            sample_ticks=[0],creator_event="director_confirms")
        result=capture_hydra_evidence(
            self.index,self.pid,"hydra_pbr_scene",1,
            camera_path="/World/Camera",renderer="Embree",width=640,
            require_gpu=False,timeout_seconds=120,
            native_take={"take_id":"hydra_pbr_take",
                         "take_sha256":take["document_sha256"],
                         "tick":0})
        self.assertEqual(result["status"],"HYDRA_FRAME_RENDERED",result)
        self.assertTrue(result["real_independent_frame_rendered"])
        comparison=result.get("comparison")
        self.assertIsNotNone(comparison)
        self.assertEqual(comparison["format"],
                         "nvp.wo2.independent_renderer_image_comparison.v1")
        self.assertEqual(comparison["source_scene_sha256"],
                         result["scene_document_sha256"])
        self.assertFalse(comparison["scene_linear_hydra_parity_proven"])
        self.assertFalse(comparison["physical_display_calibrated"])
        print("WO2_FIVE_CHANNEL_HYDRA_COMPARISON:",comparison,flush=True)


if __name__=="__main__":
    unittest.main()
