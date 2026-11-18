"""WO6-B private host authorization and owned resource admission.

Saved plans are planning receipts, never execution grants. A separately
confirmed operation is sealed to one task and one native window lifetime.
This class intentionally does not launch a process or publish a Take. The
finite protected host must hold admitted() for its complete operation,
and only that host can prove OS cleanup and terminal output.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import secrets
import threading
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings, canonical_bytes
from backend.nvp_film_index import FilmIndex, _require_pid
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_worker_host_lease import WorkerHostLease

FORMAT = "nvp.wo6.saved_retake_task.v1"
RAM_MB = 4096
GRANT_SECONDS = 300


class SavedRetakeTaskAuthority:
    """Native-host-owned object; never mount on a model or browser API."""

    def __init__(self, index, ledger, project_id, *, confirm_native, live_gate,
                 seal_execution=None):
        if (not isinstance(index, FilmIndex) or not isinstance(ledger, TaskLedger)
            or not callable(confirm_native) or not callable(live_gate)):
            raise TypeError("Native index, ledger and two host authorities required")
        self.index, self.ledger = index, ledger
        self.project_id = _require_pid(project_id)
        self.owner = "wo6take_" + self.project_id
        self.confirm_native, self.live_gate = confirm_native, live_gate
        if seal_execution is not None and not callable(seal_execution):
            raise TypeError("Host-only execution pin callback required")
        self._seal_execution = seal_execution
        self._lock = threading.RLock()
        self._grants = {}
        self._pending = False
        self._closed = False
        self.bindings = ApprovedTaskBindings(ledger, approval_check=self._check)

    def _prepare(self, plan_id, plan_sha256, new_take_id):
        from backend.nvp_wo6_saved_retake_scope import prepare_saved_retake
        return prepare_saved_retake(self.index, project_id=self.project_id,
            plan_id=plan_id, plan_sha256=plan_sha256, new_take_id=new_take_id)

    def _fresh(self, scope):
        return self._prepare(scope["plan_id"], scope["plan_document_sha256"],
                             scope["new_take_id"]) == scope

    def _check(self, approval_id, spec_sha256, document):
        with self._lock:
            task = document.get("task_id")
            if (self._closed or document.get("format") != FORMAT or
                document.get("kind") != "compositing" or
                document.get("project_id") != self.project_id or
                document.get("owner_key") != self.owner or
                document.get("native_approval_id") != approval_id or
                document.get("ram_mb") != RAM_MB or
                time.time() >= document.get("expires_at", 0) or
                self._grants.get(task) != (approval_id, spec_sha256) or
                sha256(canonical_bytes(document)).hexdigest() != spec_sha256):
                return False
            # Live policy and native source checks are distinct. A planning
            # receipt, UI boolean, or knowledge of an approval ID alone fails.
            if self.live_gate(deepcopy(document)) is not True:
                return False
            if not self._fresh(document["scope"]):
                return False
            if self._seal_execution is not None and (
                document.get("execution") != self._seal_execution(document["scope"])):
                return False
            return (not self._closed and
                    self._grants.get(task) == (approval_id, spec_sha256) and
                    time.time() < document["expires_at"] and
                    self.live_gate(deepcopy(document)) is True)

    def queue(self, *, plan_id, plan_sha256, new_take_id):
        with self._lock:
            if self._closed or self._pending:
                raise PermissionError("Native grant unavailable")
            self._pending = True
        task_id = "wo6take_" + secrets.token_hex(16)
        approval_id = "wo6grant_" + secrets.token_hex(16)
        try:
            scope = self._prepare(plan_id, plan_sha256, new_take_id)
            document = {
                "format": FORMAT, "kind": "compositing", "task_id": task_id,
                "project_id": self.project_id, "owner_key": self.owner,
                "native_approval_id": approval_id, "ram_mb": RAM_MB,
                "expires_at": int(time.time()) + GRANT_SECONDS, "scope": scope,
            }
            if self._seal_execution is not None:
                document["execution"]=self._seal_execution(scope)
            spec_sha = sha256(canonical_bytes(document)).hexdigest()
            if self.live_gate(deepcopy(document)) is not True:
                raise PermissionError("Native project/window grant unavailable")
            # Must be a separately invoked, real native confirmation showing
            # the operation and exact source/output scope and sealed digest.
            if self.confirm_native(deepcopy(document), spec_sha) is not True:
                raise PermissionError("Creator refused native Take execution")
            with self._lock:
                if self._closed:
                    raise PermissionError("Native host closed during consent")
                self._grants[task_id] = (approval_id, spec_sha)
                if not self._check(approval_id, spec_sha, document):
                    raise PermissionError("Native grant or source changed during consent")
                queued = self.bindings.enqueue(AdmissionRequest(task_id,
                    "compositing", "Create exact-source frozen Take", RAM_MB),
                    owner_key=self.owner, lane="standard", approval_id=approval_id,
                    document=document)
            return {**queued, "new_take_id": new_take_id,
                    "native_worker_started": False, "film_approved": False}
        except BaseException:
            with self._lock:
                self._grants.pop(task_id, None)
            raise
        finally:
            with self._lock:
                self._pending = False

    @contextmanager
    def admitted(self, task_id):
        """Hold the existing kernel lease across exact native operations.

        No unrelated task is ever claimed and no worker is started here.
        If the downstream host cannot prove termination/output, an ACTIVE
        reservation remains unresolved rather than being auto-released.
        """
        with WorkerHostLease(self.ledger.root):
            claim = self.bindings.claim_next(owner_key=self.owner,
                                             expected_task_id=task_id)
            if claim is None or not claim["admitted"]:
                yield None
                return
            try:
                spec = self.bindings.verified_spec(task_id, owner_key=self.owner)
                yield spec
            finally:
                self.revoke(task_id)
                row = self.ledger.get_task(task_id)
                if row is not None and row["state"] == "ACTIVE":
                    self.ledger.update(task_id, "recovering",
                        "Native completion or process-tree proof incomplete; reservation held")

    def grant_live(self, document):
        # In the FilmIndex writer lease this is deliberately read-only;
        # do not reopen a native Take (its constructor can initialize SQL).
        with self._lock:
            return (not self._closed and time.time() < document["expires_at"]
                    and self._grants.get(document["task_id"]) ==
                    (document["native_approval_id"],
                     sha256(canonical_bytes(document)).hexdigest())
                    and self.live_gate(deepcopy(document)) is True)

    def revoke(self, task_id):
        """Revocation is not proof of worker termination."""
        with self._lock:
            self._grants.pop(task_id, None)

    def close(self):
        with self._lock:
            self._closed = True
            self._grants.clear()
