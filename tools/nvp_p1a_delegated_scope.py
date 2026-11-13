"""P1-A Linux native acceptance only: put the test host in its own subtree.

A systemd-run --scope Delegate=yes scope can still contain its foreground
process at the delegation root. In cgroup v2, domain memory/pids controllers
cannot be enabled there (EBUSY). Move ONLY the tasks belonging to this new
ephemeral test scope into its host subgroup, leaving the marked root empty.
Never edit an ancestor owned by systemd or grant a browser any cgroup path.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time

from backend.nvp_worker_linux_cgroup import current_delegated_parent


def main():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("Genuine native delegated-scope test requires root-owned ephemeral scope")
    parent = current_delegated_parent()
    if not parent.name.startswith("nvp-p1a-") or not parent.name.endswith(".scope"):
        raise RuntimeError("Refusing to reorganize anything except a dedicated P1-A systemd scope")
    mount = Path("/sys/fs/cgroup").resolve()
    if not parent.resolve().is_relative_to(mount):
        raise RuntimeError("Delegation escapes kernel cgroup v2 mount")
    host = parent / "nvp-host"
    if host.exists():
        raise RuntimeError("P1-A test host subgroup already exists")
    host.mkdir(mode=0o700)
    for _ in range(15):
        members=(parent/"cgroup.procs").read_text("ascii").split()
        for pid in members:
            if not pid.isdigit():
                raise RuntimeError("Invalid host cgroup process ID")
            try:
                (host/"cgroup.procs").write_text(pid, encoding="ascii")
            except ProcessLookupError:
                pass
        if not (parent/"cgroup.procs").read_text("ascii").strip():
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("Cannot establish empty delegated root for native cgroup acceptance")
    # The same OS process is now in the scope's host subgroup. Production
    # provisions private leaves as siblings, never moves systemd tasks.
    os.execv(sys.executable,[sys.executable,"-m","pytest","-vv",
       "tests/test_nvp_p1a_native_kernel.py","-k","linux_"])


if __name__=="__main__":
    main()
