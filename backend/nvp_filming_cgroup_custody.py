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
        # Pin the cgroup directory identity. A removed/recreated private group
        # must never inherit an old host custody handle or its kill receipt.
        identity = group.stat()
        self._group_identity = (identity.st_dev, identity.st_ino)
        self._consumed = False
        self._kill_requested = False

    def _verify_group_identity(self) -> None:
        expected = getattr(self, "_group_identity", None)
        if expected is None:
            raise CgroupCustodyError("Unpinned cgroup ownership identity")
        try:
            actual = self._group.stat()
        except OSError as exc:
            raise CgroupCustodyError("Owned cgroup is no longer accessible") from exc
        if (actual.st_dev, actual.st_ino) != expected:
            raise CgroupCustodyError("Owned cgroup was replaced; custody revoked")

    def _open_owned_control(self, control: str, flags: int) -> int:
        """Open a kernel control relative to a pinned directory descriptor.

        The directory is checked again after opening; path replacement cannot
        redirect a write to an unrelated cgroup between stat() and open().
        """
        self._verify_group_identity()
        directory = os.open(self._group, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            identity = os.fstat(directory)
            if (identity.st_dev, identity.st_ino) != self._group_identity:
                raise CgroupCustodyError("Owned cgroup changed during control open")
            control_fd = os.open(control, flags | os.O_NOFOLLOW, dir_fd=directory)
            return control_fd
        finally:
            os.close(directory)

    def _read_events(self) -> str:
        fd = self._open_owned_control("cgroup.events", os.O_RDONLY)
        try:
            with os.fdopen(fd, "r", encoding="ascii") as stream:
                return stream.read(4096)
        except BaseException:
            # fdopen owns the descriptor once successfully constructed.
            raise

    def _request_kill(self) -> None:
        fd = self._open_owned_control("cgroup.kill", os.O_WRONLY)
        with os.fdopen(fd, "wb") as stream:
            stream.write(b"1")
            stream.flush()

    def verify_still_empty(self) -> dict:
        """Fresh kernel observation before reusing a one-use empty-tree receipt.

        A previous populated=0 observation is not permanent: an external
        actor could repopulate the group before worker reaping is retried.
        Never issue a second cgroup.kill to address that possibility.
        """
        if not self._consumed:
            raise CgroupCustodyError("No consumed kernel custody receipt to revalidate")
        self._verify_group_identity()
        fields = {}
        for line in self._read_events().splitlines():
            parts = line.split()
            if len(parts) != 2 or parts[0] in fields:
                raise CgroupCustodyError("Malformed or duplicate cgroup.events field")
            fields[parts[0]] = parts[1]
        if fields.get("populated") != "0":
            raise CgroupCustodyError("Previously emptied filming cgroup is no longer empty")
        self._verify_group_identity()
        return {"process_tree_custody_verified": True,
                "scope": "linux-cgroup-v2", "empty_group_verified": True}

    def stop_and_verify(self, *, timeout: float = 5.0) -> dict:
        if self._consumed:
            raise CgroupCustodyError("Cgroup custody receipt already consumed")
        if type(timeout) not in (float, int) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("Bounded positive deadline required")
        self._verify_group_identity()
        deadline = time.monotonic() + timeout
        # cgroup.kill is kernel-wide for the entire subtree; unlike killpg it
        # includes descendants that create new process sessions.
        if not getattr(self, "_kill_requested", False):
            # A write may reach the kernel before userspace observes an I/O
            # failure. Consume the request *before* issuing it: after an
            # ambiguous failure, retry may only observe cgroup.events, never
            # send a second destructive request to a potentially changed tree.
            self._kill_requested = True
            self._request_kill()
        while True:
            self._verify_group_identity()
            fields = {}
            for line in self._read_events().splitlines():
                parts = line.split()
                if len(parts) != 2 or parts[0] in fields:
                    raise CgroupCustodyError("Malformed or duplicate cgroup.events field")
                fields[parts[0]] = parts[1]
            if fields.get("populated") == "0":
                self._verify_group_identity()
                self._consumed = True
                return {"process_tree_custody_verified": True,
                        "scope": "linux-cgroup-v2", "empty_group_verified": True}
            if fields.get("populated") != "1":
                raise CgroupCustodyError("Invalid cgroup.events populated state")
            if time.monotonic() >= deadline:
                raise CgroupCustodyError("Cgroup still populated after bounded kill")
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
