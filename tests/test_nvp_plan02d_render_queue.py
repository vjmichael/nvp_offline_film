"""PLAN-02-D2 SQLite queue acceptance: no worker, no replay, fresh OS review."""
from __future__ import annotations

from copy import deepcopy
import unittest

from test_nvp_plan02c_native_camera_ai import CanonicalDirectorRailTests
from backend.nvp_plan02d_render_queue import (
    DurableRenderIntentionQueue, QUEUED, REFUSED, APPROVED, RECOVERY)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T


class DurableRenderQueueTests(unittest.TestCase):
    def setUp(self):
        CanonicalDirectorRailTests.setUp(self)
        self.consent = True
        self.scopes = []
        self.queue = DurableRenderIntentionQueue(
            self.index, ask_native=self._ask)
        self.request = {
            "take_id": self.spec["take_id"],
            "take_document_sha256": self.spec["take_document_sha256"],
            "camera_timeline_id": self.spec["camera_timeline_id"],
            "camera_timeline_revision": self.spec["camera_timeline_revision"],
            "camera_timeline_sha256": self.spec["camera_timeline_sha256"],
            "first_tick": 0,
            "last_tick_exclusive": T,
            "camera_mode": "original",
            "rail_id": None,
            "rail_revision": None,
            "rail_document_sha256": None,
        }

    def _ask(self, scope):
        self.scopes.append(scope)
        return self.consent

    def test_immutable_sqlite_review_does_not_launch_and_replay_denied(self):
        original = self.index.read_revision(
            self.pid, self.spec["take_id"], 1)["document_sha256"]
        recorded = self.queue.enqueue(self.pid, "PLAN02DJobOne", self.request)
        self.assertEqual(recorded["revision"], 1)
        self.assertEqual(recorded["status"], QUEUED)
        saved = self.index.read_revision(self.pid, "PLAN02DJobOne", 1)
        self.assertEqual(saved["kind"], "edit")
        self.assertEqual(len(saved["dependencies"]), 2)
        fresh = DurableRenderIntentionQueue(
            self.index, ask_native=self._ask)
        self.assertEqual(fresh.inspect(
            self.pid, "PLAN02DJobOne")["selection_sha256"],
            recorded["selection_sha256"])
        approved = fresh.review(self.pid, "PLAN02DJobOne", 1)
        self.assertEqual(approved["status"], APPROVED)
        self.assertEqual(approved["revision"], 2)
        self.assertFalse(approved["renderer_worker_authorized"])
        self.assertFalse(approved["export_authorized"])
        self.assertEqual(len(self.scopes), 1)
        self.assertTrue(self.scopes[0]["does_not_authorize_worker_or_export"])
        with self.assertRaises(PermissionError):
            fresh.review(self.pid, "PLAN02DJobOne", 1)
        with self.assertRaises(PermissionError):
            fresh.review(self.pid, "PLAN02DJobOne", 2)
        with self.assertRaises(PermissionError):
            fresh.execute(self.pid, "PLAN02DJobOne")
        self.assertEqual(self.index.read_revision(
            self.pid, self.spec["take_id"], 1)["document_sha256"], original)

    def test_refusal_is_durable_terminal_and_no_retry_of_one_use_authority(self):
        queued = self.queue.enqueue(self.pid, "PLAN02DRefusal", self.request)
        self.consent = False
        refused = self.queue.review(self.pid, "PLAN02DRefusal", 1)
        self.assertEqual(refused["status"], REFUSED)
        self.assertEqual(self.queue.inspect(
            self.pid, "PLAN02DRefusal")["status"], REFUSED)
        with self.assertRaises(PermissionError):
            self.queue.review(self.pid, "PLAN02DRefusal", 2)
        with self.assertRaises(RuntimeError):
            self.queue.enqueue(self.pid, "PLAN02DRefusal", self.request)
        self.assertNotEqual(queued["document_sha256"], refused["document_sha256"])

    def test_restart_revokes_even_nonexecuting_approval(self):
        self.queue.enqueue(self.pid, "PLAN02DRestart", self.request)
        self.queue.review(self.pid, "PLAN02DRestart", 1)
        restarted = DurableRenderIntentionQueue(
            self.index, ask_native=self._ask)
        recon = restarted.reconcile_restart(self.pid, "PLAN02DRestart")
        self.assertEqual(recon["status"], RECOVERY)
        self.assertEqual(recon["revision"], 3)
        self.assertFalse(recon["renderer_worker_authorized"])
        with self.assertRaises(PermissionError):
            restarted.review(self.pid, "PLAN02DRestart", 2)
        approval = restarted.review(self.pid, "PLAN02DRestart", 3)
        self.assertEqual(approval["status"], APPROVED)
        self.assertEqual(len(self.scopes), 2)
        with self.assertRaises(PermissionError):
            restarted.execute(self.pid, "PLAN02DRestart")

    def test_unapproved_rail_or_changed_source_cannot_enter_queue(self):
        request = deepcopy(self.request)
        request.update({
            "camera_mode": "approved_rail", "rail_id": self.rail,
            "rail_revision": 1, "rail_document_sha256": "0" * 64,
        })
        with self.assertRaises(KeyError):
            self.queue.enqueue(self.pid, "PLAN02DUnapproved", request)
        changed = deepcopy(self.request)
        changed["take_document_sha256"] = "0" * 64
        with self.assertRaises(PermissionError):
            self.queue.enqueue(self.pid, "PLAN02DStale", changed)
        self.assertEqual(len(self.scopes), 0)

    def test_approved_rail_dependency_is_revision_pinned(self):
        trial = self.service.preview(
            self.pid, self.rail, self.spec, expected_revision=0)
        saved = self.service.publish(
            self.pid, self.rail, self.spec, 0, trial["proposal_sha256"])
        request = {
            **self.request,
            "camera_mode": "approved_rail",
            "rail_id": self.rail,
            "rail_revision": 1,
            "rail_document_sha256": saved["rail_document_sha256"],
        }
        queued = self.queue.enqueue(self.pid, "PLAN02DRail", request)
        self.assertEqual(queued["status"], QUEUED)
        record = self.index.read_revision(self.pid, "PLAN02DRail", 1)
        self.assertEqual(len(record["dependencies"]), 3)
        self.assertTrue(any(dep["object_id"] == self.rail
                            and dep["revision"] == 1
                            for dep in record["dependencies"]))


if __name__ == "__main__":
    unittest.main()
