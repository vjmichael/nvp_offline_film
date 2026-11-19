"""Opt-in observer for existing public-fixture native suites, never creator data."""
import argparse
import json
import sys
import unittest
from pathlib import Path

from backend.nvp_performance_probe import observe

SUITES = {
    "usd": "test_nvp_openusd_take_native.py",
    "take": "test_nvp_wo6_native_take_action.py",
    "cycles": "test_nvp_conv12_real_private_720_windows.py",
    "reel": "test_nvp_p1def_p2_native.py",
    "cache": "test_nvp_slate05_preview_native.py",
}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=sorted(SUITES))
    parser.add_argument("--require-adapter-sample", action="store_true",
                        help="Require observed adapter-global memory, not GPU render qualification")
    args = parser.parse_args(argv)
    tests = Path(__file__).resolve().parents[1] / "tests"
    suite = unittest.defaultTestLoader.discover(str(tests), pattern=SUITES[args.suite])
    if suite.countTestCases() == 0:
        raise RuntimeError("Original acceptance tests missing")
    with observe(gpu=True) as session:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = session.report()
    report.update(suite=args.suite, tests_run=result.testsRun,
                  skipped=len(result.skipped), tests_successful=result.wasSuccessful())
    print("NVP_PERF_OBSERVATION " + json.dumps(report, sort_keys=True), flush=True)
    if args.require_adapter_sample and not any(
            row["scope"] == "adapter_global" and row["peak_dedicated_used_bytes"] is not None
            for row in report["gpu"]["sensors"]):
        print("NVP_PERF_ADAPTER_SAMPLE_UNAVAILABLE", flush=True)
        return 2
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
