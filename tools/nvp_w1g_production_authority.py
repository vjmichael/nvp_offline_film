"""W1-G production-only native Windows authority boundary for NSIS mutation.

A callable lambda, user-authored JSON receipt, PID list, or CI callback is
NOT an upgrade authorization. Production operators must instantiate these
native classes on Windows. No simulated approvals can enter this path.

This is a source integration point, NOT a claim that all NVP app domains
already share one kernel-owned release-wide worker roster. The release
coordinator must supply every original supervised workspace and a genuine
Windows Job Object that owns the release worker process tree; if coverage is
unavailable, the transaction is refused rather than guessed.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import threading
import time


class WindowsCreatorUpgradeApproval:
    """Real Windows OS modal approval with exact scope and one-use behavior."""

    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("Production creator approval requires Windows desktop")
        self._lock = threading.RLock()
        self._used = set()

    def __call__(self, scope):
        if (type(scope) is not dict or
            type(scope.get("operation")) is not str or
            not scope["operation"].startswith("nvp.w1g.nsis.")):
            raise PermissionError("Only native W1-G installer scopes may be reviewed")
        canonical = json.dumps(scope, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False)
        if len(canonical) > 3500:
            raise PermissionError("Unbounded native upgrade authorization")
        digest = sha256(canonical.encode("ascii")).hexdigest()
        with self._lock:
            if digest in self._used:
                raise PermissionError("A previous native upgrade approval was consumed")
            self._used.add(digest)
        import ctypes
        # MessageBoxW is a real OS-owned modal dialog, not a browser callback.
        # Default to NO, never silent consent and never treat a closed dialog
        # as approval. The operation and SHA identities are shown verbatim.
        text = ("This changes locally installed NVP program files.\n"
                "Original film files must not be changed.\n"
                "Do you authorize this ONE exact action?\n\n"
                +canonical)
        result = ctypes.windll.user32.MessageBoxW(
            0, text, "NVP — Authorize Installed Program Change",
            0x00000004 | 0x00000020 | 0x00000100)
        return result == 6


class WindowsReleaseWorkerStopEvidence:
    """Windows Job accounting plus exclusive original worker-host leases.

    Genuine kernel inspection is only meaningful with COMPLETE source
    coverage: a Windows Job handle that was retained by the original
    release supervisor and ALL its corresponding on-disk worker journals.
    No bare user-supplied PID/Boolean is accepted.

    The caller holds transaction() across both authorization and the
    filesystem swap, preventing launches through the worker host leases.
    """

    def __init__(self, installed_program: Path, *, release_job,
                 worker_workspaces: tuple[Path, ...]):
        if os.name != "nt":
            raise RuntimeError("Windows Job Object custody requires Windows")
        from backend.nvp_worker_containment import WindowsJobProcess
        if type(release_job) is not WindowsJobProcess or release_job._job is None:
            raise TypeError("Original supervisor-owned Windows Job handle required")
        if type(worker_workspaces) is not tuple or not worker_workspaces:
            raise TypeError("Explicit full release worker-workspace roster required")
        self.program = Path(installed_program)
        self.release_job = release_job
        self.workspaces = tuple(sorted({Path(p).resolve() for p in worker_workspaces}))
        if len(self.workspaces) != len(worker_workspaces):
            raise RuntimeError("Duplicate or ambiguous original worker workspace")
        self._held = False
        self._mutex = threading.Lock()

    @contextmanager
    def transaction(self):
        if not self._mutex.acquire(blocking=False):
            raise RuntimeError("Another release authorization is underway")
        try:
            from backend.nvp_worker_host_lease import WorkerHostLease
            with ExitStack() as stack:
                for root in self.workspaces:
                    if not root.is_dir() or root.is_symlink():
                        raise RuntimeError("Original worker journal workspace unavailable")
                    stack.enter_context(WorkerHostLease(root))
                self._held = True
                try:
                    yield self
                finally:
                    self._held = False
        finally:
            self._mutex.release()

    def __call__(self, original_sha):
        if not self._held:
            raise PermissionError("Kernel evidence requires held worker admission leases")
        from tools.nvp_w1g_nsis_recovery import _digest, _program
        from backend.nvp_worker_containment import WindowsJobProcess
        if (type(self.release_job) is not WindowsJobProcess or
            self.release_job._job is None):
            raise PermissionError("Original supervisor Job Object handle disappeared")
        # Atomic NSIS renames may park the ORIGINAL executable under
        # NVP.previous (upgrade) or NVP.failed (rollback) while the native
        # release lease and OS-owned Job Object remain held. Refuse any
        # unrecognized old-runtime bytes, absent source or symlink.
        candidates=(self.program,
                    self.program.with_name("NVP.previous"),
                    self.program.with_name("NVP.failed"))
        observed=[]
        for candidate in candidates:
            if candidate.exists() or candidate.is_symlink():
                observed.append(_digest(_program(candidate)))
        if original_sha not in observed:
            raise PermissionError("Original installed/parked release differs from kernel scope")
        import win32job
        info = win32job.QueryInformationJobObject(
            self.release_job._job, win32job.JobObjectBasicAccountingInformation)
        if (type(info.get("ActiveProcesses")) is not int or
            info["ActiveProcesses"] != 0):
            raise PermissionError("Release Job Object still has live descendants")
        for root in self.workspaces:
            for row in root.glob("worker_jobs.sqlite3"):
                if row.is_symlink():
                    raise RuntimeError("Linked native worker journal is untrusted")
                # Do not silently turn SQLite journal errors into free custody.
                db = sqlite3.connect(f"file:{row.as_posix()}?mode=ro", uri=True)
                try:
                    unfinished = db.execute(
                        "SELECT COUNT(*) FROM worker_jobs WHERE state IN "
                        "('PREPARED','RUNNING','CANCEL_REQUESTED','INTERRUPTED',"
                        "'FAILED','TIMED_OUT')").fetchone()[0]
                finally:
                    db.close()
                if unfinished:
                    raise PermissionError("Unreconciled native workers block upgrade")
            for journal in root.glob("*/journal.json"):
                if journal.is_symlink() or journal.parent.is_symlink():
                    raise RuntimeError("Linked native worker journal is untrusted")
                record = json.loads(journal.read_text("utf8"))
                if record.get("state") != "SUCCEEDED_VERIFIED" or (
                        record.get("process_tree_custody_verified") is not True):
                    raise PermissionError("Unverified protected-worker recovery blocks upgrade")
        return {
            "os_provenance": "windows-job-object",
            "original_runtime_sha256": original_sha,
            "process_tree_custody_verified": True,
            "active_windows_jobs": 0,
            "unresolved_worker_jobs": 0,
            "measured_at_unix": time.time(),
        }
