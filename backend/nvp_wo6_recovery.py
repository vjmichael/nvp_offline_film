"""WO6-06: durable native creator-task cancellation and crash reconciliation.

Reconciliation does not re-run a worker, undo an immutable FilmIndex commit,
promote interrupted work to SUCCEEDED or self-authorize release. OS tree
termination must be positively confirmed by a trusted native host.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from backend.nvp_ai_read_host import TrustedReadScope
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import NativeCancelRequested
from backend.nvp_worker_host_lease import WorkerHostLease

ID_RE = re.compile(r"wo6(?:take|shot)_[0-9a-f]{24}\Z")
TAKE_OP = "nvp.film.create_frozen_take.v1"
SHOT_OP = "nvp.film.author_director_shot.v1"
RECEIPT_FORMAT = "nvp.wo6.native_reconciliation_evidence.v1"


def _digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class WO6DurableRecovery:
    """First-party native recovery store over the SAME ledger SQLite authority."""

    def __init__(self, ledger: TaskLedger, *, attest_worker_tree_stopped=None):
        if not isinstance(ledger, TaskLedger):
            raise TypeError("Actual native task ledger is mandatory")
        if (attest_worker_tree_stopped is not None and
                not callable(attest_worker_tree_stopped)):
            raise TypeError("Worker cleanup must be verified by host code")
        self.ledger = ledger
        self._attest = attest_worker_tree_stopped
        with ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS wo6_cancel_intents (
                task_id TEXT PRIMARY KEY,
                requested_at REAL NOT NULL,
                actor_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                reason TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS wo6_recovery_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                recorded_at REAL NOT NULL,
                evidence_sha256 TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                UNIQUE(task_id,evidence_sha256)
            )""")
            db.commit()

    def _approved_spec(self, task_id, owner=None):
        if type(task_id) is not str or not ID_RE.fullmatch(task_id):
            raise ValueError("Unknown native WO6 task identity")
        with self.ledger._db() as db:
            db.row_factory = __import__("sqlite3").Row
            row = db.execute("""SELECT a.owner_key,a.spec_sha256,a.spec_json,
                                t.state,t.phase,t.detail,t.created_at,t.updated_at
                FROM authorized_task_specs a JOIN tasks t ON t.id=a.task_id
                WHERE a.task_id=?""", (task_id,)).fetchone()
        if row is None:
            raise PermissionError("Task is not a known authorized WO6 action")
        row = dict(row)
        if owner is not None and owner != row["owner_key"]:
            raise PermissionError("This host does not own that native operation")
        raw = row["spec_json"].encode("ascii")
        doc = json.loads(raw)
        if (hashlib.sha256(raw).hexdigest() != row["spec_sha256"] or
                canonical_bytes(doc) != raw or
                doc.get("task_id") != task_id or
                doc.get("operation") not in (TAKE_OP, SHOT_OP)):
            raise RuntimeError("Approved task ledger integrity has changed")
        return row, doc

    def cancel_requested(self, task_id):
        """Read under the host's running worker loop, never from an AI token."""
        if type(task_id) is not str or not ID_RE.fullmatch(task_id):
            raise ValueError("Invalid native task")
        with self.ledger._db() as db:
            return db.execute("""SELECT 1 FROM wo6_cancel_intents
                WHERE task_id=?""", (task_id,)).fetchone() is not None

    def request_cancel(self, scope: TrustedReadScope, task_id: str, *,
                       authorize_cancel, reason: str):
        if (not isinstance(scope, TrustedReadScope) or
                not callable(authorize_cancel) or
                type(reason) is not str or not 1 <= len(reason.strip()) <= 160):
            raise PermissionError("Native host must verify the cancel request")
        row, doc = self._approved_spec(task_id)
        if (scope.project_id != doc["project_id"] or
                scope.actor_id != doc["actor_id"] or
                authorize_cancel(scope, task_id, dict(doc)) is not True):
            raise PermissionError("Creator/host denied cancellation for this task")
        if row["state"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            raise RuntimeError("Cannot retroactively cancel a terminal native task")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT OR IGNORE INTO wo6_cancel_intents
                (task_id,requested_at,actor_id,project_id,turn_id,reason)
                VALUES (?,?,?,?,?,?)""",
                (task_id,time.time(),scope.actor_id,scope.project_id,
                 scope.turn_id,reason.strip()))
            db.commit()
        if row["state"] == "QUEUED":
            # If admission raced with this request, ACTIVE remains protected
            # by wait_guarded which now sees the committed cancel intent.
            try:
                self.ledger.cancel_queued(task_id, owner_key=row["owner_key"])
            except RuntimeError:
                pass
        state = self.ledger.get_task(task_id)
        return {
            "task_id": task_id, "state": state["state"],
            "cancel_intent_durable": True,
            "worker_tree_termination_verified": state["state"] == "CANCELLED",
            "source_commit_rolled_back": False,
        }

    def _proof(self, spec, folder):
        """Read-only proof of immutable output identity, not release acceptance."""
        pid = spec["project_id"]
        operation = spec["operation"]
        from backend.nvp_film_index import FilmIndex
        from backend.nvp_studio import Studio
        from pathlib import Path
        db = Path(spec["studio_db"])
        index = FilmIndex(Studio(db))
        oid = spec["take_id"] if operation == TAKE_OP else spec["shot_id"]
        try:
            record = index.read_revision(pid, oid, 1)
        except KeyError:
            return "NO_SOURCE_COMMIT_FOUND", None
        try:
            if operation == TAKE_OP:
                from backend.nvp_openusd_take import OpenUSDTakeCapture
                evidence = OpenUSDTakeCapture(
                    index, verify_creator_action=lambda *_: False
                ).verify_take(pid, oid)
                if (record["kind"] != "take" or
                        evidence["take_document_sha256"] !=
                        record["document_sha256"] or
                        evidence["scene_document_sha256"] !=
                        spec["scene_sha256"] or
                        evidence["timeline_document_sha256"] !=
                        spec["timeline_sha256"]):
                    raise RuntimeError("Take source SHA mismatch")
                from backend.nvp_wo6_native_take_action import RECEIPT_FORMAT as fmt
                receipt_id = "take_document_sha256"
            else:
                from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
                shooter = OpenUSDShotOverrides(
                    index, verify_director_action=lambda *_: False)
                evidence = shooter.evaluate(
                    pid, oid, 1, tick=spec["start_tick"])
                if (record["kind"] != "presentation" or
                        evidence["shot_document_sha256"] !=
                        record["document_sha256"] or
                        record["data"]["take_document_sha256"] !=
                        spec["take_sha256"] or
                        record["data"]["usd_layer_sha256"] !=
                        spec["shot_layer_sha256"]):
                    raise RuntimeError("Shot source/layer SHA mismatch")
                from backend.nvp_wo6_native_shot_action import RECEIPT as fmt
                receipt_id = "shot_sha256"
        except (RuntimeError, ValueError, KeyError, TypeError):
            return "COMMITTED_SOURCE_INTEGRITY_UNVERIFIED", None
        receipt_path = folder / "receipt.json"
        if not receipt_path.exists():
            return "COMMITTED_SOURCE_WITHOUT_WORKER_RECEIPT", record
        if receipt_path.is_symlink() or not receipt_path.is_file():
            return "COMMITTED_SOURCE_RECEIPT_INVALID", record
        try:
            raw = receipt_path.read_bytes()
            receipt = json.loads(raw)
            if (canonical_bytes(receipt) != raw or
                    receipt.get("format") != fmt or
                    receipt.get("task_id") != spec["task_id"] or
                    receipt.get("project_id") != pid or
                    receipt.get("source_impact_sha256") != spec["preview_sha256"] or
                    receipt.get(receipt_id) != record["document_sha256"] or
                    receipt.get("existing_dcp_replaced") is not False or
                    receipt.get("rendered_frames") is not False):
                raise ValueError("Worker receipt cannot be accepted")
        except (OSError, ValueError, TypeError, KeyError):
            return "COMMITTED_SOURCE_RECEIPT_INVALID", record
        return "VERIFIED_COMMIT_AND_RECEIPT_NOT_RELEASE_APPROVED", record

    def reconcile_interrupted(self, task_id: str, *, owner_key: str,
                              job_root, studio_db):
        """Single kernel-leased recovery pass after independently verified worker stop."""
        with WorkerHostLease(job_root):
            return self._reconcile_under_lease(
                task_id, owner_key=owner_key, job_root=job_root,
                studio_db=studio_db)

    def _reconcile_under_lease(self, task_id: str, *, owner_key: str,
                               job_root, studio_db):
        """Never auto-retry or release ACTIVE reservations without OS proof."""
        from pathlib import Path
        row, spec = self._approved_spec(task_id, owner=owner_key)
        if row["state"] not in ("ACTIVE", "INTERRUPTED", "CANCELLED"):
            raise RuntimeError("Only interrupted or safely stopped native work can reconcile")
        if self._attest is None or self._attest(task_id) is not True:
            raise PermissionError("Native OS process-tree cleanup not independently verified")
        folder = Path(job_root).resolve() / task_id
        if (not folder.is_dir() or folder.is_symlink() or
                type(studio_db) not in (Path, str)):
            raise RuntimeError("Native job folder/database path is unavailable")
        path = Path(studio_db)
        if path.is_symlink():
            raise RuntimeError("Untrusted symlinked Studio database")
        path = path.resolve()
        # Database is a host-injected installation value, never a model path.
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Missing or symlinked original Studio database")
        if row["state"] == "ACTIVE":
            self.ledger.finish(
                task_id, "INTERRUPTED",
                "Host verified no running worker; output requires reconciliation")
        record_path = folder / "task.json"
        raw = canonical_bytes(spec)
        if (record_path.is_symlink() or not record_path.is_file() or
                record_path.read_bytes() != raw):
            status, artifact = "SEALED_TASK_SPEC_MISSING_OR_CHANGED", None
        else:
            status, artifact = self._proof({**spec, "studio_db": str(path)}, folder)
        receipt = {
            "format": RECEIPT_FORMAT, "task_id": task_id,
            "operation": spec["operation"], "project_id": spec["project_id"],
            "evidence_status": status,
            "original_ledger_state": row["state"],
            "current_ledger_state": self.ledger.get_task(task_id)["state"],
            "immutable_artifact_id": artifact["object_id"] if artifact else None,
            "immutable_artifact_sha256": (
                artifact["document_sha256"] if artifact else None),
            "native_worker_tree_verified_stopped": True,
            "source_commit_rolled_back": False,
            "auto_retry_performed": False, "new_director_approval_issued": False,
            "film_delivered": False, "release_approved": False,
        }
        proof_sha = _digest(receipt)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT OR IGNORE INTO wo6_recovery_receipts
                (task_id,recorded_at,evidence_sha256,evidence_json)
                VALUES(?,?,?,?)""",
                (task_id,time.time(),proof_sha,canonical_bytes(receipt).decode("ascii")))
            db.commit()
        return {**receipt, "evidence_sha256": proof_sha}

    def finish_verified(self, task_id, *, detail):
        """Finalize only after native proof; atomically fence late cancel intent.

        This closes the small window between checking a cancel flag and the
        ledger's terminal state transition. No AI caller can invoke this as
        a capability; it is a first-party host operation after source proof.
        """
        if type(detail) is not str or len(detail) > 240:
            raise ValueError("Native completion detail must fit durable ledger")
        self._approved_spec(task_id)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT state FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or row[0] != "ACTIVE":
                raise RuntimeError("Only an active verified native task can finish")
            pending = db.execute(
                "SELECT 1 FROM wo6_cancel_intents WHERE task_id=?",
                (task_id,)).fetchone()
            if pending is not None:
                raise NativeCancelRequested(
                    "Creator cancellation outran native success publication")
            now = time.time()
            db.execute("""UPDATE tasks SET state='SUCCEEDED',phase='finished',
                detail=?,completed_fraction=1.0,reserved=0,updated_at=?
                WHERE id=? AND state='ACTIVE'""", (detail, now, task_id))
            self.ledger._event(
                db, task_id, "SUCCEEDED", "finished", detail, 1.0)
            db.commit()

    def status(self, task_id, *, owner_key):
        row, spec = self._approved_spec(task_id, owner=owner_key)
        with self.ledger._db() as db:
            db.row_factory = __import__("sqlite3").Row
            recovery = db.execute("""SELECT evidence_json,evidence_sha256
                FROM wo6_recovery_receipts WHERE task_id=?
                ORDER BY id DESC LIMIT 1""", (task_id,)).fetchone()
        events = self.ledger.events(task_id,limit=20)
        return {
            "format": "nvp.wo6.native_creator_task_status.v1",
            "task_id": task_id, "operation": spec["operation"],
            "state": row["state"], "phase": row["phase"],
            "detail": row["detail"], "events": events,
            "cancel_requested": self.cancel_requested(task_id),
            "latest_reconciliation": (
                {**json.loads(recovery["evidence_json"]),
                 "evidence_sha256": recovery["evidence_sha256"]}
                if recovery else None),
            "stale_active_worker_must_be_verified": (
                row["state"] == "ACTIVE" and
                time.time() - row["updated_at"] > 15),
            "film_delivered": False,
            "AI_permissions_implied": False,
        }
