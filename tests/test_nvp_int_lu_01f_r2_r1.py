"""R2-R1 Linux-testable negative/source tests; NOT genuine Windows acceptance."""
from __future__ import annotations
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest

from backend.nvp_lu_operation_journal import (
    IPCOperationJournal, JournalRefusal, OriginRefs, OperationSpec, ReceiptObservation,
)
from backend.nvp_lu_native_production_link import (
    WindowsProtectedProductionLink, NativeProductionIdentity,
    _exact_native_job_status, NATIVE_KIND,
)


def digest(raw): return sha256(raw).hexdigest()


class NativeProductionBindingR2R1(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'private'
        self.root.mkdir(mode=0o700)
        self.now = 1_800_000_000_000
        self.db = self.new_db()
        self.spec = OperationSpec(
            OriginRefs('workspace','conversation','turn','task','op-1'),
            'nvp.film.project.read', 1, 2, digest(b'payload'),
            digest(b'objects'), self.now+60_000, 'session','epoch',
            declared_effects=(2,))
        self.db.prepare(self.spec, authorize=lambda *_: True)
        self.claim = self.db.claim_dispatch('op-1', authorize=lambda *_: True)
        self.native = NativeProductionIdentity('44fce932-6f54-4db7-88ed-371c39eebc41','a'*32,digest(b'manifest'))

    def new_db(self):
        return IPCOperationJournal(self.root,
            storage_guard=lambda path: path == self.root,
            clock_ms=lambda: self.now)

    def bind(self, *, spec=None, dispatch=None, native=None, authorize=lambda *_:True):
        n = native or self.native
        return self.db.bind_native_job(spec or self.spec,
            dispatch_ref=dispatch or self.claim['dispatch_ref'],
            native_job_ref=n.job_id, project_id=n.project_id,
            manifest_sha256=n.manifest_sha256, native_kind=NATIVE_KIND,
            authorize=authorize)

    def test_dispatch_must_be_claimed_and_exact_before_native_binding(self):
        with self.assertRaises(JournalRefusal):
            self.bind(dispatch='another-dispatch')
        with self.assertRaises(JournalRefusal):
            self.bind(spec=replace(self.spec, host_epoch_ref='wrong-epoch'))
        with self.assertRaises(JournalRefusal):
            self.bind(authorize=lambda *_:False)
        with self.assertRaises(JournalRefusal):
            self.db.bind_native_job(self.spec,dispatch_ref=self.claim['dispatch_ref'],
                native_job_ref=self.native.job_id,project_id=self.native.project_id,
                manifest_sha256=self.native.manifest_sha256,native_kind='unregistered',
                authorize=lambda *_: True)
        self.assertEqual(self.db.status('op-1')['state'], 'IN_FLIGHT')
        with self.assertRaises(JournalRefusal):
            self.db.native_job_binding('op-1',authorize=lambda *_: True)

    def test_native_job_binding_is_durable_and_identical_rebind_is_idempotent(self):
        first = self.bind()
        self.assertEqual(first, self.bind())
        actual = self.new_db().native_job_binding('op-1',authorize=lambda *_: True)
        self.assertEqual(actual['native_job_ref'], self.native.job_id)
        self.assertEqual(actual['request_sha256'],self.spec.request_sha256)
        with self.assertRaises(JournalRefusal):
            self.bind(native=replace(self.native, manifest_sha256=digest(b'changed')))
        with self.assertRaises(JournalRefusal):
            self.new_db().native_job_binding('op-1', authorize=lambda *_:False)
        self.assertEqual(len([x for x in self.db.events('op-1')
                              if x['kind']=='HOST_NATIVE_JOB_BOUND']),1)

    def test_native_job_cannot_be_shared_with_another_lu_operation(self):
        self.bind()
        second = replace(self.spec,
            origin=replace(self.spec.origin,operation_ref='op-2'))
        self.db.prepare(second,authorize=lambda *_:True)
        ticket=self.db.claim_dispatch('op-2',authorize=lambda *_:True)
        with self.assertRaises(JournalRefusal):
            self.db.bind_native_job(second,dispatch_ref=ticket['dispatch_ref'],
                native_job_ref=self.native.job_id,project_id=self.native.project_id,
                manifest_sha256=self.native.manifest_sha256,native_kind=NATIVE_KIND,
                authorize=lambda *_: True)
        self.assertEqual(self.db.status('op-2')['state'],'IN_FLIGHT')

    def test_crash_uncertain_keeps_binding_but_never_retries_worker(self):
        self.bind()
        self.assertEqual(self.new_db().reconcile_after_restart(authorize=lambda *_: True),['op-1'])
        self.assertEqual(self.new_db().status('op-1')['state'],'UNCERTAIN')
        self.assertEqual(self.new_db().native_job_binding('op-1',authorize=lambda *_:True)['native_job_ref'],
                         self.native.job_id)
        with self.assertRaises(JournalRefusal):
            self.new_db().claim_dispatch('op-1',authorize=lambda *_:True)

    def test_matching_native_job_is_never_itself_terminal_effect_evidence(self):
        self.bind()
        self.assertIsNone(self.db.status('op-1')['terminal_state'])
        # A receipt from an unauthenticated or merely successful native job
        # must fail the *independent* terminal verification gate.
        observation=ReceiptObservation('op-1','APPLIED',digest(b'fake'),'DONE',True)
        with self.assertRaises(JournalRefusal):
            self.db.reconcile_receipt(self.spec,observation,
                                      verify_receipt=lambda *_:False)
        self.assertEqual(self.db.status('op-1')['state'],'IN_FLIGHT')

    def test_native_status_exact_identity_and_no_export_success_claim(self):
        native=self.native
        good={'job_id':native.job_id,'project_id':native.project_id,
              'manifest_sha256':native.manifest_sha256,
              'task_kind':'VERIFY_APPROVED_MEDIA_V1',
              'state':'RUNNING','cancel_requested':False,
              'production_dcp_accepted':False}
        self.assertEqual(_exact_native_job_status(good,native)['state'],'RUNNING')
        for changed in ({'task_kind':'PUBLISH_CINEMA'}, {'state':'DCP_PUBLISHED'},
                        {'production_dcp_accepted':True},
                        {'project_id':'b'*32},{'manifest_sha256':digest(b'other')},
                        {'cancel_requested':1}):
            with self.subTest(changed=changed),self.assertRaises(JournalRefusal):
                _exact_native_job_status({**good,**changed},native)

    def test_installed_production_custody_not_available_in_linux_fixture(self):
        if os.name=='nt': self.skipTest('Linux-only refusal')
        with self.assertRaises(JournalRefusal):
            WindowsProtectedProductionLink(self.db,object(),object(),
                resolve_native_scope=lambda *_:True,
                creator_cancel_approval=lambda *_:True)

    def test_cancel_cannot_ever_be_forged_by_protobuf_or_unbound_job(self):
        self.bind()
        class Native:
            def __init__(self): self.cancel_count=0; self.root=Path("/fixture/native-owner")
            def status(self, job):
                return {'job_id':job,'project_id':selfid.project_id,
                        'manifest_sha256':selfid.manifest_sha256,
                        'task_kind':'VERIFY_APPROVED_MEDIA_V1','state':'RUNNING',
                        'cancel_requested':self.cancel_count>0,
                        'production_dcp_accepted':False}
            def request_cancel(self, job, authorize):
                if authorize({'job_id':job,'operation':'nvp.supervisor.request_cancel.v1'}) is not True:
                    return {'status':'DENIED','job_id':job}
                self.cancel_count+=1
                return {'status':'CANCEL_REQUESTED','job_id':job}
        selfid=self.native
        production=Native()
        # Pure negative contract test. __new__ bypasses Windows constructor so
        # it is NEVER an installed native NVP supervisor or source attestation.
        owner=object.__new__(WindowsProtectedProductionLink)
        owner._ipc=self.db
        owner._production=production
        owner._require_owner=lambda *_:None
        owner._resolve_scope=lambda spec,native:True
        owner._creator_cancel=lambda *args: False
        with self.assertRaises(JournalRefusal):
            owner.signal_cancel_to_real_journal(self.spec,'USER_CANCEL')
        self.assertEqual(production.cancel_count,0)
        owner._creator_cancel=lambda spec,native,reason,scope: reason=='USER_CANCEL'
        self.assertTrue(owner.signal_cancel_to_real_journal(self.spec,'USER_CANCEL'))
        self.assertEqual(production.cancel_count,1)
        self.assertEqual(owner.observe_native_without_terminal_claim(self.spec)['state'],'RUNNING')
        self.assertEqual(self.db.status('op-1')['state'],'IN_FLIGHT')


if __name__=='__main__': unittest.main()


class BoundDuplexFixtureR2R1(unittest.TestCase):
    """Actual Linux socketpair framing; fake peer grant, not installed Lu."""
    def setUp(self):
        from backend.nvp_lu_provider_bridge import (
            NvpLuProviderBridge,AdmittedLuPeer,CAPABILITIES,
        )
        from tests.nvp_lu_provider_fixture import lu_fixture,domain_fixture
        import socket
        self.sock1,self.sock2=socket.socketpair()
        self.addCleanup(self.sock1.close)
        self.addCleanup(self.sock2.close)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)/'private';root.mkdir(mode=0o700)
        self.journal=IPCOperationJournal(root,
            storage_guard=lambda path:path==root,
            clock_ms=lambda:1_800_000_000_000)
        self.peer=AdmittedLuPeer('session','epoch','workspace')
        class TestOnlySupervisor:
            def __init__(self,peer):self.peer=peer;self.connected=True
            def verify_session(self,p):return self.connected and p==self.peer
        self.native=TestOnlySupervisor(self.peer)
        lu=lu_fixture();domain=domain_fixture()
        types={cap:domain[name] for cap,(name,_) in CAPABILITIES.items()}
        self.bridge=NvpLuProviderBridge(self.journal,lu['WorkspaceFrame'],types,
                                        supervisor=self.native)
        self.lu=lu

    def test_unknown_operation_reconcile_refuses_no_dispatch_and_no_replay(self):
        from backend.nvp_lu_provider_bridge import BoundNativeProviderExchange,PinnedProviderCodec
        bound=BoundNativeProviderExchange(self.bridge,self.sock1,self.peer,
              attest_live_owner=lambda:True)
        frame=self.lu['WorkspaceFrame'](protocol_major=1,protocol_minor=0,
            request_id='req',session_ref=self.peer.session_ref)
        frame.reconcile.operation_ref='unknown-op'
        frame.reconcile.expected_origin.workspace_ref='workspace'
        frame.reconcile.expected_origin.conversation_ref='conv'
        frame.reconcile.expected_origin.user_turn_ref='turn'
        frame.reconcile.expected_origin.task_ref='task'
        frame.reconcile.expected_origin.operation_ref='unknown-op'
        raw=frame.SerializeToString(deterministic=True)
        self.sock2.sendall(PinnedProviderCodec.pack(raw))
        self.assertTrue(bound.one_exchange())
        reply=self.sock2.recv(4096)
        self.assertEqual(PinnedProviderCodec.unpack(reply)[:1],b'\x08')
        parsed=self.lu['WorkspaceFrame']()
        parsed.ParseFromString(PinnedProviderCodec.unpack(reply))
        self.assertEqual(parsed.WhichOneof('body'),'failure')
        self.assertFalse(parsed.failure.retryable)
        self.assertFalse(parsed.failure.outcome_uncertain)
        bound.close()

    def test_native_owner_exit_before_read_or_after_decode_refuses_all_writes(self):
        from backend.nvp_lu_provider_bridge import BoundNativeProviderExchange
        lease=BoundNativeProviderExchange(self.bridge,self.sock1,self.peer,
            attest_live_owner=lambda:False)
        with self.assertRaises(JournalRefusal):lease.one_exchange()
        self.assertTrue(lease.closed)
        self.sock2.settimeout(.2)
        self.assertEqual(self.sock2.recv(4), b'')

    def test_transport_refuses_socket_hup_and_loses_volatile_stream_only(self):
        from backend.nvp_lu_provider_bridge import BoundNativeProviderExchange
        bound=BoundNativeProviderExchange(self.bridge,self.sock1,self.peer,
            attest_live_owner=lambda:True)
        self.sock2.shutdown(2)
        with self.assertRaises(JournalRefusal):bound.one_exchange()
        self.assertTrue(bound.closed)
        self.assertEqual(self.bridge._streams,{})


