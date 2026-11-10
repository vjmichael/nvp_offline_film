"""PLAN-02-D3 native execution boundary and durable no-replay tests.

The Windows/Linux positive descendant and abrupt-host-crash gate is a
separate process-native acceptance, never inferred from a mock process.
"""
from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest import mock

from test_nvp_plan02c_native_camera_ai import CanonicalDirectorRailTests
from backend.nvp_blender_worker import sha_file
from backend.nvp_plan02d_render_queue import DurableRenderIntentionQueue, APPROVED
from backend.nvp_plan02d_worker_custody import (
    SupervisedSourceRenderWorker, FAILED, EXITED, INTERRUPTED)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T


class NativeWorkerCustodyContractTests(unittest.TestCase):
    def setUp(self):
        CanonicalDirectorRailTests.setUp(self)
        self.temp=tempfile.TemporaryDirectory(prefix="nvp-plan02d-worker-")
        self.addCleanup(self.temp.cleanup)
        self.dialogs=[]
        self.grant=True
        self.queue=DurableRenderIntentionQueue(
            self.index,ask_native=lambda scope:True)
        self.source={
            "take_id":self.spec["take_id"],
            "take_document_sha256":self.spec["take_document_sha256"],
            "camera_timeline_id":self.spec["camera_timeline_id"],
            "camera_timeline_revision":self.spec["camera_timeline_revision"],
            "camera_timeline_sha256":self.spec["camera_timeline_sha256"],
            "first_tick":0,"last_tick_exclusive":T,
            "camera_mode":"original","rail_id":None,"rail_revision":None,
            "rail_document_sha256":None,
        }
        self.queue.enqueue(self.pid,"ProtectedRenderD3",self.source)
        self.queue.review(self.pid,"ProtectedRenderD3",1)
        self.runner=SupervisedSourceRenderWorker(
            self.queue,Path(self.temp.name)/"work",
            ask_native=self._ask,timeout_seconds=15)

    def _ask(self, scope):
        self.dialogs.append(scope)
        return self.grant

    def _run(self,args=("-c","print('PLAN02D_WORKER_REAL_CHILD')")):
        exe=Path(sys.executable).resolve()
        return self.runner.run(
            self.pid,"ProtectedRenderD3",
            executable=exe,executable_sha256=sha_file(exe),arguments=args)

    def test_source_review_is_never_restart_worker_permission(self):
        fresh=DurableRenderIntentionQueue(
            self.index,ask_native=lambda scope:True)
        worker=SupervisedSourceRenderWorker(
            fresh,Path(self.temp.name)/"cold",
            ask_native=self._ask,timeout_seconds=15)
        with self.assertRaises(PermissionError):
            worker.run(
                self.pid,"ProtectedRenderD3",executable=sys.executable,
                executable_sha256=sha_file(Path(sys.executable).resolve()),
                arguments=("-c","print(1)"))
        self.assertEqual(self.dialogs,[])
        self.assertEqual(fresh.inspect(
            self.pid,"ProtectedRenderD3")["status"],APPROVED)

    def test_distinct_worker_refusal_is_persisted_and_never_replayed(self):
        self.grant=False
        with self.assertRaises(PermissionError):
            self._run()
        record=self.queue.inspect(self.pid,"ProtectedRenderD3")
        self.assertEqual(record["status"],FAILED)
        self.assertEqual(len(self.dialogs),1)
        with self.assertRaises(PermissionError):
            self._run()
        with self.assertRaises(PermissionError):
            self.queue.review(self.pid,"ProtectedRenderD3",record["revision"])

    def test_missing_kernel_custody_fails_closed(self):
        with mock.patch(
            "backend.nvp_plan02d_worker_custody.launch_contained",
            side_effect=RuntimeError("Kernel containment unavailable")) as launched:
            with self.assertRaises(RuntimeError):
                self._run()
        launched.assert_called_once()
        call=launched.call_args
        self.assertEqual(call.kwargs["linux_cgroup_tree_required"],
                         sys.platform=="linux")
        self.assertEqual(self.queue.inspect(
            self.pid,"ProtectedRenderD3")["status"],FAILED)
        with self.assertRaises(PermissionError):
            self._run()

    def test_journal_crash_state_untrusted_and_no_reuse(self):
        old,_=self.queue._read(self.pid,"ProtectedRenderD3")
        self.runner._update(
            self.pid,"ProtectedRenderD3",old,
            "WORKER_STARTED_NOT_YET_VERIFIED")
        recovered=SupervisedSourceRenderWorker(
            DurableRenderIntentionQueue(
                self.index,ask_native=lambda scope:True),
            Path(self.temp.name)/"work",
            ask_native=self._ask)
        found=recovered.inventory_after_restart(self.pid,"ProtectedRenderD3")
        self.assertEqual(found["status"],INTERRUPTED)
        self.assertFalse(found["process_tree_custody_independently_verified"])
        self.assertFalse(found["automatic_replay_allowed"])
        with self.assertRaises(PermissionError):
            recovered.run(self.pid,"ProtectedRenderD3",
                          executable=sys.executable,
                          executable_sha256=sha_file(Path(sys.executable).resolve()))

    def test_real_direct_worker_success_only_if_strict_containment_available(self):
        # Successful completion is valid only when the actual kernel
        # container can launch. Linux GitHub-hosted runners often lack
        # Delegate=yes; on those hosts fail closed, NOT a synthetic PASS.
        if sys.platform=="linux":
            from backend.nvp_worker_linux_cgroup import current_delegated_parent
            try:
                current_delegated_parent()
            except RuntimeError:
                self.skipTest("Linux strict cgroup v2 has no delegated host scope")
        if os.name!="nt" and sys.platform!="linux":
            self.skipTest("Host has no supported NVP renderer custody")
        result=self._run()
        self.assertEqual(result["status"],EXITED)
        self.assertEqual(result["exit_code"],0)
        self.assertFalse(result["artifact_publication_authorized"])
        self.assertEqual(self.queue.inspect(
            self.pid,"ProtectedRenderD3")["status"],EXITED)
        with self.assertRaises(PermissionError):
            self._run()


if __name__=="__main__":
    unittest.main()
