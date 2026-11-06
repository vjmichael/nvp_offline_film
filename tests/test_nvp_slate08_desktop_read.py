"""SLATE-08 read-only source identity and native camera UI bridge acceptance."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_slate08_desktop_read import FilmCameraReadBridge


class CameraDesktopReadAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.studio=Studio(Path(self.tmp.name)/"nvp.sqlite")
        self.project=self.studio.create_project("Lens editor","")["id"]
        self.index=FilmIndex(self.studio)
        self.bridge=FilmCameraReadBridge(self.index)

    def test_no_source_does_not_fabricate_a_camera(self):
        result=self.bridge.scenes(self.project)
        self.assertEqual(result["scenes"],[])
        self.assertFalse(result["usd_loaded"])
        self.assertFalse(result["worker_started"])

    def test_native_source_selected_without_mutating_scene_or_film(self):
        published=OpenUSDSceneBridge(self.index).publish(
            self.project,"studio_set",
            prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,8]},
            ],curves=[],native_schemas=True)
        before=self.index.read_revision(self.project,"studio_set",1)
        item=self.bridge.scenes(self.project)
        self.assertEqual(len(item["scenes"]),1)
        self.assertEqual(item["scenes"][0]["document_sha256"],
                         before["document_sha256"])
        self.assertEqual(item["scenes"][0]["cameras"][0]["path"],
                         "/World/Camera")
        self.assertFalse(item["usd_loaded"])
        snapshot=self.bridge.snapshot(
            self.project,"studio_set",1,tick=0,camera_path="/World/Camera")
        self.assertEqual(snapshot["scene_document_sha256"],
                         before["document_sha256"])
        self.assertEqual(snapshot["source_tick"],0)
        self.assertFalse(snapshot["frozen_take_created"])
        self.assertEqual(len(snapshot["markers"]),1)
        self.assertEqual(self.index.read_revision(
            self.project,"studio_set",1)["document_sha256"],
            before["document_sha256"])
        self.assertEqual(self.index.list_objects(self.project,kind="take"),[])
        with self.assertRaises(ValueError):
            self.bridge.snapshot(self.project,"studio_set",1,
                                 tick=0,camera_path="/World/Fake")
        with self.assertRaises(ValueError):
            self.bridge.snapshot(self.project,"studio_set",1,
                                 tick=True,camera_path="/World/Camera")
        with self.assertRaises((ValueError,KeyError)):
            self.bridge.snapshot(self.project,"studio_set",2,
                                 tick=0,camera_path="/World/Camera")

if __name__=="__main__":
    unittest.main()
