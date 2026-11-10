"""Linux cgroup-v2 filming worker shutdown boundary.

Only accepts a host-created, private cgroup directory. The caller must own
creation/delegation and launch the worker inside it *before* publishing data.
Never reconstruct authority from a PID, journal field, or browser path.
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path


class CgroupCustodyError(RuntimeError):
    pass


class LinuxFilmingCgroup:
    """One-use host-owned cgroup-v2 kill and empty-group verification."""

    def __init__(self, *, private_group: Path, delegated_root: Path):
        if os.name != "posix" or not Path("/sys/fs/cgroup/cgroup.controllers").is_file():
            raise CgroupCustodyError("Linux cgroup v2 required")
        root = Path(delegated_root).resolve(strict=True)
        group = Path(private_group).resolve(strict=True)
        if group.parent != root or group == root:
            raise CgroupCustodyError("Only a direct child of the delegated root is allowed")
        if not (root / "cgroup.controllers").is_file():
            raise CgroupCustodyError("Delegated root is not cgroup v2")
        if not (group / "cgroup.kill").is_file() or not (group / "cgroup.events").is_file():
            raise CgroupCustodyError("Missing kernel cgroup-v2 custody controls")
        self._group = group
        self._consumed = False
        self._kill_requested = False

    def stop_and_verify(self, *, timeout: float = 5.0) -> dict:
        if self._consumed:
            raise CgroupCustodyError("Cgroup custody receipt already consumed")
        if type(timeout) not in (float, int) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("Bounded positive deadline required")
        deadline = time.monotonic() + timeout
        # cgroup.kill is kernel-wide for the entire subtree; unlike killpg it
        # includes descendants that create new process sessions.
        if not getattr(self, "_kill_requested", False):
            (self._group / "cgroup.kill").write_text("1", encoding="ascii")
            self._kill_requested = True
        while True:
            fields = {}
            for line in (self._group / "cgroup.events").read_text(encoding="ascii").splitlines():
                parts = line.split()
                if len(parts) != 2 or parts[0] in fields:
                    raise CgroupCustodyError("Malformed or duplicate cgroup.events field")
                fields[parts[0]] = parts[1]
            if fields.get("populated") == "0":
                self._consumed = True
                return {"process_tree_custody_verified": True,
                        "scope": "linux-cgroup-v2", "empty_group_verified": True}
            if fields.get("populated") != "1":
                raise CgroupCustodyError("Invalid cgroup.events populated state")
            if time.monotonic() >= deadline:
                raise CgroupCustodyError("Cgroup still populated after bounded kill")
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
