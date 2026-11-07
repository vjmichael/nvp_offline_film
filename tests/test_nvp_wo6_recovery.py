"""WO6-06 crash boundary: real FilmIndex commit vs durable task/receipt."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from backend.nvp_ai_read_host import TrustedReadScope
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_wo6_impact_preview import preview_source_impact
from backend.nvp_wo6_native_take_action import NativeTakeActionHost, RECEIPT_FORMAT
from backend.nvp_wo6_recovery import WO6DurableRecovery
from backend.nvp_resource_supervisor import NativeCancelRequested
from backend.nvp_worker_host_lease import WorkerHostLease


class WO6NativeDurability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.studio = Studio(self.base / "studio.sqlite")
        self.pid = self.studio.create_project("Recovery source film", "")["id"]
        self.index = FilmIndex(self.studio)
        bridge = OpenUSDSceneBridge(self.index)
        bridge.publish(
            self.pid, "scene", prims=[
                {"path":"/World/Actor", "role":"actor", "position":[0,0,0]},
                {"path":"/World/Camera", "role":"camera", "position":[0,0,-5]},
            ], curves=[{"path":"/World/Actor", "samples":[
                {"tick":0, "position":[0,0,0]},
                {"tick":2*TICKS_PER_SECOND, "position":[2,0,0]},
            ]}])
        self.index.register_revision(
            self.pid, "actor_source", "performance", {"format":"wo6.test.source"})
        TemporalLedger(self.index).publish(self.pid, "timeline", [{
            "event_id":"act", "event_kind":"action", "subject_id":"actor_source",
            "start_tick":0, "end_tick":2*TICKS_PER_SECOND,
            "source_id":"actor_source", "source_revision":1,
            "payload":{"usd_prim_path":"/World/Actor"},
        }], duration_tick=3*TICKS_PER_SECOND)
        scene = self.index.read_revision(self.pid, "scene", 1)
        timeline = self.index.read_revision(self.pid, "timeline", 1)
        preview = preview_source_impact(
            self.index, self.pid, "scene", 1,
            scene["document_sha256"], "retake", max_nodes=32)
        self.args = {
            "creator_decision_id":"human_confirmed",
            "scene_id":"scene", "scene_revision":1,
            "scene_sha256":scene["document_sha256"],
            "timeline_id":"timeline", "timeline_revision":1,
            "timeline_sha256":timeline["document_sha256"],
            "new_take_id":"new_take", "sample_ticks":[0,TICKS_PER_SECOND],
            "expected_preview_sha256":preview["preview_sha256"],
        }
        self.scope = TrustedReadScope("director", self.pid, "turn_queue")
        self.ledger = TaskLedger(
            self.base / "task_root",
            sampler=lambda: ResourceSnapshot(time.time(),32768,22000,0.,()))
        self.host = NativeTakeActionHost(
            self.index,self.ledger,(self.base / "job_root").absolute(),
            confirm_creator=lambda decision, scope: (
                decision=="human_confirmed" and
                scope["old_takes_immutable"] is True),
            authorize_native=lambda scope,sha,doc: (
                scope.project_id==self.pid and scope.actor_id=="director"))

    def _queued(self):
        return self.host.queue_new_take(self.scope, **self.args)["task_id"]

    def _recovery(self, stopped):
        return WO6DurableRecovery(
            self.ledger, attest_worker_tree_stopped=lambda task: stopped)

    def test_cancel_queued_is_durable_and_does_not_start_or_write(self):
        task = self._queued()
        signal = self.host.recovery.request_cancel(
            self.scope, task, authorize_cancel=lambda *_:True,
            reason="Director chose not to use this performance")
        self.assertEqual(signal["state"],"CANCELLED")
        self.assertTrue(signal["cancel_intent_durable"])
        reopened = self._recovery(True)
        self.assertTrue(reopened.cancel_requested(task))
        self.assertTrue(reopened.status(task, owner_key=self.host.owner)[
            "cancel_requested"])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"new_take")
        self.assertIsNone(self.host.run_next())
        # No model-visible source or final film was made.

    def test_different_actor_cannot_cancel_or_recover_unattested_worker(self):
        task = self._queued()
        other = TrustedReadScope("other",self.pid,"turn_2")
        with self.assertRaises(PermissionError):
            self.host.recovery.request_cancel(
                other,task,authorize_cancel=lambda *_:True,reason="not mine")
        claimed = self.host.binding.claim_next(owner_key=self.host.owner)
        self.assertTrue(claimed["admitted"])
        with self.assertRaises(PermissionError):
            self._recovery(False).reconcile_interrupted(
                task,owner_key=self.host.owner,
                job_root=self.host.root,studio_db=self.studio.db_path)
        self.assertEqual(self.ledger.get_task(task)["state"],"ACTIVE")
        with self.assertRaises(PermissionError):
            self._recovery(True).reconcile_interrupted(
                task,owner_key="wrong_owner",
                job_root=self.host.root,studio_db=self.studio.db_path)
        evidence = self._recovery(True).reconcile_interrupted(
            task,owner_key=self.host.owner,
            job_root=self.host.root,studio_db=self.studio.db_path)
        self.assertEqual(evidence["evidence_status"],"NO_SOURCE_COMMIT_FOUND")
        self.assertEqual(self.ledger.get_task(task)["state"],"INTERRUPTED")
        self.assertFalse(evidence["auto_retry_performed"])
        self.assertFalse(evidence["release_approved"])

    def test_actual_commit_then_crash_before_receipt_is_not_rolled_back(self):
        task = self._queued()
        self.host.binding.claim_next(owner_key=self.host.owner)
        # Precisely simulate crash after FilmIndex committed a real Take,
        # before the separate worker's receipt write. No synthetic output.
        OpenUSDTakeCapture(
            self.index, verify_creator_action=lambda *_: True).freeze(
                self.pid,"new_take",scene_id="scene",scene_revision=1,
                timeline_id="timeline",timeline_revision=1,
                sample_ticks=[0,TICKS_PER_SECOND],
                creator_event="host_authorized_source_only")
        original = self.index.read_revision(self.pid,"new_take",1)
        verify = self._recovery(True)
        evidence = verify.reconcile_interrupted(
            task,owner_key=self.host.owner,
            job_root=self.host.root,studio_db=self.studio.db_path)
        self.assertEqual(
            evidence["evidence_status"],
            "COMMITTED_SOURCE_WITHOUT_WORKER_RECEIPT")
        self.assertEqual(evidence["immutable_artifact_sha256"],
                         original["document_sha256"])
        self.assertFalse(evidence["source_commit_rolled_back"])
        self.assertEqual(self.ledger.get_task(task)["state"],"INTERRUPTED")
        self.assertEqual(self.index.read_revision(
            self.pid,"new_take",1)["document_sha256"],
            original["document_sha256"])
        # Later recovery may discover a genuine worker receipt and append
        # a stronger proof; it must never rewrite the original evidence.
        sealed = json.loads(
            (self.host.root / task / "task.json").read_text("utf-8"))
        receipt = {
            "format":RECEIPT_FORMAT,"task_id":task,
            "project_id":self.pid,"new_take_id":"new_take",
            "take_document_sha256":original["document_sha256"],
            "scene_sha256":self.args["scene_sha256"],
            "timeline_sha256":self.args["timeline_sha256"],
            "source_impact_sha256":sealed["preview_sha256"],
            "rendered_frames":False,"existing_dcp_replaced":False,
        }
        (self.host.root / task / "receipt.json").write_bytes(
            canonical_bytes(receipt))
        stronger = verify.reconcile_interrupted(
            task,owner_key=self.host.owner,
            job_root=self.host.root,studio_db=self.studio.db_path)
        self.assertEqual(
            stronger["evidence_status"],
            "VERIFIED_COMMIT_AND_RECEIPT_NOT_RELEASE_APPROVED")
        self.assertEqual(self.ledger.get_task(task)["state"],"INTERRUPTED")
        status = verify.status(task,owner_key=self.host.owner)
        self.assertEqual(
            status["latest_reconciliation"]["evidence_status"],
            "VERIFIED_COMMIT_AND_RECEIPT_NOT_RELEASE_APPROVED")

    def test_late_cancellation_atomically_fences_verified_success(self):
        task = self._queued()
        self.host.binding.claim_next(owner_key=self.host.owner)
        cancelled = self.host.recovery.request_cancel(
            self.scope, task, authorize_cancel=lambda *_: True,
            reason="Director cancelled while task was admitted")
        self.assertEqual(cancelled["state"], "ACTIVE")
        with self.assertRaises(NativeCancelRequested):
            self.host.recovery.finish_verified(
                task, detail="No actual finished source receipt exists")
        self.assertEqual(self.ledger.get_task(task)["state"], "ACTIVE")
        evidence = self._recovery(True).reconcile_interrupted(
            task, owner_key=self.host.owner,
            job_root=self.host.root, studio_db=self.studio.db_path)
        self.assertEqual(evidence["current_ledger_state"], "CANCELLED")
        self.assertEqual(evidence["evidence_status"], "NO_SOURCE_COMMIT_FOUND")
        self.assertTrue(self.host.recovery.cancel_requested(task))

    def test_recovery_refuses_competing_kernel_worker_host_lease(self):
        task = self._queued()
        self.host.binding.claim_next(owner_key=self.host.owner)
        with WorkerHostLease(self.host.root):
            with self.assertRaises(RuntimeError):
                self._recovery(True).reconcile_interrupted(
                    task, owner_key=self.host.owner,
                    job_root=self.host.root, studio_db=self.studio.db_path)
        self.assertEqual(self.ledger.get_task(task)["state"], "ACTIVE")

    def test_tampered_sealed_spec_cannot_claim_reconciled_success(self):
        task = self._queued()
        self.host.binding.claim_next(owner_key=self.host.owner)
        folder = self.host.root / task
        (folder / "task.json").write_text("{}",encoding="utf8")
        report = self._recovery(True).reconcile_interrupted(
            task,owner_key=self.host.owner,
            job_root=self.host.root,studio_db=self.studio.db_path)
        self.assertEqual(report["evidence_status"],
                         "SEALED_TASK_SPEC_MISSING_OR_CHANGED")
        self.assertIsNone(report["immutable_artifact_sha256"])
        self.assertFalse(report["release_approved"])


if __name__=="__main__":
    unittest.main()
