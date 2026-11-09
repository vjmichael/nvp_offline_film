"""DA-03 direct-child custody tests; no native process-tree claim."""
import subprocess
import sys
import unittest

from backend.nvp_filming_worker_custody import OwnedFilmingWorker


class FakeJournal:
    def __init__(self):
        self.calls = []

    def interrupt_preparing(self, project_id, take_id, *, expected_updated_at):
        self.calls.append((project_id, take_id, expected_updated_at))
        return {"take_id": take_id, "state": "INTERRUPTED"}


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
                timeout=2)
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
                    expected_updated_at="observed", timeout=0)
            self.assertEqual(journal.calls, [])
        finally:
            process.kill()
            process.wait()


if __name__ == "__main__":
    unittest.main()
