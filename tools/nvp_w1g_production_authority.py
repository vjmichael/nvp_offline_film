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
    """Complete native worker-domain roster plus an ALL-WORKERS kernel lock.

    The old single WindowsJobProcess argument was not a whole-release
    witness: each Blender/editorial/audio/capture subprocess owns a SEPARATE
    Job Object. All NVP `launch_contained` Windows paths now acquire a
    lifetime slot before suspended CreateProcess, and keep it until the
    original Job's kernel accounting confirms zero remaining children.
    """

    REQUIRED_DOMAINS=frozenset((
        "cycles", "filming", "editorial", "audio", "delivery"))

    def __init__(self, installed_program: Path, *,
                 worker_workspaces: dict[str, Path]):
        if os.name != "nt":
            raise RuntimeError("Windows release custody requires native Windows kernel")
        if (type(worker_workspaces) is not dict or
            set(worker_workspaces) != self.REQUIRED_DOMAINS or
            any(not isinstance(v,Path) for v in worker_workspaces.values())):
            raise PermissionError("All five original worker domains must be explicitly registered")
        self.program=Path(installed_program)
        self.workspaces={
            name: root.absolute() for name, root in worker_workspaces.items()
        }
        if len({str(p).casefold() for p in self.workspaces.values()}) != len(self.workspaces):
            raise RuntimeError("Worker domains cannot share ambiguous release journal roots")
        self._held=False
        self._mutex=threading.Lock()
        self._release_fence=None

    @contextmanager
    def transaction(self):
        if not self._mutex.acquire(blocking=False):
            raise RuntimeError("Another native release authorization is in progress")
        try:
            from backend.nvp_worker_host_lease import WorkerHostLease
            from backend.nvp_w1g_release_gate import WindowsReleaseMutationGate
            with ExitStack() as stack:
                # Critical lock ordering: individual worker launchers hold
                # WorkerHostLease BEFORE acquiring their release lifetime slot.
                # The updater must acquire workspace locks in the same order,
                # and acquire the all-worker release gate LAST. Reversing this
                # order would deadlock a worker blocked between these steps.
                for name, root in sorted(self.workspaces.items()):
                    if not root.is_dir() or root.is_symlink():
                        raise RuntimeError("Missing original supervised worker domain: "+name)
                    stack.enter_context(WorkerHostLease(root))
                self._release_fence=stack.enter_context(WindowsReleaseMutationGate())
                self._held=True
                try:
                    yield self
                finally:
                    self._held=False
                    self._release_fence=None
        finally:
            self._mutex.release()

    def __call__(self, original_sha):
        if (not self._held or self._release_fence is None or
            self._release_fence.held is not True):
            raise PermissionError("Release-wide exclusive Windows kernel gate is not held")
        from tools.nvp_w1g_nsis_recovery import _digest, _program
        if type(original_sha) is not str or len(original_sha)!=64:
            raise PermissionError("Original release identity missing")
        # The original executable remains available under NVP.previous or
        # NVP.failed during a two-rename upgrade or rollback transaction.
        candidates=(self.program,self.program.with_name("NVP.previous"),
                    self.program.with_name("NVP.failed"))
        original_found=False
        for candidate in candidates:
            if candidate.exists() or candidate.is_symlink():
                original_found |= _digest(_program(candidate)) == original_sha
        if not original_found:
            raise PermissionError("Original installed/parked release differs from kernel scope")
        # A kernel slot can be free after a host crash, but that is NOT proof
        # that its prior journal and descendants were safely reconciled.
        for name, root in sorted(self.workspaces.items()):
            journals=list(root.rglob("worker_jobs.sqlite3"))
            if len(journals)>8:
                raise RuntimeError("Unbounded native worker journal topology: "+name)
            for row in journals:
                if row.is_symlink() or row.parent.is_symlink():
                    raise RuntimeError("Linked original worker journal is untrusted")
                db=sqlite3.connect(f"file:{row.as_posix()}?mode=ro",uri=True)
                cursor=None
                try:
                    cursor=db.execute(
                        "SELECT COUNT(*) FROM worker_jobs WHERE state != 'SUCCEEDED'"
                    )
                    pending=cursor.fetchone()[0]
                finally:
                    # Windows keeps the original SQLite DB handle locked if
                    # a cached prepared statement survives sqlite3_close_v2.
                    # Close cursor BEFORE connection, including denial paths.
                    if cursor is not None:
                        cursor.close()
                    db.close()
                if pending:
                    raise PermissionError("Unreconciled Blender/worker jobs block upgrade: "+name)
            for journal in root.rglob("journal.json"):
                if journal.is_symlink() or journal.parent.is_symlink():
                    raise RuntimeError("Linked original protected-worker journal is untrusted")
                record=json.loads(journal.read_text("utf8"))
                if (record.get("state")!="SUCCEEDED_VERIFIED" or
                    record.get("process_tree_custody_verified") is not True):
                    raise PermissionError("Unverified protected-worker recovery blocks upgrade: "+name)
        # Legacy utilities are independent of the five supervised domains.
        # A hard host death can clear kernel slots but leave external outputs
        # uncertain. Any surviving registration blocks a production mutation,
        # not merely an active PID or stale timestamp.
        from backend.nvp_w1g_release_gate import release_gate_path
        legacy=release_gate_path().parent/"legacy-jobs"
        if legacy.exists() or legacy.is_symlink():
            if legacy.is_symlink() or not legacy.is_dir():
                raise PermissionError("Untrusted original legacy worker registration root")
            entries=list(legacy.iterdir())
            if len(entries)>2048:
                raise PermissionError("Unbounded original legacy worker recovery topology")
            if entries:
                raise PermissionError(
                    "Unreconciled original legacy worker markers block upgrade")
        from backend.nvp_w1g_release_gate import inspect_original_process_journals
        originals=inspect_original_process_journals()
        return {
            **originals,
            "os_provenance":"windows-job-object",
            "kernel_release_gate":"exclusive-128-slot-locks-v1",
            "release_wide_launch_fence_verified":True,
            "complete_worker_domain_roster_verified":True,
            "original_runtime_sha256":original_sha,
            "process_tree_custody_verified":True,
            "active_windows_jobs":0,
            "unresolved_worker_jobs":0,
            "measured_at_unix":time.time(),
        }
