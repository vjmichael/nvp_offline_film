"""WO2 source texture tile reads are scoped to an approved frozen Take."""
import unittest
from io import BytesIO
from PIL import Image
import test_nvp_openusd_reusable_assets as fixture

from backend.nvp_data_av_desktop import TrustedDataAVController
from backend.nvp_exact_time_shots import ExactTimeShotSequence


class WO2OriginalTileAuthority(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        picture=Image.new("RGB",(512,257),(20,120,220))
        buf=BytesIO()
        picture.save(buf,format="PNG")
        self.asset=self.assets.publish(
            self.pid,"original_tile_mesh",shape="mesh",size_m=2.,
            points=[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],
            triangles=[[0,1,2],[0,2,3]],
            mesh_uvs=[[0,0],[1,0],[1,1],[0,1]],
            preview_material={"base_color_rgb":[1,1,1],
                              "roughness":.5,"metallic":0},
            texture_png=buf.getvalue())
        self.descriptor=self.assets.open(self.pid,"original_tile_mesh",1)[0][
            "data"]["preview_material"]["texture"]
        self.scene.publish(self.pid,"tile_scene",prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,0,5]},
        ],curves=[],native_schemas=True,asset_bindings=[
            {"path":"/World/Actor","asset_id":"original_tile_mesh",
             "asset_revision":1}])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"tile_shots",scene_id="tile_scene",
            scene_revision=1,duration_tick=str(fixture.T),
            shots=[{"shot_id":"tile","camera_path":"/World/Camera",
                    "start_tick":"0","end_tick":str(fixture.T),
                    "pattern":"continuous"}])
        self.take=self.takes.freeze(
            self.pid,"tile_take",scene_id="tile_scene",
            scene_revision=1,timeline_id="tile_shots",
            timeline_revision=1,sample_ticks=[0],
            creator_event="director_confirms")
        self.controller=TrustedDataAVController(
            self.index,native_window=lambda:None,ask_native=lambda _:True)
        self.addCleanup(self.controller.close)
        self.request={
            "asset_id":"original_tile_mesh","asset_revision":1,
            "asset_document_sha256":self.asset["document_sha256"],
            "texture_sha256":self.descriptor["sha256"],
            "mip_level":0,"tile_x":1,"tile_y":1,
        }

    def _begin(self):
        result=self.controller.begin({
            "project_id":self.pid,"take_id":"tile_take",
            "take_document_sha256":self.take["document_sha256"],
            "listener_path":"/World/Camera",
            "first_sample":0,"direction":"forward"})
        self.assertEqual(result["status"],"READY")
        return result["session_id"]

    def test_tile_requires_same_live_approved_take_and_exact_asset(self):
        with self.assertRaises(PermissionError):
            self.controller.read_original_texture_tile("untrusted",
                                                      self.request)
        ticket=self._begin()
        tile=self.controller.read_original_texture_tile(ticket,self.request)
        self.assertEqual(tile["source_sha256"],self.descriptor["sha256"])
        self.assertEqual(tile["asset_document_sha256"],
                         self.asset["document_sha256"])
        self.assertEqual(tile["take_document_sha256"],
                         self.take["document_sha256"])
        self.assertEqual((tile["tile_width"],tile["tile_height"]),(256,1))
        for modified in (
            {**self.request,"texture_sha256":"0"*64},
            {**self.request,"asset_document_sha256":"0"*64},
            {**self.request,"asset_revision":2},
        ):
            with self.subTest(modified=modified):
                with self.assertRaises((PermissionError,ValueError)):
                    self.controller.read_original_texture_tile(
                        ticket,modified)
        self.controller.stop(ticket)
        with self.assertRaises(PermissionError):
            self.controller.read_original_texture_tile(ticket,self.request)

    def test_repeated_tiles_reuse_native_session_verified_image(self):
        from unittest.mock import patch
        from backend.nvp_native_usd_texture import verified_texture
        ticket=self._begin()
        with patch(
            "backend.nvp_native_usd_texture.verified_texture",
            wraps=verified_texture) as checks:
            first=self.controller.read_original_texture_tile(
                ticket,{**self.request,"tile_x":0,"tile_y":0})
            first_reads=checks.call_count
            second=self.controller.read_original_texture_tile(
                ticket,self.request)
            self.assertEqual(checks.call_count,first_reads)
            self.assertGreaterEqual(first_reads,1)
        self.assertNotEqual(first["tile_sha256"],second["tile_sha256"])
        self.controller.stop(ticket)
        self.assertIsNone(self.controller._active)

    def test_imported_but_unbound_texture_cannot_be_streamed(self):
        ticket=self._begin()
        other=self.assets.publish(
            self.pid,"unbound_tile_mesh",shape="mesh",size_m=2.,
            points=[[-1,-1,0],[1,-1,0],[0,1,0]],
            triangles=[[0,1,2]],
            mesh_uvs=[[0,0],[1,0],[0,1]],
            preview_material={"base_color_rgb":[1,1,1],
                              "roughness":.5,"metallic":0})
        request={**self.request,"asset_id":"unbound_tile_mesh",
                 "asset_document_sha256":other["document_sha256"]}
        with self.assertRaises(PermissionError):
            self.controller.read_original_texture_tile(ticket,request)


if __name__=="__main__":
    unittest.main()
