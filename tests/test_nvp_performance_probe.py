import json
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from backend import nvp_performance_probe as p


class ProbeTests(unittest.TestCase):
    def test_off_does_not_sample(self):
        @p.measured("usd.open")
        def f(x): return x
        with patch.object(p, "_snapshot", side_effect=AssertionError("sampled")):
            self.assertEqual(f(3), 3)

    def test_return_and_exception_preserved(self):
        @p.measured("usd.open")
        def f(): return object()
        with p.observe() as s:
            self.assertIsNotNone(f())
            with self.assertRaisesRegex(RuntimeError, "secret"):
                with p.span("usd.open"): raise RuntimeError("secret")
        r = s.report()
        self.assertEqual(r["stages"]["usd.open"]["calls"], 2)
        self.assertEqual(r["stages"]["usd.open"]["raised"], 1)
        self.assertNotIn("secret", json.dumps(r))
        self.assertIsNone(r["gpu_memory_bytes"])

    def test_bounded_and_nested(self):
        with p.observe() as a:
            for _ in range(1000):
                with p.span("reel.frame"): pass
            with p.observe() as b:
                with p.span("reel.frame"): pass
            with p.span("untrusted_project_name"): pass
        self.assertEqual(a.rows["reel.frame"]["calls"], 1000)
        self.assertEqual(len(a.rows), 1)
        self.assertEqual(b.rows["reel.frame"]["calls"], 1)
        self.assertIsNone(p._ACTIVE.get())

    def test_unknown_not_zero(self):
        with patch.object(p, "_snapshot", return_value=dict.fromkeys(p.HOST_FIELDS)):
            with p.observe() as s:
                with p.span("usd.compose"): pass
        row = s.rows["usd.compose"]
        self.assertIsNone(row["peak_rss_bytes"])
        self.assertIsNone(row["read_bytes"])
        self.assertEqual(row["io_sample_pairs"], 0)

    def test_observer_failure_never_changes_authority(self):
        with p.observe() as s:
            with patch.object(p, "_snapshot", side_effect=OSError("bad")):
                with self.assertRaises(PermissionError):
                    with p.span("take.worker"): raise PermissionError("denied")
        self.assertEqual(s.observation_errors, 1)

    def test_job_accounting_only_closed(self):
        fake = SimpleNamespace(JobObjectBasicAccountingInformation=1,
            JobObjectExtendedLimitInformation=2)
        fake.QueryInformationJobObject = lambda h, kind: (
            {"ActiveProcesses": 0, "TotalUserTime": 12, "TotalKernelTime": 8}
            if kind == 1 else {"PeakJobMemoryUsed": 4096})
        with patch.dict(sys.modules, {"win32job": fake}):
            with p.observe() as s:
                p.observe_windows_job(object())
                p.observe_windows_job(object())
        self.assertEqual(s.job, {"samples": 2, "cpu_samples": 2, "commit_samples": 2,
                                 "cpu_100ns": 40, "peak_commit_bytes": 4096})

    def test_cache_return_value_unchanged(self):
        @p.measured("cache.lookup")
        def lookup(value): return value
        result = object()
        with p.observe() as s:
            self.assertIs(lookup(result), result)
            self.assertIsNone(lookup(None))
        self.assertEqual(s.cache, {"hits": 1, "misses": 1})

    def test_real_host_measurement(self):
        with p.observe() as s:
            with p.span("reel.analysis"):
                data = bytearray(1024 * 1024)
                self.assertEqual(len(data), 1024 * 1024)
        row = s.rows["reel.analysis"]
        self.assertGreater(row["wall_ns"], 0)
        self.assertGreaterEqual(row["cpu_ns"], 0)
        if sys.platform.startswith("linux"):
            self.assertGreater(row["peak_rss_bytes"], 0)

if __name__ == "__main__": unittest.main()
