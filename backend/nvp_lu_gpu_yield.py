"""NVP-INT-LU-01E-GPU-01: durable, request-only Lu GPU-yield coordination.

This is NVP's *client-side* state machine. It contains no model manager,
process killer, signer, installed Lu listener, or local GPU-release issuer.
The accepted Lu Core GPU-yield lease/all-clear messages are NOT in the pinned
lu.workspace.v0 contract yet (Core issue #250); positive native admission
therefore requires an independently authenticated future Core interface.

Never interpret legacy ResourceTransitionDecision.ALLOWED as a VRAM lease.
Never send an all-clear from a Python finally block or a PID exit code alone.
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

from backend.nvp_lu_operation_journal import OriginRefs, _ref, _digest

GPU_JOB = re.compile(r"(?:ltx|wan|blender|nvp_gpu)_[a-f0-9]{24}\Z")
PROJECT = re.compile(r"[a-f0-9]{32}\Z")
DEVICE = re.compile(r"[A-Za-z0-9_.:/-]{1,96}\Z")
VALID_PHASES = frozenset({
    'PREPARED', 'REQUEST_SENT', 'WAITING_CORE', 'GRANTED', 'PROCESSING',
    'QUIESCENCE_PENDING', 'ALL_CLEAR_READY', 'ALL_CLEAR_SENT',
    'RELEASED', 'REFUSED', 'UNCERTAIN',
})
RELOAD_STATES = frozenset({'PENDING', 'READY', 'DEFERRED', 'FAILED', 'NOT_REQUESTED'})
MAX_VRAM = 128 * 1024**3
MAX_DURATION_MS = 8 * 60 * 60 * 1000
MAX_ACTIVE = 64


class GpuYieldRefusal(PermissionError):
    """Resource admission is unavailable/unsafe; never fall back to starting."""


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _sha(obj) -> str:
    return sha256(_json(obj).encode('ascii')).hexdigest()


def _job(value: str) -> str:
    if type(value) is not str or not GPU_JOB.fullmatch(value):
        raise ValueError('Reviewed NVP native diffuser job reference required')
    return value


def _device(value: str) -> str:
    if type(value) is not str or not DEVICE.fullmatch(value):
        raise ValueError('Native observed GPU device identity required')
    return value


def _positive_int(value: int, bound: int) -> int:
    if type(value) is not int or not 0 < value <= bound:
        raise ValueError('Invalid bounded positive resource quantity')
    return value


@dataclass(frozen=True)
class YieldIntent:
    origin: OriginRefs                 # Lu trusted original user turn, NOT NVP-generated permission.
    session_ref: str                  # Host-owned admitted session, not a bearer credential.
    core_epoch_ref: str
    project_id: str
    native_job_ref: str              # Exact NVP SCM/Job protected production task.
    device_ref: str                  # Independently observed physical/OS device, not model path.
    desired_free_vram_bytes: int
    duration_ms: int
    deadline_unix_ms: int

    def __post_init__(self):
        if type(self.origin) is not OriginRefs:
            raise ValueError('Original typed Lu turn identity required')
        _ref(self.session_ref); _ref(self.core_epoch_ref)
        if type(self.project_id) is not str or not PROJECT.fullmatch(self.project_id):
            raise ValueError('Canonical NVP project identity required')
        _job(self.native_job_ref); _device(self.device_ref)
        _positive_int(self.desired_free_vram_bytes, MAX_VRAM)
        _positive_int(self.duration_ms, MAX_DURATION_MS)
        if type(self.deadline_unix_ms) is not int or self.deadline_unix_ms <= 0:
            raise ValueError('Bounded Lu request deadline required')

    @property
    def intent_sha256(self) -> str:
        return _sha(asdict(self))


@dataclass(frozen=True)
class CoreYieldGrant:
    """Fields of a Core-issued *verified* grant, not authorization by itself."""
    operation_ref: str
    intent_sha256: str
    session_ref: str
    core_epoch_ref: str
    native_job_ref: str
    device_ref: str
    lease_ref: str                  # Minted by Lu; never a bearer credential.
    model_generation_ref: str      # Selected Lu model identity generation (not file/path).
    observed_free_vram_bytes: int
    sampled_unix_ms: int
    expires_unix_ms: int
    durable_core_receipt_sha256: str

    def __post_init__(self):
        for ref in (self.operation_ref, self.session_ref, self.core_epoch_ref,
                    self.lease_ref, self.model_generation_ref):
            _ref(ref)
        _job(self.native_job_ref); _device(self.device_ref)
        _digest(self.intent_sha256); _digest(self.durable_core_receipt_sha256)
        _positive_int(self.observed_free_vram_bytes, MAX_VRAM)
        if type(self.sampled_unix_ms) is not int or type(self.expires_unix_ms) is not int:
            raise ValueError('Native Core measurement and expiry required')


@dataclass(frozen=True)
class NativeGpuQuiescence:
    """Host-observed witness; input data alone is NEVER proof without OS verifier."""
    operation_ref: str
    native_job_ref: str
    device_ref: str
    lease_ref: str
    worker_tree_reaped: bool
    gpu_contexts_quiescent: bool
    release_fence_closed: bool
    scm_custody_verified: bool
    active_gpu_workers: int
    durable_native_receipt_sha256: str

    def __post_init__(self):
        _ref(self.operation_ref); _job(self.native_job_ref)
        _device(self.device_ref); _ref(self.lease_ref)
        _digest(self.durable_native_receipt_sha256)
        if (any(type(getattr(self, x)) is not bool for x in (
                'worker_tree_reaped', 'gpu_contexts_quiescent',
                'release_fence_closed', 'scm_custody_verified')) or
                type(self.active_gpu_workers) is not int or self.active_gpu_workers < 0):
            raise ValueError('Genuine native kernel and GPU context evidence required')


@dataclass(frozen=True)
class CoreReleaseAck:
    operation_ref: str
    lease_ref: str
    core_epoch_ref: str
    release_ref: str
    native_receipt_sha256: str
    core_release_receipt_sha256: str
    reload_state: str             # Lu reports this; NVP never requests a model load.

    def __post_init__(self):
        for x in (self.operation_ref, self.lease_ref, self.core_epoch_ref, self.release_ref):
            _ref(x)
        _digest(self.native_receipt_sha256); _digest(self.core_release_receipt_sha256)
        if type(self.reload_state) is not str or self.reload_state not in RELOAD_STATES:
            raise ValueError('Unknown Core-owned model reload state')


class GpuYieldJournal:
    """SQLite WAL/FULL protected owner journal, with exact operation/lease binding.

    storage_guard and owner authorization hooks MUST be supplied by the real
    NVP installed native supervisor. Test callbacks are NOT installed evidence.
    """
    def __init__(self, root: Path | str, *, storage_guard: Callable[[Path], bool],
                 clock_ms: Callable[[], int] = _now_ms):
        self.root = Path(root)
        self.path = self.root / 'nvp-lu-gpu-yields.sqlite3'
        self._storage_guard = storage_guard
        self._clock_ms = clock_ms
        if not callable(storage_guard) or not callable(clock_ms):
            raise GpuYieldRefusal('Protected NVP owner guard and clock required')
        self._guard()
        if not self.path.exists():
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os,'O_NOFOLLOW',0)
            try:
                fd = os.open(self.path, flags, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        with self._tx() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1):
                raise GpuYieldRefusal('Unknown protected GPU yield journal schema')
            db.execute('''CREATE TABLE IF NOT EXISTS gpu_yields (
                operation_ref TEXT PRIMARY KEY,
                scope_json TEXT NOT NULL,
                scope_sha256 TEXT NOT NULL,
                state TEXT NOT NULL,
                grant_json TEXT,
                lease_ref TEXT UNIQUE,
                quiescence_json TEXT,
                release_ref TEXT UNIQUE,
                acknowledgement_json TEXT,
                created_ms INTEGER NOT NULL,
                updated_ms INTEGER NOT NULL
            )''')
            db.execute('PRAGMA user_version=1')

    def _guard(self):
        if (not self.root.is_absolute() or not self.root.is_dir() or
                self.root.is_symlink() or self.root.resolve(strict=True) != self.root):
            raise GpuYieldRefusal('Existing absolute protected state root required')
        if os.name == 'posix' and self.root.stat().st_mode & 0o077:
            raise GpuYieldRefusal('GPU journal directory cannot be shared')
        for p in (self.path, *(Path(str(self.path) + s) for s in ('-wal','-shm','-journal'))):
            try: st = p.lstat()
            except FileNotFoundError: continue
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or
                    (os.name=='posix' and st.st_mode & 0o077)):
                raise GpuYieldRefusal('Unprotected or linked GPU journal file')
        if self._storage_guard(self.root) is not True:
            raise GpuYieldRefusal('NVP owner/EFS storage attestation missing')

    @contextmanager
    def _tx(self):
        self._guard()
        db = sqlite3.connect(str(self.path), isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA busy_timeout=10000')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            self._guard()
            yield db
            self._guard()
            db.commit()
        except BaseException:
            if db.in_transaction: db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _row(db, ref):
        row = db.execute('SELECT * FROM gpu_yields WHERE operation_ref=?',(_ref(ref),)).fetchone()
        if row is None: raise GpuYieldRefusal('Unknown GPU operation: no retry or release')
        if row['state'] not in VALID_PHASES: raise GpuYieldRefusal('Unknown GPU yield state')
        return row

    @staticmethod
    def _public(row):
        return {'operation_ref':row['operation_ref'], 'state':row['state'],
                'lease_ref':row['lease_ref'], 'release_ref':row['release_ref'],
                'has_verified_quiescence':row['quiescence_json'] is not None,
                'has_core_release_ack':row['acknowledgement_json'] is not None}

    def inspect(self, ref: str, *, authorize) -> dict:
        with self._tx() as db:
            row=self._row(db,ref)
            self._authorize(authorize,'inspect',dict(self._public(row)))
            return self._public(row)

    @staticmethod
    def _authorize(fn, action, scope):
        if not callable(fn) or fn(action, dict(scope)) is not True:
            raise GpuYieldRefusal('No original-turn protected native authorization')

    def prepare(self, intent: YieldIntent, *, authorize) -> dict:
        if type(intent) is not YieldIntent:
            raise ValueError('Typed GPU request required')
        data=_json(asdict(intent))
        ref=intent.origin.operation_ref
        with self._tx() as db:
            row=db.execute('SELECT * FROM gpu_yields WHERE operation_ref=?',(ref,)).fetchone()
            if row is not None:
                if row['scope_json']!=data or row['scope_sha256']!=intent.intent_sha256:
                    raise GpuYieldRefusal('GPU operation replayed with changed original scope')
                self._authorize(authorize,'request-reconcile',asdict(intent))
                return self._public(row)  # No implicit re-transmit.
            self._authorize(authorize,'request',asdict(intent))
            now=self._clock_ms()
            if intent.deadline_unix_ms<=now or intent.deadline_unix_ms>now+MAX_DURATION_MS:
                raise GpuYieldRefusal('Expired or unbounded GPU request deadline')
            live=db.execute("SELECT COUNT(*) FROM gpu_yields WHERE state NOT IN ('RELEASED','REFUSED')").fetchone()[0]
            if live >= MAX_ACTIVE: raise GpuYieldRefusal('Too many unresolved GPU reservations')
            db.execute('INSERT INTO gpu_yields(operation_ref,scope_json,scope_sha256,state,created_ms,updated_ms) VALUES(?,?,?,\'PREPARED\',?,?)',
                (ref,data,intent.intent_sha256,now,now))
            return self._public(self._row(db,ref))

    def mark_request_sent(self, intent: YieldIntent, *, authorize) -> dict:
        """Durable pre-transmission fence; crash after this means UNCERTAIN."""
        with self._tx() as db:
            row=self._row(db,intent.origin.operation_ref)
            if row['scope_sha256']!=intent.intent_sha256 or row['state']!='PREPARED':
                raise GpuYieldRefusal('Only one fresh cooperative-unload request permitted')
            self._authorize(authorize,'send',asdict(intent))
            if intent.deadline_unix_ms<=self._clock_ms():
                raise GpuYieldRefusal('GPU request deadline passed')
            db.execute("UPDATE gpu_yields SET state='REQUEST_SENT',updated_ms=? WHERE operation_ref=?",
                       (self._clock_ms(),intent.origin.operation_ref))
            return self._public(self._row(db,intent.origin.operation_ref))

    def record_legacy_decision(self, ref: str, *, allowed: bool, verify_core_decision) -> dict:
        """An ALLOWED advisory reply cannot prove freed VRAM or grant a lease."""
        if type(allowed) is not bool: raise ValueError('Typed legacy decision required')
        with self._tx() as db:
            row=self._row(db,ref)
            if row['state'] not in ('REQUEST_SENT','WAITING_CORE'):
                raise GpuYieldRefusal('No outstanding legacy resource advisory request')
            self._authorize(verify_core_decision,'core-legacy-advisory',self._public(row))
            target='WAITING_CORE' if allowed else 'REFUSED'
            db.execute('UPDATE gpu_yields SET state=?,updated_ms=? WHERE operation_ref=?',
                       (target,self._clock_ms(),ref))
            return self._public(self._row(db,ref))

    def accept_verified_core_grant(self, intent: YieldIntent, grant: CoreYieldGrant, *, verify_core_grant) -> dict:
        """Only independently verified Core-issued lease+memory release permits launch."""
        if type(grant) is not CoreYieldGrant: raise ValueError('Core lease type required')
        with self._tx() as db:
            row=self._row(db,intent.origin.operation_ref)
            self._authorize(verify_core_grant,'core-grant',{'scope':asdict(intent),'grant':asdict(grant)})
            if row['scope_sha256']!=intent.intent_sha256:
                raise GpuYieldRefusal('Changed user-turn / NVP source identity')
            if row['state']=='GRANTED' and row['grant_json']==_json(asdict(grant)):
                return self._public(row)
            if row['state'] not in ('REQUEST_SENT','WAITING_CORE'):
                raise GpuYieldRefusal('Core grant was not expected')
            now=self._clock_ms()
            if (grant.operation_ref!=intent.origin.operation_ref or
                grant.intent_sha256!=intent.intent_sha256 or
                grant.session_ref!=intent.session_ref or
                grant.core_epoch_ref!=intent.core_epoch_ref or
                grant.native_job_ref!=intent.native_job_ref or
                grant.device_ref!=intent.device_ref or
                grant.observed_free_vram_bytes<intent.desired_free_vram_bytes or
                grant.sampled_unix_ms<row['created_ms'] or
                grant.sampled_unix_ms>now+2000 or
                grant.expires_unix_ms<=now or
                grant.expires_unix_ms>row['created_ms']+intent.duration_ms or
                now>=intent.deadline_unix_ms):
                raise GpuYieldRefusal('No fresh original Lu grant plus measured released VRAM')
            try:
                db.execute('UPDATE gpu_yields SET state=\'GRANTED\',grant_json=?,lease_ref=?,updated_ms=? WHERE operation_ref=?',
                   (_json(asdict(grant)),grant.lease_ref,now,intent.origin.operation_ref))
            except sqlite3.IntegrityError as exc:
                raise GpuYieldRefusal('Lu GPU lease reused by another original operation') from exc
            return self._public(self._row(db,intent.origin.operation_ref))

    def begin_processing(self, intent: YieldIntent, *, verify_live_core_lease, verify_nvp_native_launch) -> dict:
        with self._tx() as db:
            row=self._row(db,intent.origin.operation_ref)
            if row['scope_sha256']!=intent.intent_sha256 or row['state']!='GRANTED':
                raise GpuYieldRefusal('Diffusion cannot start without confirmed Lu yield lease')
            grant=CoreYieldGrant(**json.loads(row['grant_json']))
            if (grant.expires_unix_ms<=self._clock_ms() or
                    self._clock_ms()>=intent.deadline_unix_ms):
                raise GpuYieldRefusal('Lu lease expired before diffuser admission')
            self._authorize(verify_live_core_lease,'core-live-lease',asdict(grant))
            self._authorize(verify_nvp_native_launch,'nvp-native-admission',
                            {'scope':asdict(intent),'grant':asdict(grant)})
            db.execute("UPDATE gpu_yields SET state='PROCESSING',updated_ms=? WHERE operation_ref=?",
                       (self._clock_ms(),intent.origin.operation_ref))
            return self._public(self._row(db,intent.origin.operation_ref))

    def abandon_granted_job_before_launch(self, intent: YieldIntent, *,
                                          verify_no_native_worker) -> dict:
        """Cancel a *granted but never started* job with independent OS proof.

        Lu owns its yielded model until NVP sends verified all-clear. A creator
        cancellation before launch cannot strand the lease forever, but a
        source-only assertion that no GPU child started is insufficient.
        """
        with self._tx() as db:
            row=self._row(db,intent.origin.operation_ref)
            if row['scope_sha256']!=intent.intent_sha256 or row['state']!='GRANTED':
                raise GpuYieldRefusal('Only an unstarted bound Core grant can be abandoned')
            self._authorize(verify_no_native_worker,'nvp-verified-no-launch',
                            {'scope':asdict(intent),'grant':json.loads(row['grant_json'])})
            db.execute("UPDATE gpu_yields SET state='QUIESCENCE_PENDING',updated_ms=? WHERE operation_ref=?",
                       (self._clock_ms(),intent.origin.operation_ref))
            return self._public(self._row(db,intent.origin.operation_ref))

    def mark_processing_stopped(self, ref: str, *, authorize_owner) -> dict:
        """Stopped report is not SCM/Job/GPU quiescence proof."""
        with self._tx() as db:
            row=self._row(db,ref)
            if row['state']!='PROCESSING':
                raise GpuYieldRefusal('Only an admitted GPU job can report worker stop')
            self._authorize(authorize_owner,'stop-observed',self._public(row))
            db.execute("UPDATE gpu_yields SET state='QUIESCENCE_PENDING',updated_ms=? WHERE operation_ref=?",
                       (self._clock_ms(),ref))
            return self._public(self._row(db,ref))

    def accept_native_quiescence(self, witness: NativeGpuQuiescence, *, verify_installed_native_receipt) -> dict:
        """Requires independent SCM/Job AND GPU context observation for *all* workers."""
        if type(witness) is not NativeGpuQuiescence:
            raise ValueError('Typed kernel/SCM witness required')
        with self._tx() as db:
            row=self._row(db,witness.operation_ref)
            if row['state']!='QUIESCENCE_PENDING' or not row['grant_json']:
                raise GpuYieldRefusal('No finished protected worker to release')
            intent=json.loads(row['scope_json']); grant=json.loads(row['grant_json'])
            if (witness.native_job_ref!=intent['native_job_ref'] or
                witness.device_ref!=intent['device_ref'] or
                witness.lease_ref!=grant['lease_ref'] or
                not (witness.worker_tree_reaped and witness.gpu_contexts_quiescent and
                     witness.release_fence_closed and witness.scm_custody_verified) or
                witness.active_gpu_workers!=0):
                raise GpuYieldRefusal('NVP GPU workers/contexts are not safely quiescent')
            self._authorize(verify_installed_native_receipt,'nvp-scm-gpu-quiescent',
                            {'scope':intent, 'grant':grant,'witness':asdict(witness)})
            db.execute("UPDATE gpu_yields SET state='ALL_CLEAR_READY',quiescence_json=?,updated_ms=? WHERE operation_ref=?",
                       (_json(asdict(witness)),self._clock_ms(),witness.operation_ref))
            return self._public(self._row(db,witness.operation_ref))

    def mark_all_clear_sent(self, ref: str, *, authorize_owner) -> dict:
        """Persist idempotency ref BEFORE sending; never synthesize Core ack."""
        with self._tx() as db:
            row=self._row(db,ref)
            if row['state']!='ALL_CLEAR_READY' or not row['quiescence_json']:
                raise GpuYieldRefusal('Cannot release Lu lease without native quiescence')
            self._authorize(authorize_owner,'send-all-clear',self._public(row))
            release_ref='gpu-clear-'+secrets.token_hex(16)
            db.execute("UPDATE gpu_yields SET state='ALL_CLEAR_SENT',release_ref=?,updated_ms=? WHERE operation_ref=?",
                       (release_ref,self._clock_ms(),ref))
            return self._public(self._row(db,ref))

    def accept_lu_release_ack(self, ack: CoreReleaseAck, *, verify_core_ack) -> dict:
        if type(ack) is not CoreReleaseAck: raise ValueError('Typed Core release acknowledgment required')
        with self._tx() as db:
            row=self._row(db,ack.operation_ref)
            if row['state']=='RELEASED' and row['acknowledgement_json']==_json(asdict(ack)):
                self._authorize(verify_core_ack,'core-release-ack-repeat',{'ack':asdict(ack)})
                return self._public(row)
            if row['state'] not in ('ALL_CLEAR_SENT','UNCERTAIN') or not row['quiescence_json']:
                raise GpuYieldRefusal('Core cannot acknowledge a nonexistent all-clear')
            grant=json.loads(row['grant_json']); witness=json.loads(row['quiescence_json'])
            if (ack.lease_ref!=row['lease_ref'] or ack.core_epoch_ref!=grant['core_epoch_ref'] or
                ack.release_ref!=row['release_ref'] or
                ack.native_receipt_sha256!=witness['durable_native_receipt_sha256']):
                raise GpuYieldRefusal('Foreign, stale or altered Core all-clear acknowledgment')
            self._authorize(verify_core_ack,'core-release-ack',
                            {'grant':grant,'witness':witness,'ack':asdict(ack)})
            db.execute("UPDATE gpu_yields SET state='RELEASED',acknowledgement_json=?,updated_ms=? WHERE operation_ref=?",
                       (_json(asdict(ack)),self._clock_ms(),ack.operation_ref))
            return self._public(self._row(db,ack.operation_ref))

    def recover_after_restart(self, *, authorize_owner) -> list[str]:
        """Keep Lu unloaded until Core independently proves safe; NEVER resend."""
        unresolved=[]
        with self._tx() as db:
            for row in db.execute("SELECT * FROM gpu_yields WHERE state NOT IN ('RELEASED','REFUSED','UNCERTAIN')").fetchall():
                self._authorize(authorize_owner,'reconcile',self._public(row))
                db.execute("UPDATE gpu_yields SET state='UNCERTAIN',updated_ms=? WHERE operation_ref=?",
                           (self._clock_ms(),row['operation_ref']))
                unresolved.append(row['operation_ref'])
        return unresolved

    def core_reconcile(self, ref: str, *, verify_reconciliation) -> dict:
        """Exposes bound evidence for an authenticated Core-side reconciliation.

        Not a request to renew/restart/reload and never a synthetic release.
        """
        with self._tx() as db:
            row=self._row(db,ref)
            self._authorize(verify_reconciliation,'reconcile-read',self._public(row))
            return {'state':row['state'],'scope':json.loads(row['scope_json']),
                    'grant':json.loads(row['grant_json']) if row['grant_json'] else None,
                    'quiescence':json.loads(row['quiescence_json']) if row['quiescence_json'] else None,
                    'release_ref':row['release_ref']}


class LegacyResourceRequestCodec:
    """Existing canonical Lu 1.2 resource_request wire, *advisory only*.

    frame_class comes from NVP's source-pinned generated Lu Protobuf module.
    The actual installed named-pipe/UDS session authenticates each frame.
    No inferred grant/lease/approval from resource_decision is permitted.
    """
    WIRE_MAJOR = 1
    WIRE_MINOR = 2

    def __init__(self, frame_class):
        if (not hasattr(frame_class, 'DESCRIPTOR') or
                frame_class.DESCRIPTOR.full_name != 'lu.workspace.v0.WorkspaceFrame' or
                not any(f.name=='resource_request' and f.number==21 for f in frame_class.DESCRIPTOR.fields)):
            raise GpuYieldRefusal('Exact generated Lu resource Protobuf required')
        self.frame_class=frame_class

    def build_cooperative_unload(self, intent: YieldIntent, *, request_id: str):
        frame=self.frame_class(protocol_major=self.WIRE_MAJOR,protocol_minor=self.WIRE_MINOR,
            request_id=_ref(request_id),session_ref=intent.session_ref)
        request=frame.resource_request
        for f in intent.origin.__dataclass_fields__:
            setattr(request.origin,f,getattr(intent.origin,f))
        request.action=1  # lu.workspace.v0 RESOURCE_ACTION_COOPERATIVE_UNLOAD
        request.desired_free_vram_bytes=intent.desired_free_vram_bytes
        return frame

    def build_capacity_query(self, intent: YieldIntent, *, request_id: str):
        """Read-only capability/memory inquiry; does not unload Lu's model."""
        frame=self.build_cooperative_unload(intent,request_id=request_id)
        frame.resource_request.action=4  # RESOURCE_ACTION_QUERY_CAPACITY
        return frame

    def observe_decision(self, frame, intent: YieldIntent, *, request_id: str):
        if (type(frame) is not self.frame_class or
                frame.protocol_major!=self.WIRE_MAJOR or
                frame.protocol_minor!=self.WIRE_MINOR or
                frame.request_id!=request_id or
                frame.session_ref!=intent.session_ref or
                frame.WhichOneof('body')!='resource_decision' or
                frame.resource_decision.operation_ref!=intent.origin.operation_ref):
            raise GpuYieldRefusal('Foreign Lu resource response/session')
        decision=frame.resource_decision.decision
        if decision==2: return 'DENIED'
        if decision in (1,3,4): return 'ADVISORY_ONLY'  # ALLOWED, DEFERRED, UNKNOWN
        raise GpuYieldRefusal('Unknown Lu resource transition')


