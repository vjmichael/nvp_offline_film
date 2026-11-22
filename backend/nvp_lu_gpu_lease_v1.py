"""NVP native-client adapter for Lu Core's SOURCE-DRAFT gpu-lease-v1 wire.

NVP cannot mint grants, unload Lu models, or prove installed Windows SCM.
Both halves of the *same* OS-admitted Lu session must be feature-negotiated.
A wire GRANTED is only a claim until the independently installed Lu host
attests the same original turn/model generation/VRAM release. Likewise a
RESTORED reply is not a durable Core acknowledgment without host evidence.

Pinned source: Lu PR #244 60afe6908a6abe3408bb952869d85b43781313ca
               workspace.proto Git blob 747b7472ab7e4bdfd7d646dd629b2c45a9c63dd1
The runtime is intentionally disabled unless the original installed host
supplies all peer, receipt and OS worker-stop verifier interfaces.
"""
from __future__ import annotations

from dataclasses import asdict
import secrets
import time

from backend.nvp_lu_gpu_yield import (
    CoreReleaseAck, CoreYieldGrant, GpuYieldRefusal, NativeGpuQuiescence,
    YieldIntent, _ref,
)

LU_GPU_PROTO_COMMIT = '60afe6908a6abe3408bb952869d85b43781313ca'
LU_GPU_PROTO_BLOB = '747b7472ab7e4bdfd7d646dd629b2c45a9c63dd1'
FEATURE = 'gpu-lease-v1'
MAX_FRAME_BYTES = 256 * 1024
# wire values are schema-locked to Lu's current generated Protobuf enum.
ADMISSION_ALLOWED = 1
GPU_GRANTED = 2
GPU_RESTORED = 5
GPU_DRAINING = 1
GPU_RELEASING = 3
ADMISSION_DEFERRED = 2


