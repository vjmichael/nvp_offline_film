"""CONV-01/06: original PNG source admission via exact trusted WebView + OS picker.

This is a real FilmIndex, original USD 3D mesh and decoded source PNG test.
The test-only native dialog is not evidence of installed Windows/EFS OS custody.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import sys
import unittest

from PIL import Image

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_native_usd_texture import verified_texture


class OriginalNativeWindow:
    def __init__(self,png_path):
        self.url="http://127.0.0.1:19991/"
        self.png_path=png_path
        self.approved=True
        self.picks=0
        self.dialogs=0
        self.last_prompt=None

    def get_current_url(self):
        return self.url

    def create_file_dialog(self,*args,**kwargs):
        self.picks+=1
        return (str(self.png_path),)

    def create_confirmation_dialog(self,title,description):
        self.dialogs+=1
        self.last_prompt=description
        return self.approved


class OriginalUVTextureNativeImport(unittest.TestCase):
    def setUp(self):
        self.work=TemporaryDirectory(prefix="nvp-conv06-wo2-native-")
        self.addCleanup(self.work.cleanup)
        root=Path(self.work.name)
        studio=Studio(root/"film.sqlite3")
        self.pid=studio.create_project("Native original PNG source","")["id"]
        self.index=FilmIndex(studio)
        self.assets=OpenUSDAssetRegistry(self.index)
        self.name="OriginalMappedAsset"
        self.original=self.assets.publish(
            self.pid,self.name,shape="mesh",size_m=2.,
            points=[[-1.,-1.,0.],[1.,-1.,0.],
                    [1.,1.,0.],[-1.,1.,0.]],
            triangles=[[0,1,2],[0,2,3]],
            mesh_uvs=[[0,0],[1,0],[1,1],[0,1]],
            preview_material={
                "base_color_rgb":[.3,.6,.8],
                "roughness":.4,"metallic":0.1})
        picture=Image.new("RGB",(32,16),(20,110,210))
        buf=BytesIO()
        picture.save(buf,format="PNG")
        self.png=buf.getvalue()
        self.selected=root/"original-selected.png"
        self.selected.write_bytes(self.png)
        self.window=OriginalNativeWindow(self.selected)
        self.bridge=object.__new__(TrustedDesktopCameraBridge)
        self.bridge.index=self.index
        self.bridge.origin="http://127.0.0.1:19991"
        self.bridge.window=self.window
        self.bridge._closing=False
        self.bridge._project_lock_check=lambda:False
        self.request={
            "project_id":self.pid,"asset_id":self.name,
            "source_revision":1,
            "source_document_sha256":self.original["document_sha256"]}

    def import_original(self,request=None):
        # The installed host normally supplies webview.FileDialog.
        # No browser-supplied string or external file URL is accepted.
        fake=SimpleNamespace(FileDialog=SimpleNamespace(OPEN="native_open"))
        with patch.dict(sys.modules,{"webview":fake}):
            return self.bridge.data_av_import_original_mesh_texture(
                self.request if request is None else request)

    def test_real_uv_mesh_png_revises_source_without_rewriting_original(self):
        available=self.bridge.film01c_texture_catalog(self.pid)
        self.assertEqual(available["original_uv_meshes"],[{
            "asset_id":self.name,"revision":1,
            "document_sha256":self.original["document_sha256"]}])
        self.assertFalse(available["original_png_bytes_exposed"])
        result=self.import_original()
        self.assertEqual(result["status"],"ORIGINAL_SOURCE_TEXTURE_BOUND")
        self.assertEqual(result["format"],"nvp.wo2.native_original_texture_import.v1")
        self.assertTrue(result["native_source_reopened"])
        self.assertFalse(result["original_modified"])
        self.assertFalse(result["film_master_approved"])
        self.assertEqual(result["source_revision"],1)
        self.assertEqual(result["revision"],2)
        self.assertEqual(result["original_png_sha256"],sha256(self.png).hexdigest())
        self.assertEqual(self.window.picks,1)
        self.assertEqual(self.window.dialogs,1)
        self.assertIn(self.original["document_sha256"],self.window.last_prompt)
        self.assertIn(result["original_png_sha256"],self.window.last_prompt)
        old,_=self.assets.open(self.pid,self.name,1)
        current,_=self.assets.open(self.pid,self.name,2)
        self.assertEqual(old["document_sha256"],self.original["document_sha256"])
        self.assertNotIn("texture",old["data"]["preview_material"])
        self.assertEqual(current["document_sha256"],result["document_sha256"])
        self.assertEqual(current["data"]["points"],old["data"]["points"])
        self.assertEqual(current["data"]["triangles"],old["data"]["triangles"])
        self.assertEqual(current["data"]["mesh_uvs"],old["data"]["mesh_uvs"])
        descriptor=current["data"]["preview_material"]["texture"]
        self.assertEqual(verified_texture(self.index,self.pid,descriptor)[0],self.png)
        updated=self.bridge.film01c_texture_catalog(self.pid)
        self.assertEqual(updated["original_uv_meshes"],[])
        self.assertEqual(updated["sources"][0]["source_id"],self.name)
        self.assertEqual(updated["sources"][0]["revision"],2)
        self.assertEqual(updated["sources"][0]["png_sha256"],
                         [result["original_png_sha256"]])
        self.assertFalse(updated["external_texture_paths_allowed"])

    def test_independent_native_roughness_approval_reopens_both_original_pngs(self):
        base=self.import_original()
        self.assertEqual(base["revision"],2)
        source=self.index.read_revision(self.pid,self.name,2)
        roughness=Image.new("RGB",(32,16),(90,90,90))
        output=BytesIO()
        roughness.save(output,format="PNG")
        original_map=output.getvalue()
        file=Path(self.work.name)/"separately-selected-roughness.png"
        file.write_bytes(original_map)
        self.window.png_path=file
        self.window.dialogs=0
        request={
            "project_id":self.pid,"asset_id":self.name,
            "source_revision":2,
            "source_document_sha256":source["document_sha256"]}
        with patch.dict(sys.modules,{"webview":SimpleNamespace(
                FileDialog=SimpleNamespace(OPEN="native_original_roughness"))}):
            accepted=self.bridge.data_av_import_original_mesh_roughness(request)
        self.assertEqual(accepted["format"],
            "nvp.wo2.native_original_roughness_import.v1")
        self.assertEqual(accepted["status"],"ORIGINAL_ROUGHNESS_SOURCE_BOUND")
        self.assertEqual(accepted["revision"],3)
        self.assertFalse(accepted["film_master_approved"])
        self.assertEqual(accepted["original_base_png_sha256"],
                         sha256(self.png).hexdigest())
        self.assertEqual(accepted["original_roughness_png_sha256"],
                         sha256(original_map).hexdigest())
        self.assertEqual(self.window.dialogs,1)
        self.assertIn(source["document_sha256"],self.window.last_prompt)
        old,_=self.assets.open(self.pid,self.name,1)
        textured,_=self.assets.open(self.pid,self.name,2)
        revised,stage=self.assets.open(self.pid,self.name,3)
        self.assertNotIn("texture",old["data"]["preview_material"])
        self.assertNotIn("pbr_maps",textured["data"]["preview_material"])
        self.assertEqual(revised["data"]["points"],old["data"]["points"])
        self.assertEqual(revised["data"]["mesh_uvs"],old["data"]["mesh_uvs"])
        self.assertEqual(
            revised["data"]["preview_material"]["texture"],
            textured["data"]["preview_material"]["texture"])
        self.assertEqual(
            revised["data"]["preview_material"]["pbr_maps"]["roughness"]["sha256"],
            sha256(original_map).hexdigest())
        from pxr import UsdShade,Usd
        shader=UsdShade.Shader(Usd.Stage.Open(stage).GetPrimAtPath(
            "/Asset/Material/MtlxMap_Roughness"))
        self.assertTrue(shader)
        self.assertEqual(str(shader.GetInput("file").GetAttr().Get().path),
                         "nvp-blob://texture/"+sha256(original_map).hexdigest())

    def test_roughness_denial_invalid_pixels_and_browser_path_refused(self):
        base=self.import_original()
        src=self.index.read_revision(self.pid,self.name,2)
        request={"project_id":self.pid,"asset_id":self.name,
                 "source_revision":2,
                 "source_document_sha256":src["document_sha256"]}
        self.window.approved=False
        fake=SimpleNamespace(FileDialog=SimpleNamespace(OPEN="native"))
        with patch.dict(sys.modules,{"webview":fake}):
            refused=self.bridge.data_av_import_original_mesh_roughness(request)
        self.assertEqual(refused["status"],"NATIVE_DENIED")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,self.name,3)
        self.window.approved=True
        for bad in (
            {**request,"source_png_path":str(self.selected)},
            {**request,"creator_approved":True},
            {**request,"source_document_sha256":"f"*64}):
            with self.subTest(bad=bad):
                with patch.dict(sys.modules,{"webview":fake}):
                    with self.assertRaises((PermissionError,ValueError,RuntimeError)):
                        self.bridge.data_av_import_original_mesh_roughness(bad)
        self.window.url="https://hostile.example/"
        with patch.dict(sys.modules,{"webview":fake}):
            with self.assertRaisesRegex(PermissionError,"origin"):
                self.bridge.data_av_import_original_mesh_roughness(request)
        self.window.url="http://127.0.0.1:19991/"
        # The base-color RGB image is not an authentic scalar roughness map.
        # Reject before prompting the director and before new FilmIndex blobs.
        dialogs_before=self.window.dialogs
        with patch.dict(sys.modules,{"webview":fake}):
            with self.assertRaises(ValueError):
                self.bridge.data_av_import_original_mesh_roughness(request)
        self.assertEqual(self.window.dialogs,dialogs_before)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,self.name,3)

    def test_denied_or_cancelled_picker_cannot_create_texture_asset_revision(self):
        self.window.approved=False
        denied=self.import_original()
        self.assertEqual(denied["status"],"NATIVE_DENIED")
        self.assertFalse(denied["original_modified"])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,self.name,2)
        self.window.create_file_dialog=lambda *_args,**_kwargs:()
        cancelled=self.import_original()
        self.assertEqual(cancelled["status"],"CANCELLED")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,self.name,2)

    def test_browser_path_and_grant_spoofs_do_not_open_native_file(self):
        for hostile in (
            {**self.request,"texture_path":str(self.selected)},
            {**self.request,"png_base64":"unverified"},
            {**self.request,"creator_approved":True},
            {**self.request,"source_document_sha256":"f"*64}):
            with self.subTest(hostile=hostile):
                with self.assertRaises((PermissionError,ValueError,RuntimeError)):
                    self.import_original(hostile)
        self.assertEqual(self.window.dialogs,0)
        self.window.url="https://attacker.example/"
        with self.assertRaisesRegex(PermissionError,"origin"):
            self.import_original()
        self.window.url="http://127.0.0.1:19991/"
        self.bridge._project_lock_check=lambda:True
        with self.assertRaisesRegex(PermissionError,"protected"):
            self.import_original()
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,self.name,2)

    def test_native_symlink_and_generic_unreviewed_png_are_rejected(self):
        with self.assertRaises(PermissionError):
            self.assets.publish(
                self.pid,"UnreviewedTex",shape="mesh",size_m=2.,
                points=[[-1,-1,0],[1,-1,0],[0,1,0]],
                triangles=[[0,1,2]],
                mesh_uvs=[[0,0],[1,0],[0,1]],
                preview_material={
                    "base_color_rgb":[1,1,1],
                    "roughness":.5,"metallic":0},
                texture_png=self.png)
        link=Path(self.work.name)/"symlink.png"
        try:
            link.symlink_to(self.selected)
        except (OSError,NotImplementedError):
            return
        self.window.png_path=link
        with self.assertRaisesRegex(PermissionError,"unsafe path"):
            self.import_original()
        self.assertEqual(self.window.dialogs,0)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,self.name,2)


if __name__=="__main__":
    unittest.main()