class ProviderToProductionIntegrationFixture(unittest.TestCase):
    """Real R2 provider methods, synthetic owner; NOT installed admission."""
    def test_bound_provider_cancel_uses_single_original_production_journal_signal(self):
        from backend.nvp_lu_provider_bridge import (
            NvpLuProviderBridge, AdmittedLuPeer, CAPABILITIES,
        )
        from tests.nvp_lu_provider_fixture import lu_fixture, domain_fixture
        from uuid import uuid4
        import sqlite3
        lu=lu_fixture();domain=domain_fixture()
        inputs={cap:domain[name] for cap,(name,_) in CAPABILITIES.items()}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'private'; root.mkdir(mode=0o700)
            db=IPCOperationJournal(root,storage_guard=lambda path:path==root,
                                  clock_ms=lambda:1_800_000_000_000)
            peer=AdmittedLuPeer('session','epoch','workspace')
            class TestSupervisor:
                def __init__(self):self.dispatch=0;self.generic_cancel=0;self.connected=True
                def verify_session(self,p):return self.connected and p==peer
                def admit_effect(self,*_):return self.connected
                def dispatch_once(self,*_):self.dispatch+=1;return True
                def authorize_supervisor_result(self,*_):return self.connected
                def authorize_inspect(self,*_):return self.connected
                def authorize_cancel(self,*_):return self.connected
                def verify_cancel_ack(self,*_):return self.connected
                def cancel_native(self,*_):self.generic_cancel+=1;return True
            supervisor=TestSupervisor()
            native=NativeProductionIdentity(str(uuid4()),'a'*32,digest(b'plan'))
            class ProductionStub:
                def __init__(self):self.cancelled=0;self.root=root
                def status(self,job_id):
                    return dict(job_id=job_id,project_id=native.project_id,
                        manifest_sha256=native.manifest_sha256,
                        task_kind='VERIFY_APPROVED_MEDIA_V1',
                        state='RUNNING',cancel_requested=bool(self.cancelled),
                        production_dcp_accepted=False)
                def request_cancel(self,job_id,authorize):
                    if authorize({'job_id':job_id, 'operation':
                         'nvp.supervisor.request_cancel.v1'}) is not True:
                        return {'job_id':job_id,'status':'DENIED'}
                    self.cancelled+=1
                    return {'job_id':job_id,'status':'CANCEL_REQUESTED'}
            source=ProductionStub()
            link=object.__new__(WindowsProtectedProductionLink)  # test only!
            link._ipc=db;link._production=source
            link._require_owner=lambda *_:None
            link._resolve_scope=lambda *args:True
            link._creator_cancel=lambda *args:True
            bridge=NvpLuProviderBridge(db,lu['WorkspaceFrame'],inputs,
                supervisor=supervisor,native_production_link=link)
            invoke=lu['WorkspaceFrame'](protocol_major=1,protocol_minor=0,
                                       request_id='r1',session_ref='session')
            origin=invoke.invoke.origin
            origin.workspace_ref='workspace';origin.conversation_ref='conv'
            origin.user_turn_ref='turn';origin.task_ref='task';origin.operation_ref='op-1'
            invoke.invoke.capability_id='nvp.film.project.read'
            invoke.invoke.capability_version=1
            invoke.invoke.input.type_url='type.googleapis.com/nvp.film.v1.ProjectReadRequest'
            invoke.invoke.input.encoded_message=inputs['nvp.film.project.read'](
                project_ref='a'*32).SerializeToString(deterministic=True)
            invoke.invoke.deadline_unix_ms=1_800_000_060_000
            self.assertIsNone(bridge.handle(invoke.SerializeToString(deterministic=True),peer))
            self.assertEqual(supervisor.dispatch,1)
            with closing(sqlite3.connect(db.path)) as con:
                ticket=con.execute("SELECT dispatch_ref FROM ipc_operations WHERE operation_ref='op-1'").fetchone()[0]
            bind=bridge.supervisor_bind_native_production_job('op-1',ticket,native)
            self.assertEqual(bind['native_job_ref'],native.job_id)
            cancel=lu['WorkspaceFrame'](protocol_major=1,protocol_minor=0,
                request_id='r2',session_ref='session')
            cancel.cancel.operation_ref='op-1';cancel.cancel.reason_code='USER_CANCEL'
            data=bridge.handle(cancel.SerializeToString(deterministic=True),peer)
            result=lu['WorkspaceFrame']();result.ParseFromString(data)
            self.assertTrue(result.cancel_ack.signal_recorded)
            self.assertEqual(source.cancelled,1)
            self.assertEqual(supervisor.generic_cancel,0)
            self.assertTrue(db.status('op-1')['cancel_requested'])
            self.assertEqual(db.status('op-1')['state'],'IN_FLIGHT')
            self.assertIsNone(db.status('op-1')['terminal_state'])
            supervisor.connected=False
            cancel.request_id='r3'
            with self.assertRaises(JournalRefusal):
                bridge.handle(cancel.SerializeToString(deterministic=True),peer)
            self.assertEqual(source.cancelled,1)