class LuGpuLeaseV1Codec:
    """Bounded typed WorkspaceFrame (tag 38/39/40), never independent auth."""
    def __init__(self, frame_class, *, schema_git_blob: str):
        if type(schema_git_blob) is not str or schema_git_blob != LU_GPU_PROTO_BLOB:
            raise GpuYieldRefusal('Unreviewed Lu Core GPU-lease Protobuf source')
        desc = getattr(frame_class, 'DESCRIPTOR', None)
        if desc is None or desc.full_name != 'lu.workspace.v0.WorkspaceFrame':
            raise GpuYieldRefusal('Canonical generated Lu WorkspaceFrame required')
        expected = {
            'gpu_lease_request': (38, 'GpuLeaseRequest'),
            'gpu_lease_outcome': (39, 'GpuLeaseOutcome'),
            'gpu_lease_release': (40, 'GpuLeaseRelease'),
            'gpu_lease_poll': (41, 'GpuLeasePoll'),
        }
        for name, (number, typename) in expected.items():
            fld = desc.fields_by_name.get(name)
            if (fld is None or fld.number != number or
                    fld.message_type.full_name != 'lu.workspace.v0.' + typename or
                    fld.containing_oneof is None or fld.containing_oneof.name != 'body'):
                raise GpuYieldRefusal('Lu GPU lease wire tag/type incompatible')
        request = desc.fields_by_name['gpu_lease_request'].message_type
        release = desc.fields_by_name['gpu_lease_release'].message_type
        outcome = desc.fields_by_name['gpu_lease_outcome'].message_type
        poll = desc.fields_by_name['gpu_lease_poll'].message_type
        if ({f.name: f.number for f in request.fields} != {
                'origin': 1, 'device_ref': 2, 'required_free_vram_bytes': 3,
                'max_duration_ms': 4} or
            {f.name: f.number for f in release.fields} != {
                'origin': 1, 'lease_ref': 2, 'nvp_worker_stop_ref': 3} or
            {f.name: f.number for f in outcome.fields} != {
                'operation_ref': 1, 'decision': 2, 'phase': 3, 'lease_ref': 4,
                'measured_available_vram_bytes': 5, 'reason_code': 6} or
            {f.name:f.number for f in poll.fields} != {
                'origin':1,'lease_ref':2,'transition':3}):
            raise GpuYieldRefusal('Lu GPU lease fields changed without review')
        self.frame_class = frame_class

    @staticmethod
    def _check_version(major: int, minor: int) -> None:
        if type(major) is not int or major != 1 or type(minor) is not int or minor not in (0, 1, 2):
            raise GpuYieldRefusal('Unnegotiated Lu GPU protocol version')

    def _frame(self, intent: YieldIntent, request_id: str, major: int, minor: int):
        self._check_version(major, minor)
        return self.frame_class(protocol_major=major, protocol_minor=minor,
                                request_id=_ref(request_id), session_ref=intent.session_ref)

    @staticmethod
    def _origin(target, intent: YieldIntent):
        for name in intent.origin.__dataclass_fields__:
            setattr(target, name, getattr(intent.origin, name))

    @staticmethod
    def _bounded(frame):
        if len(frame.SerializeToString()) > MAX_FRAME_BYTES:
            raise GpuYieldRefusal('Overlong Lu GPU frame')
        return frame

    def acquire(self, intent: YieldIntent, *, request_id: str, major: int = 1, minor: int = 0):
        frame = self._frame(intent, request_id, major, minor)
        msg = frame.gpu_lease_request
        self._origin(msg.origin, intent)
        msg.device_ref = intent.device_ref
        msg.required_free_vram_bytes = intent.desired_free_vram_bytes
        msg.max_duration_ms = intent.duration_ms
        return self._bounded(frame)

    def release(self, intent: YieldIntent, *, lease_ref: str,
                worker_stop_ref: str, request_id: str, major: int = 1, minor: int = 0):
        frame = self._frame(intent, request_id, major, minor)
        msg = frame.gpu_lease_release
        self._origin(msg.origin, intent)
        msg.lease_ref = _ref(lease_ref)
        msg.nvp_worker_stop_ref = _ref(worker_stop_ref)
        return self._bounded(frame)

    def poll(self, intent: YieldIntent, *, lease_ref: str, transition: int,
             request_id: str, major: int = 1, minor: int = 0):
        if type(transition) is not int or transition not in (1, 2):
            raise GpuYieldRefusal('Invalid Lu original GPU lease transition')
        frame=self._frame(intent, request_id, major, minor)
        message=frame.gpu_lease_poll
        self._origin(message.origin,intent)
        message.lease_ref=_ref(lease_ref)
        message.transition=transition
        return self._bounded(frame)

    def outcome(self, reply, intent: YieldIntent, *, request_id: str,
                expected_phase: int, major: int = 1, minor: int = 0,
                lease_ref: str | None = None, allow_deferred: bool = False):
        self._check_version(major, minor)
        if (type(reply) is not self.frame_class or
                reply.protocol_major != major or reply.protocol_minor != minor or
                reply.request_id != request_id or reply.session_ref != intent.session_ref or
                reply.WhichOneof('body') != 'gpu_lease_outcome' or reply.sequence != 0):
            raise GpuYieldRefusal('Unbound Lu GPU reply / wrong session, version or operation')
        self._bounded(reply)
        result = reply.gpu_lease_outcome
        if result.operation_ref != intent.origin.operation_ref:
            raise GpuYieldRefusal('Lu GPU operation origin changed')
        if (allow_deferred and result.decision == ADMISSION_DEFERRED and
                result.phase == (GPU_DRAINING if expected_phase == GPU_GRANTED else GPU_RELEASING) and
                result.lease_ref and
                (lease_ref is None or result.lease_ref == lease_ref) and
                not result.HasField('measured_available_vram_bytes')):
            # Core queued the ORIGINAL effect. Do not re-submit another unload
            # or treat this resource claim as VRAM available. Poll exact ref.
            return result
        if result.decision != ADMISSION_ALLOWED:
            raise GpuYieldRefusal('Lu GPU resource state ungranted or uncertain')
        if result.phase != expected_phase or not result.lease_ref:
            raise GpuYieldRefusal('Lu GPU model-release / restore phase not proven')
        if lease_ref is not None and result.lease_ref != lease_ref:
            raise GpuYieldRefusal('Core GPU lease changed between grant and all-clear')
        if expected_phase == GPU_GRANTED:
            if (not result.HasField('measured_available_vram_bytes') or
                    result.measured_available_vram_bytes < intent.desired_free_vram_bytes):
                raise GpuYieldRefusal('Core GPU VRAM measurement absent/insufficient')
        return result


