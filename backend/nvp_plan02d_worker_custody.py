"""PLAN-02-D3: source-pinned, supervised render process custody.

A *trusted native host* invokes this interface after D2 source review. No
pywebview/browser method exposes command, executable, cwd or authorization
here. A separate fresh OS dialog is mandatory; it does not come from the
persistent D2 approval. Process-tree enforcement reuses NVP's existing
suspended Windows Job Object or strict delegated Linux cgroup + guardian,
never an uncontained Popen or process-group-only fallback.

An interrupted receipt remains UNTRUSTED. Kernel custody and the stale-intent
rejection must be witnessed by the platform's native acceptance gate.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import subprocess
import sys
import threading
import time

from backend.nvp_blender_worker import sha_file
from backend.nvp_film_index import _require_pid, _id, _sha
from backend.nvp_plan02d_render_queue import (
    APPROVED, DurableRenderIntentionQueue)
from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_host_lease import WorkerHostLease

STARTED = "WORKER_STARTED_NOT_YET_VERIFIED"
EXITED = "WORKER_EXIT_VERIFIED_NO_ARTIFACT_PROMOTION"
CANCELLED = "WORKER_CANCELLED_TREE_VERIFIED"
FAILED = "WORKER_FAILED_OR_UNVERIFIED"
INTERRUPTED = "INTERRUPTED_ORPHAN_OUTPUT_UNTRUSTED"


class SupervisedSourceRenderWorker:
    """One host-owned worker for one pinned source + executable.

    This is the custody interface, not the approved renderer's shot script.
    Only an internal NVP host may pass a binary + typed immutable arguments.
    Do not expose this class through webview's JS API or FastAPI.
    """

    def __init__(self, queue: DurableRenderIntentionQueue, workspace, *,
                 ask_native, memory_mb=1024, timeout_seconds=60):
        if not isinstance(queue, DurableRenderIntentionQueue) or not callable(ask_native):
            raise TypeError("Native queue and independent OS worker grant required")
        if (type(memory_mb) is not int or not 256 <= memory_mb <= 65536 or
                type(timeout_seconds) is not int or
                not 1 <= timeout_seconds <= 600):
            raise ValueError("Bounded OS worker resource limits required")
        root = Path(workspace)
        if root.is_symlink():
            raise PermissionError("Worker workspace cannot be a symlink")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.queue = queue
        self.ask_native = ask_native
        self.memory_mb = memory_mb
        self.timeout_seconds = timeout_seconds
        self._cancel = threading.Event()
        self._active = False
        self._active_lock = threading.Lock()

    def cancel(self):
        """Signal a live worker; actual cancellation receipt waits for tree exit."""
        self._cancel.set()

    def _update(self, project_id, job_id, old, status, *,
                exit_code=None, stdout_sha256=None, error=None):
        scope = self.queue.selector.preview(project_id, old["data"]["selection"])
        if scope["selection_sha256"] != old["data"]["selection_sha256"]:
            raise RuntimeError("Original source changed during OS worker execution")
        data = {
            **old["data"], "status": status,
            "previous_transition_sha256": old["document_sha256"],
            "authorizes_renderer_worker": False,
            "authorizes_export": False,
            "allows_unattended_replay": False,
            "worker_exit_code": exit_code,
            "worker_stdout_sha256": stdout_sha256,
            "worker_error": error,
        }
        return self.queue.index.register_revision(
            project_id, job_id, "edit", data,
            expected_revision=old["revision"],
            dependencies=old["dependencies"])

    def run(self, project_id, job_id, *, executable,
            executable_sha256, arguments=()):
        """Launch only after a fresh second native dialog and hash/source recheck.

        Caller is a trusted first-party host, NOT JS. Output remains
        unpromoted; D4 has its own independently verified publication.
        """
        pid = _require_pid(project_id)
        _id(job_id, "supervised render job")
        _sha(executable_sha256)
        binary = Path(executable)
        if (not binary.is_absolute() or binary.is_symlink() or
                not binary.is_file() or binary.resolve().is_relative_to(self.root)):
            raise PermissionError("Pinned executable outside worker workspace required")
        binary = binary.resolve(strict=True)
        if (type(arguments) not in (tuple, list) or len(arguments) > 24 or
                any(type(arg) is not str or len(arg) > 512 or
                    "\x00" in arg for arg in arguments)):
            raise PermissionError("Only bounded trusted native process arguments")
        if sha_file(binary) != executable_sha256:
            raise RuntimeError("Selected first-party renderer executable changed")
        with self._active_lock:
            if self._active:
                raise RuntimeError("One supervised renderer at a time")
            self._active = True
            self._cancel.clear()
        try:
            # Lock serializes execution with cold-start interruption inventory.
            with WorkerHostLease(self.root):
                old, data = self.queue._read(pid, job_id)
                if data["status"] != APPROVED:
                    raise PermissionError("Source review refused, stale or already consumed")
                self.queue.inspect(pid, job_id)
                scope = self.queue.selector.preview(pid, data["selection"])
                consent = self.ask_native({
                    "operation": "nvp.plan02d.launch_pinned_worker_once.v1",
                    "project_id": pid, "job_id": job_id,
                    "job_revision": old["revision"],
                    "source_selection_sha256": scope["selection_sha256"],
                    "take_sha256": scope["take_document_sha256"],
                    "camera_timeline_sha256": scope["camera_timeline_sha256"],
                    "rail_sha256": (scope["approved_rail"]["rail_document_sha256"]
                                   if scope["approved_rail"] else None),
                    "executable_sha256": executable_sha256,
                    "memory_mb": self.memory_mb,
                    "timeout_seconds": self.timeout_seconds,
                    "no_export_or_original_edit_authorized": True,
                })
                if consent is not True:
                    self._update(pid, job_id, old, FAILED,
                                 error="Creator refused separate worker launch")
                    raise PermissionError("Fresh native render-worker consent refused")
                if (self.queue.selector.preview(pid, data["selection"]) != scope or
                        self.queue._read(pid, job_id)[0]["document_sha256"] !=
                        old["document_sha256"] or
                        sha_file(binary) != executable_sha256):
                    raise PermissionError("Stale source, queue or executable after OS consent")
                # Persist BEFORE execution. A crashed host cannot silently
                # replay this accepted/started intention on restart.
                started = self._update(pid, job_id, old, STARTED)
                row = self.queue.index.read_revision(pid, job_id, started["revision"])
                outpath = self.root / (job_id + ".out")
                errpath = self.root / (job_id + ".err")
                if outpath.exists() or errpath.exists():
                    raise FileExistsError("No overwrite of prior worker output")
                proc = None
                output_sha = None
                exit_code = None
                state = FAILED
                failure = None
                try:
                    with outpath.open("xb") as stdout, errpath.open("xb") as stderr:
                        proc = launch_contained(
                            [str(binary), *arguments], cwd=str(self.root),
                            stdout=stdout, stderr=stderr,
                            memory_mb=self.memory_mb,
                            linux_cgroup_tree_required=sys.platform == "linux")
                        deadline = time.monotonic() + self.timeout_seconds
                        while True:
                            code = proc.poll()
                            if code is not None:
                                exit_code = code
                                state = EXITED if code == 0 and not self._cancel.is_set() else FAILED
                                break
                            if self._cancel.is_set():
                                proc.terminate_tree()
                                exit_code = proc.poll()
                                state = CANCELLED
                                break
                            if time.monotonic() >= deadline:
                                proc.terminate_tree()
                                exit_code = proc.poll()
                                failure = "OS-supervised worker exceeded time budget"
                                break
                            time.sleep(.05)
                        # close() must finish guardian cleanup / Job close even if
                        # the direct child has already returned (grandchildren).
                        proc.close()
                        proc = None
                    output_sha = sha_file(outpath)
                    if sha_file(binary) != executable_sha256:
                        raise RuntimeError("Pinned executable SHA changed after worker")
                    if self.queue.selector.preview(pid, data["selection"]) != scope:
                        raise RuntimeError("Source changed during supervised worker")
                except BaseException as exc:
                    failure = type(exc).__name__ + ": " + str(exc)
                    state = FAILED
                    if proc is not None:
                        try:
                            proc.terminate_tree()
                            proc.close()
                        except Exception as cleanup:
                            failure += "; OS cleanup UNVERIFIED: " + str(cleanup)
                    # Failed cleanup is not a successful custody assertion.
                finally:
                    try:
                        self._update(pid, job_id, row, state,
                                     exit_code=exit_code,
                                     stdout_sha256=output_sha,
                                     error=failure)
                    except Exception as journal_error:
                        raise RuntimeError(
                            "Worker completion journal unverified; no artifact promotion"
                        ) from journal_error
                if state != EXITED:
                    raise RuntimeError(failure or "Renderer cancelled, failed or was refused")
                return {
                    "status": EXITED, "job_id": job_id,
                    "selection_sha256": scope["selection_sha256"],
                    "executable_sha256": executable_sha256,
                    "stdout_sha256": output_sha,
                    "exit_code": exit_code,
                    "process_tree_custody_mode": (
                        "windows_kill_on_close_job_object"
                        if os.name == "nt" else "linux_strict_delegated_cgroup_v2"),
                    "original_source_modified": False,
                    "artifact_publication_authorized": False,
                }
        finally:
            with self._active_lock:
                self._active = False

    def inventory_after_restart(self, project_id, job_id):
        """Unfinished jobs are poison, not auto-recoverable approvals.

        Positive kernel cleanup must be established through the independent
        native descendant/crash witness; a database state alone cannot prove it.
        """
        pid = _require_pid(project_id)
        _id(job_id, "renderer intention")
        with WorkerHostLease(self.root):
            old, data = self.queue._read(pid, job_id)
            if data["status"] != STARTED:
                return self.queue.inspect(pid, job_id)
            record = self._update(pid, job_id, old, INTERRUPTED,
                                  error="Host restart: output and OS orphan custody unverified")
            return {
                "job_id": job_id, "revision": record["revision"],
                "status": INTERRUPTED,
                "process_tree_custody_independently_verified": False,
                "automatic_replay_allowed": False,
                "artifact_publication_authorized": False,
            }
