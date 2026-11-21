"""New Lu gpu-lease-v1 wire and durable handoff; all positive peers are fixtures.

The actual Windows signer, installed Core, NVP SCM worker and AMD driver are
NOT present here; these tests only validate the source's refusal boundaries.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from backend.nvp_lu_gpu_lease_v1 import (
    LU_GPU_PROTO_BLOB, LuGpuLeaseV1Codec, NativeLuGpuLeaseV1Gateway,
)
from backend.nvp_lu_gpu_yield import (
    CoreReleaseAck, CoreYieldGrant, GpuYieldJournal, GpuYieldRefusal,
    NativeGpuQuiescence, NvpGpuYieldCoordinator, YieldIntent,
)
from backend.nvp_lu_operation_journal import OriginRefs


def wire_frame():
    """Structurally projected source-only descriptor, NOT installed generated Lu SDK."""
    d=descriptor_pb2.FileDescriptorProto(name='nvp_gpu_r1_test_only.proto',
        package='lu.workspace.v0',syntax='proto3')
    def message(name, fields):
        m=d.message_type.add(name=name)
        for number,n,t,msg in fields:
            f=m.field.add(name=n,number=number,label=1,type=t)
            if msg:f.type_name='.lu.workspace.v0.'+msg
        return m
    origin=message('OriginRefs',[(i,n,9,None) for i,n in enumerate((
        'workspace_ref','conversation_ref','user_turn_ref','task_ref','operation_ref'),1)])
    req=message('GpuLeaseRequest',[(1,'origin',11,'OriginRefs'),(2,'device_ref',9,None),
        (3,'required_free_vram_bytes',4,None),(4,'max_duration_ms',4,None)])
    outcome=message('GpuLeaseOutcome',[(1,'operation_ref',9,None),(2,'decision',5,None),
        (3,'phase',5,None),(4,'lease_ref',9,None),(5,'measured_available_vram_bytes',4,None),
        (6,'reason_code',9,None)])
    optional=outcome.oneof_decl.add(name='_measured_available_vram_bytes')
    fld=outcome.field[4];fld.proto3_optional=True;fld.oneof_index=0
    rel=message('GpuLeaseRelease',[(1,'origin',11,'OriginRefs'),(2,'lease_ref',9,None),
        (3,'nvp_worker_stop_ref',9,None)])
    poll=message('GpuLeasePoll',[(1,'origin',11,'OriginRefs'),
        (2,'lease_ref',9,None),(3,'transition',5,None)])
    frame=message('WorkspaceFrame',[(1,'protocol_major',13,None),
        (2,'protocol_minor',13,None),(3,'request_id',9,None),
        (4,'session_ref',9,None),(5,'sequence',4,None)])
    frame.oneof_decl.add(name='body')
    for name,number,msg in [('gpu_lease_request',38,'GpuLeaseRequest'),
                            ('gpu_lease_outcome',39,'GpuLeaseOutcome'),
                            ('gpu_lease_release',40,'GpuLeaseRelease'),
                            ('gpu_lease_poll',41,'GpuLeasePoll')]:
        f=frame.field.add(name=name,number=number,label=1,type=11,
                          type_name='.lu.workspace.v0.'+msg,oneof_index=0)
    pool=descriptor_pool.DescriptorPool();pool.Add(d)
    return message_factory.GetMessageClass(pool.FindMessageTypeByName('lu.workspace.v0.WorkspaceFrame'))


def h(x):return sha256(x).hexdigest()


class Owner:
    """Deliberately uninstalled test-only host oracle."""
    def __init__(self):self.fail=set();self.witness=None;self.record=[]
    def ok(self,name):
        self.record.append(name)
        return name not in self.fail
    def verify_installed_session(self,intent):return self.ok('session')
    def authorize_original_turn(self,intent,action,detail):return self.ok('turn')
    def verify_core_released_vram(self,intent,grant,detail):return self.ok('core-grant')
    def verify_live_core_gpu_lease(self,intent,detail):return self.ok('core-live')
    def verify_native_diffuser_admission(self,intent,detail):return self.ok('nvp-launch')
    def verify_native_scm_gpu_quiescence(self,intent,witness,detail):return self.ok('scm-stop')
    def verify_core_durable_release_ack(self,intent,ack,detail):return self.ok('core-ack')
    def observe_native_gpu_quiescence(self,intent):
        if not self.ok('observe-stop'):raise GpuYieldRefusal('Original worker remains')
        return self.witness
    def verify_no_protected_gpu_worker_launched(self,intent,detail):return self.ok('no-worker')


class GpuLeaseV1Wire(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'protected';self.root.mkdir(mode=0o700)
        self.now=1_800_000_000_000
        self.intent=YieldIntent(
            origin=OriginRefs('workspace-1','conversation-1','turn-1','task-1','op-1'),
            session_ref='core-session-1',core_epoch_ref='core-epoch-1',
            project_id='a'*32,native_job_ref='ltx_'+'b'*24,
            device_ref='gpu-0',desired_free_vram_bytes=8*1024**3,
            duration_ms=600000,deadline_unix_ms=self.now+300000)
        self.frame_class=wire_frame()
        self.codec=LuGpuLeaseV1Codec(self.frame_class,schema_git_blob=LU_GPU_PROTO_BLOB)
        self.owner=Owner()
        self.original=CoreYieldGrant('op-1',self.intent.intent_sha256,
            'core-session-1','core-epoch-1','ltx_'+'b'*24,'gpu-0',
            'core-lease-1','model-gen-1',10*1024**3,self.now,self.now+250000,
            h(b'installed-Core-GPU-release-receipt'))
        self.witness=NativeGpuQuiescence('op-1','ltx_'+'b'*24,'gpu-0','core-lease-1',
            True,True,True,True,0,h(b'native-SCM-Job-stop-receipt'))
        self.owner.witness=self.witness
        self.trust={'peer':True,'feature':True,'grant':True,'ack':True,'stop':True}
        self.exchange_calls=[]; self.reply_mutation={}
        def exchange(frame):
            self.exchange_calls.append(frame.WhichOneof('body'))
            reply=self.frame_class(protocol_major=frame.protocol_major,
                protocol_minor=frame.protocol_minor,
                request_id=frame.request_id,session_ref=frame.session_ref)
            outcome=reply.gpu_lease_outcome
            outcome.operation_ref=self.intent.origin.operation_ref
            outcome.decision=1
            outcome.lease_ref='core-lease-1'
            if frame.WhichOneof('body')=='gpu_lease_request':
                outcome.phase=2;outcome.measured_available_vram_bytes=10*1024**3
            else:outcome.phase=5
            outcome.reason_code='GPU_READY'
            for key,value in self.reply_mutation.items():
                if key in ('request_id','session_ref','protocol_minor','protocol_major'):
                    setattr(reply,key,value)
                else:setattr(outcome,key,value)
            return reply
        def attest_grant(intent,claim):return self.original if self.trust['grant'] else None
        def attest_ack(intent,witness,grant,release_ref,claim):
            if not self.trust['ack']:return None
            return CoreReleaseAck(intent.origin.operation_ref,grant.lease_ref,
                intent.core_epoch_ref,release_ref,witness.durable_native_receipt_sha256,
                h(b'Core-durable-release-ack'),'READY')
        self.port=NativeLuGpuLeaseV1Gateway(self.frame_class,
            schema_git_blob=LU_GPU_PROTO_BLOB,native_exchange=exchange,
            verify_installed_lu_peer=lambda i:self.trust['peer'],
            verify_negotiated_feature=lambda i,f:f=='gpu-lease-v1' and self.trust['feature'],
            attest_core_grant=attest_grant,attest_core_release=attest_ack,
            native_worker_stop_ref=lambda i,w:
                'nvp-scm:'+w.durable_native_receipt_sha256 if self.trust['stop'] else '')
        self.journal=GpuYieldJournal(self.root,storage_guard=lambda r:r==self.root,
                                     clock_ms=lambda:self.now)
        self.flow=NvpGpuYieldCoordinator(self.journal,native_owner=self.owner,core_port=self.port)
        self.auth=lambda *_:True

    def test_lu_async_unload_and_reload_poll_original_lease(self):
        """New Lu async queue is DEFERRED, never a grant or a retry."""
        initial=self.port._exchange
        self.port._wait=lambda seconds:None
        events=[]
        def queued(frame):
            kind=frame.WhichOneof('body');events.append(kind)
            if kind in ('gpu_lease_request','gpu_lease_release'):
                response=initial(frame)
                value=response.gpu_lease_outcome
                value.decision=2
                value.phase=1 if kind=='gpu_lease_request' else 3
                value.ClearField('measured_available_vram_bytes')
                return response
            if kind=='gpu_lease_poll':
                poll=frame.gpu_lease_poll
                self.assertEqual(poll.origin.operation_ref,self.intent.origin.operation_ref)
                self.assertEqual(poll.lease_ref,'core-lease-1')
                self.assertIn(poll.transition,(1,2))
                reply=initial(frame)
                value=reply.gpu_lease_outcome
                value.phase=2 if poll.transition==1 else 5
                if poll.transition==1:
                    value.measured_available_vram_bytes=10*1024**3
                return reply
            return initial(frame)
        self.port._exchange=queued
        grant=self.flow.request(self.intent)
        self.assertEqual(grant.lease_ref,'core-lease-1')
        self.assertEqual(events[:2],['gpu_lease_request','gpu_lease_poll'])
        result=self.flow.run_admitted_protected_diffusion(
            self.intent,run_worker=lambda:'picture-unapproved')
        self.assertEqual(result,'picture-unapproved')
        self.assertEqual(events[-2:],['gpu_lease_release','gpu_lease_poll'])
        self.assertEqual(self.journal.inspect('op-1',authorize=self.auth)['state'],'RELEASED')

    def test_never_launch_on_indefinitely_deferred_original_job(self):
        self.port._wait=lambda _:None
        self.port.max_poll_attempts=2
        original=self.port._exchange
        def pending(frame):
            outcome=original(frame)
            value=outcome.gpu_lease_outcome
            value.decision=2;value.phase=1
            value.lease_ref='core-lease-1'
            value.ClearField('measured_available_vram_bytes')
            return outcome
        self.port._exchange=pending
        with self.assertRaises(GpuYieldRefusal):self.flow.request(self.intent)
        with self.assertRaises(GpuYieldRefusal):self.flow.begin_diffusion(self.intent)
        self.assertEqual(self.journal.inspect('op-1',authorize=self.auth)['state'],'REQUEST_SENT')

    def test_poll_wrong_lease_is_never_a_source_of_positive_authority(self):
        self.port._wait=lambda _:None
        original=self.port._exchange
        def foreign(frame):
            outcome=original(frame)
            value=outcome.gpu_lease_outcome
            if frame.WhichOneof('body')=='gpu_lease_request':
                value.decision=2;value.phase=1
                value.ClearField('measured_available_vram_bytes')
            else:value.lease_ref='gpu-foreign'
            return outcome
        self.port._exchange=foreign
        with self.assertRaises(GpuYieldRefusal):self.flow.request(self.intent)
        with self.assertRaises(GpuYieldRefusal):self.flow.begin_diffusion(self.intent)

    def test_exact_wire_fields_and_no_foreign_inference_lease(self):
        frame=self.codec.acquire(self.intent,request_id='req-1')
        self.assertEqual(frame.WhichOneof('body'),'gpu_lease_request')
        self.assertEqual(frame.gpu_lease_request.origin.operation_ref,'op-1')
        self.assertEqual(frame.gpu_lease_request.device_ref,'gpu-0')
        self.assertEqual(frame.gpu_lease_request.required_free_vram_bytes,8*1024**3)
        self.assertEqual(frame.gpu_lease_request.max_duration_ms,600000)
        clear=self.codec.release(self.intent,lease_ref='core-lease-1',
            worker_stop_ref='nvp-scm:'+self.witness.durable_native_receipt_sha256,
            request_id='req-2')
        self.assertEqual(clear.WhichOneof('body'),'gpu_lease_release')
        self.assertEqual(clear.gpu_lease_release.lease_ref,'core-lease-1')
        self.assertEqual(clear.gpu_lease_release.origin.user_turn_ref,'turn-1')

    def test_pinned_git_schema_required_and_no_old_proto(self):
        with self.assertRaises(GpuYieldRefusal):LuGpuLeaseV1Codec(self.frame_class,schema_git_blob='0'*40)
        from tests.test_nvp_int_lu_01e_gpu import legacy_projected_frame
        with self.assertRaises(GpuYieldRefusal):LuGpuLeaseV1Codec(legacy_projected_frame(),schema_git_blob=LU_GPU_PROTO_BLOB)

    def test_no_feature_or_peer_must_not_send_any_request(self):
        for key in ('peer','feature'):
            with self.subTest(key=key):
                self.trust[key]=False
                with self.assertRaises(GpuYieldRefusal):self.flow.request(self.intent)
                self.assertEqual(self.exchange_calls,[])
                self.trust[key]=True
        with self.assertRaises(GpuYieldRefusal):
            self.journal.inspect('op-1',authorize=self.auth)

    def test_valid_wire_grant_attested_then_native_worker_then_durable_ack(self):
        grant=self.flow.request(self.intent)
        self.assertEqual(grant,self.original)
        self.assertEqual(self.journal.inspect('op-1',authorize=self.auth)['state'],'GRANTED')
        events=[]
        result=self.flow.run_admitted_protected_diffusion(
            self.intent,run_worker=lambda:events.append('NVP-LTX') or 'picture-pending-review')
        self.assertEqual(result,'picture-pending-review')
        self.assertEqual(events,['NVP-LTX'])
        self.assertEqual(self.exchange_calls,['gpu_lease_request','gpu_lease_release'])
        self.assertEqual(self.journal.inspect('op-1',authorize=self.auth)['state'],'RELEASED')
        self.assertEqual(self.journal.recover_after_restart(authorize_owner=self.auth),[])
        self.assertIn('scm-stop',self.owner.record)
        self.assertIn('core-ack',self.owner.record)

    def test_untrusted_proto_grant_needs_host_attestor_no_worker(self):
        self.trust['grant']=False
        with self.assertRaises(GpuYieldRefusal):self.flow.request(self.intent)
        self.assertEqual(self.journal.inspect('op-1',authorize=self.auth)['state'],'REQUEST_SENT')
        with self.assertRaises(GpuYieldRefusal):self.flow.begin_diffusion(self.intent)

    def test_denied_deferred_wrong_phase_missing_lease_and_undersized_capacity(self):
        for mutation in ({'decision':2},{'decision':3},{'phase':1},
                          {'lease_ref':''},{'measured_available_vram_bytes':1},
                          {'operation_ref':'other'}):
            with self.subTest(mutation=mutation):
                self.reply_mutation=mutation
                with self.assertRaises(GpuYieldRefusal):self.port.request_cooperative_gpu_yield(self.intent)
                self.assertEqual(self.owner.record,[])
        self.reply_mutation={}

    def test_wrong_reply_session_request_version_and_body_fail(self):
        for edits in ({'request_id':'forged'}, {'session_ref':'stolen'},
                      {'protocol_major':2}, {'protocol_minor':99}):
            with self.subTest(edits=edits):
                self.reply_mutation=edits
                with self.assertRaises(GpuYieldRefusal):self.port.request_cooperative_gpu_yield(self.intent)
        self.reply_mutation={}

    def test_host_receipt_must_bind_exact_grant_and_core_epoch(self):
        for edits in ({'lease_ref':'other'},{'intent_sha256':h(b'wrong')},
                      {'core_epoch_ref':'other'},{'native_job_ref':'ltx_'+'c'*24},
                      {'observed_free_vram_bytes':9*1024**3}):
            with self.subTest(edits=edits):
                self.original=replace(self.original,**edits)
                with self.assertRaises(GpuYieldRefusal):self.port.request_cooperative_gpu_yield(self.intent)
                # restore exact known-good receipt, never recompute from forged claims
                self.original=CoreYieldGrant('op-1',self.intent.intent_sha256,
                    'core-session-1','core-epoch-1','ltx_'+'b'*24,'gpu-0',
                    'core-lease-1','model-gen-1',10*1024**3,self.now,self.now+250000,
                    h(b'installed-Core-GPU-release-receipt'))

    def test_no_all_clear_without_verified_worker_quiescence(self):
        self.flow.request(self.intent)
        self.flow.begin_diffusion(self.intent)
        self.flow.worker_stopped(self.intent)
        self.owner.fail.add('scm-stop')
        with self.assertRaises(GpuYieldRefusal):
            self.flow.after_verified_shutdown(self.intent,self.witness)
        self.assertEqual(self.exchange_calls,['gpu_lease_request'])
        with self.assertRaises(GpuYieldRefusal):self.flow.send_all_clear(self.intent)

    def test_core_release_phase_does_not_forge_durable_ack(self):
        self.flow.request(self.intent);self.flow.begin_diffusion(self.intent)
        self.flow.worker_stopped(self.intent)
        self.flow.after_verified_shutdown(self.intent,self.witness)
        self.trust['ack']=False
        with self.assertRaises(GpuYieldRefusal):self.flow.send_all_clear(self.intent)
        self.assertEqual(self.exchange_calls,['gpu_lease_request','gpu_lease_release'])
        self.assertEqual(self.journal.inspect('op-1',authorize=self.auth)['state'],'ALL_CLEAR_SENT')

    def test_bad_worker_stop_locator_blocks_release_before_wire(self):
        self.flow.request(self.intent);self.flow.begin_diffusion(self.intent)
        self.flow.worker_stopped(self.intent)
        self.flow.after_verified_shutdown(self.intent,self.witness)
        self.trust['stop']=False
        with self.assertRaises(GpuYieldRefusal):self.flow.send_all_clear(self.intent)
        self.assertEqual(self.exchange_calls,['gpu_lease_request'])

    def test_transport_revocation_after_exchange_refuses_instead_of_grant(self):
        original=self.port._exchange
        def disconnect(frame):
            value=original(frame)
            self.trust['peer']=False
            return value
        self.port._exchange=disconnect
        with self.assertRaises(GpuYieldRefusal):self.flow.request(self.intent)
        self.assertEqual(self.journal.inspect('op-1',authorize=self.auth)['state'],'REQUEST_SENT')

    def test_duplicate_request_cannot_dispatch_twice(self):
        self.flow.request(self.intent)
        with self.assertRaises(GpuYieldRefusal):self.flow.request(self.intent)
        self.assertEqual(self.exchange_calls,['gpu_lease_request'])

    def test_restart_uncertain_has_no_automatic_release(self):
        self.flow.request(self.intent)
        reopened=GpuYieldJournal(self.root,storage_guard=lambda r:r==self.root,
                                 clock_ms=lambda:self.now)
        self.assertEqual(reopened.recover_after_restart(authorize_owner=self.auth),['op-1'])
        with self.assertRaises(GpuYieldRefusal):reopened.mark_all_clear_sent('op-1',authorize_owner=self.auth)
        self.assertEqual(self.exchange_calls,['gpu_lease_request'])


if __name__=='__main__':unittest.main()

# A Linux/source-only process must never instantiate a purported Windows
# production supervisor, even with a forged module implementing every method.
class WindowsNativeBindingDenials(unittest.TestCase):
    @unittest.skipIf(__import__('sys').platform == 'win32',
                     'Real Windows type and native signer checks run on installed host')
    def test_source_only_runtime_cannot_claim_installed_supervisor(self):
        from backend.nvp_lu_windows_gpu_binding import open_installed_windows_gpu_yield_binding
        with self.assertRaises(GpuYieldRefusal):
            open_installed_windows_gpu_yield_binding(object(), object(),
                core_port=object(),native_owner=object())

class NativeWorkerIdentityPostconditions(unittest.TestCase):
    def test_no_ltx_worker_switch_after_lu_model_unload(self):
        from backend.nvp_lu_windows_gpu_binding import require_original_native_gpu_job_result
        intent=YieldIntent(
            origin=OriginRefs('ws','conv','turn','task','operation'),
            session_ref='session',core_epoch_ref='epoch',project_id='a'*32,
            native_job_ref='ltx_'+'a'*24,device_ref='gpu-0',
            desired_free_vram_bytes=2*1024**3,duration_ms=300000,
            deadline_unix_ms=1800000400000)
        genuine={'job_id':intent.native_job_ref,'state':'PICTURE_VERIFIED_UNAPPROVED'}
        self.assertIs(require_original_native_gpu_job_result(intent,genuine),genuine)
        for invalid in ({'job_id':'ltx_'+'b'*24},
                        {'job_id':intent.native_job_ref+'-other'},
                        {'state':'COMPLETE'},'ltx','fake'):
            with self.subTest(invalid=invalid), self.assertRaises(GpuYieldRefusal):
                require_original_native_gpu_job_result(intent,invalid)
