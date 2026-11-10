"""PLAN-04 refusal, stale-source, one-use and native Blender custody denial.

Positive real Windows/Linux Blender/Cycles execution is in the separate
tools.nvp_plan04_cycles_native_witness; no fake blender runner here is
evidence of a rendered image.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_plan02d_render_queue import DurableRenderIntentionQueue
from backend.nvp_plan04_original_cycles import OriginalCyclesProduction
from backend.nvp_resource_ledger import TaskLedger
from test_nvp_plan02d_derived_raster import ActualSourceRasterTests

T=7056000000


class OriginalCyclesAdmissionTests(unittest.TestCase):
    def setUp(self):
        ActualSourceRasterTests.setUp(self)
        tmp=tempfile.TemporaryDirectory(prefix="nvp-plan04-cycles-deny-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.ledger=TaskLedger(self.root/"resource")
        executable=Path(sys.executable).resolve(strict=True)
        # No Blender is ever launched by these refusal/stale tests.
        self.supervisor=BlenderWorkerSupervisor(
            self.root/"blender",blender_executable=executable,
            blender_sha256=sha_file(executable),blender_version="Blender 5.2.3",
            activity_ledger=self.ledger)
        self.native_decisions=[]
        self.queue=DurableRenderIntentionQueue(
            self.index,ask_native=lambda scope:True)
        task=self.queue.enqueue(self.pid,"Plan04RefusalJob",self.request)
        self.review=self.queue.review(
            self.pid,"Plan04RefusalJob",task["revision"])

    def host(self,decision):
        return OriginalCyclesProduction(
            self.index,self.queue,self.supervisor,
            ask_native=lambda scope:self.native_decisions.append(scope) or decision)

    def test_native_refusal_prevents_all_blender_spawn_and_consumes_review(self):
        obj=self.host(False)
        with patch.object(self.supervisor,"run") as native:
            with self.assertRaisesRegex(PermissionError,"refused"):
                obj.render_once(self.pid,"Plan04RefusalJob",self.review["revision"],
                                self.review["selection_sha256"],T//3)
            native.assert_not_called()
        self.assertEqual(len(self.native_decisions),1)
        self.assertFalse(self.native_decisions[0]["output_publication_authorized"])
        with self.assertRaises(PermissionError):
            obj.render_once(self.pid,"Plan04RefusalJob",self.review["revision"],
                            self.review["selection_sha256"],T//3)
        self.assertEqual(len(self.native_decisions),1)

    def test_stale_source_never_opens_native_permission_dialog(self):
        obj=self.host(True)
        with patch.object(self.supervisor,"run") as native:
            with self.assertRaises(PermissionError):
                obj.render_once(self.pid,"Plan04RefusalJob",self.review["revision"],
                                "0"*64,T//3)
            native.assert_not_called()
        self.assertEqual(self.native_decisions,[])

    def test_os_confirmation_callback_error_fails_closed_and_no_replay(self):
        def broken(_):
            raise RuntimeError("OS confirmation dialog lost user presence")
        obj=OriginalCyclesProduction(
            self.index,self.queue,self.supervisor,ask_native=broken)
        with patch.object(self.supervisor,"run") as native:
            with self.assertRaisesRegex(RuntimeError,"user presence"):
                obj.render_once(self.pid,"Plan04RefusalJob",self.review["revision"],
                                self.review["selection_sha256"],T//3)
            native.assert_not_called()
        with self.assertRaises(PermissionError):
            obj.render_once(self.pid,"Plan04RefusalJob",self.review["revision"],
                            self.review["selection_sha256"],T//3)

    def test_restarted_queue_cannot_replay_approved_original_render(self):
        fresh=DurableRenderIntentionQueue(
            self.index,ask_native=lambda _:True)
        obj=OriginalCyclesProduction(
            self.index,fresh,self.supervisor,ask_native=lambda _:True)
        with patch.object(self.supervisor,"run") as native:
            with self.assertRaises(PermissionError):
                obj.render_once(self.pid,"Plan04RefusalJob",self.review["revision"],
                                self.review["selection_sha256"],T//3)
            native.assert_not_called()


if __name__=="__main__":
    unittest.main()
