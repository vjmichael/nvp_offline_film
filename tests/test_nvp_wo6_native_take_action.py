"""Real OpenUSD source worker and Windows AppContainer publication test."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_wo6_saved_retake_scope import prepare_saved_retake
from backend.nvp_wo6_native_take_action import _payload,execute_saved_retake
from tools.nvp_wo6_take_worker import evaluate_input


class Window:
    def get_current_url(self):return "http://127.0.0.1:51213/"
    def create_confirmation_dialog(self,*_):return True


class NativeTakeActionTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        studio=Studio(root/"film.sqlite")
        self.index=FilmIndex(studio);self.pid=studio.create_project("Movie","Idea")["id"]
        OpenUSDSceneBridge(self.index).publish(self.pid,"Scene",prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]}],
            curves=[{"path":"/World/Actor","samples":[
                {"tick":0,"position":[0,0,0]},
                {"tick":TICKS_PER_SECOND,"position":[2,0,0]}]}])
        self.index.register_revision(self.pid,"Action","performance",{"verb":"walk"})
        TemporalLedger(self.index).publish(self.pid,"Time",[
            {"event_id":"move","event_kind":"action","subject_id":"Actor",
             "start_tick":0,"end_tick":TICKS_PER_SECOND,"source_id":"Action",
             "source_revision":1,"payload":{"usd_prim_path":"/World/Actor"}}],
             duration_tick=2*TICKS_PER_SECOND)
        self.capture=OpenUSDTakeCapture(self.index,verify_creator_action=lambda *_:True)
        self.original=self.capture.freeze(self.pid,"Original",scene_id="Scene",
            scene_revision=1,timeline_id="Time",timeline_revision=1,
            sample_ticks=[0,TICKS_PER_SECOND],creator_event="fixture")
        self.bridge=TrustedDesktopCameraBridge(self.index,origin="http://127.0.0.1:51213")
        self.addCleanup(self.bridge._close);self.bridge._attach_window(Window())
        proposal={"project_id":self.pid,"source_id":"Original","source_revision":1,
            "source_sha256":self.original["document_sha256"],"change_kind":"retake",
            "intention":"Preserve original scene and timing","screenplay_scene_id":None}
        preview=self.bridge.wo6_plan_preview(proposal)
        self.plan=self.bridge.wo6_plan_save({"proposal":proposal,
            "preview_sha256":preview["preview_sha256"]})["record"]
        self.ledger=TaskLedger(root/"runtime",sampler=lambda:ResourceSnapshot(1,32768,24000,0,()))

    def args(self):
        return {"project_id":self.pid,"plan_id":self.plan["object_id"],
            "plan_sha256":self.plan["document_sha256"],"new_take_id":"NewTake"}

    def test_real_pathless_worker_evaluates_original_checkpoints(self):
        scope=prepare_saved_retake(self.index,**self.args())
        result=evaluate_input(_payload(self.index,scope))
        old=self.index.read_revision(self.pid,"Original",1)
        self.assertEqual(result["sample_digest_sha256"],old["data"]["sample_digest_sha256"])
        self.assertEqual(result["checkpoint_count"],2)

    @unittest.skipUnless(os.name=="nt","Windows native AppContainer custody required")
    def test_actual_native_worker_and_verified_immutable_publication(self):
        seen=[]
        result=execute_saved_retake(self.index,self.ledger,**self.args(),
            confirm_native=lambda spec,digest:seen.append((spec,digest)) or True,
            live_gate=lambda _:True)
        self.assertEqual(len(seen),1)
        self.assertEqual(result["status"],"VERIFIED_NEW_TAKE")
        self.assertTrue(result["worker_executed"])
        self.assertFalse(result["film_approved"])
        self.assertEqual(self.ledger.get_task(result["task_id"])["state"],"SUCCEEDED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.assertEqual(self.index.read_revision(self.pid,"Original",1)["document_sha256"],
                         self.original["document_sha256"])
        verified=self.capture.verify_take(self.pid,"NewTake")
        self.assertEqual(verified["take_document_sha256"],result["take_document_sha256"])
        receipt=self.index.read_revision(self.pid,"NewTake",1)["data"]["protected_retake_execution"]
        self.assertTrue(receipt["process_tree_custody_verified"])
        from backend.nvp_w1g_release_gate import release_process_journal_root
        import json
        evidence=json.loads((release_process_journal_root()/
            (receipt["original_process_journal_id"]+".json")).read_text("utf-8"))
        self.assertEqual(evidence["state"],"TREE_REAPED_VERIFIED")
        self.assertEqual(evidence["command_sha256"],receipt["command_sha256"])
        self.assertEqual(receipt["spec_sha256"],seen[0][1])

    @unittest.skipUnless(os.name=="nt","Windows native scope required")
    def test_separate_worker_refusal_creates_no_take(self):
        with self.assertRaises(PermissionError):
            execute_saved_retake(self.index,self.ledger,**self.args(),
                confirm_native=lambda *_:False,live_gate=lambda _:True)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        with self.assertRaises(KeyError):self.index.read_revision(self.pid,"NewTake")


if __name__=="__main__":unittest.main()