class NativeLuGpuLeaseV1Gateway:
    """Versioned NVP client over an ALREADY admitted native Lu pipe/UDS.

    Every verifier belongs to the separately installed OS-authenticated host.
    The source is incapable of deriving trusted grant/ack receipts from frames.
    When the installed verifier is absent or returns data without independent
    original-turn provenance, no positive admission occurs.
    """
    def __init__(self, frame_class, *, schema_git_blob: str,
                 native_exchange, verify_installed_lu_peer,
                 verify_negotiated_feature, attest_core_grant,
                 attest_core_release, native_worker_stop_ref,
                 major: int = 1, minor: int = 0,
                 max_poll_attempts: int = 360, poll_delay_s: float = 0.5,
                 wait_between_polls=None):
        self.codec = LuGpuLeaseV1Codec(frame_class, schema_git_blob=schema_git_blob)
        self.codec._check_version(major, minor)
        callbacks=(native_exchange, verify_installed_lu_peer,
                   verify_negotiated_feature, attest_core_grant,
                   attest_core_release, native_worker_stop_ref)
        if not all(callable(x) for x in callbacks):
            raise GpuYieldRefusal('Native Lu peer/feature/receipt/native-worker verifiers required')
        (self._exchange, self._peer, self._feature, self._grant,
         self._release, self._stop_ref) = callbacks
        if (type(max_poll_attempts) is not int or not 1 <= max_poll_attempts <= 360 or
                type(poll_delay_s) not in (int,float) or not 0 < poll_delay_s <= 2 or
                (wait_between_polls is not None and not callable(wait_between_polls))):
            raise GpuYieldRefusal('Bounded installed GPU lease poll budget required')
        self.major, self.minor = major, minor
        self.max_poll_attempts=max_poll_attempts
        self.poll_delay_s=float(poll_delay_s)
        self._wait=wait_between_polls or time.sleep

    def ready_for_safe_roundtrip(self, intent: YieldIntent) -> bool:
        # Both request AND release must be supported on the same admitted
        # Core epoch/session. No legacy COOPERATIVE_UNLOAD half-protocol.
        return self._peer(intent) is True and self._feature(intent, FEATURE) is True

    def _guard(self, intent: YieldIntent):
        if not self.ready_for_safe_roundtrip(intent):
            raise GpuYieldRefusal('No complete authenticated Lu gpu-lease-v1 roundtrip')

    def _roundtrip(self, intent: YieldIntent, frame, request_id, phase, lease_ref=None):
        self._guard(intent)
        reply = self._exchange(frame)
        self._guard(intent)  # Auth or feature may be revoked while awaiting Core.
        status=self.codec.outcome(reply, intent, request_id=request_id,
                                  expected_phase=phase, major=self.major,
                                  minor=self.minor, lease_ref=lease_ref,
                                  allow_deferred=True)
        if status.decision == ADMISSION_ALLOWED:
            return status
        original_ref=status.lease_ref
        if lease_ref is not None and original_ref != lease_ref:
            raise GpuYieldRefusal('Core queued another original GPU lease')
        for _ in range(self.max_poll_attempts):
            # The original user-turn deadline and live session remain
            # requirements. Time budget cannot itself grant or release VRAM.
            if time.time_ns() // 1_000_000 >= intent.deadline_unix_ms:
                raise GpuYieldRefusal('Lu GPU lease polling deadline exceeded')
            self._wait(self.poll_delay_s)
            self._guard(intent)
            poll_id='nvp-gpu-poll-'+secrets.token_hex(16)
            frame=self.codec.poll(intent,lease_ref=original_ref,
                                  transition=(1 if phase==GPU_GRANTED else 2),
                                  request_id=poll_id,major=self.major,minor=self.minor)
            reply=self._exchange(frame)
            self._guard(intent)
            status=self.codec.outcome(reply,intent,request_id=poll_id,
                expected_phase=phase,major=self.major,minor=self.minor,
                lease_ref=original_ref,allow_deferred=True)
            if status.decision == ADMISSION_ALLOWED:
                return status
        raise GpuYieldRefusal('Lu GPU transition still deferred; never launch or re-unload')

    def request_cooperative_gpu_yield(self, intent: YieldIntent):
        self._guard(intent)
        req_id = 'nvp-gpu-lease-' + secrets.token_hex(16)
        frame = self.codec.acquire(intent, request_id=req_id,
                                   major=self.major, minor=self.minor)
        claim = self._roundtrip(intent, frame, req_id, GPU_GRANTED)
        # A checked Protobuf GRANTED claim is NOT independent installed Core
        # evidence, and does not contain model_generation, Core epoch, durable
        # receipt SHA or expiry. The installed host must supply all of them.
        grant = self._grant(intent, claim)
        if type(grant) is not CoreYieldGrant:
            raise GpuYieldRefusal('No independently authenticated installed Core VRAM-release receipt')
        if (grant.operation_ref != intent.origin.operation_ref or
                grant.intent_sha256 != intent.intent_sha256 or
                grant.session_ref != intent.session_ref or
                grant.core_epoch_ref != intent.core_epoch_ref or
                grant.native_job_ref != intent.native_job_ref or
                grant.device_ref != intent.device_ref or
                grant.lease_ref != claim.lease_ref or
                grant.observed_free_vram_bytes != claim.measured_available_vram_bytes):
            raise GpuYieldRefusal('Installed Core lease receipt disagrees with Lu wire claim')
        self._guard(intent)
        return grant

    def send_verified_gpu_all_clear(self, intent: YieldIntent, evidence: dict,
                                    release_ref: str):
        self._guard(intent)
        if (type(evidence) is not dict or not isinstance(evidence.get('grant'), dict) or
                not isinstance(evidence.get('quiescence'), dict)):
            raise GpuYieldRefusal('Protected NVP journal all-clear evidence absent')
        grant = CoreYieldGrant(**evidence['grant'])
        witness = NativeGpuQuiescence(**evidence['quiescence'])
        if (grant.operation_ref != intent.origin.operation_ref or
                grant.intent_sha256 != intent.intent_sha256 or
                grant.session_ref != intent.session_ref or
                grant.core_epoch_ref != intent.core_epoch_ref or
                grant.native_job_ref != intent.native_job_ref or
                grant.device_ref != intent.device_ref or
                witness.operation_ref != grant.operation_ref or
                witness.native_job_ref != grant.native_job_ref or
                witness.device_ref != grant.device_ref or
                witness.lease_ref != grant.lease_ref or
                not (witness.worker_tree_reaped and witness.gpu_contexts_quiescent and
                     witness.release_fence_closed and witness.scm_custody_verified) or
                witness.active_gpu_workers != 0):
            raise GpuYieldRefusal('All-clear does not bind exact SCM/Job quiescence')
        # Original NVP SCM/Job native owner must resolve and attest this
        # locator; a caller-chosen hash or UI string is never proof.
        locator = self._stop_ref(intent, witness)
        if type(locator) is not str or not locator or len(locator)>128:
            raise GpuYieldRefusal('No OS-authenticated NVP worker-stop locator')
        _ref(locator)
        _ref(release_ref)
        req_id = 'nvp-gpu-clear-' + secrets.token_hex(16)
        frame = self.codec.release(intent, lease_ref=grant.lease_ref,
                                   worker_stop_ref=locator, request_id=req_id,
                                   major=self.major, minor=self.minor)
        claim = self._roundtrip(intent, frame, req_id, GPU_RESTORED, grant.lease_ref)
        ack = self._release(intent, witness, grant, release_ref, claim)
        if type(ack) is not CoreReleaseAck:
            raise GpuYieldRefusal('No independently authenticated durable Lu release receipt')
        if (ack.operation_ref != intent.origin.operation_ref or
                ack.lease_ref != grant.lease_ref or
                ack.core_epoch_ref != intent.core_epoch_ref or
                ack.release_ref != release_ref or
                ack.native_receipt_sha256 != witness.durable_native_receipt_sha256):
            raise GpuYieldRefusal('Lu durable all-clear receipt does not bind NVP native stop')
        self._guard(intent)
        return ack
