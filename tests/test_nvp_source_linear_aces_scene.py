"""DA-06D actual native USD scene -> FLOAT32 -> OCIO ACES2 acceptance.

The test freezes a real USD scene/camera/lights/geometry at Film Time,
executes the independent Z-buffer in linear float, applies a saved creative
decision with pinned ACES2, checks 16-bit PNG, and proves original-source
SHA is unchanged. No fake 8-bit PNG offered as scene-linear input.
"""
import hashlib
import unittest
from io import BytesIO

import numpy as np
from PIL import Image
import test_nvp_openusd_reusable_assets as fixture

from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster
from backend.nvp_native_color_decisions import NativeColorDecisions
from backend.nvp_native_aces_color import NativeACESColor,policy
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge

T=fixture.T
DEFAULTS={
    "exposure_stops":0.2,"contrast":1.0,
    "saturation":1.0,"temperature_kelvin":6500,
    "tint_magenta_green":0,
}


class NativeSourceLinearACESAcceptance(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        self.scene.publish(
            self.pid,"source_color_world",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Key","role":"light","position":[1,2,3]},
            ],curves=[],native_schemas=True,asset_bindings=[{
                "path":"/World/Actor","asset_id":"body_geometry",
                "asset_revision":1,
            }])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"source_color_shots",scene_id="source_color_world",
            scene_revision=1,duration_tick=str(T),shots=[{
                "shot_id":"ColorTakeShot",
                "camera_path":"/World/Camera","pattern":"continuous",
                "start_tick":"0","end_tick":str(T),
            }])
        self.take=self.takes.freeze(
            self.pid,"SourceColorTake",scene_id="source_color_world",
            scene_revision=1,timeline_id="source_color_shots",
            timeline_revision=1,sample_ticks=[0,T//2],
            creator_event="director_confirms")
        self.grade=NativeColorDecisions(self.index).publish(
            self.pid,"SourceColor001",
            take_id="SourceColorTake",
            take_sha256=self.take["document_sha256"],
            parameters=DEFAULTS)
        self.policy,_=policy()
        self.raster=NativeSceneLinearRaster(self.index)

    def render(self,tick=0):
        return self.raster.render(
            self.pid,"SourceColorTake",self.take["document_sha256"],
            tick=tick,camera_path="/World/Camera")

    def test_original_usd_scene_produces_real_float_radiance_and_source_audit(self):
        original_sha=self.index.read_revision(
            self.pid,"source_color_world",1)["document_sha256"]
        pixels,receipt=self.render(0)
        self.assertEqual(pixels.dtype,np.float32)
        self.assertEqual(pixels.shape,(360,640,4))
        self.assertEqual(float(pixels[:,:,3].min()),1.0)
        self.assertTrue(np.isfinite(pixels).all())
        self.assertGreater(receipt["rasterized_triangles"],0)
        self.assertGreater(receipt["source_geometry_triangles"],0)
        self.assertEqual(receipt["original_usd_sphere_lights"],1)
        self.assertGreater(float(pixels[:,:,:3].max()),0)
        self.assertEqual(receipt["source_working_space"],
                         "Linear Rec.709 (sRGB)")
        self.assertFalse(receipt["source_color_appearance_calibrated"])
        self.assertFalse(receipt["master_approved"])
        self.assertEqual(
            receipt["scene_linear_rgba_sha256"],
            hashlib.sha256(pixels.tobytes()).hexdigest())
        self.assertEqual(self.index.read_revision(
            self.pid,"source_color_world",1)["document_sha256"],original_sha)
        later,other=self.render(T//2)
        self.assertEqual(later.shape,pixels.shape)
        self.assertEqual(other["time_tick"],str(T//2))
        np.testing.assert_array_equal(pixels,self.render(0)[0])

    def test_original_source_to_native_aces16_is_bound_to_grade_and_config(self):
        take_sha=self.take["document_sha256"]
        before=self.index.read_revision(
            self.pid,"body_geometry",1)["document_sha256"]
        png,receipt=NativeACESColor(self.index).process_verified_usd_scene(
            self.pid,"SourceColorTake",take_sha,
            "SourceColor001",1,self.grade["document_sha256"],
            tick=0,camera_path="/World/Camera",
            expected_config_sha256=self.policy["configuration_sha256"])
        self.assertEqual(receipt["status"],
            "VERIFIED_SOURCE_UNMASTERED_ACES2_SDR_DERIVATIVE")
        self.assertEqual(receipt["bit_depth"],16)
        self.assertEqual(png[24],16)
        self.assertEqual(png[25],2)
        self.assertEqual(receipt["scene_linear_source"]["original_take_sha256"],
                         take_sha)
        self.assertEqual(receipt["scene_linear_source"][
            "scene_linear_rgba_sha256"],receipt["declared_source_rgb_sha256"])
        self.assertEqual(receipt["png16_sha256"],hashlib.sha256(png).hexdigest())
        with Image.open(BytesIO(png)) as image:
            self.assertEqual(image.size,(640,360))
        self.assertEqual(self.index.read_revision(
            self.pid,"body_geometry",1)["document_sha256"],before)
        self.assertEqual(self.index.read_revision(
            self.pid,"SourceColorTake",1)["document_sha256"],take_sha)
        self.assertFalse(receipt["cinema_master_approved"])

    def test_invalid_original_take_camera_and_config_rejected(self):
        with self.assertRaises(RuntimeError):
            self.raster.render(
                self.pid,"SourceColorTake","f"*64,
                tick=0,camera_path="/World/Camera")
        with self.assertRaises(RuntimeError):
            self.raster.render(
                self.pid,"SourceColorTake",self.take["document_sha256"],
                tick=0,camera_path="/World/Actor")
        with self.assertRaises(RuntimeError):
            NativeACESColor(self.index).process_verified_usd_scene(
                self.pid,"SourceColorTake",self.take["document_sha256"],
                "SourceColor001",1,self.grade["document_sha256"],
                tick=0,camera_path="/World/Camera",
                expected_config_sha256="f"*64)

    def test_creator_approved_native_aces_source_preview_only(self):
        class Window:
            def __init__(self):self.questions=[];self.allow=True
            def get_current_url(self):return "http://127.0.0.1:7777/"
            def create_confirmation_dialog(self,title,message):
                self.questions.append(message);return self.allow
        window=Window()
        bridge=TrustedDesktopCameraBridge(
            self.index,origin="http://127.0.0.1:7777")
        bridge._attach_window(window)
        self.addCleanup(bridge._close)
        request={
            "project_id":self.pid,
            "take_id":"SourceColorTake",
            "take_sha256":self.take["document_sha256"],
            "grade_id":"SourceColor001",
            "grade_revision":1,
            "grade_sha256":self.grade["document_sha256"],
            "film_time_tick":0,
            "expected_config_sha256":self.policy["configuration_sha256"],
        }
        window.allow=False
        with self.assertRaises(PermissionError):
            bridge.data_av_native_aces_review(request)
        window.allow=True
        preview=bridge.data_av_native_aces_review(request)
        self.assertEqual(preview["output_mime"],"image/png")
        self.assertFalse(preview["saved_picture_files"])
        self.assertEqual(preview["original_camera_path"],"/World/Camera")
        self.assertFalse(preview["original_modified"])
        self.assertIn(self.grade["document_sha256"],window.questions[-1])
        self.assertIn(self.policy["configuration_sha256"],window.questions[-1])
        with self.assertRaises(RuntimeError):
            bridge.data_av_native_aces_review(
                {**request,"film_time_tick":T+1})


if __name__=="__main__":
    unittest.main()
