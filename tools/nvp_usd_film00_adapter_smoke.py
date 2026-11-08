"""USD-FILM-00: independently execute existing NVP OpenUSD adapter suites.

Keep genuine source integration tests separate from generic pxr schema support.
No individual test suite is silently skipped; all statuses and bounded real
stdout excerpts are captured even when later suites continue/fail.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

FORMAT = "nvp.usd_film00.existing_adapter_native_regressions.v1"
SUITES = (
    "test_nvp_openusd_take_native.py",
    "test_nvp_openusd_reusable_assets.py",
    "test_nvp_openusd_native_schemas.py",
    "test_nvp_native_usd_facial_material.py",
    "test_nvp_wo3_materialx_integrity.py",
)


def run_all(*, timeout_each=240):
    root = Path(__file__).resolve().parents[1]
    cases = []
    for suite in SUITES:
        case_file = root / "tests" / suite
        if not case_file.is_file():
            cases.append({"suite": suite, "status": "MISSING_TEST", "exit_code": None})
            continue
        start = time.monotonic()
        args = [
            sys.executable, "-m", "unittest", "discover",
            "-s", "tests", "-p", suite, "-v",
        ]
        try:
            p = subprocess.run(
                args, cwd=root, capture_output=True, text=True,
                timeout=timeout_each, check=False,
                encoding="utf8", errors="replace",
            )
            output = p.stdout + "\n" + p.stderr
            ok = p.returncode == 0
            result = {"suite": suite, "status": "PASS" if ok else "FAIL",
                      "exit_code": p.returncode}
        except subprocess.TimeoutExpired as exc:
            chunks = [exc.stdout or b"", exc.stderr or b""]
            output = "\n".join(
                c.decode("utf8", "replace") if isinstance(c, bytes) else c
                for c in chunks)
            result = {"suite": suite, "status": "TIMEOUT", "exit_code": None}
        result["elapsed_seconds"] = round(time.monotonic() - start, 3)
        result["output_tail"] = output[-18000:]
        cases.append(result)
        print(f"[USD-FILM-00] {suite}: {result['status']}",
              flush=True)
        if result["status"] != "PASS":
            print(result["output_tail"][-7000:], flush=True)
    return {
        "format": FORMAT, "python": sys.version.split()[0],
        "os": platform.platform(),
        "git_sha_reported": os.environ.get("GITHUB_SHA", "NOT_IN_CI"),
        "cases": cases, "all_real_existing_adapter_regressions_passed": all(
            c["status"] == "PASS" for c in cases),
        "rendered_pixels_accepted": False,
        "installed_blender_accepted": False,
        "photorealism_accepted": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    target = Path(args.output).resolve()
    if not target.parent.is_dir():
        raise ValueError("Native adapter audit output directory does not exist")
    report = run_all()
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", "utf8")
    return 0 if report["all_real_existing_adapter_regressions_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