class NativeLuAdvisoryGateway:
    """Existing Lu v1.2 *read-only* capacity inquiry on the admitted pipe.

    Native exchange and peer verification must be the installed original OS
    owner; this object opens NO sockets and has NO credential, signer or model
    process privileges. A legacy ALLOWED response is informational only. The
    safe lease/all-clear interface remains unavailable until Core issue #250.
    """
    def __init__(self, frame_class, *, native_exchange, verify_installed_lu_peer):
        if not callable(native_exchange) or not callable(verify_installed_lu_peer):
            raise GpuYieldRefusal('Authenticated native Lu Gateway carrier required')
        self.codec=LegacyResourceRequestCodec(frame_class)
        self._exchange=native_exchange
        self._verify_peer=verify_installed_lu_peer

    def ready_for_safe_roundtrip(self, intent: YieldIntent) -> bool:
        return False  # No durable GPU all-clear acknowledgment in Lu v1.2.

    def request_cooperative_gpu_yield(self, intent: YieldIntent):
        # Core v1.2 has no GPU-yield lease or all-clear acknowledgement.
        # Sending a live unload now could strand Lu with its model evicted
        # and NVP unable to prove completion. Refuse until Core #250's
        # *complete* authenticated roundtrip is supported, then replace the
        # whole request/ack port; never enable only this first half.
        raise GpuYieldRefusal('No safe unload+all-clear roundtrip in draft Lu Core #250')

    def query_capacity(self, intent: YieldIntent):
        if self._verify_peer(intent) is not True:
            raise GpuYieldRefusal('Installed Lu session not authenticated')
        request_id='nvp-gpu-query-'+secrets.token_hex(12)
        msg=self.codec.build_capacity_query(intent,request_id=request_id)
        reply=self._exchange(msg)
        if self._verify_peer(intent) is not True:
            raise GpuYieldRefusal('Lu session revoked during capacity query')
        return self.codec.observe_decision(reply,intent,request_id=request_id)

    def send_verified_gpu_all_clear(self, intent: YieldIntent, evidence, release_ref):
        # Legacy Lu has no host-issued GPU yield lease nor durable all-clear ack.
        raise GpuYieldRefusal('Unimplemented Core signed GPU all-clear contract #250')


