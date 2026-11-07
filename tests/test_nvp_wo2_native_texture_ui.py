"""WO2 native desktop texture picker and source revision acceptance."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
import test_nvp_openusd_reusable_assets as fixture

from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_native_usd_texture import publish_texture


class Window:
    def __init__(self,path):
        self.path=path
        self.approve=True
    def get_current_url(self):
        return "http://127.0.0.1:43211/"
    def create_confirmation_dialog(self,title,message):
        return self.approve
    def create_file_dialog(self,*args,**kwargs):
        return [str(self.path)]


class TrustedWO2DesktopTextureTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        with tempfile.TemporaryDirectory() as tmp:
            image=Image.new("RGB",(2,2),(20,120,240))
            buffer=BytesIO()
            image.save(buffer,format="PNG")
            self.png=buffer.getvalue()
        self.path=Path(self.temp.name)/"original.png"
        self.path.write_bytes(self.png)
        # The actual host requires OS pywebview; native unit tests exercise
        # its exact IPC contract without requiring a GUI installation.
        module_patch=patch.dict("sys.modules",{
            "webview":SimpleNamespace(FileDialog=SimpleNamespace(OPEN=1))})
        module_patch.start()
        self.addCleanup(module_patch.stop)
        self.window=Window(self.path)
        self.bridge=TrustedDesktopCameraBridge(
            self.index,origin="http://127.0.0.1:43211",
            host_factory=lambda cb:None)
        self.bridge._attach_window(self.window)
        self.addCleanup(self.bridge._close)
        self.assets.publish(
            self.pid,"mesh_for_texture",shape="mesh",size_m=2,
            points=[[0,0,0],[1,0,0],[0,1,0]],
            triangles=[[0,1,2]],mesh_uvs=[[0,0],[1,0],[0,1]],
            preview_material={"base_color_rgb":[1,1,1],
                              "roughness":.5,"metallic":0})

    def test_os_picker_import_and_revision_are_distinct_consent_actions(self):
        imported=self.bridge.data_av_import_original_texture(self.pid)
        self.assertEqual(imported["status"],"ORIGINAL_TEXTURE_IMPORTED")
        digest=imported["texture"]["sha256"]
        rows=self.bridge.data_av_texture_mesh_catalog(self.pid)["assets"]
        row=next(x for x in rows if x["asset_id"]=="mesh_for_texture")
        first=self.assets.open(self.pid,"mesh_for_texture",1)[0]
        receipt=self.bridge.data_av_apply_original_texture({
            "project_id":self.pid,"asset_id":row["asset_id"],
            "asset_revision":row["asset_revision"],
            "asset_document_sha256":row["asset_document_sha256"],
            "texture_sha256":digest})
        self.assertEqual(receipt["status"],"NEW_SOURCE_REVISION")
        self.assertEqual(receipt["asset_revision"],2)
        old=self.assets.open(self.pid,"mesh_for_texture",1)[0]
        new=self.assets.open(self.pid,"mesh_for_texture",2)[0]
        self.assertEqual(old["document_sha256"],first["document_sha256"])
        self.assertNotIn("texture",old["data"]["preview_material"])
        self.assertEqual(new["data"]["preview_material"]["texture"]["sha256"],
                         digest)
        with self.assertRaises(RuntimeError):
            self.bridge.data_av_apply_original_texture({
                "project_id":self.pid,"asset_id":row["asset_id"],
                "asset_revision":1,
                "asset_document_sha256":row["asset_document_sha256"],
                "texture_sha256":digest})

    def test_native_creator_can_publish_each_typed_channel_without_mutating_prior(self):
        first=self.bridge.data_av_import_original_texture(self.pid)
        row=next(x for x in self.bridge.data_av_texture_mesh_catalog(
            self.pid)["assets"] if x["asset_id"]=="mesh_for_texture")
        source_sha=row["asset_document_sha256"]
        receipt=self.bridge.data_av_apply_original_texture({
            "project_id":self.pid,"asset_id":"mesh_for_texture",
            "asset_revision":1,"asset_document_sha256":source_sha,
            "texture_sha256":first["texture"]["sha256"],
            "channel":"normal"})
        self.assertEqual(receipt["status"],"NEW_SOURCE_REVISION")
        self.assertEqual(receipt["source_material_channel"],"normal")
        old=self.assets.open(self.pid,"mesh_for_texture",1)[0]
        new=self.assets.open(self.pid,"mesh_for_texture",2)[0]
        self.assertNotIn("pbr_maps",old["data"]["preview_material"])
        self.assertEqual(
            new["data"]["preview_material"]["pbr_maps"]["normal"]["sha256"],
            first["texture"]["sha256"])
        self.assertEqual(old["document_sha256"],source_sha)
        from backend.nvp_native_usd_texture import publish_texture
        gray=Image.new("RGB",(2,2),(50,50,50))
        out=BytesIO()
        gray.save(out,format="PNG")
        scalar=publish_texture(self.index,self.pid,out.getvalue())
        follow=self.bridge.data_av_apply_original_texture({
            "project_id":self.pid,"asset_id":"mesh_for_texture",
            "asset_revision":2,
            "asset_document_sha256":new["document_sha256"],
            "texture_sha256":scalar["sha256"],
            "channel":"roughness"})
        self.assertEqual(follow["asset_revision"],3)
        final=self.assets.open(self.pid,"mesh_for_texture",3)[0]["data"][
            "preview_material"]["pbr_maps"]
        self.assertEqual(set(final),{"normal","roughness"})
        self.assertEqual(final["normal"]["sha256"],
                         first["texture"]["sha256"])

    def test_native_denial_does_not_publish_revision(self):
        imported=self.bridge.data_av_import_original_texture(self.pid)
        self.window.approve=False
        row=self.bridge.data_av_texture_mesh_catalog(self.pid)["assets"]
        row=next(x for x in row if x["asset_id"]=="mesh_for_texture")
        denied=self.bridge.data_av_apply_original_texture({
            "project_id":self.pid,"asset_id":"mesh_for_texture",
            "asset_revision":1,
            "asset_document_sha256":row["asset_document_sha256"],
            "texture_sha256":imported["texture"]["sha256"]})
        self.assertEqual(denied["status"],"DENIED")
        self.assertEqual(self.index.read_revision(
            self.pid,"mesh_for_texture")["revision"],1)


if __name__=="__main__":
    unittest.main()
