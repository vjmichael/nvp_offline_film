"""PLAN-02-D4 genuine native OpenUSD/PNG and approved rail regression.

No fake raster callback; real authored sphere source, real UsdGeom.Camera,
frozen Digital Take and actual Pillow-decoded derived PNG are independently
reopened. No Blender/Hydra cinematic quality or DCI acceptance claim.
"""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import unittest

from PIL import Image

import test_nvp_data_av_native as fixture
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_plan02c_rails import CanonicalSourceRails
from backend.nvp_plan02d_derived_raster import SourceSelectedNativeRaster
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge

T=fixture.T


class ActualSourceRasterTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDigitalTakeAudioTests.setUp(self)
        self.granted=True
        self.dialogs=[]
        self.renderer=SourceSelectedNativeRaster(
            self.index,ask_native=self._ask)
        asset=OpenUSDAssetRegistry(self.index).publish(
            self.pid,"RasterSphere",shape="sphere",size_m=1.5)
        scene=self.scene.publish(
            self.pid,"RasterWorld",prims=[
                {"path":"/World/RasterCam","role":"camera","position":[0,0,0]},
                {"path":"/World/RasterSphere","role":"prop","position":[0,3,0]},
            ],curves=[],native_schemas=True,asset_bindings=[
                {"path":"/World/RasterSphere","asset_id":"RasterSphere",
                 "asset_revision":asset["revision"]}])
        self.plan=ExactTimeShotSequence(self.index).publish(
            self.pid,"RasterCuts",scene_id="RasterWorld",scene_revision=1,
            duration_tick=str(2*T),shots=[{
                "shot_id":"RasterShot","camera_path":"/World/RasterCam",
                "start_tick":"0","end_tick":str(2*T),"pattern":"continuous"}])
        frozen=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
                event=="fresh_raster_freeze").freeze(
            self.pid,"RasterTake",scene_id="RasterWorld",scene_revision=1,
            timeline_id="RasterCuts",timeline_revision=1,
            sample_ticks=[0,T],creator_event="fresh_raster_freeze")
        self.take_sha=frozen["document_sha256"]
        self.request={
            "take_id":"RasterTake","take_document_sha256":self.take_sha,
            "camera_timeline_id":"RasterCuts","camera_timeline_revision":1,
            "camera_timeline_sha256":self.plan["document_sha256"],
            "first_tick":0,"last_tick_exclusive":T,
            "camera_mode":"original","rail_id":None,"rail_revision":None,
            "rail_document_sha256":None,
        }

    def _ask(self,scope):
        self.dialogs.append(scope)
        return self.granted

    def test_original_camera_produces_actual_png_and_distinct_review(self):
        preview=self.renderer.selector.preview(self.pid,self.request)
        one=self.renderer.preview(
            self.pid,self.request,preview["selection_sha256"],T//3)
        with Image.open(BytesIO(one["png_bytes"])) as image:
            self.assertEqual(image.size,(640,360))
            self.assertEqual(image.format,"PNG")
        self.assertFalse(one["ffmpeg_used"])
        self.assertEqual(self.dialogs,[])
        denied=self.granted
        self.granted=False
        with self.assertRaises(PermissionError):
            self.renderer.publish(
                self.pid,"RasterDenied",self.request,
                preview["selection_sha256"],T//3,one["png_sha256"])
        self.granted=denied
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"RasterDenied",1)
        saved=self.renderer.publish(
            self.pid,"RasterOriginal",self.request,
            preview["selection_sha256"],T//3,one["png_sha256"])
        self.assertEqual(saved["status"],"VERIFIED_DERIVED_OPENUSD_PNG")
        self.assertFalse(saved["cinema_master_accepted"])
        with self.assertRaises(RuntimeError):
            self.renderer.publish(
                self.pid,"RasterOriginal",self.request,
                preview["selection_sha256"],T//3,one["png_sha256"])
        self.assertEqual(self.index.read_revision(
            self.pid,"RasterTake",1)["document_sha256"],self.take_sha)
        self.assertEqual(self.sound.read(
            self.pid,"mic_signal",1,0,128),self.original[:256])

    def test_approved_director_rail_changes_real_png_without_changing_take(self):
        from test_nvp_data_av_native import Window
        bridge=TrustedDesktopCameraBridge(
            self.index,origin="http://127.0.0.1:7777")
        bridge._attach_window(Window())
        self.addCleanup(bridge._close)
        chosen=next(row for row in bridge.plan02c_catalog(self.pid)["sources"]
                    if row["source_take_id"]=="RasterTake")
        rail_spec=deepcopy(chosen["suggested_unapproved_rail_spec"])
        rail_spec["camera_id"]="RasterDirectorCam"
        rail_spec["technique"]="dolly"
        rail_spec["nodes"][0]["target_m"]=[0.,3.,0.]
        rail_spec["nodes"][1]["target_m"]=[0.,3.,0.]
        rail_spec["nodes"][1]["position_m"]=[0.5,0.,0.]
        rails=CanonicalSourceRails(self.index,approve=lambda scope:True)
        trial=rails.preview(self.pid,"RasterDirector",rail_spec,expected_revision=0)
        published=rails.publish(
            self.pid,"RasterDirector",rail_spec,0,trial["proposal_sha256"])
        original=self.renderer.selector.preview(self.pid,self.request)
        a=self.renderer.preview(
            self.pid,self.request,original["selection_sha256"],T//3)
        approved={**self.request,
            "camera_mode":"approved_rail",
            "rail_id":"RasterDirector",
            "rail_revision":published["revision"],
            "rail_document_sha256":published["rail_document_sha256"]}
        selected=self.renderer.selector.preview(self.pid,approved)
        b=self.renderer.preview(
            self.pid,approved,selected["selection_sha256"],T//3)
        self.assertNotEqual(a["png_sha256"],b["png_sha256"])
        with Image.open(BytesIO(b["png_bytes"])) as image:
            self.assertIsNotNone(image.getbbox())
        saved=self.renderer.publish(
            self.pid,"RasterRailImage",approved,
            selected["selection_sha256"],T//3,b["png_sha256"])
        receipt=self.index.read_revision(self.pid,"RasterRailImage",1)
        self.assertEqual(len(receipt["dependencies"]),3)
        self.assertEqual(saved["source_take_sha256"],self.take_sha)
        self.assertFalse(saved["source_modified"])
        self.assertEqual(self.index.read_revision(
            self.pid,"RasterTake",1)["document_sha256"],self.take_sha)
        stale=deepcopy(approved)
        stale["rail_document_sha256"]="0"*64
        with self.assertRaises(PermissionError):
            self.renderer.preview(
                self.pid,stale,selected["selection_sha256"],T//3)


if __name__=="__main__":
    unittest.main()
