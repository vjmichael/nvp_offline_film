"""Real SQLite lifecycle and single-use native control; no OS worker mock claim."""
import unittest
import test_nvp_wo6_retake_recovery as fixtures
from backend.nvp_wo6_retake_control import RetakeControl


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RecoveryTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def test_preparation_cancel_and_single_use(self):
        control = RetakeControl()
        self.assertEqual(control.request(), "NOT_READY")
        with self.fixture.recovery() as recovery:
            task, _ = self.fixture.setup_task(recovery)
            control.bind(recovery, task)
            self.assertEqual(control.request(), "CANCELLATION_REQUESTED")
            self.assertTrue(recovery.cancelled(task))
            self.assertEqual(self.fixture.ledger.get_task(task)["state"], "ACTIVE")
            self.assertEqual(recovery.reconcile(self.fixture.index, self.fixture.pid), [(task, "CANCELLED")])
            self.assertEqual(control.request(), "TOO_LATE")
            control.close()
            with self.assertRaises(PermissionError):
                control.bind(recovery, task)
        self.assertEqual(control.request(), "NOT_ACTIVE")

    def test_late_request_cannot_change_publication(self):
        with self.fixture.recovery() as recovery:
            task, _ = self.fixture.setup_task(recovery, "CUSTODY_CLOSED")
            control = RetakeControl()
            control.bind(recovery, task)
            recovery.publication_pending(task, {"receipt": True})
            self.assertEqual(control.request(), "TOO_LATE")
            self.assertFalse(recovery.cancelled(task))
            control.close()

    def test_unbound_handle_cannot_cancel_another_operation(self):
        with self.fixture.recovery() as recovery:
            task, _ = self.fixture.setup_task(recovery)
            first, other = RetakeControl(), RetakeControl()
            first.bind(recovery, task)
            self.assertEqual(other.request(), "NOT_READY")
            self.assertFalse(recovery.cancelled(task))
            first.close()
            self.assertEqual(first.request(), "NOT_ACTIVE")
            self.assertFalse(recovery.cancelled(task))


if __name__ == "__main__":
    unittest.main()
