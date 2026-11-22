"""WO6-C recovery boundary: record exact native execution, never replay approval.

Only an already kernel-leased native Take host can mutate this journal.  A
missing or interrupted launch/cleanup record is NOT permission to release a
reservation.  Original Windows job evidence alone is not profile/ACL cleanup.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_film_index import FilmIndex, _require_pid
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_worker_host_lease import WorkerHostLease

FORMAT = "nvp.wo6.saved_retake_task.v1"
RECEIPT = "nvp.wo6.protected_take_execution.v1"
JOB = re.compile(r"nvpjob_[0-9a-f]{32}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")


def _digest(value):
    return sha256(canonical_bytes(value)).hexdigest()


def _original_job(journal_id, command_sha):
    """Read original, bounded, independently re-opened native Job evidence."""
    from backend.nvp_w1g_release_gate import release_process_journal_root
    if not isinstance(journal_id, str) or not JOB.fullmatch(journal_id):
        raise PermissionError("Invalid original native Job identity")
    if not isinstance(command_sha, str) or not HEX.fullmatch(command_sha):
        raise PermissionError("Invalid exact native command digest")
    path = release_process_journal_root() / (journal_id + ".json")
    if (path.is_symlink() or path.with_suffix(".new").exists() or
        path.with_suffix(".new").is_symlink() or not path.is_file() or path.stat().st_size > 2048):
        raise PermissionError("Original native Job record unavailable")
    with path.open("rb") as stream:
        raw = stream.read(2049)
    if len(raw) > 2048:
        raise PermissionError("Original native Job record exceeds limit")
    row = json.loads(raw.decode("utf8"))
    if (type(row) is not dict or
        row.get("format") != "nvp.w1g.original_windows_job_journal.v1" or
        row.get("job_id") != journal_id or row.get("command_sha256") != command_sha or
        row.get("state") != "TREE_REAPED_VERIFIED" or
        row.get("process_tree_custody_verified") is not True or
        row.get("worker_exit_verified") is not True):
        raise PermissionError("Original native Job tree cleanup unverified")
    return row


class RetakeRecovery:
    """Private execution checkpoint and read/reconcile authority under host lease."""
    def __init__(self, ledger, lease):
        if not isinstance(ledger, TaskLedger) or not isinstance(lease, WorkerHostLease):
            raise TypeError("Native resource ledger and kernel lease required")
        self.ledger, self.lease = ledger, lease
        self._held()
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS wo6_retake_lifecycle (
                task_id TEXT PRIMARY KEY, spec_sha256 TEXT NOT NULL,
                state TEXT NOT NULL, job_id TEXT, receipt_sha256 TEXT,
                cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1))
            )""")

    def _held(self):
        if self.lease.fd is None or self.lease.root != self.ledger.root:
            raise PermissionError("Exact kernel host lease required for recovery")

    def _spec(self, db, task):
        row = db.execute("""SELECT t.state,t.kind,t.reserved,s.owner_key,
                     a.owner_key,a.kind,a.approval_id,a.spec_sha256,a.spec_json
              FROM tasks t JOIN task_schedule s ON s.task_id=t.id
              JOIN authorized_task_specs a ON a.task_id=t.id WHERE t.id=?""", (task,)).fetchone()
        if row is None:
            raise PermissionError("Missing exact approved task")
        state, kind, reserved, owner, approved_owner, approved_kind, approval, digest, serialized = row
        spec = json.loads(serialized)
        pid = _require_pid(spec.get("project_id"))
        if (owner != "wo6take_" + pid or owner != approved_owner or owner != spec.get("owner_key") or
            kind != approved_kind or kind != "compositing" or spec.get("kind") != kind or
            spec.get("format") != FORMAT or spec.get("task_id") != task or
            spec.get("native_approval_id") != approval or
            canonical_bytes(spec).decode("ascii") != serialized or _digest(spec) != digest or
            spec.get("scope", {}).get("project_id") != pid or
            (state == "ACTIVE" and reserved != 1)):
            raise PermissionError("Exact saved Take task binding differs")
        return state, digest, spec

    def prepare(self, task, spec):
        self._held()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            state, digest, saved = self._spec(db, task)
            if state != "ACTIVE" or saved != spec:
                raise PermissionError("Native recovery preparation lacks exact admission")
            db.execute("INSERT INTO wo6_retake_lifecycle(task_id,spec_sha256,state,job_id,receipt_sha256) VALUES(?,?,?,NULL,NULL)",
                       (task, digest, "PREPARED"))
            db.commit()

    def _advance(self, task, old, new, *, job=None, receipt=None):
        self._held()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            state, digest, _ = self._spec(db, task)
            if state != "ACTIVE":
                raise PermissionError("Native recovery checkpoint lacks active task")
            row = db.execute("SELECT spec_sha256,state,job_id,receipt_sha256,cancel_requested FROM wo6_retake_lifecycle WHERE task_id=?", (task,)).fetchone()
            if row is None or row[:2] != (digest, old):
                raise PermissionError("Invalid native recovery checkpoint transition")
            if new == "PUBLICATION_PENDING" and row[4] != 0:
                raise PermissionError("Take cancelled before publication fence")
            if new == "LAUNCH_INTENT" and row[4] != 0:
                raise PermissionError("Take cancelled before launch")
            if job is not None and row[2] not in (None, job):
                raise PermissionError("Original native Job identity changed")
            if receipt is not None and row[3] not in (None, receipt):
                raise PermissionError("Exact Take receipt changed")
            db.execute("UPDATE wo6_retake_lifecycle SET state=?,job_id=?,receipt_sha256=? WHERE task_id=?",
                       (new, job or row[2], receipt or row[3], task))
            db.commit()

    def request_cancel(self, task):
        """Host-local control only. Atomically fence launch/publication, no release."""
        self._held()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            state, digest, _ = self._spec(db, task)
            row = db.execute("SELECT spec_sha256,state FROM wo6_retake_lifecycle WHERE task_id=?", (task,)).fetchone()
            if state != "ACTIVE" or row is None or row[0] != digest:
                raise PermissionError("No exact active Take to cancel")
            if row[1] not in ("PREPARED", "LAUNCH_INTENT", "RUNNING", "CUSTODY_CLOSED"):
                return False
            db.execute("UPDATE wo6_retake_lifecycle SET cancel_requested=1 WHERE task_id=?", (task,))
            db.commit()
            return True

    def cancelled(self, task):
        self._held()
        with self.ledger._db() as db:
            state, digest, _ = self._spec(db, task)
            row = db.execute("SELECT spec_sha256,cancel_requested FROM wo6_retake_lifecycle WHERE task_id=?", (task,)).fetchone()
            if state != "ACTIVE" or row is None or row[0] != digest:
                raise PermissionError("No exact active Take control")
            return row[1] == 1

    def launch_intent(self, task):
        self._advance(task, "PREPARED", "LAUNCH_INTENT")

    def running(self, task, journal_id):
        if not isinstance(journal_id, str) or not JOB.fullmatch(journal_id):
            raise PermissionError("Invalid native Job identity")
        self._advance(task, "LAUNCH_INTENT", "RUNNING", job=journal_id)

    def custody_closed(self, task, journal_id):
        # Called ONLY after the actual AppContainer close (profile + ACL),
        # joined pipes and empty workspace. A read of the Job file alone must
        # never call this. Original journal confirms exact command separately.
        self._held()
        with self.ledger._db() as db:
            _, _, spec = self._spec(db, task)
        _original_job(journal_id, spec["execution"]["command_sha256"])
        self._advance(task, "RUNNING", "CUSTODY_CLOSED", job=journal_id)

    def publication_pending(self, task, receipt):
        self._advance(task, "CUSTODY_CLOSED", "PUBLICATION_PENDING", receipt=_digest(receipt))

    def take_verified(self, task, receipt):
        self._advance(task, "PUBLICATION_PENDING", "TAKE_VERIFIED", receipt=_digest(receipt))

    def _verify_publication(self, index, pid, task, spec, spec_sha, row, lifecycle):
        # Existing immutable FilmIndex and actual OpenUSD reopen. Never run a
        # worker, adopt an unknown Take, or treat a receipt as a new approval.
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        scope, execution = spec["scope"], spec["execution"]
        oid = scope["new_take_id"]
        receipt = row["data"]["protected_retake_execution"]
        expected = {"format": RECEIPT, "project_id": pid, "task_id": task,
                    "spec_sha256": spec_sha, "scope_sha256": scope["scope_sha256"],
                    "plan_id": scope["plan_id"], "plan_document_sha256": scope["plan_document_sha256"],
                    "original_take_id": scope["original_take_id"], "original_take_sha256": scope["original_take_sha256"],
                    "new_take_id": oid, "scene_sha256": scope["scene_sha256"],
                    "timeline_sha256": scope["timeline_sha256"],
                    "original_process_journal_id": lifecycle[2],
                    "process_tree_custody_verified": True, **execution}
        if (row.get("kind") != "take" or row.get("revision") != 1 or set(receipt) != set(expected) | {"sample_digest_sha256"} or
            any(receipt.get(k) != v for k, v in expected.items()) or
            _digest(receipt) != lifecycle[3] or receipt["process_tree_custody_verified"] is not True):
            raise PermissionError("Recovered Take does not match exact authorized publication")
        capture = OpenUSDTakeCapture(index, verify_creator_action=lambda *_: False)
        proof = capture.verify_take(pid, oid)
        original = capture.verify_take(pid, scope["original_take_id"])
        original_row = index.read_revision(pid, scope["original_take_id"], 1)
        if (proof.get("status") != "VERIFIED_FROZEN_DATA_TAKE" or
            original.get("status") != "VERIFIED_FROZEN_DATA_TAKE" or
            original_row["kind"] != "take" or original_row["document_sha256"] != scope["original_take_sha256"] or
            original_row["data"]["sample_digest_sha256"] != receipt["sample_digest_sha256"] or
            proof["take_document_sha256"] != row["document_sha256"] or
            original["take_document_sha256"] != scope["original_take_sha256"] or
            receipt["sample_digest_sha256"] != row["data"]["sample_digest_sha256"]):
            raise PermissionError("Recovered immutable Take or original source differs")

    def reconcile(self, index, project_id):
        self._held()
        if not isinstance(index, FilmIndex):
            raise TypeError("Trusted FilmIndex required")
        pid = _require_pid(project_id)
        index.studio.get_project(pid)
        # The approved-spec table is opened by existing admission machinery.
        # On a new runtime there is nothing to reconcile; do not create grants.
        with self.ledger._db() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='authorized_task_specs'").fetchone() is None:
                return []
            tasks = db.execute("""SELECT t.id FROM tasks t JOIN task_schedule s ON s.task_id=t.id
                WHERE s.owner_key=? AND t.state IN ('ACTIVE','QUEUED') ORDER BY t.id LIMIT 1001""",
                ("wo6take_" + pid,)).fetchall()
        if len(tasks) > 1000:
            raise PermissionError("Unbounded saved Take recovery set")
        results = []
        for (task,) in tasks:
            try:
                with self.ledger._db() as db:
                    state, spec_sha, spec = self._spec(db, task)
                    lifecycle = db.execute("SELECT spec_sha256,state,job_id,receipt_sha256,cancel_requested FROM wo6_retake_lifecycle WHERE task_id=?", (task,)).fetchone()
                if state == "QUEUED" and lifecycle is None:
                    self.ledger.cancel_queued(task, owner_key="wo6take_" + pid)
                    results.append((task, "CANCELLED")); continue
                if lifecycle is None or lifecycle[0] != spec_sha:
                    raise PermissionError("Missing exact durable Take lifecycle")
                phase = lifecycle[1]
                cancelled = lifecycle[4] == 1
                scope = spec["scope"]
                try:
                    row = index.read_revision(pid, scope["new_take_id"])
                except KeyError as exc:
                    # Missing blob, invalid revision or missing film is not
                    # the same thing as a genuinely unused Take identity.
                    if exc.args != ("Film object not found",) or index.history(pid,scope["new_take_id"]):
                        raise
                    row = None
                if phase == "PREPARED" and row is None and lifecycle[2:4] == (None, None):
                    terminal = "CANCELLED" if cancelled else "INTERRUPTED"
                elif phase in ("CUSTODY_CLOSED", "PUBLICATION_PENDING", "TAKE_VERIFIED"):
                    _original_job(lifecycle[2], spec["execution"]["command_sha256"])
                    if row is None and phase != "TAKE_VERIFIED":
                        terminal = "CANCELLED" if cancelled else "INTERRUPTED"
                    elif row is not None and not cancelled and phase in ("PUBLICATION_PENDING", "TAKE_VERIFIED"):
                        self._verify_publication(index, pid, task, spec, spec_sha, row, lifecycle)
                        terminal = "SUCCEEDED"
                    else:
                        raise PermissionError("Contradictory immutable Take checkpoint")
                else:
                    raise PermissionError("Native launch or cleanup remains uncertain")
                self.ledger.finish(task, terminal, "Reconciled exact interrupted Take; no worker replayed")
                results.append((task, terminal))
            except Exception:
                # Never release malformed, missing, contradictory, or merely
                # absent-PID evidence. No exception includes private film paths.
                results.append((task, "HELD_UNVERIFIED"))
        return results
