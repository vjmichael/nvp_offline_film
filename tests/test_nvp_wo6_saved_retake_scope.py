"""Native OpenUSD source-reopen and planning-only execution boundary."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_wo6_saved_retake_scope import prepare_saved_retake
from tests.test_nvp_wo6_creator_plan import Window


class SavedRetakeScopeTests(unittest.TestCase):
    def setUp(self):
        folder=TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.studio=Studio(Path(folder.name)/"film.sqlite")
        self.pid=self.studio.create_project("Film","Idea")["id"]
        self.index=FilmIndex(self.studio)
        self.scenes=OpenUSDSceneBridge(self.index)
        self.prims=[{"path":"/World/Actor","role":"actor","position":[0,0,0]}]
        self.scenes.publish(self.pid,"Scene",prims=self.prims,curves=[])
        TemporalLedger(self.index).publish(self.pid,"Time",[],
            duration_tick=TICKS_PER_SECOND)
        self.original=OpenUSDTakeCapture(self.index,
            verify_creator_action=lambda event,scope:event=="native_fixture").freeze(
            self.pid,"Original",scene_id="Scene",scene_revision=1,
            timeline_id="Time",timeline_revision=1,sample_ticks=[0],
            creator_event="native_fixture")
        self.bridge=TrustedDesktopCameraBridge(self.index,
            origin="http://127.0.0.1:51213")
        self.addCleanup(self.bridge._close)
        window=Window()
        window.approve=True
        self.bridge._attach_window(window)
        proposal={"project_id":self.pid,"source_id":"Original",
            "source_revision":1,"source_sha256":self.original["document_sha256"],
            "change_kind":"retake","intention":"Retake from exact source",
            "screenplay_scene_id":None}
        preview=self.bridge.wo6_plan_preview(proposal)
        self.plan=self.bridge.wo6_plan_save({"proposal":proposal,
            "preview_sha256":preview["preview_sha256"]})["record"]

    def prepare(self, **overrides):
        args={"project_id":self.pid,"plan_id":self.plan["object_id"],
              "plan_sha256":self.plan["document_sha256"],"new_take_id":"NewTake"}
        return prepare_saved_retake(self.index,**dict(args,**overrides))

    def test_real_source_reopened_but_no_worker_grant_or_take(self):
        scope=self.prepare()
        self.assertTrue(scope["native_take_reopened"])
        self.assertFalse(scope["worker_authorized"])
        self.assertFalse(scope["worker_executed"])
        self.assertEqual(scope,self.prepare())
        self.assertEqual(scope["original_take_sha256"],self.original["document_sha256"])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NewTake")

    def test_wrong_plan_digest_and_existing_take_denied(self):
        with self.assertRaises(PermissionError):
            self.prepare(plan_sha256="0"*64)
        with self.assertRaises(PermissionError):
            self.prepare(new_take_id="Original")

    def test_superseded_scene_and_changed_impact_denied(self):
        self.scenes.publish(self.pid,"Scene",prims=self.prims,
                            curves=[],expected_revision=1)
        with self.assertRaises(PermissionError):
            self.prepare()


if __name__=="__main__":
    unittest.main()