class UninstalledCoreGpuYieldPort:
    """Default bridge: no Core lease/all-clear protocol installed; always deny."""
    def ready_for_safe_roundtrip(self, intent: YieldIntent) -> bool:
        return False

    def __getattr__(self, name):
        raise GpuYieldRefusal('Lu Core GPU yield lease/all-clear not installed (Core #250)')


class NvpGpuYieldCoordinator:
    """Native-owner-sealed orchestration; absolutely no direct model reload API.

    The port is only implementable after Lu Core publishes an accepted
    version-negotiated GPU yield+all-clear IPC. Python fixture ports in tests
    do NOT attest signed/installed Lu or genuine Windows GPU custody.
    """
    def __init__(self, journal: GpuYieldJournal, *, native_owner, core_port=None):
        if type(journal) is not GpuYieldJournal or native_owner is None:
            raise TypeError('Protected owner and GPU yield journal required')
        self.journal=journal
        self.owner=native_owner
        self.core=core_port if core_port is not None else UninstalledCoreGpuYieldPort()

    def _auth(self, intent, action, detail):
        if self.owner.verify_installed_session(intent) is not True:
            raise GpuYieldRefusal('No current installed NVP/Lu peer session')
        return self.owner.authorize_original_turn(intent, action, detail) is True

    def request(self, intent: YieldIntent):
        """One cooperative unload request; cannot itself start a GPU worker."""
        if self.owner.verify_installed_session(intent) is not True:
            raise GpuYieldRefusal('No installed Lu/NVP resource session')
        # Require BOTH sides of the Core-owned unload/all-clear protocol before
        # ever sending a request capable of evicting Lu's selected model.
        if not hasattr(self.core,'ready_for_safe_roundtrip') or \
                self.core.ready_for_safe_roundtrip(intent) is not True:
            raise GpuYieldRefusal('Lu GPU yield lease/all-clear feature not negotiated')
        verify=lambda action, detail:self._auth(intent,action,detail)
        self.journal.prepare(intent,authorize=verify)
        self.journal.mark_request_sent(intent,authorize=verify)
        # Core's existing advisory operation may be sent over its installed
        # resource_request wire, but no ALLOWED status is a release grant.
        # Installed protocol must return a separately verifiable Core grant.
        result=self.core.request_cooperative_gpu_yield(intent)
        if type(result) is CoreYieldGrant:
            # This must already be a separately OS-attested Core receipt from
            # NativeLuGpuLeaseV1Gateway; the native owner re-verifies it before
            # the durable GPU worker launch can be admitted.
            self.receive_grant(intent, result)
        # Only the strictly validated existing Lu Gateway frame may change
        # advisory state. A model-supplied string cannot create a permission.
        if isinstance(self.core, NativeLuAdvisoryGateway):
            self.journal.record_legacy_decision(intent.origin.operation_ref,
                allowed=(result!='DENIED'),
                verify_core_decision=lambda action,detail:self._auth(intent,action,detail))
        return result

    def receive_grant(self, intent: YieldIntent, grant: CoreYieldGrant):
        return self.journal.accept_verified_core_grant(intent,grant,
            verify_core_grant=lambda action,detail:
                self._auth(intent,action,detail) and
                self.owner.verify_core_released_vram(intent,grant,detail) is True)

    def begin_diffusion(self, intent: YieldIntent):
        return self.journal.begin_processing(intent,
            verify_live_core_lease=lambda action,detail:
                self._auth(intent,action,detail) and
                self.owner.verify_live_core_gpu_lease(intent,detail) is True,
            verify_nvp_native_launch=lambda action,detail:
                self._auth(intent,action,detail) and
                self.owner.verify_native_diffuser_admission(intent,detail) is True)

    def cancel_before_launch(self, intent: YieldIntent):
        return self.journal.abandon_granted_job_before_launch(intent,
            verify_no_native_worker=lambda action,detail:
                self._auth(intent,action,detail) and
                self.owner.verify_no_protected_gpu_worker_launched(intent,detail) is True)

    def worker_stopped(self, intent: YieldIntent):
        return self.journal.mark_processing_stopped(intent.origin.operation_ref,
            authorize_owner=lambda action,detail:self._auth(intent,action,detail))

    def after_verified_shutdown(self, intent: YieldIntent, witness: NativeGpuQuiescence):
        return self.journal.accept_native_quiescence(witness,
            verify_installed_native_receipt=lambda action,detail:
                self._auth(intent,action,detail) and
                self.owner.verify_native_scm_gpu_quiescence(intent,witness,detail) is True)

    def run_admitted_protected_diffusion(self, intent: YieldIntent, *, run_worker):
        """Gate the real NVP protected worker on the Lu-confirmed GPU lease.

        The callable must be the existing native SCM/AppContainer-supervised
        NVP diffuser (e.g. ProtectedLtxHandoff.run) supplied by the installed
        host. On *every* outcome, seek independent OS/GPU proof before any
        all-clear. An exception never implies memory is free; no proof means
        the model remains fenced, not optimistic Lu reload.
        """
        if not callable(run_worker):
            raise GpuYieldRefusal('Installed protected diffuser callable required')
        self.begin_diffusion(intent)
        try:
            result=run_worker()
        except BaseException:
            # Preserve the failed render's exception. This is a signaled stop,
            # not evidence of kernel Job or GPU context exit.
            self.worker_stopped(intent)
            try:
                witness=self.owner.observe_native_gpu_quiescence(intent)
                self.after_verified_shutdown(intent,witness)
                self.send_all_clear(intent)
            except BaseException:
                # No all-clear without proven quiescence; retain pending state.
                pass
            raise
        else:
            self.worker_stopped(intent)
            witness=self.owner.observe_native_gpu_quiescence(intent)
            self.after_verified_shutdown(intent,witness)
            self.send_all_clear(intent)
            # The result is an NVP picture/processing outcome, *not* proof
            # Lu has reloaded. The Core ack must be received separately.
            return result

    def send_all_clear(self, intent: YieldIntent):
        record=self.journal.mark_all_clear_sent(intent.origin.operation_ref,
            authorize_owner=lambda action,detail:self._auth(intent,action,detail))
        evidence=self.journal.core_reconcile(intent.origin.operation_ref,
            verify_reconciliation=lambda action,detail:self._auth(intent,action,detail))
        # Actual native port must authenticate original session/grant, serialize
        # Core-accepted protobuf and wait for a Core durable ack; no local reload.
        outcome=self.core.send_verified_gpu_all_clear(intent, evidence, record['release_ref'])
        if type(outcome) is CoreReleaseAck:
            # The IPC reply is not an acknowledgment: a trusted Core-owned
            # durable receipt is required and rechecked against NVP's journal.
            self.receive_release_ack(intent, outcome)
        return outcome

    def receive_release_ack(self, intent: YieldIntent, ack: CoreReleaseAck):
        return self.journal.accept_lu_release_ack(ack,
            verify_core_ack=lambda action,detail:
                self._auth(intent,action,detail) and
                self.owner.verify_core_durable_release_ack(intent,ack,detail) is True)
