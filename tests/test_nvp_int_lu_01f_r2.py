"""R2 source/runtime fixtures: NO genuine installed Lu Core or production grant."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import unittest

from backend.nvp_lu_operation_journal import (
    IPCOperationJournal, JournalRefusal, ReceiptObservation,
)
from backend.nvp_lu_provider_bridge import (
    AdmittedLuPeer, NvpLuProviderBridge, PinnedProviderCodec,
    CAPABILITIES, MAX_FRAME_BYTES,
)
try:
    from nvp_lu_provider_fixture import lu_fixture, domain_fixture
except ModuleNotFoundError:  # For direct `python -m unittest tests.test_...`
    from tests.nvp_lu_provider_fixture import lu_fixture, domain_fixture

LU = lu_fixture()
DOMAIN = domain_fixture()
INPUTS = {cap: DOMAIN[name] for cap, (name, _) in CAPABILITIES.items()}


class NativeOwnerFixture:
    """Explicit test double; never a valid installed OS/creator attestation."""
    def __init__(self, peer):
        self.peer = peer
        self.approved = True
        self.creator_approved = True
        self.connected = True
        self.dispatches = []
        self.cancel_signals = []
        self.receipts = {}
        self.fail_dispatch_after_claim = False

    def verify_session(self, peer):
        return self.connected and peer == self.peer

    def admit_effect(self, peer, spec, typed, objs):
        return (self.verify_session(peer) and self.approved and self.creator_approved
                and spec.origin.user_turn_ref == 'turn-1'
                and spec.declared_effects == CAPABILITIES[spec.capability_id][1]
                and spec.host_epoch_ref == self.peer.core_epoch_ref)

    def dispatch_once(self, peer, spec, ticket, typed, objs):
        if self.fail_dispatch_after_claim:
            raise ConnectionError('test-only worker exit')
        assert self.verify_session(peer)
        assert ticket not in self.dispatches
        self.dispatches.append(ticket)
        return True

    def authorize_inspect(self, peer, op_ref, action, snapshot):
        return self.verify_session(peer) and snapshot['operation_ref'] == op_ref

    def authorize_cancel(self, peer, spec, reason):
        return self.verify_session(peer) and self.approved and reason == 'USER_CANCEL'

    def cancel_native(self, peer, spec, reason):
        self.cancel_signals.append(spec.origin.operation_ref)
        return True

    def verify_cancel_ack(self, peer, spec, ack, binding):
        return self.verify_session(peer) and ack and binding['operation_ref'] == spec.origin.operation_ref

    def authorize_supervisor_revocation(self, ref, reason, action, snapshot):
        return self.approved and reason == 'HOST_REVOKED' and snapshot['operation_ref'] == ref

    def revoke_native(self, spec, reason):
        return True

    def authorize_supervisor_result(self, ref, action, snapshot):
        return self.approved and snapshot['operation_ref'] == ref

    def verify_native_terminal(self, spec, observed, binding):
        return (self.approved and
                observed is self.receipts.get(spec.origin.operation_ref) and
                binding['request_sha256'] == spec.request_sha256 and
                binding['dispatch_ref'] is not None)

    def authorize_reconcile(self, peer, spec):
        # A restarted Core can have a new host epoch, but its original user-turn
        # scope must still be explicitly authenticated by actual OS-owned host.
        return self.verify_session(peer) and self.approved and spec.origin.user_turn_ref == 'turn-1'

    def lookup_receipt(self, peer, spec):
        return self.receipts.get(spec.origin.operation_ref)

    def verify_receipt(self, peer, spec, observed, binding):
        return (self.verify_session(peer) and
                observed is self.receipts.get(spec.origin.operation_ref) and
                binding['request_sha256'] == spec.request_sha256 and
                binding['dispatch_ref'] is not None)


class ProviderR2(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'protected'
        self.root.mkdir(mode=0o700)
        self.root = self.root.resolve(strict=True)
        self.now = 1_800_000_000_000
        self.journal = self.fresh_journal()
        self.peer = AdmittedLuPeer('host-session-1','core-epoch-1','workspace-1')
        self.native = NativeOwnerFixture(self.peer)
        self.bridge = self.fresh_bridge()

    def fresh_journal(self):
        return IPCOperationJournal(self.root,
            storage_guard=lambda path: path == self.root,
            clock_ms=lambda: self.now)

    def fresh_bridge(self, *, journal=None, supervisor=None):
        return NvpLuProviderBridge(journal or self.journal, LU['WorkspaceFrame'], INPUTS,
            supervisor=supervisor or self.native)

    def frame(self, kind, *, request_id='request-1', peer=None):
        p = peer or self.peer
        f = LU['WorkspaceFrame'](protocol_major=1, protocol_minor=0,
                 request_id=request_id, session_ref=p.session_ref)
        getattr(f, kind).SetInParent()
        return f

    def invoke(self, *, cap='nvp.film.project.read', request_id='request-1', peer=None,
               deadline=None, object_refs=0):
        f = self.frame('invoke',request_id=request_id,peer=peer)
        origin = f.invoke.origin
        origin.workspace_ref = 'workspace-1'
        origin.conversation_ref = 'conversation-1'
        origin.user_turn_ref = 'turn-1'
        origin.task_ref = 'task-1'
        origin.operation_ref = 'operation-1'
        f.invoke.capability_id = cap
        f.invoke.capability_version = 1
        f.invoke.deadline_unix_ms = deadline or (self.now + 60_000)
        f.invoke.input.type_url = 'type.googleapis.com/nvp.film.v1.' + CAPABILITIES[cap][0]
        f.invoke.input.encoded_message = INPUTS[cap](project_ref='project-1').SerializeToString(deterministic=True)
        for i in range(object_refs):
            r = f.invoke.input_refs.add()
            r.owner_module_id = 'nvp.film'
            r.object_ref = f'asset-{i}'
            r.sha256 = sha256(f'blob-{i}'.encode()).digest()
            r.size_bytes = 100
            r.expiry_unix_ms = self.now + 60_000
        return f

    def send(self, frame, *, peer=None, bridge=None):
        b = bridge or self.bridge
        return b.handle(frame.SerializeToString(deterministic=True),peer or self.peer)

    def untrusted_output(self, wire):
        f = LU['WorkspaceFrame']()
        f.ParseFromString(wire)
        return f

    def credit(self, *, request_id='credit-1', acknowledged=0, additional=1, peer=None):
        f = self.frame('stream_credit',request_id=request_id,peer=peer)
        f.stream_credit.operation_ref = 'operation-1'
        f.stream_credit.acknowledged_sequence = acknowledged
        f.stream_credit.additional_events = additional
        return f

    def reconcile(self, *, request_id='reconcile-1'):
        f = self.frame('reconcile',request_id=request_id)
        f.reconcile.operation_ref = 'operation-1'
        f.reconcile.expected_origin.CopyFrom(self.invoke().invoke.origin)
        return f

    def applied(self, *, reason='OWNER_FINISHED'):
        receipt = ReceiptObservation('operation-1','APPLIED',
                sha256(b'native-external-receipt').hexdigest(), reason, True)
        self.native.receipts['operation-1'] = receipt
        return receipt

    def test_lu_to_nvp_invoke_roundtrip_and_bounded_credit(self):
        self.assertIsNone(self.send(self.invoke()))
        self.assertEqual(len(self.native.dispatches),1)
        state = self.journal.status('operation-1')
        self.assertEqual(state['state'],'IN_FLIGHT')
        out = self.untrusted_output(self.send(self.credit()))
        self.assertEqual(out.WhichOneof('body'),'operation_event')
        self.assertEqual(out.operation_event.operation_ref,'operation-1')
        self.assertEqual(out.operation_event.progress.stage_code,'DISPATCH_ADMITTED')
        self.assertEqual(out.sequence,1)
        self.assertEqual(out.request_id,'request-1')
        self.assertIsNone(self.send(self.credit(request_id='credit-2',acknowledged=1)))
        self.assertEqual(len(self.native.dispatches),1)

    def test_matching_duplicate_invoke_never_reexecutes(self):
        inv = self.invoke()
        self.send(inv)
        with self.assertRaises(JournalRefusal):self.send(inv)
        fresh = self.fresh_bridge(journal=self.fresh_journal())
        with self.assertRaises(JournalRefusal):self.send(inv,bridge=fresh)
        self.assertEqual(len(self.native.dispatches),1)

    def test_ref_collision_on_typed_payload_and_object_refs(self):
        original = self.invoke(object_refs=1)
        self.send(original)
        changed = self.invoke(object_refs=1)
        changed.invoke.input_refs[0].sha256 = sha256(b'other').digest()
        with self.assertRaises(JournalRefusal):self.send(changed,bridge=self.fresh_bridge())
        altered = self.invoke(object_refs=1)
        altered.invoke.input.encoded_message = INPUTS['nvp.film.project.read'](project_ref='different').SerializeToString()
        with self.assertRaises(JournalRefusal):self.send(altered,bridge=self.fresh_bridge())
        self.assertEqual(len(self.native.dispatches),1)

    def test_native_supervisor_denial_and_missing_default(self):
        self.native.approved = False
        with self.assertRaises(JournalRefusal):self.send(self.invoke())
        self.assertEqual(self.native.dispatches,[])
        self.native.approved = True
        self.native.creator_approved = False
        with self.assertRaises(JournalRefusal):self.send(self.invoke())
        self.native.creator_approved = True
        missing = NvpLuProviderBridge(self.journal,LU['WorkspaceFrame'],INPUTS)
        with self.assertRaises(JournalRefusal):self.send(self.invoke(),bridge=missing)
        self.assertEqual(self.native.dispatches,[])

    def test_refusal_is_sanitized_without_retry_or_raw_diagnostics(self):
        self.native.approved = False
        refused = self.untrusted_output(self.bridge.handle_safe(
            self.invoke().SerializeToString(deterministic=True),self.peer))
        self.assertEqual(refused.WhichOneof('body'),'failure')
        self.assertEqual(refused.failure.code,'NVP_REFUSED')
        self.assertFalse(refused.failure.retryable)
        self.assertFalse(refused.failure.outcome_uncertain)
        self.assertNotIn('sqlite',refused.failure.explanation.lower())
        forged = AdmittedLuPeer('other-session','other-epoch','workspace-1')
        with self.assertRaises(JournalRefusal):
            self.bridge.handle_safe(self.invoke().SerializeToString(deterministic=True),forged)

    def test_uncertain_dispatch_returns_not_retryable_protocol_failure(self):
        self.native.fail_dispatch_after_claim = True
        failed = self.untrusted_output(self.bridge.handle_safe(
            self.invoke().SerializeToString(deterministic=True),self.peer))
        self.assertEqual(failed.failure.code,'NVP_OUTCOME_UNCERTAIN')
        self.assertTrue(failed.failure.outcome_uncertain)
        self.assertFalse(failed.failure.retryable)
        self.assertEqual(self.journal.status('operation-1')['state'],'IN_FLIGHT')
        self.assertEqual(len(self.native.dispatches),0)

    def test_lu_cannot_spoof_session_epoch_or_origin(self):
        forged = AdmittedLuPeer('host-session-forged','core-epoch-1','workspace-1')
        with self.assertRaises(JournalRefusal):self.send(self.invoke(peer=forged),peer=forged)
        mismatched = self.invoke()
        mismatched.invoke.origin.workspace_ref = 'workspace-2'
        with self.assertRaises(JournalRefusal):self.send(mismatched)
        with self.assertRaises(JournalRefusal):self.send(self.invoke(),peer=forged)
        self.assertEqual(self.native.dispatches,[])

    def test_missing_typed_schema_unregistered_and_unknown_fields_denied(self):
        with self.assertRaises(JournalRefusal):
            NvpLuProviderBridge(self.journal,LU['WorkspaceFrame'],{},supervisor=self.native)
        inv = self.invoke()
        inv.invoke.input.type_url = 'type.googleapis.com/evil.v1.ProjectReadRequest'
        with self.assertRaises(JournalRefusal):self.send(inv)
        inv = self.invoke()
        inv.invoke.capability_version = 2
        with self.assertRaises(JournalRefusal):self.send(inv)
        inv = self.invoke()
        inv.invoke.input.encoded_message += b'\xa0\x06\x01'  # unknown field #100
        with self.assertRaises(JournalRefusal):self.send(inv)
        with self.assertRaises(JournalRefusal):self.bridge.handle(self.invoke().SerializeToString()+b'\xa0\x06\x01',self.peer)
        self.assertEqual(self.native.dispatches,[])

    def test_object_ref_caps_hash_size_expiry_and_duplicate(self):
        for n in (17,):
            with self.assertRaises(JournalRefusal):self.send(self.invoke(object_refs=n))
        for bad in ('sha256','owner_module_id','size_bytes','expiry_unix_ms'):
            inv = self.invoke(object_refs=1)
            if bad == 'sha256': inv.invoke.input_refs[0].sha256 = b'0' * 31
            elif bad == 'owner_module_id': inv.invoke.input_refs[0].owner_module_id = 'lu.core'
            elif bad == 'size_bytes': inv.invoke.input_refs[0].size_bytes = 0
            else: inv.invoke.input_refs[0].expiry_unix_ms = self.now
            with self.subTest(bad=bad),self.assertRaises(JournalRefusal):self.send(inv)
        duplicated = self.invoke(object_refs=2)
        duplicated.invoke.input_refs[1].object_ref = duplicated.invoke.input_refs[0].object_ref
        with self.assertRaises(JournalRefusal):self.send(duplicated)

    def test_effect_declaration_is_full_compound_without_downgrade(self):
        inv = self.invoke(cap='nvp.film.render.shot')
        self.send(inv)
        bound = self.journal.bound_spec('operation-1',authorize=lambda *_:True)
        self.assertEqual(bound.effect_class,4)
        self.assertEqual(bound.declared_effects,(4,3))
        self.assertEqual(len(self.native.dispatches),1)

    def test_no_render_without_independent_creator_grant(self):
        self.native.creator_approved = False
        with self.assertRaises(JournalRefusal):self.send(self.invoke(cap='nvp.film.render.shot'))
        self.assertFalse(self.native.dispatches)

    def test_cancel_ack_records_signal_not_terminal(self):
        self.send(self.invoke())
        f = self.frame('cancel',request_id='cancel-request-1')
        f.cancel.operation_ref = 'operation-1'
        f.cancel.reason_code = 'USER_CANCEL'
        out = self.untrusted_output(self.send(f))
        self.assertEqual(out.WhichOneof('body'),'cancel_ack')
        self.assertTrue(out.cancel_ack.signal_recorded)
        self.assertEqual(self.native.cancel_signals,['operation-1'])
        state = self.journal.status('operation-1')
        self.assertTrue(state['cancel_requested'])
        self.assertTrue(state['cancel_acknowledged'])
        self.assertEqual(state['state'],'IN_FLIGHT')
        self.assertIsNone(state['terminal_state'])

    def test_cancel_before_native_dispatch_is_only_signal_no_worker_receipt(self):
        spec = self.bridge._spec(self.invoke(), self.peer)
        self.journal.prepare(spec,authorize=lambda *_:True)
        cancel = self.frame('cancel')
        cancel.cancel.operation_ref = 'operation-1'
        cancel.cancel.reason_code = 'USER_CANCEL'
        out = self.untrusted_output(self.send(cancel))
        self.assertTrue(out.cancel_ack.signal_recorded)
        self.assertTrue(self.journal.status('operation-1')['cancel_requested'])
        self.assertFalse(self.journal.status('operation-1')['cancel_acknowledged'])
        self.assertFalse(self.native.cancel_signals)
        with self.assertRaises(JournalRefusal):self.send(self.invoke())

    def test_supervisor_revocation_requires_independent_native_owner_and_blocks_fresh_dispatch(self):
        spec = self.bridge._spec(self.invoke(), self.peer)
        self.journal.prepare(spec, authorize=lambda *_:True)
        self.native.approved = False
        with self.assertRaises(JournalRefusal):
            self.bridge.supervisor_revoke('operation-1','HOST_REVOKED')
        self.native.approved = True
        self.bridge.supervisor_revoke('operation-1','HOST_REVOKED')
        self.assertTrue(self.journal.status('operation-1')['revoked'])
        with self.assertRaises(JournalRefusal):self.send(self.invoke())
        self.assertEqual(self.native.dispatches,[])

    def test_cancel_wrong_reason_or_session_revocation(self):
        self.send(self.invoke())
        bad = self.frame('cancel')
        bad.cancel.operation_ref = 'operation-1'
        bad.cancel.reason_code = 'UNAUTH_REASON'
        with self.assertRaises(JournalRefusal):self.send(bad)
        self.native.connected = False
        with self.assertRaises(JournalRefusal):self.send(self.frame('cancel'))
        self.assertFalse(self.native.cancel_signals)

    def test_reconcile_requires_original_turn_and_authenticated_evidence(self):
        self.send(self.invoke())
        unknown = self.untrusted_output(self.send(self.reconcile()))
        self.assertEqual(unknown.reconciled.observed.state,5)
        self.assertFalse(unknown.reconciled.evidence_available)
        changed = self.reconcile()
        changed.reconcile.expected_origin.user_turn_ref = 'turn-else'
        with self.assertRaises(JournalRefusal):self.send(changed)
        self.applied()
        applied = self.untrusted_output(self.send(self.reconcile(request_id='reconcile-2')))
        self.assertEqual(applied.reconciled.observed.state,1)
        self.assertTrue(applied.reconciled.evidence_available)
        self.assertEqual(self.journal.status('operation-1')['state'],'TERMINAL')
        self.assertEqual(applied.reconciled.observed.durable_receipt_sha256,
                         sha256(b'native-external-receipt').digest())

    def test_real_supervisor_terminal_durably_emitted_only_after_credit(self):
        self.send(self.invoke())
        observed = self.applied()
        stored = self.bridge.record_native_terminal('operation-1',observed)
        self.assertEqual(stored['terminal_state'],'APPLIED')
        self.assertTrue(stored['evidence_available'])
        output = self.untrusted_output(self.send(self.credit()))
        self.assertEqual(output.WhichOneof('body'),'operation_event')
        self.assertEqual(output.operation_event.WhichOneof('data'),'terminal')
        self.assertEqual(output.operation_event.terminal.state,1)
        self.assertEqual(output.sequence,1)
        self.assertEqual(output.operation_event.terminal.durable_receipt_sha256,
                         sha256(b'native-external-receipt').digest())
        self.assertIsNone(self.send(self.credit(request_id='credit-2',acknowledged=1)))
        self.assertEqual(len(self.native.dispatches),1)

    def test_native_terminal_persists_through_lu_disconnect_without_grant(self):
        self.send(self.invoke())
        self.bridge.disconnect()
        self.native.connected = False
        self.applied()
        self.bridge.record_native_terminal('operation-1',self.native.receipts['operation-1'])
        self.assertEqual(self.fresh_journal().status('operation-1')['terminal_state'],'APPLIED')
        self.native.connected = True
        fresh = self.fresh_bridge(journal=self.fresh_journal())
        resolved = self.untrusted_output(self.send(self.reconcile(),bridge=fresh))
        self.assertEqual(resolved.reconciled.observed.state,1)
        self.assertTrue(resolved.reconciled.evidence_available)

    def test_native_supervisor_refuses_unverified_terminal(self):
        self.send(self.invoke())
        self.native.approved = False
        forged = ReceiptObservation('operation-1','APPLIED',sha256(b'invented').hexdigest(),
                                    'NOT_AUTHENTIC',True)
        with self.assertRaises(JournalRefusal):
            self.bridge.record_native_terminal('operation-1',forged)
        self.assertEqual(self.journal.status('operation-1')['state'],'IN_FLIGHT')

    def test_restart_and_disconnected_worker_never_autoretry(self):
        self.native.fail_dispatch_after_claim = True
        with self.assertRaises(JournalRefusal):self.send(self.invoke())
        self.assertEqual(self.journal.status('operation-1')['state'],'IN_FLIGHT')
        self.native.fail_dispatch_after_claim = False
        self.assertEqual(self.fresh_journal().reconcile_after_restart(authorize=lambda *_:True),
                         ['operation-1'])
        fresh = self.fresh_bridge(journal=self.fresh_journal())
        with self.assertRaises(JournalRefusal):self.send(self.invoke(),bridge=fresh)
        self.assertEqual(len(self.native.dispatches),0)
        self.applied()
        out = self.untrusted_output(self.send(self.reconcile(),bridge=fresh))
        self.assertEqual(out.reconciled.observed.state,1)

    def test_credit_bounds_and_replay_do_not_redeliver_native_work(self):
        self.send(self.invoke())
        with self.assertRaises(JournalRefusal):self.send(self.credit(additional=65))
        with self.assertRaises(JournalRefusal):self.send(self.credit(acknowledged=1))
        result = self.send(self.credit())
        self.assertIsNotNone(result)
        with self.assertRaises(JournalRefusal):self.send(self.credit())
        with self.assertRaises(JournalRefusal):self.send(self.credit(request_id='credit-2',acknowledged=0,additional=64))
        self.assertEqual(len(self.native.dispatches),1)
        self.bridge.disconnect()
        with self.assertRaises(JournalRefusal):self.send(self.credit(request_id='credit-3'))

    def test_real_socket_partial_framing_and_truncation(self):
        left,right=socket.socketpair()
        try:
            raw=self.invoke().SerializeToString(deterministic=True)
            packed=PinnedProviderCodec.pack(raw)
            right.sendall(packed[:2]); right.sendall(packed[2:9]); right.sendall(packed[9:])
            self.assertEqual(PinnedProviderCodec.read_frame(left),raw)
            PinnedProviderCodec.write_frame(left,raw)
            self.assertEqual(PinnedProviderCodec.read_frame(right),raw)
            right.sendall(struct.pack('!I',12) + b'123'); right.shutdown(socket.SHUT_WR)
            with self.assertRaises(JournalRefusal):PinnedProviderCodec.read_frame(left)
        finally:
            left.close();right.close()

    def test_frame_prefix_and_version_negative(self):
        raw = self.invoke().SerializeToString(deterministic=True)
        packed = PinnedProviderCodec.pack(raw)
        self.assertEqual(PinnedProviderCodec.unpack(packed),raw)
        for bad in (b'',b'\x00',struct.pack('!I',len(raw)+1)+raw,
                    struct.pack('!I',MAX_FRAME_BYTES+1)+raw,packed+b'trailing'):
            with self.subTest(bad=bad[:8]),self.assertRaises(JournalRefusal):
                PinnedProviderCodec.unpack(bad)
        inv = self.invoke(); inv.protocol_major = 2
        with self.assertRaises(JournalRefusal):self.send(inv)
        inv = self.invoke(); inv.sequence = 1
        with self.assertRaises(JournalRefusal):self.send(inv)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux AF_UNIX kernel fixture')
    def test_actual_kernel_peer_credentials_with_separate_process_proto_framing(self):
        # Executes real OS UDS transport in separate process with SO_PEERCRED.
        # Child is deliberately *not* a Lu Core; merely echoes canonical bytes.
        incoming, outgoing = socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            code = r'''
import socket,struct,sys
from google.protobuf.message import Message
fd = int(sys.argv[1]); sock=socket.socket(fileno=fd)
header=sock.recv(4)
size=struct.unpack('!I',header)[0]
assert 0 < size <= 262144
buf=b''
while len(buf)<size:
    part=sock.recv(size-len(buf))
    if not part: raise RuntimeError('truncated')
    buf+=part
sock.sendall(struct.pack('!I',len(buf))+buf)
'''
            child=subprocess.Popen([sys.executable,'-c',code,str(outgoing.fileno())],
                pass_fds=(outgoing.fileno(),), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            outgoing.close()
            pid, uid, gid = struct.unpack('3i',incoming.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            self.assertEqual(uid,os.getuid())
            self.assertEqual(gid,os.getgid())
            # Kernel peer PID is the original creator until child executes;
            # this fixture checks source transport only, never treats PID as admission.
            raw=self.invoke().SerializeToString(deterministic=True)
            incoming.sendall(PinnedProviderCodec.pack(raw))
            header=incoming.recv(4)
            size=struct.unpack('!I',header)[0]
            buf=b''
            while len(buf)<size: buf+=incoming.recv(size-len(buf))
            self.assertEqual(buf,raw)
            self.assertIsNone(self.bridge.handle(buf,self.peer))
            stdout,stderr=child.communicate(timeout=6)
            self.assertEqual(child.returncode,0,stderr.decode())
            self.assertEqual(len(self.native.dispatches),1)
        finally:
            incoming.close(); outgoing.close()


if __name__ == '__main__':
    unittest.main()
