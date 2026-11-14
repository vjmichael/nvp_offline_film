"""DA-03 direct-child custody tests; no native process-tree claim."""
import subprocess
import math
import os
import sys
import unittest
from unittest import mock

from backend.nvp_filming_worker_custody import OwnedFilmingWorker


class FakeJournal:
    def __init__(self):
        self.calls = []

    def interrupt_preparing(self, project_id, take_id, *, expected_updated_at):
        self.calls.append((project_id, take_id, expected_updated_at))
        return {"take_id": take_id, "state": "INTERRUPTED"}


@unittest.skipIf(os.name=="nt","Legacy direct-child filming retired on Windows; use native Job session")
class FilmingWorkerCustodyTests(unittest.TestCase):
    def spawn(self):
        return subprocess.Popen([sys.executable, "-c",
                                 "import time; time.sleep(30)"],
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)

    def test_real_child_exit_precedes_journal_transition(self):
        process = self.spawn()
        try:
            journal = FakeJournal()
            worker = OwnedFilmingWorker(process)
            result = worker.interrupt_journal(
                journal, "project", "take", expected_updated_at="observed",
                timeout=2, allow_direct_child_only=True)
            self.assertIsNotNone(process.poll())
            self.assertEqual(journal.calls, [("project", "take", "observed")])
            self.assertTrue(result["direct_child_exit_verified"])
            self.assertFalse(result["process_tree_custody_verified"])
            with self.assertRaises(RuntimeError):
                worker.stop_and_verify()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_default_rejects_unverified_descendants_without_stopping_worker(self):
        process = self.spawn()
        try:
            journal = FakeJournal()
            worker = OwnedFilmingWorker(process)
            with self.assertRaisesRegex(RuntimeError, "Process-tree custody unverified"):
                worker.interrupt_journal(journal, "project", "take",
                                         expected_updated_at="observed")
            self.assertIsNone(process.poll())
            self.assertEqual(journal.calls, [])
            receipt = worker.stop_and_verify(timeout=2)
            self.assertTrue(receipt.direct_child_only)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_nonfinite_and_boolean_deadlines_fail_without_journal_mutation(self):
        process = self.spawn()
        try:
            journal = FakeJournal()
            worker = OwnedFilmingWorker(process)
            for invalid in (float("nan"), float("inf"), -float("inf"), True, False):
                with self.subTest(timeout=repr(invalid)):
                    with self.assertRaises(ValueError):
                        worker.interrupt_journal(
                            journal, "project", "take",
                            expected_updated_at="observed", timeout=invalid,
                            allow_direct_child_only=True)
            self.assertEqual(journal.calls, [])
            self.assertIsNone(process.poll())
        finally:
            process.kill()
            process.wait()

    def test_already_exited_child_is_reaped_once(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.exit(7)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        process.wait(timeout=5)
        worker = OwnedFilmingWorker(process)
        receipt = worker.stop_and_verify(timeout=1)
        self.assertTrue(receipt.exited)
        self.assertEqual(receipt.returncode, 7)
        with self.assertRaises(RuntimeError):
            worker.stop_and_verify(timeout=1)

    def test_timeout_retry_does_not_repeat_graceful_signal(self):
        process = self.spawn()
        try:
            worker = OwnedFilmingWorker(process)
            original_wait = process.wait
            attempts = [0]

            def first_wait_times_out(*args, **kwargs):
                attempts[0] += 1
                if attempts[0] <= 2:
                    raise subprocess.TimeoutExpired(process.args, kwargs.get("timeout"))
                return original_wait(*args, **kwargs)

            with mock.patch.object(process, "wait", side_effect=first_wait_times_out), \
                 mock.patch.object(process, "terminate", wraps=process.terminate) as terminate:
                with self.assertRaises(subprocess.TimeoutExpired):
                    worker.stop_and_verify(timeout=0.1)
                # A failed exit attestation must not consume the handle.
                receipt = worker.stop_and_verify(timeout=2)
                self.assertTrue(receipt.exited)
                self.assertEqual(terminate.call_count, 1)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_timeout_retry_never_reissues_forced_kill(self):
        process = self.spawn()
        try:
            worker = OwnedFilmingWorker(process)
            original_wait = process.wait
            attempts = [0]

            def delayed_reap(*args, **kwargs):
                attempts[0] += 1
                if attempts[0] <= 2:
                    raise subprocess.TimeoutExpired(process.args, kwargs.get("timeout"))
                return original_wait(*args, **kwargs)

            with mock.patch.object(process, "wait", side_effect=delayed_reap), \
                 mock.patch.object(process, "kill", wraps=process.kill) as kill:
                with self.assertRaises(subprocess.TimeoutExpired):
                    worker.stop_and_verify(timeout=0.1)
                receipt = worker.stop_and_verify(timeout=2)
                self.assertTrue(receipt.exited)
                self.assertEqual(kill.call_count, 1)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_pid_alone_cannot_be_admitted(self):
        with self.assertRaises(TypeError):
            OwnedFilmingWorker(12345)

    def test_bad_timeout_cannot_interrupt_journal(self):
        process = self.spawn()
        try:
            journal = FakeJournal()
            worker = OwnedFilmingWorker(process)
            with self.assertRaises(ValueError):
                worker.interrupt_journal(
                    journal, "project", "take",
                    expected_updated_at="observed", timeout=0,
                    allow_direct_child_only=True)
            self.assertEqual(journal.calls, [])
        finally:
            process.kill()
            process.wait()


if __name__ == "__main__":
    unittest.main()


class WindowsDirectChildRefusal(unittest.TestCase):
    @unittest.skipUnless(os.name=="nt","Windows original kernel gate only")
    def test_direct_popen_can_never_publish_original_take(self):
        process=subprocess.Popen([sys.executable,"-c","import time; time.sleep(5)"],
              stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            with self.assertRaisesRegex(RuntimeError,"direct-child filming retired"):
                OwnedFilmingWorker(process)
        finally:
            process.kill();process.wait()
