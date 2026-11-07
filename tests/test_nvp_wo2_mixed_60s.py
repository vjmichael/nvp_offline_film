"""WO2 representative frozen source: real skin + five-channel PBR + lighting.

This runs 60 genuine CPU source frames over exact Film Time, not synthetic
frames and not installed GPU acceptance. It is deliberately separate from
the tiny cube continuity smoke and records the heavier source evidence.
"""
from io import BytesIO
from pathlib import Path
import json
import unittest

from PIL import Image
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_wo2_continuity import measure_native_frozen_take
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
import test_nvp_slate07_skinned_camera as fixture


def _png(color):
    buf=BytesIO()
    Image.new("RGB",(8,8),color).save(buf,format="PNG")
    return buf.getvalue()


class WO2RealMixedSixtySecondScene(unittest.TestCase):
    def setUp(self):
        fixture.RealCharacterAndLens.setUp(self)
        assets=OpenUSDAssetRegistry(self.index)
        self.asset=assets.publish(
            self.pid,"MixedPBRProp",shape="mesh",size_m=3.,
            points=[[-1.,-1.,0.],[1.,-1.,0.],
                    [1.,1.,0.],[-1.,1.,0.]],
            triangles=[[0,1,2],[0,2,3]],
            mesh_uvs=[[0,0],[1,0],[1,1],[0,1]],
            preview_material={"base_color_rgb":[.8,.7,.6],
                              "roughness":.4,"metallic":.1},
            texture_png=_png((190,130,70)),
            pbr_maps_png={
                "roughness":_png((120,120,120)),
                "metallic":_png((60,60,60)),
                "emission":_png((18,25,70)),
                "normal":_png((128,128,255)),
                "opacity":_png((255,255,255)),
            })
        self.scene.publish(
            self.pid,"mixed_60_world",
            prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Prop","role":"prop","position":[2,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,8]},
                {"path":"/World/Key","role":"light","position":[0,5,5]},
                {"path":"/World/Fill","role":"light","position":[-3,2,4]},
            ],
            curves=[{"path":"/World/Actor","samples":[
                {"tick":0,"position":[0,0,0]},
                {"tick":2*T,"position":[1,0,0]},
                {"tick":59*T,"position":[2,0,0]}]}],
            native_schemas=True,skeletal_rigs=self.rigs,
            asset_bindings=[{"path":"/World/Prop",
                             "asset_id":"MixedPBRProp","asset_revision":1}])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"mixed_60_shots",
            scene_id="mixed_60_world",scene_revision=1,
            duration_tick=str(60*T),
            shots=[{"shot_id":"mixed_camera",
                    "camera_path":"/World/Camera",
                    "start_tick":"0","end_tick":str(60*T),
                    "pattern":"continuous"}])
        self.take=self.takes.freeze(
            self.pid,"mixed_60_take",
            scene_id="mixed_60_world",scene_revision=1,
            timeline_id="mixed_60_shots",timeline_revision=1,
            sample_ticks=[0,T,2*T,30*T,59*T],
            creator_event="freeze_take")
        self.scene_sha=self.index.read_revision(
            self.pid,"mixed_60_world",1)["document_sha256"]

    def test_actual_skinned_and_textured_scene_continuity(self):
        native=NativeSceneLinearRaster(self.index)
        pixels,first=native.render(
            self.pid,"mixed_60_take",self.take["document_sha256"],
            tick=0,camera_path="/World/Camera")
        self.assertGreater(first["source_uv_texture_rasterized_triangles"],0)
        self.assertGreater(first["actual_usd_skinned_actors"],0)
        self.assertEqual(first["scene_document_sha256"],self.scene_sha)
        self.assertFalse(first["original_source_modified"]
                         if "original_source_modified" in first else
                         first["source_modified"])
        result=measure_native_frozen_take(
            self.index,self.pid,"mixed_60_take",
            self.take["document_sha256"],"/World/Camera",
            duration_seconds=60,sample_hz=1)
        self.assertEqual(result["status"],"COMPLETE")
        self.assertEqual(result["processed_frames"],60)
        self.assertTrue(result["real_source_rendering_proven"])
        self.assertTrue(result["within_memory_budget"])
        self.assertFalse(result["gpu_hardware_verified"])
        self.assertEqual(
            self.index.read_revision(self.pid,"mixed_60_world",1)[
                "document_sha256"],self.scene_sha)
        report={
            **result,
            "representative_original_usd_skinning":True,
            "representative_original_usd_material_channels":5,
            "representative_source_light_count":2,
            "source_scene_sha256":self.scene_sha,
            "source_pbr_asset_sha256":self.asset["document_sha256"],
            "actual_native_textured_triangles":
                first["source_uv_texture_rasterized_triangles"],
            "actual_native_skinned_actors":
                first["actual_usd_skinned_actors"],
            "physical_gpu_hardware_accepted":False,
        }
        Path("wo2-mixed-60s-receipt.json").write_text(
            json.dumps(report,sort_keys=True,indent=2)+"\n",
            encoding="utf-8")
        print("WO2_MIXED_60S_SOURCE_RECEIPT:",
              json.dumps(report,sort_keys=True),flush=True)


if __name__=="__main__":
    unittest.main()
