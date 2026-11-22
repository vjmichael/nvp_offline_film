"""CONV-01/06: original bounded static USD mesh in active DataAV view model.

This checks source-authentic asset reopening and denial of forged bindings.
No original actor facial/skin, PNG upload, rendering or film-master approval.
"""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_data_av_visual import visual_state

MATRIX=[[1.,0.,0.,0.],[0.,1.,0.,0.],
        [0.,0.,1.,0.],[0.,0.,0.,1.]]


class OriginalStaticMeshView(unittest.TestCase):
    def test_real_original_usd_mesh_readback_and_forged_layer_refusal(self):
        with TemporaryDirectory(prefix="nvp-conv06-original-visual-") as d:
            studio=Studio(Path(d)/"film.sqlite3")
            pid=studio.create_project(
                "Verified original static mesh view",
                "Source-only mesh; no real render")["id"]
            index=FilmIndex(studio)
            assets=OpenUSDAssetRegistry(index)
            assets.publish(pid,"OriginalMesh",shape="mesh",size_m=2,
                points=[[-1.,-1.,0.],[1.,-1.,0.],
                        [1.,1.,0.],[-1.,1.,0.]],
                triangles=[[0,1,2],[0,2,3]],
                mesh_uvs=[[0,0],[1,0],[1,1],[0,1]],
                preview_material={
                    "base_color_rgb":[.1,.3,.5],
                    "roughness":.6,"metallic":0.0})
            original,_=assets.open(pid,"OriginalMesh",1)
            binding={
                "asset_id":"OriginalMesh","asset_revision":1,
                "asset_document_sha256":original["document_sha256"],
                "asset_layer_sha256":original["data"]["layer_sha256"]}
            obj={
                "path":"/World/OriginalMesh","semantic_role":"prop",
                "world_matrix":MATRIX,
                "world_translation":[0.,0.,0.],
                "asset":binding}
            snapshot={
                "time_tick":0,
                "scene_document_sha256":"a"*64,
                "timeline_document_sha256":"b"*64,
                "objects":[obj]}
            result=visual_state(index,pid,snapshot)
            self.assertEqual(result["format"],
                "nvp.data_av.native_visual_state.v1")
            view=result["objects"][0]
            self.assertEqual(view["shape"],"mesh")
            self.assertEqual(view["mesh_points"],original["data"]["points"])
            self.assertEqual(view["mesh_triangles"],[[0,1,2],[0,2,3]])
            self.assertEqual(view["mesh_uvs"],[[0,0],[1,0],[1,1],[0,1]])
            self.assertTrue(view["source_mesh_reopened"])
            self.assertFalse(view["gizmo_only"])
            self.assertFalse(view["source_texture_pixels_exposed"])
            self.assertFalse(view["source_skinning_authorized"])
            self.assertFalse(result["image_samples_rendered"])
            forged={**snapshot,"objects":[{
                **obj,"asset":{**binding,"asset_layer_sha256":"f"*64}}]}
            with self.assertRaises(RuntimeError):
                visual_state(index,pid,forged)


if __name__=="__main__":
    unittest.main()
