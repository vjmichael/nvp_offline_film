"""Pressure watchdog tests: no sleep, no real OS kills, no resource fake release."""
import subprocess
import unittest

from backend.nvp_resource_supervisor import wait_guarded, ResourceGuardStop


class FakeWorker:
    def __init__(self, sequence=None):
        self.sequence = list(sequence or [None])
        self.stopped = False
        self.waited = False

    def poll(self):
        return self.sequence.pop(0) if len(self.sequence) > 1 else self.sequence[0]

    def terminate_tree(self):
        self.stopped = True
        self.sequence = [-9]

    def wait(self, timeout=None):
        self.waited = True
        return self.poll()


class FakeLedger:
    def __init__(self, samples):
        self.samples = list(samples)
        self.calls = 0

    def critical_pressure(self, task_id):
        self.calls += 1
        return self.samples.pop(0) if self.samples else None


class WatchdogAcceptance(unittest.TestCase):
    def run_guard(self, worker, ledger, times=None, timeout=20):
        tick = iter(times or [0] * 20)
        return wait_guarded(worker, ledger, "job_1", timeout_seconds=timeout,
                            clock=lambda: next(tick), sleep=lambda _: None)

    def test_success_reaps_worker_without_terminating(self):
        w = FakeWorker([None, 0])
        self.assertEqual(self.run_guard(w, FakeLedger([None])), 0)
        self.assertTrue(w.waited)
        self.assertFalse(w.stopped)

    def test_single_spike_does_not_kill(self):
        w = FakeWorker([None, None, 0])
        self.assertEqual(self.run_guard(w, FakeLedger(["pressure", None])), 0)
        self.assertFalse(w.stopped)

    def test_consecutive_pressure_terminates_only_owned_worker(self):
        w = FakeWorker([None, None, None])
        ledger = FakeLedger(["pressure", "pressure"])
        with self.assertRaises(ResourceGuardStop):
            self.run_guard(w, ledger)
        self.assertTrue(w.stopped)
        self.assertEqual(ledger.calls, 2)

    def test_recovered_pressure_resets_strikes(self):
        w = FakeWorker([None, None, None, None, 0])
        self.assertEqual(self.run_guard(w, FakeLedger(["bad", None, "bad", None])), 0)
        self.assertFalse(w.stopped)

    def test_timeout_terminates(self):
        w = FakeWorker([None, None])
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_guard(w, FakeLedger([None]), times=[0, 2], timeout=1)
        self.assertTrue(w.stopped)

    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):
            wait_guarded(FakeWorker(), FakeLedger([]), "job_1",
                         timeout_seconds=10, critical_samples=1)

    def test_worker_must_be_contained_interface(self):
        with self.assertRaises(TypeError):
            wait_guarded(object(), FakeLedger([]), "job_1", timeout_seconds=10)


if __name__ == "__main__":
    unittest.main()
