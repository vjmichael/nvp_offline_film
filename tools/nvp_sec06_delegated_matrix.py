"""Independent SEC-06 delegated Linux native matrix.

Invoked ONLY by an actual systemd-run transient service with Delegate=yes,
DelegateSubgroup=host. The service controller, not this Python program,
provisions the kernel cgroup. No mocked delegation or skip permits acceptance.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from backend.nvp_worker_linux_cgroup import (
    CGROUP_MOUNT, current_cgroup_relative, current_delegated_parent,
)

REQUIRED = (
    "test_audio_linux_strict_cgroup.py",
    "test_nvp_sec06_linux_ancestor_migration.py",
    "test_audio_native_os_termination.py",
    "test_audio_admission_outbox.py",
    "test_audio_admission_crash_gap.py",
    "test_nvp_w1g_protected_upgrade.py",
    "test_nvp_w1g_production_authority.py",
)


def main() -> int:
    if sys.platform != "linux" or os.environ.get("NVP_REQUIRE_DELEGATED_CGROUP") != "1":
        raise RuntimeError("SEC-06 native delegated Linux runner requires explicit kernel mode")
    scope = current_delegated_parent().resolve(strict=True)
    host = (CGROUP_MOUNT / current_cgroup_relative().lstrip("/")).resolve(strict=True)
    if host == scope or not host.is_relative_to(scope):
        raise RuntimeError("SEC-06 host must be placed in a real delegated subgroup")
    if not {"memory", "pids"}.issubset(
        set((scope / "cgroup.controllers").read_text("ascii").split())
    ):
        raise RuntimeError("SEC-06 delegated memory and pids controllers unavailable")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    print("SEC-06 exact-head source SHA:", source, flush=True)
    print("SEC-06 kernel delegated parent:", scope, flush=True)
    print("SEC-06 kernel host subgroup:", host, flush=True)
    for pattern in REQUIRED:
        print("SEC-06 native OS fixture:", pattern, flush=True)
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s",
                        "tests", "-p", pattern, "-v"], check=True)
    # The integrated P1-A original ADC producer must be admitted by the
    # SAME delegated service/guardian/kernel policy as the SEC-06 worker.
    # Pytest-selected native Linux cases are mandatory; no skipped mock pass.
    print("SEC-06 + P1-A native delegated kernel producer fixtures",flush=True)
    subprocess.run([sys.executable,"-m","pytest","-vv",
                    "tests/test_nvp_p1a_native_kernel.py","-k","linux_"],
                   check=True)
    print("SEC-06 completed real delegated Linux matrix at", source, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
