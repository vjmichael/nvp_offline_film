"""DA-03 direct-child custody deadline regressions (no FFmpeg)."""
import math
import subprocess
import sys
import unittest

from backend.nvp_filming_worker_custody import OwnedFilmingWorker


class WorkerDeadlineTests(unittest.TestCase):
    def test_nonfinite_and_boolean_deadlines_fail_before_signalling_child(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
        try:
            owner = OwnedFilmingWorker(process)
            for timeout in (float("nan"), float("inf"), -float("inf"), True, False, 0, 61):
                with self.subTest(timeout=repr(timeout)):
                    with self.assertRaises(ValueError):
                        owner.stop_and_verify(timeout=timeout)
                    self.assertIsNone(process.poll())
            receipt = owner.stop_and_verify(timeout=5)
            self.assertTrue(receipt.exited)
            self.assertEqual(receipt.pid, process.pid)
            self.assertTrue(receipt.direct_child_only)
            with self.assertRaises(RuntimeError):
                owner.stop_and_verify()
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)

    def test_already_exited_owned_child_can_be_reaped_once(self):
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait(timeout=5)
        receipt = OwnedFilmingWorker(process).stop_and_verify(timeout=1)
        self.assertEqual(receipt.returncode, 0)
        self.assertTrue(receipt.direct_child_only)


if __name__ == "__main__":
    unittest.main()
