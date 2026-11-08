"""Required REAL Hydra color-response test: no renderer -> test FAILURE.

The untrusted renderer is NEVER mocked; genuine first-party immutable
FilmIndex PNGs, native OpenUSD geometry, camera and light are used. The
result proves only relative sRGB-like texture response through the renderer's
USD PreviewSurface fallback, not physical OpenPBR/MaterialX pixel parity.
"""
import json
import os
from io import BytesIO
from pathlib import Path
import unittest

from PIL import Image

import test_nvp_openusd_reusable_assets as fixture
from backend.nvp_wo2_hydra_probe import capture_hydra_evidence
from backend.nvp_wo3_hydra_color_fidelity import (
    verify_relative_hydra_swatch_response)


class RequiredRealHydraTextureColor(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)

    @staticmethod
    def png(rgb):
        dst=BytesIO()
        Image.new("RGB",(8,8),rgb).save(dst,format="PNG")
        return dst.getvalue()

    def render_swatch(self,name,rgb,*,material_context_probe):
        aid="wo3_color_"+name
        sid="wo3_color_scene_"+name
        self.assets.publish(
            self.pid,aid,shape="mesh",size_m=2.,
            points=[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],
            triangles=[[0,1,2],[0,2,3]],
            mesh_uvs=[[0,0],[1,0],[1,1],[0,1]],
            preview_material={"base_color_rgb":[1.,1.,1.],
                              "roughness":.5,"metallic":0.},
            texture_png=self.png(rgb),
            pbr_maps_png={
                "roughness":self.png((100,100,100)),
                "metallic":self.png((0,0,0)),
                "emission":self.png((7,9,11)),
                "normal":self.png((128,128,255)),
                "opacity":self.png((255,255,255)),
            })
        record,_=self.assets.open(self.pid,aid,1)
        self.assertEqual(record["data"]["preview_material"]["texture"]
                         ["color_space"],"sRGB")
        self.scene.publish(
            self.pid,sid,prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Light","role":"light","position":[1,2,3]},
            ],curves=[],native_schemas=True,
            asset_bindings=[{"path":"/World/Actor",
                             "asset_id":aid,"asset_revision":1}])
        scene,_=self.scene.open(self.pid,sid,1)
        observed=capture_hydra_evidence(
            self.index,self.pid,sid,1,camera_path="/World/Camera",
            renderer="Storm",width=320,timeout_seconds=150,
            require_gpu=True,material_context_probe=material_context_probe)
        self.assertEqual(observed["status"],"HYDRA_FRAME_RENDERED",
                         "REAL usdrecord/Storm unavailable or failed: "
                         +str(observed))
        self.assertEqual(
            observed["scene_document_sha256"],scene["document_sha256"])
        self.assertEqual(
            len(observed["approved_texture_sha256"]),6)
        self.assertFalse(observed["hydra_shader_parity_accepted"])
        self.assertFalse(observed["physical_display_calibrated"])
        self.assertEqual(observed["material_context_probe"],material_context_probe)
        return observed

    def test_real_hydra_dual_and_isolated_materialx_source_color_response(self):
        # Four genuine USD/Hydra render subprocesses (no mocked pixels).
        # Context-isolated runs remove all universal PreviewSurface fallbacks
        # *on a disposable stage only* before executing Storm.
        measured={}
        for context in ("dual","mtlx_only"):
            with self.subTest(material_context=context):
                red=self.render_swatch("red_"+context,(240,20,20),
                    material_context_probe=context)
                blue=self.render_swatch("blue_"+context,(20,20,240),
                    material_context_probe=context)
                receipt=verify_relative_hydra_swatch_response(
                    red,blue,required_context=context)
                self.assertTrue(receipt["actual_independent_hydra_pixels_verified"])
                self.assertEqual(receipt["material_context_probe"],context)
                self.assertFalse(receipt["materialx_openpbr_shading_parity_verified"])
                self.assertFalse(receipt["absolute_reference_color_accuracy_verified"])
                self.assertFalse(receipt["theatrical_color_accepted"])
                measured[context]=receipt
        self.assertTrue(
            measured["mtlx_only"]["materialx_only_relative_color_response_verified"])
        self.assertTrue(
            measured["dual"]["dual_context_relative_color_response_verified"])
        receipt={
            "status":"HYDRA_DUAL_AND_ISOLATED_MTLX_COLOR_RESPONSES_MEASURED",
            "workflow_commit_sha":os.environ.get("GITHUB_SHA"),
            "relative_color_measurements":measured,
            "materialx_openpbr_shading_parity_verified":False,
            "absolute_reference_color_accuracy_verified":False,
            "theatrical_color_accepted":False,
        }
        output=Path("wo3-hydra-color-evidence.json")
        output.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\\n",
                          encoding="utf-8")
        print("WO3_REAL_HYDRA_COLOR_RECEIPT:",
              json.dumps(receipt,sort_keys=True),flush=True)


if __name__=="__main__":
    unittest.main()
