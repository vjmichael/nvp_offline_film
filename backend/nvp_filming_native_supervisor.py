"""PLAN-03 / DA-03: native filming publication worker with actual OS tree custody.

Reuses the already independently exercised NVP OS worker layer:
Windows suspended child assigned to JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
Linux strict host-delegated cgroup v2 + out-of-group crash guardian.

This is a trusted host-only API. Never expose it to FastAPI or pywebview as
an arbitrary process runner. Its stop receipt authorizes only an *interrupted*
journal state, not publication, replay, or approval of any immutable Take.
"""
from __future__ import annotations

from hashlib import sha256
import math
import os
from pathlib import Path
import sys

from backend.nvp_film_index import _require_pid, _id
from backend.nvp_filming_publication_journal import FilmingPublicationJournal
from backend.nvp_worker_containment import launch_contained


class FilmingWorkerCustodyError(RuntimeError):
    pass


def sha_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class NativeFilmingTreeWorker:
    """Bounded one-use owned worker, tied to one PREPARING original Take.

    The native host *must* provide actual OS human review before calling
    launch; a test double is never evidence of physical operator consent.
    """
    def __init__(self, *, journal: FilmingPublicationJournal, workspace: Path,
                 ask_native, memory_mb: int = 1024):
        if not isinstance(journal, FilmingPublicationJournal):
            raise TypeError("Actual FilmIndex filming publication journal required")
        if not callable(ask_native):
            raise TypeError("Human OS approval callback required")
        if type(memory_mb) is not int or not 256 <= memory_mb <= 65536:
            raise ValueError("Bounded memory admission required")
        root = Path(workspace)
        if not root.is_absolute() or root.is_symlink():
            raise ValueError("Native owned work directory must be absolute, not symlinked")
        self.root = root
        self.journal = journal
        self._ask = ask_native
        self.memory_mb = memory_mb
        self._process = None
        self._started = None
        self._consumed = False

    def launch(self, project_id: str, take_id: str, *, executable: Path,
               executable_sha256: str, args: tuple[str, ...] = ()) -> dict:
        pid = _require_pid(project_id)
        _id(take_id, "filming take")
        if self._consumed or self._process is not None or self._started is not None:
            raise FilmingWorkerCustodyError("One native worker per original Take admission")
        if type(args) is not tuple or len(args) > 24 or any(
                type(v) is not str or len(v) > 512 or "\x00" in v for v in args):
            raise ValueError("Bounded native worker arguments required")
        binary = Path(executable)
        if (not binary.is_absolute() or binary.is_symlink() or
                not binary.is_file() or binary.is_relative_to(self.root) or
                executable_sha256 != sha_file(binary)):
            raise PermissionError("Trusted worker executable must be outside workspace, pinned by exact SHA")
        # Admission only if an actual journal entry is PREPARING and was read
        # before any OS dialog or process creation.
        matches = [item for item in self.journal.unresolved(pid)
                   if item["take_id"] == take_id and item["state"] == "PREPARING"]
        if len(matches) != 1:
            raise PermissionError("Filming Take is not in one fresh PREPARING state")
        original = matches[0]
        scope = {
            "operation": "nvp.plan03.launch_filming_tree_worker_once.v1",
            "project_id": pid, "take_id": take_id,
            "journal_updated_at": original["updated_at"],
            "executable_sha256": executable_sha256,
            "args_sha256": sha256("\x00".join(args).encode()).hexdigest(),
            "memory_mb": self.memory_mb,
            "original_or_export_publication_authorized": False,
        }
        if self._ask(scope) is not True:
            self._consumed = True
            raise PermissionError("Human native filming worker launch refused")
        # Source could change during a modal OS dialog. New human approval is
        # required for a changed journal/worker even if old consent was true.
        matches_after = [item for item in self.journal.unresolved(pid)
                         if item["take_id"] == take_id and item["state"] == "PREPARING"]
        if matches_after != [original] or sha_file(binary) != executable_sha256:
            self._consumed = True
            raise PermissionError("Stale filming job or executable after human consent")
        self._consumed = True # one human decision cannot launch two workers
        self.root.mkdir(parents=True, exist_ok=True)
        out = self.root / (take_id + ".stdout")
        err = self.root / (take_id + ".stderr")
        if out.exists() or err.exists() or out.is_symlink() or err.is_symlink():
            raise FileExistsError("No overwrite of original filming worker logs")
        with out.open("xb") as stdout, err.open("xb") as stderr:
            # No uncustodied fallback. A real delegated Linux cgroup must
            # exist; Windows process is suspended until assigned to a Job.
            worker = launch_contained(
                [str(binary), *args],cwd=str(self.root),
                stdout=stdout,stderr=stderr,memory_mb=self.memory_mb,
                linux_cgroup_tree_required=(sys.platform == "linux"))
        self._process = worker
        self._started = {
            "project_id": pid, "take_id": take_id,
            "updated_at": original["updated_at"],
            "executable_sha256": executable_sha256,
        }
        return {
            "status": "OS_CONTAINED_PREPARING_NOT_PUBLISHED",
            "pid": worker.pid,
            "native_process_tree_custody_mode": (
                "windows_job_kill_on_close" if os.name == "nt"
                else "linux_strict_cgroup_v2"),
            "original_take_published": False,
            "automatic_replay_authorized": False,
        }

    def stop_and_interrupt(self, *, timeout_seconds=20) -> dict:
        """Only move the journal after kernel-wide tree termination succeeds.

        Linux close() waits for the independent cgroup guardian; Windows
        terminate_tree()+close() destroys the whole Job, including detached
        grandchildren. On any error keep PREPARING/poisoned for recovery.
        """
        if (type(timeout_seconds) not in (int,float) or
                not math.isfinite(timeout_seconds) or
                not 0 < timeout_seconds <= 60):
            raise ValueError("Bounded custody timeout required")
        if self._process is None or self._started is None:
            raise FilmingWorkerCustodyError("No currently owned OS filming worker")
        worker = self._process
        self._process = None  # one-use even after ambiguous OS failure
        started = self._started
        self._started = None
        try:
            worker.terminate_tree()
            exit_code = worker.poll()
            if exit_code is None:
                raise FilmingWorkerCustodyError("Direct child exit cannot be independently confirmed")
            worker.close() # guards against escaped descendants
        except BaseException as exc:
            raise FilmingWorkerCustodyError(
                "Process-tree custody unverified; original publication remains PREPARING"
            ) from exc
        result = self.journal.interrupt_preparing(
            started["project_id"],started["take_id"],
            expected_updated_at=started["updated_at"])
        return {**result,
                "worker_process_tree_custody_verified": True,
                "worker_exit_code": exit_code,
                "scope": ("windows_job_kill_on_close" if os.name=="nt"
                          else "linux_strict_cgroup_v2"),
                "original_take_published": False,
                "automatic_replay_authorized": False}

    def inventory_after_restart(self, project_id: str) -> dict:
        """Read-only crash recovery; no PID-based reconstruction or replay."""
        pid = _require_pid(project_id)
        records = self.journal.reconcile(pid)
        return {"status": "REVIEW_REQUIRED",
                "process_tree_custody_after_restart_unverified": True,
                "automatic_replay_authorized": False,
                "original_take_published": False,
                "journal_records": records}
