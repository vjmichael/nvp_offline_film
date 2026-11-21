"""Inert local regression for NVP-INT-LU-01F-R1, not installed Lu acceptance."""
from __future__ import annotations
from contextlib import closing

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from backend.nvp_lu_operation_journal import (
    IPCOperationJournal, JournalRefusal, OperationSpec, OriginRefs, ReceiptObservation,
)


def digest(value: bytes = b"") -> str:
    return sha256(value).hexdigest()


def accept(*_):
    """Test-only hook. Never a production identity, effect grant, or receipt."""
    return True


def deny(*_):
    return False


class OperationLifecycleR1(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "protected"
        self.root.mkdir(mode=0o700)
        self.now = 1_800_000_000_000
        self.new = lambda: IPCOperationJournal(
            self.root, storage_guard=lambda path: path == self.root,
            clock_ms=lambda: self.now,
        )
        self.db = self.new()
        self.origin = OriginRefs("workspace-1", "conversation-1", "turn-1", "task-1", "operation-1")
        self.spec = OperationSpec(self.origin, "nvp.film.project.read", 1, 2,
                                  digest(b"typed-input"), digest(b"object-refs"), self.now + 60_000,
                                  "session-1", "core-epoch-1")

    def receipt(self, state="APPLIED", *, key=b"final", evidence=True):
        return ReceiptObservation(self.origin.operation_ref, state, digest(key), "HOST_OBSERVED", evidence)

    def test_prepare_is_durable_and_duplicate_is_inert(self):
        first = self.db.prepare(self.spec, authorize=accept)
        self.assertEqual(first["state"], "PREPARED")
        self.assertEqual(first["request_sha256"], self.spec.request_sha256)
        self.assertEqual(self.new().prepare(self.spec, authorize=deny), first)
        self.assertEqual([x["kind"] for x in self.db.events("operation-1")], ["PREPARED"])
        self.assertEqual(self.new().status("operation-1"), first)

    def test_ref_collision_refuses_altered_original_user_turn_or_payload(self):
        self.db.prepare(self.spec, authorize=accept)
        for altered in (
            replace(self.spec, origin=replace(self.origin, user_turn_ref="turn-other")),
            replace(self.spec, effect_class=3),
            replace(self.spec, capability_id="nvp.film.render.shot"),
            replace(self.spec, input_sha256=digest(b"different")),
            replace(self.spec, deadline_unix_ms=self.now + 70_000),
            replace(self.spec, host_session_ref="session-2"),
            replace(self.spec, host_epoch_ref="core-epoch-2"),
        ):
            with self.subTest(altered=altered), self.assertRaises(JournalRefusal):
                self.new().prepare(altered, authorize=accept)
        self.assertEqual(self.db.status("operation-1")["state"], "PREPARED")

    def test_refuse_authorization_and_invalid_specs(self):
        with self.assertRaises(JournalRefusal):
            self.db.prepare(self.spec, authorize=deny)
        with self.assertRaises(ValueError):
            OperationSpec(self.origin, "other.module.exec", 1, 4, digest(), digest(), self.now + 100, "session-1", "core-epoch-1")
        with self.assertRaises(ValueError):
            OperationSpec(self.origin, "nvp.film.render.shot", 1, 0, digest(), digest(), self.now + 100, "session-1", "core-epoch-1")
        with self.assertRaises(ValueError):
            OriginRefs("/foo?a", "c", "t", "task", "op")
        with self.assertRaises(JournalRefusal):
            self.db.status("operation-missing")

    def test_dispatch_single_claim_even_with_concurrent_callers(self):
        self.db.prepare(self.spec, authorize=accept)
        def attempt(_):
            try:
                return self.new().claim_dispatch("operation-1", authorize=accept)
            except JournalRefusal:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(12)))
        winners = [r for r in results if r is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(winners[0]["dispatch_ref"]), 32)
        self.assertEqual(self.db.status("operation-1")["state"], "IN_FLIGHT")

    def test_cancel_request_is_not_worker_cancel_ack(self):
        self.db.prepare(self.spec, authorize=accept)
        with self.assertRaises(JournalRefusal):
            self.db.signal_cancel("operation-1", reason_code="CREATOR_CANCEL", authorize=deny)
        first = self.db.signal_cancel("operation-1", reason_code="CREATOR_CANCEL", authorize=accept)
        self.assertTrue(first["cancel_requested"])
        self.assertEqual(first["state"], "PREPARED")
        self.assertEqual(self.db.signal_cancel("operation-1", reason_code="CREATOR_CANCEL", authorize=accept), first)
        with self.assertRaises(JournalRefusal):
            self.db.claim_dispatch("operation-1", authorize=accept)
        self.assertEqual([x["kind"] for x in self.db.events("operation-1")].count("CANCEL_SIGNAL_RECORDED"), 1)

    def test_revoke_before_dispatch_prevents_all_execution(self):
        self.db.prepare(self.spec, authorize=accept)
        self.db.signal_revoke("operation-1", reason_code="HOST_REVOKED", authorize=accept)
        self.assertTrue(self.new().status("operation-1")["revoked"])
        with self.assertRaises(JournalRefusal):
            self.db.claim_dispatch("operation-1", authorize=accept)
        with self.assertRaises(JournalRefusal):
            self.db.reconcile_receipt(self.spec, self.receipt(), verify_receipt=accept)

    def test_cancel_ack_is_not_cancellation_terminal(self):
        self.db.prepare(self.spec, authorize=accept)
        self.db.claim_dispatch("operation-1", authorize=accept)
        with self.assertRaises(JournalRefusal):
            self.db.record_cancel_ack("operation-1", signal_recorded=True, verify_ack=accept)
        self.db.signal_cancel("operation-1", reason_code="USER_CANCEL", authorize=accept)
        with self.assertRaises(JournalRefusal):
            self.db.record_cancel_ack("operation-1", signal_recorded=True, verify_ack=deny)
        self.assertFalse(self.db.record_cancel_ack("operation-1", signal_recorded=False,
                                                   verify_ack=accept)["cancel_acknowledged"])
        state = self.db.record_cancel_ack("operation-1", signal_recorded=True,
                                          verify_ack=lambda signal, binding: signal and
                                          binding["request_sha256"] == self.spec.request_sha256)
        self.assertTrue(state["cancel_acknowledged"])
        self.assertEqual(state["state"], "IN_FLIGHT")
        self.assertIsNone(state["terminal_state"])
        self.assertEqual(self.new().record_cancel_ack("operation-1", signal_recorded=True,
                                                       verify_ack=accept), state)
        self.assertEqual(sum(e["kind"] == "HOST_CANCEL_SIGNAL_ACKNOWLEDGED"
                             for e in self.db.events("operation-1")), 1)

    def test_dispatched_cancel_and_revoke_do_not_forge_terminal(self):
        self.db.prepare(self.spec, authorize=accept)
        self.db.claim_dispatch("operation-1", authorize=accept)
        self.db.signal_cancel("operation-1", reason_code="USER_CANCEL", authorize=accept)
        self.db.signal_revoke("operation-1", reason_code="SESSION_REVOKED", authorize=accept)
        current = self.new().status("operation-1")
        self.assertEqual(current["state"], "IN_FLIGHT")
        self.assertIsNone(current["terminal_state"])
        self.assertTrue(current["cancel_requested"])
        self.assertTrue(current["revoked"])
        # An effect may have applied before cancellation; don't lie about it.
        resolved = self.db.reconcile_receipt(self.spec, self.receipt(), verify_receipt=accept)
        self.assertEqual(resolved["terminal_state"], "APPLIED")
        self.assertTrue(resolved["cancel_requested"])
        with self.assertRaises(JournalRefusal):
            self.db.signal_cancel("operation-1", reason_code="LATE", authorize=accept)

    def test_restart_converts_flight_to_uncertain_without_retry(self):
        self.db.prepare(self.spec, authorize=accept)
        self.db.claim_dispatch("operation-1", authorize=accept)
        with self.assertRaises(JournalRefusal):
            self.db.reconcile_after_restart(authorize=deny)
        self.assertEqual(self.new().reconcile_after_restart(authorize=accept), ["operation-1"])
        self.assertEqual(self.new().reconcile_after_restart(authorize=accept), [])
        self.assertEqual(self.new().status("operation-1")["state"], "UNCERTAIN")
        with self.assertRaises(JournalRefusal):
            self.db.claim_dispatch("operation-1", authorize=accept)
        self.assertEqual(self.db.reconcile_receipt(self.spec, self.receipt(), verify_receipt=accept)["state"], "TERMINAL")

    def test_abrupt_child_process_exit_requires_host_reconciliation(self):
        # A real independent Python process durably claims delivery, then
        # terminates without shutdown, a receipt, or a cancellation callback.
        code = r"""
import os, sys
from pathlib import Path
from backend.nvp_lu_operation_journal import IPCOperationJournal, OriginRefs, OperationSpec
from hashlib import sha256
root = Path(sys.argv[1]); now = int(sys.argv[2])
accept = lambda *args: True  # test-only, not a real Lu broker
journal = IPCOperationJournal(root, storage_guard=lambda x: x == root,
                              clock_ms=lambda: now)
origin = OriginRefs('workspace-1','conversation-1','turn-1','task-1','operation-1')
spec = OperationSpec(origin,'nvp.film.project.read',1,2,
    sha256(b'typed-input').hexdigest(),sha256(b'object-refs').hexdigest(),
    now + 60000,'session-1','core-epoch-1')
journal.prepare(spec, authorize=accept)
journal.claim_dispatch('operation-1', authorize=accept)
os._exit(93)
"""
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        child = subprocess.run([sys.executable, "-c", code, str(self.root), str(self.now)],
                               env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 93, child.stderr)
        current = self.new().status("operation-1")
        self.assertEqual(current["state"], "IN_FLIGHT")
        self.assertEqual(self.new().reconcile_after_restart(authorize=accept), ["operation-1"])
        with self.assertRaises(JournalRefusal):
            self.new().claim_dispatch("operation-1", authorize=accept)
        self.assertEqual(self.new().status("operation-1")["state"], "UNCERTAIN")

    def test_uncertain_host_receipt_is_not_final_and_can_be_reconciled(self):
        self.db.prepare(self.spec, authorize=accept)
        self.db.claim_dispatch("operation-1", authorize=accept)
        unknown = self.receipt("UNCERTAIN", key=b"unknown", evidence=False)
        first = self.db.reconcile_receipt(self.spec, unknown, verify_receipt=accept)
        self.assertEqual(first["state"], "UNCERTAIN")
        self.assertIsNone(first["terminal_state"])
        count_before = len(self.db.events("operation-1"))
        self.assertEqual(self.db.reconcile_receipt(self.spec, unknown, verify_receipt=accept), first)
        self.assertEqual(len(self.db.events("operation-1")), count_before)
        resolved = self.new().reconcile_receipt(self.spec, self.receipt("REFUSED"), verify_receipt=accept)
        self.assertEqual(resolved["terminal_state"], "REFUSED")

    def test_receipt_requires_true_host_verification_and_identity(self):
        self.db.prepare(self.spec, authorize=accept)
        self.db.claim_dispatch("operation-1", authorize=accept)
        with self.assertRaises(JournalRefusal):
            self.db.reconcile_receipt(self.spec, self.receipt(), verify_receipt=deny)
        with self.assertRaises(PermissionError):
            self.receipt("APPLIED", evidence=False)
        changed = replace(self.spec, origin=replace(self.origin, task_ref="different-task"))
        with self.assertRaises(JournalRefusal):
            self.db.reconcile_receipt(changed, self.receipt(), verify_receipt=accept)
        with self.assertRaises(JournalRefusal):
            self.db.reconcile_receipt(self.spec, replace(self.receipt(), operation_ref="different"), verify_receipt=accept)
        self.assertEqual(self.db.status("operation-1")["state"], "IN_FLIGHT")

    def test_terminal_idempotency_and_conflicting_terminal_refusal(self):
        self.db.prepare(self.spec, authorize=accept)
        self.db.claim_dispatch("operation-1", authorize=accept)
        applied = self.db.reconcile_receipt(self.spec, self.receipt(), verify_receipt=accept)
        self.assertEqual(self.new().reconcile_receipt(self.spec, self.receipt(), verify_receipt=accept), applied)
        with self.assertRaises(JournalRefusal):
            self.db.reconcile_receipt(self.spec, self.receipt("FAILED"), verify_receipt=accept)
        with self.assertRaises(JournalRefusal):
            self.db.reconcile_receipt(self.spec, self.receipt(key=b"new"), verify_receipt=accept)
        with self.assertRaises(JournalRefusal):
            self.db.reconcile_receipt(self.spec,
                                      replace(self.receipt(), reason_code="OTHER_REASON"),
                                      verify_receipt=accept)
        self.assertEqual(self.db.status("operation-1")["terminal_state"], "APPLIED")

    def test_deadline_is_enforced_on_dispatch(self):
        self.db.prepare(self.spec, authorize=accept)
        self.now += 60_000
        with self.assertRaises(JournalRefusal):
            self.db.claim_dispatch("operation-1", authorize=accept)
        self.assertEqual(self.db.status("operation-1")["state"], "PREPARED")

    def test_storage_needs_a_real_external_guard_and_rejects_symlink(self):
        with self.assertRaises(JournalRefusal):
            IPCOperationJournal(self.root, storage_guard=deny)
        evil = self.root / "unexpected"
        evil.write_text("not a database", encoding="utf8")
        dbpath = self.root / "nvp-lu-operations.sqlite3"
        dbpath.unlink()
        dbpath.symlink_to(evil)
        with self.assertRaises(JournalRefusal):
            self.new()

    def test_storage_refuses_broad_posix_permission(self):
        if os.name != "posix":
            self.skipTest("POSIX permissions")
        os.chmod(self.root / "nvp-lu-operations.sqlite3", 0o644)
        with self.assertRaises(JournalRefusal):
            self.new()

    def test_integrity_and_no_secrets_in_journal(self):
        self.db.prepare(self.spec, authorize=accept)
        self.db.claim_dispatch("operation-1", authorize=accept)
        self.db.signal_cancel("operation-1", reason_code="USER_CANCEL", authorize=accept)
        self.db.reconcile_after_restart(authorize=accept)
        # The journal stores canonical origin refs, a typed input digest and
        # bounded event metadata, never encoded media, passwords or HMAC keys.
        with closing(sqlite3.connect(str(self.db.path))) as con:
            values = con.execute("SELECT bound_spec,request_sha256 FROM ipc_operations").fetchone()
        self.assertNotIn("secret", str(values).lower())
        self.assertEqual(len(values[1]), 64)
        self.assertEqual(self.db.status("operation-1")["state"], "UNCERTAIN")


if __name__ == "__main__":
    unittest.main()
