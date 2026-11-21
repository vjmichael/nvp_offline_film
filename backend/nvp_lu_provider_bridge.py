"""NVP-INT-LU-01F-R2: NVP-side LuWorkspaceProvider Protobuf supervisor seam.

The Lu Core -> NVP provider direction uses the *existing* pinned
lu.workspace.v0.WorkspaceFrame + LuWorkspaceProvider role. No JSON, HTTP,
TCP, invented credential exchange, or production listener is provided here.
A genuine OS-authenticated native owner must create the session context,
provide compiled/registered exact Protobuf classes, enforce per-turn Lu/NVP
creator/effect grants, and own worker custody and receipt verification.

This module is a fail-closed dispatcher/codec, NOT installation, OS identity
verification, a signing service, an authorized Core, or a model control path.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
import struct
import socket
import time
from typing import Mapping

from google.protobuf.message import Message

from backend.nvp_lu_operation_journal import (
    IPCOperationJournal, JournalRefusal, OperationSpec, OriginRefs,
    ReceiptObservation, _ref,
)

LU_PROTO_BLOB_SHA = '4e01d921197fb1c58c99958479b1cede36e13c9a'
LU_COMMIT_SHA = '9f43d078aa5e979de0ff72ca4c19e8c5829572af'
WIRE_MAJOR, WIRE_MINOR = 1, 0
MAX_FRAME_BYTES = 256 * 1024
MAX_TYPED_BYTES = 64 * 1024
MAX_OBJECT_REFS = 16
MAX_CREDIT = 64
MAX_OUTSTANDING = 64
MAX_OBJECT_SIZE = 1 << 40

# Reviewed NVP contracts/nvp/film/v1/capabilities.json at NVP 7ece5eb6;
# effect numbers are EXACT Lu workspace.v0 EffectClass values.
# This is a conservative local allowlist, NOT a Lu capability registration.
CAPABILITIES = {
    'nvp.film.project.read': ('ProjectReadRequest', (2,)),
    'nvp.film.scene.read': ('SceneReadRequest', (2,)),
    'nvp.film.story.propose': ('StoryProposalRequest', (3,)),
    'nvp.film.project.commit': ('ProjectCommitRequest', (3,)),
    'nvp.film.render.shot': ('RenderShotRequest', (4, 3)),
    'nvp.film.picture.review.read': ('PictureReviewReadRequest', (2,)),
    'nvp.film.picture.review.decide': ('PictureReviewDecisionRequest', (3,)),
    'nvp.film.edit.export': ('FilmExportRequest', (4, 3)),
}
TERMINAL_ENUM = {'APPLIED': 1, 'REFUSED': 2, 'FAILED': 3,
                 'CANCELLED': 4, 'UNCERTAIN': 5}


@dataclass(frozen=True)
class AdmittedLuPeer:
    """Informational context from trusted NVP native owner, NOT a bearer token.

    The dispatcher re-verifies it with the supervisor for EACH message.
    Constructing this Python class cannot authenticate anything.
    """
    session_ref: str
    core_epoch_ref: str
    workspace_ref: str

    def __post_init__(self):
        for v in (self.session_ref, self.core_epoch_ref, self.workspace_ref):
            _ref(v)


class UnconfiguredNativeSupervisor:
    """Default denies everything; actual installed owner adapter not shipped."""
    def __getattr__(self, name):
        raise JournalRefusal('NVP native supervisor/installer custody is not connected')


class PinnedProviderCodec:
    """Uses externally supplied *generated* Lu Protobuf message classes.

    Production owner MUST verify source SHA and schema blob before supplying
    these classes. Local projected message types are for tests only.
    """
    def __init__(self, frame_class):
        if (not hasattr(frame_class, 'DESCRIPTOR') or
                frame_class.DESCRIPTOR.full_name != 'lu.workspace.v0.WorkspaceFrame'):
            raise JournalRefusal('Wrong Lu workspace Protobuf type')
        self.frame_class = frame_class

    def decode(self, raw: bytes):
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_FRAME_BYTES:
            raise JournalRefusal('Unbounded Lu Protobuf frame')
        frame = self.frame_class()
        try:
            frame.ParseFromString(raw)
        except Exception as exc:
            raise JournalRefusal('Malformed Lu Protobuf frame') from exc
        canonical = self.frame_class()
        canonical.CopyFrom(frame)
        canonical.DiscardUnknownFields()
        if canonical.SerializeToString(deterministic=True) != raw:
            raise JournalRefusal('Noncanonical or unknown Lu message fields')
        if frame.protocol_major != WIRE_MAJOR or frame.protocol_minor != WIRE_MINOR:
            raise JournalRefusal('Unsupported Lu wire version')
        if frame.sequence != 0:
            raise JournalRefusal('Inbound nonstream message had nonzero sequence')
        if frame.WhichOneof('body') not in ('invoke','cancel','reconcile','stream_credit'):
            raise JournalRefusal('Unaccepted inbound Lu provider message')
        _ref(frame.request_id)
        _ref(frame.session_ref)
        return frame

    def encode(self, frame) -> bytes:
        if frame.DESCRIPTOR.full_name != 'lu.workspace.v0.WorkspaceFrame':
            raise JournalRefusal('Unknown outgoing Lu Protobuf class')
        raw = frame.SerializeToString(deterministic=True)
        if not 0 < len(raw) <= MAX_FRAME_BYTES:
            raise JournalRefusal('Outbound Lu Protobuf frame too large')
        return raw

    @staticmethod
    def pack(raw: bytes) -> bytes:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_FRAME_BYTES:
            raise JournalRefusal('Invalid framed payload')
        return struct.pack('!I', len(raw)) + raw

    @staticmethod
    def read_frame(stream: socket.socket, *, now=time.monotonic) -> bytes:
        """Bounded big-endian u32 framing on an ALREADY native-attested socket."""
        deadline = now() + 3.0
        def exact(length):
            data = bytearray()
            while len(data) < length:
                remain = deadline - now()
                if remain <= 0:
                    raise TimeoutError('Lu provider frame receive deadline')
                stream.settimeout(remain)
                try:
                    part = stream.recv(length - len(data))
                except socket.timeout as exc:
                    raise TimeoutError('Lu provider frame receive deadline') from exc
                if not part:
                    raise JournalRefusal('Truncated Lu provider socket frame')
                data.extend(part)
            return bytes(data)
        size = struct.unpack('!I', exact(4))[0]
        if not 0 < size <= MAX_FRAME_BYTES:
            raise JournalRefusal('Lu provider frame length outside bound')
        return exact(size)

    @staticmethod
    def write_frame(stream: socket.socket, raw: bytes, *, now=time.monotonic) -> None:
        """Bounded partial-write framing; does not authenticate the peer."""
        payload = memoryview(PinnedProviderCodec.pack(raw))
        deadline = now() + 3.0
        while payload:
            remain = deadline - now()
            if remain <= 0:
                raise TimeoutError('Lu provider frame send deadline')
            stream.settimeout(remain)
            try:
                sent = stream.send(payload)
            except socket.timeout as exc:
                raise TimeoutError('Lu provider frame send deadline') from exc
            if sent <= 0:
                raise JournalRefusal('Lu provider socket closed during send')
            payload = payload[sent:]

    @staticmethod
    def unpack(packed: bytes) -> bytes:
        if type(packed) is not bytes or len(packed) < 4:
            raise JournalRefusal('Truncated Lu length prefix')
        size = struct.unpack('!I', packed[:4])[0]
        if not 0 < size <= MAX_FRAME_BYTES or len(packed) != 4 + size:
            raise JournalRefusal('Truncated, oversized or trailing Lu frame')
        return packed[4:]


class OperationStream:
    """Per-owner in-memory progress budget; never authoritative after restart."""
    def __init__(self, op_ref: str, request_id: str, peer: AdmittedLuPeer):
        self.operation_ref = _ref(op_ref)
        self.request_id = _ref(request_id)
        self.peer = peer
        self.credit = 0
        self.last_sent = 0
        self.last_ack = 0
        self._credit_ids = set()
        self.pending_terminal = False
        self.terminal_sent = False

    def add_credit(self, *, request_id: str, acknowledged_sequence: int, additional_events: int):
        _ref(request_id)
        if request_id in self._credit_ids or len(self._credit_ids) >= MAX_CREDIT:
            raise JournalRefusal("Repeated or excessive stream credit request")
        if (type(acknowledged_sequence) is not int or acknowledged_sequence < self.last_ack
                or acknowledged_sequence > self.last_sent or
                type(additional_events) is not int or not 0 < additional_events <= MAX_CREDIT):
            raise JournalRefusal('Invalid or replayed stream credit')
        pending = self.last_sent - acknowledged_sequence
        if pending + self.credit + additional_events > MAX_OUTSTANDING:
            raise JournalRefusal('Lu stream budget exceeded')
        self.last_ack = acknowledged_sequence
        self.credit += additional_events
        self._credit_ids.add(request_id)

    def send_sequence(self) -> int:
        if not self.credit:
            raise JournalRefusal('No Lu event stream credit')
        self.credit -= 1
        self.last_sent += 1
        return self.last_sent


class NvpLuProviderBridge:
    """Messages from Lu to NVP, routed only through an NVP native supervisor.

    The supervisor *must* implement:
      verify_session(peer) -> bool: OS-verified, enrolled, nonrevoked session
      admit_effect(peer, spec, typed_input, objects) -> bool: per-turn Core grant
          AND NVP creator/revision/worker policy, including full effect set
      dispatch_once(peer, spec, dispatch_ref, typed_input, objects) -> bool:
          protected/native worker accepted the single durable dispatch
      authorize_cancel(peer, spec, reason_code) -> bool
      cancel_native(peer, spec, reason_code) -> bool: signal only
      verify_cancel_ack(peer, spec, ack, binding) -> bool
      authorize_reconcile(peer, spec) -> bool: same original Lu user scope
      lookup_receipt(peer, spec) -> ReceiptObservation | None
      verify_receipt(peer, spec, observation, binding) -> bool

    All entrypoints are inert when these gates are unavailable. These are
    *host-installed callbacks*, not caller-provided authorization arguments.
    """
    def __init__(self, journal: IPCOperationJournal, frame_class,
                 domain_input_types: Mapping[str, type], *, supervisor=None,
                 native_production_link=None, installed_scm_picture=None):
        if not isinstance(journal, IPCOperationJournal):
            raise JournalRefusal('NVP durable owner journal required')
        self.journal = journal
        self.codec = PinnedProviderCodec(frame_class)
        self.domain_input_types = dict(domain_input_types)
        for cap, (input_name, _) in CAPABILITIES.items():
            cls = self.domain_input_types.get(cap)
            if (cls is None or not hasattr(cls, 'DESCRIPTOR') or
                    cls.DESCRIPTOR.full_name != f'nvp.film.v1.{input_name}'):
                raise JournalRefusal(f'Missing generated NVP input descriptor: {cap}')
        self.supervisor = supervisor if supervisor is not None else UnconfiguredNativeSupervisor()
        if native_production_link is not None:
            from backend.nvp_lu_native_production_link import WindowsProtectedProductionLink
            if type(native_production_link) is not WindowsProtectedProductionLink:
                raise JournalRefusal('Actual installed Windows supervisor link required')
        self.native_production_link = native_production_link
        if installed_scm_picture is not None:
            from backend.nvp_lu_scm_picture_receipt import InstalledWindowsScmPictureReceipt
            if type(installed_scm_picture) is not InstalledWindowsScmPictureReceipt:
                raise JournalRefusal('Only installed Windows SCM picture receipt path admitted')
        self.installed_scm_picture = installed_scm_picture
        self._streams = {}  # Volatile only, bounded. No startup replay.
        self._stream_lock = RLock()

    def _verified(self, peer: AdmittedLuPeer, frame) -> None:
        if (type(peer) is not AdmittedLuPeer or frame.session_ref != peer.session_ref
                or self.supervisor.verify_session(peer) is not True):
            raise JournalRefusal('Lu peer not independently admitted by NVP native owner')

    @staticmethod
    def _origin(proto) -> OriginRefs:
        return OriginRefs(proto.workspace_ref, proto.conversation_ref,
                          proto.user_turn_ref, proto.task_ref, proto.operation_ref)

    def _typed_input(self, invoke):
        cap = _ref(invoke.capability_id)
        if cap not in CAPABILITIES or invoke.capability_version != 1:
            raise JournalRefusal('Capability is unregistered or wrong version')
        expected_input, effects = CAPABILITIES[cap]
        value = invoke.input
        if (value.type_url != f'type.googleapis.com/nvp.film.v1.{expected_input}' or
                len(value.encoded_message) == 0 or
                len(value.encoded_message) > MAX_TYPED_BYTES):
            raise JournalRefusal('Invalid NVP typed payload or type URL')
        cls = self.domain_input_types[cap]
        msg = cls()
        try:
            msg.ParseFromString(value.encoded_message)
        except Exception as exc:
            raise JournalRefusal('Malformed NVP domain payload') from exc
        copied = cls(); copied.CopyFrom(msg); copied.DiscardUnknownFields()
        if copied.SerializeToString(deterministic=True) != value.encoded_message:
            raise JournalRefusal('Unknown or noncanonical NVP domain payload')
        return effects

    @staticmethod
    def _objects(objects, *, now_ms: int) -> None:
        if len(objects) > MAX_OBJECT_REFS:
            raise JournalRefusal('Too many NVP object locators')
        seen = set()
        for obj in objects:
            if (obj.owner_module_id != 'nvp.film' or not obj.sha256 or
                    len(obj.sha256) != 32 or not any(obj.sha256) or
                    not 0 < obj.size_bytes <= MAX_OBJECT_SIZE or
                    obj.expiry_unix_ms <= now_ms):
                raise JournalRefusal('NVP object locator lacks bounded source identity')
            _ref(obj.object_ref)
            if obj.object_ref in seen:
                raise JournalRefusal('Duplicate NVP object locator')
            seen.add(obj.object_ref)
        # ObjectRef is *never* authority. The native host must resolve/recheck
        # original workspace, revision, caller, hash, size, expiry and ACL.

    def _spec(self, frame, peer: AdmittedLuPeer) -> OperationSpec:
        invoke = frame.invoke
        origin = self._origin(invoke.origin)
        if origin.workspace_ref != peer.workspace_ref:
            raise JournalRefusal('Lu user workspace not bound to admitted session')
        effects = self._typed_input(invoke)
        self._objects(invoke.input_refs, now_ms=self.journal._clock_ms())
        if invoke.deadline_unix_ms <= self.journal._clock_ms():
            raise JournalRefusal('Lu operation deadline expired')
        # Source-ordered object locator serialization binds all locators and
        # hashes without treating their strings as grants.
        objects_wire = b''.join(struct.pack('!I',len(x.SerializeToString(deterministic=True)))+
                                x.SerializeToString(deterministic=True) for x in invoke.input_refs)
        return OperationSpec(origin,invoke.capability_id,invoke.capability_version,
            effects[0],sha256(invoke.input.SerializeToString(deterministic=True)).hexdigest(),
            sha256(b'nvp.lu.refs.v1\0'+objects_wire).hexdigest(),
            invoke.deadline_unix_ms,peer.session_ref,peer.core_epoch_ref,
            declared_effects=tuple(effects))

    def _original(self, peer, op_ref):
        spec = self.journal.bound_spec(op_ref,authorize=lambda action, snapshot:
            self.supervisor.verify_session(peer) is True and
            self.supervisor.authorize_inspect(peer, op_ref, action, snapshot) is True)
        if spec.origin.workspace_ref != peer.workspace_ref:
            raise JournalRefusal('Operation was owned by another workspace')
        return spec

    def handle(self, raw: bytes, peer: AdmittedLuPeer):
        """Handle one untrusted decoded Protobuf frame; response raw bytes or None.

        No socket is opened here. Installed native custody must verify both OS
        peers before presenting any request, and must bound IO independently.
        Invoke returns no event until the caller supplies StreamCredit.
        """
        frame = self.codec.decode(raw)
        self._verified(peer, frame)
        kind = frame.WhichOneof('body')
        if kind == 'invoke':
            return self._invoke(frame,peer)
        if kind == 'cancel':
            return self._cancel(frame,peer)
        if kind == 'reconcile':
            return self._reconcile(frame,peer)
        return self._credit(frame,peer)

    def handle_safe(self, raw: bytes, peer: AdmittedLuPeer):
        """Fixed-category refusal response for an authenticated peer only.

        Malformed frames and unauthenticated peers must be dropped by the
        native transport, not reflected back with security diagnostics.
        A previously claimed dispatch ALWAYS yields outcome_uncertain=true,
        never a retryable "not delivered" promise.
        """
        try:
            return self.handle(raw, peer)
        except (JournalRefusal, ValueError, TimeoutError):
            frame = self.codec.decode(raw)  # May refuse: close transport.
            self._verified(peer, frame)     # Never answer unauthenticated peers.
            ref = None
            if frame.WhichOneof('body') == 'invoke':
                ref = frame.invoke.origin.operation_ref
            elif frame.WhichOneof('body') == 'cancel':
                ref = frame.cancel.operation_ref
            elif frame.WhichOneof('body') == 'reconcile':
                ref = frame.reconcile.operation_ref
            uncertain = False
            if ref:
                try:
                    state = self.journal.status(ref)
                except (ValueError, JournalRefusal):
                    pass
                else:
                    uncertain = state['state'] in ('IN_FLIGHT','UNCERTAIN')
            out = self.codec.frame_class(protocol_major=1,protocol_minor=0,
                request_id=frame.request_id, session_ref=peer.session_ref)
            out.failure.code = 'NVP_OUTCOME_UNCERTAIN' if uncertain else 'NVP_REFUSED'
            out.failure.retryable = False
            out.failure.outcome_uncertain = uncertain
            out.failure.explanation = 'Use original-operation reconciliation; no implicit retry' \
                if uncertain else 'Request not admitted by NVP owner'
            return self.codec.encode(out)

    def _invoke(self, frame, peer):
        spec = self._spec(frame, peer)
        ref = spec.origin.operation_ref
        with self._stream_lock:
            if ref in self._streams:
                raise JournalRefusal('Duplicate live invoke requires Reconcile')
            if len(self._streams) >= MAX_OUTSTANDING:
                raise JournalRefusal('No provider stream capacity; no native dispatch')
        # User/creator/effect authority is rechecked for both preparation and
        # the atomic dispatch claim. A false gate cannot become a grant.
        authorize = lambda action, snap: self.supervisor.verify_session(peer) is True and \
            self.supervisor.admit_effect(peer, spec, frame.invoke.input,
                                         tuple(frame.invoke.input_refs)) is True
        self.journal.prepare(spec, authorize=authorize)
        claim = self.journal.claim_dispatch(ref, authorize=authorize)
        # Having claimed dispatch, ANY error/timeout is ambiguous. Do not
        # roll back to PREPARED or issue a second native dispatch.
        try:
            if self.supervisor.dispatch_once(peer,spec,claim['dispatch_ref'],
                                              frame.invoke.input,
                                              tuple(frame.invoke.input_refs)) is not True:
                raise JournalRefusal('Native supervisor refused dispatch receipt')
        except BaseException as exc:
            raise JournalRefusal('Dispatch outcome requires durable reconciliation') from exc
        with self._stream_lock:
            self._streams[ref] = OperationStream(ref, frame.request_id, peer)
        return None

    def supervisor_bind_native_production_job(self, operation_ref: str,
                                              dispatch_ref: str, native_identity):
        """Owner-only cross-journal handoff after actual NVP worker admission.

        Never callable from a Protobuf frame; can't create a native job and
        doesn't turn a read-only integrity worker into LTX/export authority.
        """
        if self.native_production_link is None:
            raise JournalRefusal('No installed protected production owner')
        spec = self.journal.bound_spec(operation_ref,
            authorize=lambda action, snap: self.supervisor.authorize_supervisor_result(
                operation_ref, action, snap) is True)
        return self.native_production_link.bind_after_native_admission(
            spec, dispatch_ref, native_identity)

    def _cancel(self, frame, peer):
        ref = _ref(frame.cancel.operation_ref)
        reason = _ref(frame.cancel.reason_code)
        spec = self._original(peer, ref)
        if (spec.host_session_ref != peer.session_ref or
                spec.host_epoch_ref != peer.core_epoch_ref):
            raise JournalRefusal('Cancellation cannot cross host epochs without new admission')
        allow = lambda action, snap: self.supervisor.authorize_cancel(peer,spec,reason) is True
        before = self.journal.status(ref)
        self.journal.signal_cancel(ref,reason_code=reason,authorize=allow)
        if before['state'] == 'PREPARED':
            # No native worker has been dispatched. The durable journal has
            # accepted the cancel signal; this is NOT terminal cancellation.
            ack = True
        else:
            # If an actual ProductionJournal job is attached, its native
            # creator-authorized request_cancel is the single cancellation
            # signal source. Do not send a second generic worker cancel.
            if self.native_production_link is not None:
                ack = self.native_production_link.signal_cancel_to_real_journal(
                    spec, reason) is True
            else:
                ack = self.supervisor.cancel_native(peer,spec,reason) is True
            self.journal.record_cancel_ack(ref,signal_recorded=ack,
                verify_ack=lambda signal,binding: self.supervisor.verify_cancel_ack(
                    peer,spec,signal,binding) is True)
        out = self.codec.frame_class(protocol_major=1,protocol_minor=0,
            request_id=frame.request_id,session_ref=peer.session_ref)
        out.cancel_ack.operation_ref = ref
        out.cancel_ack.signal_recorded = ack
        return self.codec.encode(out)

    def _reconcile(self, frame, peer):
        ref = _ref(frame.reconcile.operation_ref)
        origin = self._origin(frame.reconcile.expected_origin)
        if origin.operation_ref != ref:
            raise JournalRefusal('Reconcile operation and original origin disagree')
        spec = self._original(peer,ref)
        if origin != spec.origin or self.supervisor.authorize_reconcile(peer,spec) is not True:
            raise JournalRefusal('Reconciliation has no original user-turn authority')
        observation = self.supervisor.lookup_receipt(peer,spec)
        if observation is not None:
            if type(observation) is not ReceiptObservation:
                raise JournalRefusal('NVP owner returned untyped receipt evidence')
            self.journal.reconcile_receipt(spec,observation,
                verify_receipt=lambda observed,bound,binding:
                self.supervisor.verify_receipt(peer,bound,observed,binding) is True)
        state = self.journal.status(ref)
        out = self.codec.frame_class(protocol_major=1,protocol_minor=0,
            request_id=frame.request_id,session_ref=peer.session_ref)
        receipt = out.reconciled.observed
        receipt.operation_ref = ref
        if state['state'] == 'TERMINAL':
            receipt.state = TERMINAL_ENUM[state['terminal_state']]
            receipt.reason_code = state['reason_code']
            receipt.durable_receipt_sha256 = bytes.fromhex(state['receipt_sha256'])
            out.reconciled.evidence_available = state['evidence_available']
        else:
            # PREPARED, IN_FLIGHT or UNCERTAIN cannot be represented as APPLIED
            # and may not be retried. Unproved crash outcome == UNCERTAIN.
            receipt.state = TERMINAL_ENUM['UNCERTAIN']
            receipt.reason_code = state['reason_code'] or 'AWAIT_NATIVE_EVIDENCE'
            if state['state'] == 'UNCERTAIN' and state['evidence_available'] and state['receipt_sha256']:
                receipt.durable_receipt_sha256 = bytes.fromhex(state['receipt_sha256'])
                out.reconciled.evidence_available = True
            else:
                out.reconciled.evidence_available = False
        return self.codec.encode(out)

    def _credit(self, frame, peer):
        ref = _ref(frame.stream_credit.operation_ref)
        with self._stream_lock:
            stream = self._streams.get(ref)
            if stream is None or stream.peer != peer:
                raise JournalRefusal('Unknown or cross-session stream; reconcile instead')
            # Credit is not authorization and cannot create a new dispatch.
            stream.add_credit(request_id=frame.request_id,
                acknowledged_sequence=frame.stream_credit.acknowledged_sequence,
                additional_events=frame.stream_credit.additional_events)
            terminal = stream.pending_terminal and not stream.terminal_sent
            if stream.terminal_sent or (stream.last_sent and not terminal):
                return None  # No synthetic progress repeated after first event.
            seq = stream.send_sequence()
            if terminal:
                stream.terminal_sent = True
        out = self.codec.frame_class(protocol_major=1,protocol_minor=0,
            request_id=stream.request_id,session_ref=peer.session_ref,sequence=seq)
        out.operation_event.operation_ref = ref
        if terminal:
            state = self.journal.status(ref)
            if state['state'] != 'TERMINAL' or not state['evidence_available']:
                raise JournalRefusal('Cannot stream a terminal without durable evidence')
            receipt = out.operation_event.terminal
            receipt.operation_ref = ref
            receipt.state = TERMINAL_ENUM[state['terminal_state']]
            receipt.reason_code = state['reason_code']
            receipt.durable_receipt_sha256 = bytes.fromhex(state['receipt_sha256'])
        else:
            out.operation_event.progress.stage_code = 'DISPATCH_ADMITTED'
        return self.codec.encode(out)

    def supervisor_revoke(self, ref: str, reason_code: str):
        """Handle independent NVP native-owner revocation without a live Lu peer.

        Lu v0 has no RevokeOperation message. Revocation is delivered through
        protected installer/host session custody and NVP supervisor events,
        NEVER by pretending a CancelOperation is a revocation grant.
        """
        spec = self.journal.bound_spec(ref,
            authorize=lambda action, snapshot:
                self.supervisor.authorize_supervisor_revocation(ref, reason_code,
                    action, snapshot) is True)
        state = self.journal.signal_revoke(ref, reason_code=reason_code,
            authorize=lambda action, snapshot:
                self.supervisor.authorize_supervisor_revocation(ref,reason_code,
                    action,snapshot) is True)
        if state['state'] in ('IN_FLIGHT','UNCERTAIN'):
            # Native owner must deliver revocation/stop signal independently;
            # failure never resets journal state or forges terminal CANCELLED.
            if self.supervisor.revoke_native(spec,reason_code) is not True:
                raise JournalRefusal('Revoked operation requires native stop reconciliation')
        return state

    def record_native_terminal(self, ref: str, observed: ReceiptObservation):
        """Native-owner terminal evidence, permitted after Lu connection dies.

        Requires *independent* NVP SCM/worker custody verification. Commit the
        original terminal BEFORE scheduling optional Protobuf event emission.
        """
        spec = self.journal.bound_spec(ref,authorize=lambda action,snapshot:
            self.supervisor.authorize_supervisor_result(ref,action,snapshot) is True)
        state = self.journal.reconcile_receipt(spec,observed,
            verify_receipt=lambda result,bound,binding:
                self.supervisor.verify_native_terminal(bound,result,binding) is True)
        if state['state'] == 'TERMINAL':
            with self._stream_lock:
                stream = self._streams.get(ref)
                if stream is not None:
                    stream.pending_terminal = True
        return state

    def supervisor_reconcile_signed_picture(self, ref: str):
        """Native owner verifies CNG/EFS/SCM result then commits real receipt.

        This method never constructs a signer or grants a capability. The
        installed SCM owner independently ties original user turn, film/Take,
        kernel exit and one-use nonce to the already dispatched operation.
        """
        if self.installed_scm_picture is None:
            raise JournalRefusal('Protected installed SCM picture verifier is absent')
        state = self.installed_scm_picture.reconcile_signed_picture(ref)
        if state['state'] == 'TERMINAL' and state['terminal_state'] == 'APPLIED':
            with self._stream_lock:
                stream = self._streams.get(ref)
                if stream is not None:
                    stream.pending_terminal = True
        return state

    def disconnect(self):
        """Forget event credit after native transport loss; NEVER retry ops."""
        with self._stream_lock:
            self._streams.clear()


class BoundNativeProviderExchange:
    """One request over an *already OS-admitted* full-duplex Lu IPC stream.

    The native Windows host supplies the existing observed-pipe handle lease
    (ObservedWindowsLuPipe.assert_observed_process_alive) and its separate
    installed signer/credential broker must admit the same session. This class
    does neither OS admission nor enrollment. It does not open a listener,
    create a socket, supply a credential, or retry a claimed IPC operation.
    Test Linux socketpairs are only transport fixtures.
    """
    def __init__(self, bridge: NvpLuProviderBridge, stream, peer: AdmittedLuPeer,
                 *, attest_live_owner):
        if (type(bridge) is not NvpLuProviderBridge or
                type(peer) is not AdmittedLuPeer or
                not callable(attest_live_owner) or
                not callable(getattr(stream, 'recv', None)) or
                not callable(getattr(stream, 'send', None)) or
                not callable(getattr(stream, 'settimeout', None))):
            raise JournalRefusal('Native owner-bound full-duplex stream required')
        self.bridge=bridge
        self.stream=stream
        self.peer=peer
        self.attest_live_owner=attest_live_owner
        self.closed=False

    def _witness(self):
        if (self.closed or self.attest_live_owner() is not True or
                self.bridge.supervisor.verify_session(self.peer) is not True):
            raise JournalRefusal('Protected native owner/session lease expired')

    def one_exchange(self):
        """Read one bounded frame, dispatch or refuse, and write at most one.

        Original streams are never auto-resumed on disconnect: the caller must
        perform explicit authorized ReconcileOperation on a new admitted peer.
        """
        try:
            self._witness()              # Before reading untrusted bytes.
            raw=self.bridge.codec.read_frame(self.stream)
            self._witness()              # Detect native-owner exit mid-recv.
            response=self.bridge.handle_safe(raw,self.peer)
            self._witness()              # Detect revoke during work.
            if response is not None:
                # Same bounded codec on native WinPipeStream and AF_UNIX;
                # every send re-witnesses host generation and live enrollment.
                self.bridge.codec.write_frame(self.stream,response)
                self._witness()
            return response is not None
        except BaseException:
            self.close()
            raise

    def close(self):
        if not self.closed:
            self.closed=True
            self.bridge.disconnect()
            # Release the actual pipe/socket on refusal; the owning installed
            # lease must separately release its retained process handle.
            try:
                self.stream.close()
            except OSError:
                pass
