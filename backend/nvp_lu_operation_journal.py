"""NVP-INT-LU-01F-R1: durable, *non-authorizing* NVP-side IPC ledger.

No Lu Core transport, credential, grant, execution or automatic retry is
exposed here. A protected NVP supervisor must separately attest storage,
caller identity, original user-turn authority and genuine host receipts.
The journal only preserves state and rejects ambiguous or replayed effects.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from typing import Callable

REF = re.compile(r"[A-Za-z0-9_.:/-]{1,128}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
EFFECTS = frozenset(range(1, 9))  # Exact lu.workspace.v0 EffectClass values.
TERMINALS = frozenset({"APPLIED", "REFUSED", "FAILED", "CANCELLED"})
STATES = frozenset({"PREPARED", "IN_FLIGHT", "UNCERTAIN", "TERMINAL"})
MAX_LIVE_OPERATIONS = 4096
MAX_EVENTS_PER_OPERATION = 64
MAX_DETAIL_BYTES = 2048


def _ref(value: object) -> str:
    if type(value) is not str or REF.fullmatch(value) is None:
        raise ValueError("Invalid opaque IPC reference")
    return value


def _digest(value: object) -> str:
    if type(value) is not str or DIGEST.fullmatch(value) is None or value == "0" * 64:
        raise ValueError("Invalid 32-byte SHA-256 hex digest")
    return value


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def _clock() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True)
class OriginRefs:
    workspace_ref: str
    conversation_ref: str
    user_turn_ref: str
    task_ref: str
    operation_ref: str

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            _ref(getattr(self, name))


@dataclass(frozen=True)
class OperationSpec:
    origin: OriginRefs
    capability_id: str
    capability_version: int
    effect_class: int
    input_sha256: str
    object_refs_sha256: str
    deadline_unix_ms: int
    host_session_ref: str  # Host-minted; must be externally attested.
    host_epoch_ref: str    # Exact admitted host epoch, not bearer proof.
    declared_effects: tuple[int, ...] = ()  # R2: preserve compound EXECUTE + WRITE.

    def __post_init__(self):
        if type(self.origin) is not OriginRefs:
            raise ValueError("Host-bound original Lu OriginRefs required")
        _ref(self.capability_id)
        _ref(self.host_session_ref)
        _ref(self.host_epoch_ref)
        if not self.capability_id.startswith("nvp.film."):
            raise ValueError("Only the NVP film capability namespace is admitted")
        if (type(self.capability_version) is not int or not 0 < self.capability_version <= 65535
                or type(self.effect_class) is not int or self.effect_class not in EFFECTS
                or type(self.deadline_unix_ms) is not int or self.deadline_unix_ms <= 0):
            raise ValueError("Invalid bounded Lu capability metadata")
        if (type(self.declared_effects) is not tuple or
                any(type(x) is not int or x not in EFFECTS for x in self.declared_effects) or
                len(set(self.declared_effects)) != len(self.declared_effects) or
                (self.declared_effects and self.effect_class not in self.declared_effects)):
            raise ValueError("Invalid complete declared effect set")
        _digest(self.input_sha256)
        _digest(self.object_refs_sha256)

    @property
    def request_sha256(self) -> str:
        return sha256(_canonical(asdict(self)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReceiptObservation:
    operation_ref: str
    terminal_state: str
    durable_receipt_sha256: str
    reason_code: str
    evidence_available: bool

    def __post_init__(self):
        _ref(self.operation_ref)
        _digest(self.durable_receipt_sha256)
        _ref(self.reason_code)
        if self.terminal_state not in TERMINALS | {"UNCERTAIN"}:
            raise ValueError("Unsupported Lu terminal state")
        if type(self.evidence_available) is not bool:
            raise ValueError("Evidence availability must be boolean")
        if self.terminal_state != "UNCERTAIN" and not self.evidence_available:
            raise PermissionError("No externally verified durable terminal evidence")


class JournalRefusal(PermissionError):
    """State or authorization conflict: fail closed, no implicit retry."""


class IPCOperationJournal:
    """Transactional SQLite operation state, inert until host wiring is accepted.

    `storage_guard(path)` and per-transition `authorize(action, snapshot)` are
    mandatory *host-provided* hooks, not security attestations supplied here.
    `verify_receipt(observation, bound_spec)` must verify a genuine host result
    against the original operation and origin, not merely return True in prod.
    """

    def __init__(self, state_root: Path | str, *, storage_guard: Callable[[Path], bool],
                 clock_ms: Callable[[], int] = _clock):
        if not callable(storage_guard) or not callable(clock_ms):
            raise JournalRefusal("Protected supervisor storage and clock are required")
        root = Path(state_root)
        if (not root.is_absolute() or not root.is_dir() or root.is_symlink()
                or root.resolve(strict=True) != root):
            raise JournalRefusal("An existing absolute protected state directory is required")
        self.root = root
        self.path = root / "nvp-lu-operations.sqlite3"
        self._storage_guard = storage_guard
        self._clock_ms = clock_ms
        self._check_storage()
        if not self.path.exists():
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(self.path, flags, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        self._check_storage()
        with self._tx() as db:
            current = db.execute("PRAGMA user_version").fetchone()[0]
            if current not in (0, 1, 2):
                raise JournalRefusal("Unknown durable Lu IPC journal schema")
            db.execute("""CREATE TABLE IF NOT EXISTS ipc_operations (
                operation_ref TEXT PRIMARY KEY,
                bound_spec TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('PREPARED','IN_FLIGHT','UNCERTAIN','TERMINAL')),
                cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1)),
                revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1)),
                cancel_acknowledged INTEGER NOT NULL DEFAULT 0 CHECK(cancel_acknowledged IN (0,1)),
                dispatch_ref TEXT,
                terminal_state TEXT,
                receipt_sha256 TEXT,
                reason_code TEXT,
                evidence_available INTEGER NOT NULL DEFAULT 0,
                created_ms INTEGER NOT NULL,
                updated_ms INTEGER NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS ipc_operation_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_ref TEXT NOT NULL REFERENCES ipc_operations(operation_ref),
                event_kind TEXT NOT NULL,
                detail TEXT NOT NULL,
                recorded_ms INTEGER NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS ipc_operation_state ON ipc_operations(state)")
            # R2-R1: a native production task is never inferred from a Lu
            # request. It is attached only *after* a protected NVP owner
            # independently confirms the existing real job and exact dispatch.
            db.execute("""CREATE TABLE IF NOT EXISTS ipc_native_jobs (
                operation_ref TEXT PRIMARY KEY REFERENCES ipc_operations(operation_ref),
                dispatch_ref TEXT NOT NULL UNIQUE,
                native_job_ref TEXT NOT NULL UNIQUE,
                native_kind TEXT NOT NULL CHECK(native_kind='production-integrity'),
                project_id TEXT NOT NULL,
                manifest_sha256 TEXT NOT NULL,
                recorded_ms INTEGER NOT NULL
            )""")
            db.execute("PRAGMA user_version=2")

    def _check_storage(self) -> None:
        # Path and ACL/EFS protection are the host's responsibility. No Linux
        # fixture result can assert actual Windows installed storage custody.
        try:
            if self.root.is_symlink() or not self.root.is_dir():
                raise JournalRefusal("IPC state directory replaced")
            for p in (self.path, *(Path(str(self.path) + s) for s in ("-wal", "-shm", "-journal"))):
                try:
                    mode = p.lstat().st_mode
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(mode) or p.stat().st_nlink != 1:
                    raise JournalRefusal("IPC database or sidecar is not a unique regular file")
                if os.name == "posix" and (mode & 0o077):
                    raise JournalRefusal("IPC journal accessible to another local user")
            if os.name == "posix" and self.root.stat().st_mode & 0o077:
                raise JournalRefusal("IPC journal directory accessible to another local user")
            if self._storage_guard(self.root) is not True:
                raise JournalRefusal("Host did not attest protected state storage")
        except OSError as exc:
            raise JournalRefusal("Protected IPC journal storage inaccessible") from exc

    @contextmanager
    def _tx(self):
        self._check_storage()
        db = sqlite3.connect(str(self.path), isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            self._check_storage()
            yield db
            self._check_storage()
            db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _require(self, authorize, action: str, data: dict) -> None:
        if not callable(authorize) or authorize(action, dict(data)) is not True:
            raise JournalRefusal("No verified NVP supervisor authorization")

    def _row(self, db, ref: str):
        row = db.execute("SELECT * FROM ipc_operations WHERE operation_ref=?", (_ref(ref),)).fetchone()
        if row is None:
            raise JournalRefusal("Unknown IPC operation: no execution or replay")
        return row

    def _snapshot(self, row) -> dict:
        return {"operation_ref": row["operation_ref"], "request_sha256": row["request_sha256"],
                "state": row["state"], "cancel_requested": bool(row["cancel_requested"]),
                "revoked": bool(row["revoked"]),
                "cancel_acknowledged": bool(row["cancel_acknowledged"]),
                "terminal_state": row["terminal_state"],
                "receipt_sha256": row["receipt_sha256"], "evidence_available": bool(row["evidence_available"]),
                "reason_code": row["reason_code"]}

    def _event(self, db, ref: str, kind: str, detail: dict) -> None:
        payload = _canonical(detail)
        if len(payload.encode("utf-8")) > MAX_DETAIL_BYTES:
            raise JournalRefusal("IPC event metadata exceeds bound")
        count = db.execute("SELECT COUNT(*) FROM ipc_operation_events WHERE operation_ref=?", (ref,)).fetchone()[0]
        if count >= MAX_EVENTS_PER_OPERATION:
            raise JournalRefusal("IPC event quota reached; manual review required")
        db.execute("INSERT INTO ipc_operation_events(operation_ref,event_kind,detail,recorded_ms) VALUES(?,?,?,?)",
                   (ref, kind, payload, self._clock_ms()))

    def prepare(self, spec: OperationSpec, *, authorize) -> dict:
        """Record an exact host-authorized request; NEVER dispatch automatically."""
        if type(spec) is not OperationSpec:
            raise ValueError("OperationSpec required")
        bound = _canonical(asdict(spec))
        ref = spec.origin.operation_ref
        with self._tx() as db:
            old = db.execute("SELECT * FROM ipc_operations WHERE operation_ref=?", (ref,)).fetchone()
            if old is not None:
                if old["bound_spec"] != bound or old["request_sha256"] != spec.request_sha256:
                    raise JournalRefusal("Operation reference replayed with changed identity/payload")
                return self._snapshot(old)  # Idempotent only, no authorization replay.
            live = db.execute("SELECT COUNT(*) FROM ipc_operations WHERE state!='TERMINAL'").fetchone()[0]
            if live >= MAX_LIVE_OPERATIONS:
                raise JournalRefusal("Bounded IPC journal capacity exhausted")
            self._require(authorize, "nvp.lu.prepare.v1", asdict(spec))
            now = self._clock_ms()
            if spec.deadline_unix_ms <= now:
                raise JournalRefusal("Expired operation cannot be prepared")
            db.execute("""INSERT INTO ipc_operations(operation_ref,bound_spec,request_sha256,state,
                created_ms,updated_ms) VALUES(?,?,?,'PREPARED',?,?)""",
                (ref, bound, spec.request_sha256, now, now))
            self._event(db, ref, "PREPARED", {"request_sha256": spec.request_sha256})
            return self._snapshot(self._row(db, ref))

    def claim_dispatch(self, ref: str, *, authorize) -> dict:
        """At-most-once local dispatch admission, not proof of delivery to Lu."""
        with self._tx() as db:
            row = self._row(db, ref)
            if row["state"] != "PREPARED" or row["cancel_requested"] or row["revoked"]:
                raise JournalRefusal("No safe fresh dispatch; reconcile instead")
            spec = json.loads(row["bound_spec"])
            self._require(authorize, "nvp.lu.dispatch.v1", spec)
            if spec["deadline_unix_ms"] <= self._clock_ms():
                raise JournalRefusal("Expired operation cannot be dispatched")
            ticket = secrets.token_hex(16)
            db.execute("UPDATE ipc_operations SET state='IN_FLIGHT',dispatch_ref=?,updated_ms=? WHERE operation_ref=?",
                       (ticket, self._clock_ms(), ref))
            self._event(db, ref, "DISPATCH_CLAIMED", {"request_sha256": row["request_sha256"]})
            return {"operation_ref": ref, "dispatch_ref": ticket,
                    "request_sha256": row["request_sha256"]}

    def signal_cancel(self, ref: str, *, reason_code: str, authorize) -> dict:
        """Record a request to cancel, never fake worker exit or rollback."""
        reason = _ref(reason_code)
        with self._tx() as db:
            row = self._row(db, ref)
            self._require(authorize, "nvp.lu.cancel.v1",
                          {**self._snapshot(row), "bound_spec": json.loads(row["bound_spec"])})
            if row["state"] == "TERMINAL":
                raise JournalRefusal("Terminal operation cannot be retrospectively cancelled")
            if not row["cancel_requested"]:
                db.execute("UPDATE ipc_operations SET cancel_requested=1,updated_ms=? WHERE operation_ref=?",
                           (self._clock_ms(), ref))
                self._event(db, ref, "CANCEL_SIGNAL_RECORDED", {"reason_code": reason})
            return self._snapshot(self._row(db, ref))

    def record_cancel_ack(self, ref: str, *, signal_recorded: bool, verify_ack) -> dict:
        """Bind Lu CancelAcknowledged to the dispatched operation only.

        Acknowledgment means the host recorded a cancel *signal*. It never
        proves the worker exited, the effect was undone, or terminal CANCELLED.
        """
        if type(signal_recorded) is not bool:
            raise ValueError("Lu cancellation acknowledgment must be boolean")
        with self._tx() as db:
            row = self._row(db, ref)
            if not row["cancel_requested"] or not row["dispatch_ref"]:
                raise JournalRefusal("No dispatched cancellation to acknowledge")
            binding = {"operation_ref": ref, "dispatch_ref": row["dispatch_ref"],
                       "request_sha256": row["request_sha256"]}
            if not callable(verify_ack) or verify_ack(signal_recorded, dict(binding)) is not True:
                raise JournalRefusal("Unauthenticated cancel acknowledgment")
            if signal_recorded and not row["cancel_acknowledged"]:
                db.execute("UPDATE ipc_operations SET cancel_acknowledged=1,updated_ms=? WHERE operation_ref=?",
                           (self._clock_ms(), ref))
                self._event(db, ref, "HOST_CANCEL_SIGNAL_ACKNOWLEDGED", {})
            return self._snapshot(self._row(db, ref))

    def signal_revoke(self, ref: str, *, reason_code: str, authorize) -> dict:
        """Revocation blocks future dispatch; does not undo a completed effect."""
        reason = _ref(reason_code)
        with self._tx() as db:
            row = self._row(db, ref)
            self._require(authorize, "nvp.lu.revoke.v1",
                          {**self._snapshot(row), "bound_spec": json.loads(row["bound_spec"])})
            if not row["revoked"]:
                db.execute("UPDATE ipc_operations SET revoked=1,updated_ms=? WHERE operation_ref=?",
                           (self._clock_ms(), ref))
                self._event(db, ref, "REVOCATION_RECORDED", {"reason_code": reason})
            return self._snapshot(self._row(db, ref))

    def reconcile_after_restart(self, *, authorize) -> list[str]:
        """Never retry in-flight work; move it to durable UNCERTAIN."""
        with self._tx() as db:
            self._require(authorize, "nvp.lu.recover.v1", {"kind": "host_supervisor_only"})
            rows = db.execute("SELECT operation_ref FROM ipc_operations WHERE state='IN_FLIGHT' ORDER BY operation_ref").fetchall()
            for row in rows:
                ref = row["operation_ref"]
                db.execute("UPDATE ipc_operations SET state='UNCERTAIN',updated_ms=? WHERE operation_ref=?",
                           (self._clock_ms(), ref))
                self._event(db, ref, "RESTART_OUTCOME_UNCERTAIN", {})
            return [r["operation_ref"] for r in rows]

    def reconcile_receipt(self, spec: OperationSpec, observation: ReceiptObservation, *,
                          verify_receipt) -> dict:
        """Apply only independently authenticated exact-operation host evidence.

        `verify_receipt` must validate original user turn, host admission,
        per-turn effect grant, receipt custody and worker terminal evidence.
        A testing lambda is not an installed attestation. UNCERTAIN is not an
        effect failure and can later be reconciled to a verified terminal.
        """
        if type(spec) is not OperationSpec or type(observation) is not ReceiptObservation:
            raise ValueError("Typed operation and receipt evidence required")
        if observation.operation_ref != spec.origin.operation_ref:
            raise JournalRefusal("Receipt operation identity mismatch")
        with self._tx() as db:
            row = self._row(db, observation.operation_ref)
            if row["bound_spec"] != _canonical(asdict(spec)) or row["request_sha256"] != spec.request_sha256:
                raise JournalRefusal("Receipt origin, effect or payload does not match durable request")
            if row["state"] == "PREPARED":
                raise JournalRefusal("No dispatched effect to reconcile")
            binding = {"operation_ref": row["operation_ref"],
                       "request_sha256": row["request_sha256"],
                       "dispatch_ref": row["dispatch_ref"]}
            if (not callable(verify_receipt)
                    or verify_receipt(observation, spec, dict(binding)) is not True):
                raise JournalRefusal("No independently authenticated host receipt")
            if row["state"] == "TERMINAL":
                if (row["terminal_state"] != observation.terminal_state or
                        row["receipt_sha256"] != observation.durable_receipt_sha256 or
                        row["reason_code"] != observation.reason_code):
                    raise JournalRefusal("Conflicting terminal receipt; never overwrite")
                return self._snapshot(row)
            if observation.terminal_state == "UNCERTAIN":
                if (row["state"] == "UNCERTAIN" and
                        row["receipt_sha256"] == observation.durable_receipt_sha256 and
                        row["reason_code"] == observation.reason_code and
                        bool(row["evidence_available"]) == observation.evidence_available):
                    return self._snapshot(row)
                db.execute("""UPDATE ipc_operations SET state='UNCERTAIN',reason_code=?,
                    receipt_sha256=?,evidence_available=?,updated_ms=? WHERE operation_ref=?""",
                    (observation.reason_code,observation.durable_receipt_sha256,
                     int(observation.evidence_available),self._clock_ms(),observation.operation_ref))
                self._event(db, observation.operation_ref, "HOST_OUTCOME_UNCERTAIN",
                            {"receipt_sha256": observation.durable_receipt_sha256})
            else:
                db.execute("""UPDATE ipc_operations SET state='TERMINAL',terminal_state=?,
                    reason_code=?,receipt_sha256=?,evidence_available=1,updated_ms=? WHERE operation_ref=?""",
                    (observation.terminal_state,observation.reason_code,
                     observation.durable_receipt_sha256,self._clock_ms(),observation.operation_ref))
                self._event(db, observation.operation_ref, "HOST_TERMINAL_VERIFIED",
                            {"terminal_state": observation.terminal_state,
                             "receipt_sha256": observation.durable_receipt_sha256})
            return self._snapshot(self._row(db, observation.operation_ref))

    def bind_native_job(self, spec: OperationSpec, *, dispatch_ref: str,
                        native_job_ref: str, project_id: str,
                        manifest_sha256: str, native_kind: str, authorize) -> dict:
        """Durably attach an ALREADY host-verified native production job.

        Not an instruction to execute a worker. A native job is minted by the
        protected NVP production supervisor, never by Lu. An interrupted
        attachment may leave a dispatched IPC operation UNCERTAIN; it may not
        be repeated or assigned to an arbitrary new native job.
        """
        if type(spec) is not OperationSpec or native_kind != 'production-integrity':
            raise JournalRefusal('Unsupported native operation type')
        ticket = _ref(dispatch_ref)
        job = _ref(native_job_ref)
        project = _ref(project_id)
        manifest = _digest(manifest_sha256)
        ref = spec.origin.operation_ref
        with self._tx() as db:
            row = self._row(db, ref)
            if (row['bound_spec'] != _canonical(asdict(spec)) or
                    row['request_sha256'] != spec.request_sha256 or
                    row['dispatch_ref'] != ticket or
                    row['state'] not in ('IN_FLIGHT', 'UNCERTAIN', 'TERMINAL')):
                raise JournalRefusal('Native binding is not the claimed IPC dispatch')
            details = {'operation_ref': ref, 'dispatch_ref': ticket,
                       'request_sha256': spec.request_sha256,
                       'native_job_ref': job, 'native_kind': native_kind,
                       'project_id': project, 'manifest_sha256': manifest}
            self._require(authorize, 'nvp.lu.bind_native_job.v1', details)
            existing = db.execute('SELECT * FROM ipc_native_jobs WHERE operation_ref=?',
                                  (ref,)).fetchone()
            if existing is not None:
                if any(existing[k] != details[k] for k in
                       ('dispatch_ref','native_job_ref','native_kind','project_id',
                        'manifest_sha256')):
                    raise JournalRefusal('Conflicting native job binding')
            else:
                try:
                    db.execute("""INSERT INTO ipc_native_jobs
                        (operation_ref,dispatch_ref,native_job_ref,native_kind,
                         project_id,manifest_sha256,recorded_ms)
                         VALUES(?,?,?,?,?,?,?)""",
                        (ref,ticket,job,native_kind,project,manifest,self._clock_ms()))
                except sqlite3.IntegrityError as exc:
                    raise JournalRefusal('Native job reused across IPC operations') from exc
                self._event(db, ref, 'HOST_NATIVE_JOB_BOUND',
                            {'native_kind': native_kind, 'manifest_sha256': manifest})
            return dict(details)

    def dispatch_binding(self, ref: str, *, authorize) -> dict:
        """Read exact at-most-once dispatch identity for protected receipt linking.

        Never accepts the dispatch token from Lu or the worker. A native owner
        must authorize this lookup against the original request and user turn.
        Returned data is correlation only, not a permission to re-dispatch.
        """
        with self._tx() as db:
            row = self._row(db, ref)
            if row['state'] not in ('IN_FLIGHT','UNCERTAIN','TERMINAL') or not row['dispatch_ref']:
                raise JournalRefusal('No claimed native dispatch to reconcile')
            evidence = {'operation_ref': row['operation_ref'],
                        'dispatch_ref': row['dispatch_ref'],
                        'request_sha256': row['request_sha256']}
            self._require(authorize, 'nvp.lu.inspect_dispatch.v1', evidence)
            return evidence

    def native_job_binding(self, ref: str, *, authorize) -> dict:
        """Return only an owner-authorized original job binding; never a grant."""
        with self._tx() as db:
            row = self._row(db, ref)
            binding = db.execute('SELECT * FROM ipc_native_jobs WHERE operation_ref=?',
                                 (ref,)).fetchone()
            if binding is None:
                raise JournalRefusal('No protected native job attached to operation')
            evidence = {k: binding[k] for k in ('operation_ref','dispatch_ref',
                'native_job_ref','native_kind','project_id','manifest_sha256')}
            evidence['request_sha256'] = row['request_sha256']
            if row['dispatch_ref'] != binding['dispatch_ref']:
                raise JournalRefusal('Native binding lost original dispatch identity')
            self._require(authorize, 'nvp.lu.inspect_native_job.v1', evidence)
            return evidence

    def bound_spec(self, ref: str, *, authorize) -> OperationSpec:
        """Retrieve original immutable scope only after protected-supervisor approval.

        Cancel carries no OriginRefs in Lu's wire format. Callers must NOT
        infer the original user scope from the current UI or a claimed peer.
        """
        with self._tx() as db:
            row = self._row(db, ref)
            original = json.loads(row["bound_spec"])
            self._require(authorize, "nvp.lu.inspect_original.v1", self._snapshot(row))
            origin = OriginRefs(**original.pop("origin"))
            original["declared_effects"] = tuple(original.get("declared_effects", ()))
            spec = OperationSpec(origin=origin, **original)
            if spec.request_sha256 != row["request_sha256"]:
                raise JournalRefusal("Original IPC operation binding was modified")
            return spec

    def status(self, ref: str) -> dict:
        with self._tx() as db:
            return self._snapshot(self._row(db, ref))

    def events(self, ref: str) -> list[dict]:
        with self._tx() as db:
            self._row(db, ref)
            rows = db.execute("SELECT event_kind,detail,recorded_ms FROM ipc_operation_events WHERE operation_ref=? ORDER BY event_id",
                              (ref,)).fetchall()
            return [{"kind": r["event_kind"], "detail": json.loads(r["detail"]),
                     "recorded_ms": r["recorded_ms"]} for r in rows]
