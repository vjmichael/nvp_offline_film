"""Portable contract tests for bounded native Windows installed-process gates."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_p0f01_windows_process_gate import run, FORMAT


class P0F01NativeProcessGateTests(unittest.TestCase):
    def test_success_receipt_is_durable_and_source_labeled(self):
        with TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "steps.jsonl"
            code = run(stage="native-smoke", timeout_seconds=5, stage_log=receipt,
                       command=[sys.executable, "-c", "print('ok')"])
            self.assertEqual(code, 0)
            entries = [json.loads(line) for line in receipt.read_text().splitlines()]
            self.assertEqual([e["status"] for e in entries],
                             ["starting", "launched", "passed"])
            self.assertTrue(all(e["format"] == FORMAT for e in entries))
            self.assertEqual(entries[-1]["exit_code"], 0)

    def test_nonzero_exits_do_not_pass(self):
        with TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "steps.jsonl"
            result = run(stage="failed-app", timeout_seconds=5, stage_log=receipt,
                         command=[sys.executable, "-c", "raise SystemExit(17)"])
            self.assertEqual(result, 3)
            self.assertEqual(json.loads(receipt.read_text().splitlines()[-1])["exit_code"], 17)

    def test_timeout_is_not_a_pass_and_is_reaped(self):
        with TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "steps.jsonl"
            result = run(stage="hung-app", timeout_seconds=0.15, stage_log=receipt,
                         command=[sys.executable, "-c", "import time; time.sleep(30)"])
            self.assertEqual(result, 2)
            entries = [json.loads(s) for s in receipt.read_text().splitlines()]
            self.assertEqual(entries[-1]["status"], "timeout")
            self.assertNotIn("passed", [e["status"] for e in entries])

    def test_path_and_scope_validation(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "steps.jsonl"
            for stage in ("", "bad/name", "native exploit"):
                with self.subTest(stage=stage), self.assertRaises(ValueError):
                    run(stage=stage, timeout_seconds=1, stage_log=p, command=[sys.executable])
            with self.assertRaises(ValueError):
                run(stage="install", timeout_seconds=0, stage_log=p, command=[sys.executable])
            with self.assertRaises(ValueError):
                run(stage="install", timeout_seconds=1, stage_log=p, command=[])

    def test_missing_executable_is_not_a_pass(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "steps.jsonl"
            result = run(stage="missing", timeout_seconds=1, stage_log=p,
                         command=[str(Path(tmp) / "absent.exe")])
            self.assertEqual(result, 1)
            self.assertEqual(json.loads(p.read_text().splitlines()[-1])["status"], "launch_failed")


if __name__ == "__main__":
    unittest.main()
