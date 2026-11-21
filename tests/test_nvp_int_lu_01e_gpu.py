"""Source-only NVP GPU yield tests. ALL positive Core/SCM witnesses are fixtures."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from backend.nvp_lu_operation_journal import OriginRefs
from backend.nvp_lu_gpu_yield import (
    CoreReleaseAck, CoreYieldGrant, GpuYieldJournal, GpuYieldRefusal,
    LegacyResourceRequestCodec, NativeGpuQuiescence, NativeLuAdvisoryGateway, NvpGpuYieldCoordinator,
    UninstalledCoreGpuYieldPort, YieldIntent,
)


def digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def legacy_projected_frame():
    """Test-only Protobuf v1.2 field-number projection; NOT live Lu Core SDK."""
    d = descriptor_pb2.FileDescriptorProto(name='gpu_legacy_fixture.proto', package='lu.workspace.v0', syntax='proto3')
    origin = d.message_type.add(name='OriginRefs')
    for i, name in enumerate(('workspace_ref','conversation_ref','user_turn_ref','task_ref','operation_ref'), 1):
        f=origin.field.add(name=name,number=i,label=1,type=9)
    req=d.message_type.add(name='ResourceTransitionRequest')
    f=req.field.add(name='origin',number=1,label=1,type=11,type_name='.lu.workspace.v0.OriginRefs')
    f=req.field.add(name='action',number=2,label=1,type=5)
    f=req.field.add(name='desired_free_vram_bytes',number=4,label=1,type=4)
    dec=d.message_type.add(name='ResourceTransitionDecision')
    f=dec.field.add(name='operation_ref',number=1,label=1,type=9)
    f=dec.field.add(name='decision',number=2,label=1,type=5)
    frame=d.message_type.add(name='WorkspaceFrame')
    for i,name,t in ((1,'protocol_major',13),(2,'protocol_minor',13),(3,'request_id',9),(4,'session_ref',9)):
        f=frame.field.add(name=name,number=i,label=1,type=t)
    body=frame.oneof_decl.add(name='body')
    for i,name,message in ((21,'resource_request','ResourceTransitionRequest'),(22,'resource_decision','ResourceTransitionDecision')):
        f=frame.field.add(name=name,number=i,label=1,type=11,type_name='.lu.workspace.v0.'+message,oneof_index=0)
    pool=descriptor_pool.DescriptorPool()
    pool.Add(d)
    return message_factory.GetMessageClass(pool.FindMessageTypeByName('lu.workspace.v0.WorkspaceFrame'))


class TestOwner:
    def __init__(self):
        self.fail=set()
        self.actions=[]
    def _allow(self, name, action):
        self.actions.append((name, action))
        return name not in self.fail
    def verify_installed_session(self, intent): return self._allow('session','verify')
    def authorize_original_turn(self, intent, action, detail): return self._allow('turn',action)
    def verify_core_released_vram(self, intent, grant, detail): return self._allow('lu-grant','release')
    def verify_live_core_gpu_lease(self, intent, detail): return self._allow('lu-live','admit')
    def verify_native_diffuser_admission(self, intent, detail): return self._allow('nvp-start','launch')
    def verify_native_scm_gpu_quiescence(self, intent, witness, detail): return self._allow('scm','quiescence')
    def verify_core_durable_release_ack(self, intent, ack, detail): return self._allow('lu-ack','release')
    def verify_no_protected_gpu_worker_launched(self, intent, detail): return self._allow('no-worker','no-launch')
    def observe_native_gpu_quiescence(self, intent):
        if 'scm' in self.fail:
            raise GpuYieldRefusal('Native GPU job not fully quiescent')
        return self.expected_witness


class TestCorePort:
    def __init__(self): self.sent=[]
    def ready_for_safe_roundtrip(self,intent): return True  # TEST FIXTURE ONLY
    def request_cooperative_gpu_yield(self,intent):
        self.sent.append(('request',intent.origin.operation_ref))
        return 'CORE_ADVISORY_NOT_GRANT'
    def send_verified_gpu_all_clear(self,intent,evidence,release_ref):
        self.sent.append(('all-clear',release_ref,evidence['quiescence']['durable_native_receipt_sha256']))
        return 'AWAITING_LU_DURABLE_ACK'


class GpuYieldLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'private';self.root.mkdir(mode=0o700)
        self.now=1_800_000_000_000
        self.intent=YieldIntent(
            origin=OriginRefs('nvp-workspace','conversation','original-user-turn','task-1','gpu-op-1'),
            session_ref='session-1',core_epoch_ref='core-epoch-1',
            project_id='a'*32,native_job_ref='ltx_'+'b'*24,
            device_ref='pci:0000:0a:00.0', desired_free_vram_bytes=15*1024**3,
            duration_ms=600_000,deadline_unix_ms=self.now+300_000)
        self.journal=GpuYieldJournal(self.root,storage_guard=lambda p:p==self.root,
                                     clock_ms=lambda:self.now)
        self.owner=TestOwner(); self.port=TestCorePort()
        self.flow=NvpGpuYieldCoordinator(self.journal,native_owner=self.owner,core_port=self.port)
        self.auth=lambda *_:True
        self.grant=CoreYieldGrant(
            operation_ref='gpu-op-1', intent_sha256=self.intent.intent_sha256,
            session_ref=self.intent.session_ref,core_epoch_ref=self.intent.core_epoch_ref,
            native_job_ref=self.intent.native_job_ref,device_ref=self.intent.device_ref,
            lease_ref='lu-yield-1',model_generation_ref='model-gen-12',
            observed_free_vram_bytes=18*1024**3,
            sampled_unix_ms=self.now,expires_unix_ms=self.now+400_000,
            durable_core_receipt_sha256=digest(b'lu-core-signed-release'))
        self.witness=NativeGpuQuiescence(
            operation_ref='gpu-op-1',native_job_ref=self.intent.native_job_ref,
            device_ref=self.intent.device_ref,lease_ref='lu-yield-1',
            worker_tree_reaped=True,gpu_contexts_quiescent=True,
            release_fence_closed=True,scm_custody_verified=True,active_gpu_workers=0,
            durable_native_receipt_sha256=digest(b'scm-gpu-quiescent'))
        self.owner.expected_witness=self.witness

    def request_grant(self):
        self.assertEqual(self.flow.request(self.intent),'CORE_ADVISORY_NOT_GRANT')
        self.flow.receive_grant(self.intent,self.grant)

    def start(self):
        self.request_grant()
        self.flow.begin_diffusion(self.intent)

    def ready(self):
        self.start()
        self.flow.worker_stopped(self.intent)
        self.flow.after_verified_shutdown(self.intent,self.witness)

    def ack(self,release_ref):
        return CoreReleaseAck('gpu-op-1','lu-yield-1','core-epoch-1',release_ref,
                              self.witness.durable_native_receipt_sha256,
                              digest(b'core-ack'), 'PENDING')

    def test_full_verified_flow_uses_no_local_model_control(self):
        self.ready()
        self.assertEqual(self.flow.send_all_clear(self.intent),'AWAITING_LU_DURABLE_ACK')
        release=self.journal.inspect('gpu-op-1',authorize=self.auth)['release_ref']
        out=self.flow.receive_release_ack(self.intent,self.ack(release))
        self.assertEqual(out['state'],'RELEASED')
        self.assertEqual(len(self.port.sent),2)
        self.assertEqual(self.port.sent[1][0],'all-clear')
        self.assertEqual(self.journal.recover_after_restart(authorize_owner=self.auth),[])
        self.assertTrue(any(x[0]=='scm' for x in self.owner.actions))
        self.assertTrue(any(x[0]=='lu-ack' for x in self.owner.actions))

    def test_no_core_installed_refuses_without_start(self):
        flow=NvpGpuYieldCoordinator(self.journal,native_owner=self.owner)
        with self.assertRaises(GpuYieldRefusal): flow.request(self.intent)
        with self.assertRaises(GpuYieldRefusal): flow.begin_diffusion(self.intent)
        with self.assertRaises(GpuYieldRefusal): self.journal.inspect('gpu-op-1',authorize=self.auth)

    def test_lu_allowed_advisory_does_not_admit_diffusion(self):
        self.flow.request(self.intent)
        self.journal.record_legacy_decision('gpu-op-1',allowed=True,verify_core_decision=self.auth)
        with self.assertRaises(GpuYieldRefusal): self.flow.begin_diffusion(self.intent)
        self.assertEqual(self.journal.inspect('gpu-op-1',authorize=self.auth)['state'],'WAITING_CORE')

    def test_real_wire_advisory_only_no_lease_or_model_control(self):
        cls=legacy_projected_frame()
        requests=[]
        def exchange(req):
            requests.append(req)
            response=cls(protocol_major=1,protocol_minor=2,
                         request_id=req.request_id,session_ref=req.session_ref)
            response.resource_decision.operation_ref=req.resource_request.origin.operation_ref
            response.resource_decision.decision=1
            return response
        port=NativeLuAdvisoryGateway(cls,native_exchange=exchange,
                            verify_installed_lu_peer=lambda intent:True)
        flow=NvpGpuYieldCoordinator(self.journal,native_owner=self.owner,core_port=port)
        with self.assertRaises(GpuYieldRefusal): flow.request(self.intent)
        self.assertEqual(requests,[])  # No half-protocol unload stranded in Core.
        with self.assertRaises(GpuYieldRefusal): self.journal.inspect('gpu-op-1',authorize=self.auth)
        self.assertEqual(port.query_capacity(self.intent),'ADVISORY_ONLY')
        self.assertEqual(requests[0].resource_request.action,4)  # read-only
        with self.assertRaises(GpuYieldRefusal):flow.begin_diffusion(self.intent)
        with self.assertRaises(GpuYieldRefusal):port.send_verified_gpu_all_clear(self.intent,{},'ref')

    def test_advisory_gateway_revoked_or_foreign_session_refuses(self):
        cls=legacy_projected_frame()
        calls=[]
        def exchange(req):
            calls.append('exchange')
            reply=cls(protocol_major=1,protocol_minor=2,request_id=req.request_id,session_ref='wrong')
            reply.resource_decision.operation_ref=req.resource_request.origin.operation_ref
            reply.resource_decision.decision=1
            return reply
        port=NativeLuAdvisoryGateway(cls,native_exchange=exchange,
                    verify_installed_lu_peer=lambda intent:True)
        with self.assertRaises(GpuYieldRefusal):port.query_capacity(self.intent)
        self.assertEqual(calls,['exchange'])
        denied=NativeLuAdvisoryGateway(cls,native_exchange=exchange,
                    verify_installed_lu_peer=lambda intent:False)
        with self.assertRaises(GpuYieldRefusal):denied.query_capacity(self.intent)
        self.assertEqual(calls,['exchange'])

    def test_core_request_send_failure_leaves_durable_no_retry_fence(self):
        class LostResponse(TestCorePort):
            def request_cooperative_gpu_yield(self,intent):
                super().request_cooperative_gpu_yield(intent)
                raise ConnectionError('Lu session disconnected after dispatch')
        self.flow=NvpGpuYieldCoordinator(self.journal,native_owner=self.owner,
                                         core_port=LostResponse())
        with self.assertRaises(ConnectionError):self.flow.request(self.intent)
        self.assertEqual(self.journal.inspect('gpu-op-1',authorize=self.auth)['state'],'REQUEST_SENT')
        with self.assertRaises(GpuYieldRefusal):self.flow.request(self.intent)
        self.assertEqual(self.journal.recover_after_restart(authorize_owner=self.auth),['gpu-op-1'])
        with self.assertRaises(GpuYieldRefusal):self.flow.begin_diffusion(self.intent)

    def test_lu_advisory_wrong_request_and_version_are_denied(self):
        cls=legacy_projected_frame(); codec=LegacyResourceRequestCodec(cls)
        frame=cls(protocol_major=1,protocol_minor=2,request_id='req-1',session_ref='session-1')
        frame.resource_decision.operation_ref='gpu-op-1'
        frame.resource_decision.decision=1
        for field,value in [('protocol_minor',0),('request_id','wrong'),
                            ('session_ref','wrong'),('protocol_major',2)]:
            bad=cls();bad.CopyFrom(frame);setattr(bad,field,value)
            with self.subTest(field=field),self.assertRaises(GpuYieldRefusal):
                codec.observe_decision(bad,self.intent,request_id='req-1')

    def test_legacy_denial_is_terminal_refused(self):
        self.flow.request(self.intent)
        self.journal.record_legacy_decision('gpu-op-1',allowed=False,verify_core_decision=self.auth)
        with self.assertRaises(GpuYieldRefusal): self.flow.receive_grant(self.intent,self.grant)
        self.assertEqual(self.journal.inspect('gpu-op-1',authorize=self.auth)['state'],'REFUSED')

    def test_grant_missing_or_forged_is_refused(self):
        self.flow.request(self.intent)
        for mutation in [
            {'intent_sha256':digest(b'other')}, {'session_ref':'other-session'},
            {'core_epoch_ref':'other-epoch'}, {'native_job_ref':'ltx_'+'c'*24},
            {'device_ref':'other-device'}, {'operation_ref':'other-op'},
            {'observed_free_vram_bytes':1}, {'expires_unix_ms':self.now-1},
            {'expires_unix_ms':self.now+700_000},
            {'sampled_unix_ms':self.now+10_000},
            {'sampled_unix_ms':self.now-1},
        ]:
            with self.subTest(mutation=mutation), self.assertRaises(GpuYieldRefusal):
                self.flow.receive_grant(self.intent,replace(self.grant,**mutation))
        self.assertEqual(self.journal.inspect('gpu-op-1',authorize=self.auth)['state'],'REQUEST_SENT')

    def test_no_positive_trust_callback_for_grant(self):
        self.flow.request(self.intent)
        for blocked in ('session','turn','lu-grant'):
            self.owner.fail.add(blocked)
            with self.subTest(blocked=blocked),self.assertRaises(GpuYieldRefusal):
                self.flow.receive_grant(self.intent,self.grant)
            self.owner.fail.remove(blocked)

    def test_verified_grant_cannot_be_reused_for_new_job(self):
        self.request_grant()
        new=replace(self.intent,origin=replace(self.intent.origin,operation_ref='gpu-op-2'),
                    native_job_ref='ltx_'+'c'*24)
        self.flow.request(new)
        with self.assertRaises(GpuYieldRefusal):
            self.flow.receive_grant(new,replace(self.grant,operation_ref='gpu-op-2',
                                intent_sha256=new.intent_sha256,native_job_ref=new.native_job_ref))

    def test_expiry_denies_new_worker_even_after_grant(self):
        self.request_grant()
        self.now+=400_001
        with self.assertRaises(GpuYieldRefusal): self.flow.begin_diffusion(self.intent)

    def test_native_worker_admission_and_core_lease_are_mandatory(self):
        self.request_grant()
        for blocked in ('lu-live','nvp-start','session','turn'):
            self.owner.fail.add(blocked)
            with self.subTest(blocked=blocked),self.assertRaises(GpuYieldRefusal):
                self.flow.begin_diffusion(self.intent)
            self.owner.fail.remove(blocked)
        self.assertEqual(self.journal.inspect('gpu-op-1',authorize=self.auth)['state'],'GRANTED')

    def test_cannot_clear_before_worker_reaped(self):
        self.start()
        with self.assertRaises(GpuYieldRefusal): self.flow.send_all_clear(self.intent)
        with self.assertRaises(GpuYieldRefusal): self.flow.after_verified_shutdown(self.intent,self.witness)
        self.flow.worker_stopped(self.intent)
        for edit in [
            {'native_job_ref':'ltx_'+'c'*24}, {'device_ref':'wrong-device'},
            {'lease_ref':'other-lease'}, {'worker_tree_reaped':False},
            {'gpu_contexts_quiescent':False}, {'release_fence_closed':False},
            {'scm_custody_verified':False}, {'active_gpu_workers':1},
        ]:
            with self.subTest(edit=edit), self.assertRaises(GpuYieldRefusal):
                self.flow.after_verified_shutdown(self.intent,replace(self.witness,**edit))
        with self.assertRaises(GpuYieldRefusal): self.flow.send_all_clear(self.intent)

    def test_no_scm_attestation_no_release(self):
        self.start(); self.flow.worker_stopped(self.intent)
        self.owner.fail.add('scm')
        with self.assertRaises(GpuYieldRefusal): self.flow.after_verified_shutdown(self.intent,self.witness)
        with self.assertRaises(GpuYieldRefusal): self.flow.send_all_clear(self.intent)

    def test_release_ack_requires_exact_lease_nonce_epoch_and_native_receipt(self):
        self.ready(); self.flow.send_all_clear(self.intent)
        ref=self.journal.inspect('gpu-op-1',authorize=self.auth)['release_ref']
        for mutation in [
            {'lease_ref':'other-lease'}, {'core_epoch_ref':'wrong-epoch'},
            {'release_ref':'wrong-nonce'}, {'native_receipt_sha256':digest(b'other')},
        ]:
            with self.subTest(mutation=mutation), self.assertRaises(GpuYieldRefusal):
                self.flow.receive_release_ack(self.intent,replace(self.ack(ref),**mutation))
        self.owner.fail.add('lu-ack')
        with self.assertRaises(GpuYieldRefusal): self.flow.receive_release_ack(self.intent,self.ack(ref))
        self.owner.fail.remove('lu-ack')
        self.assertEqual(self.flow.receive_release_ack(self.intent,self.ack(ref))['state'],'RELEASED')
        self.assertEqual(self.flow.receive_release_ack(self.intent,self.ack(ref))['state'],'RELEASED')
        with self.assertRaises(GpuYieldRefusal):
            self.flow.receive_release_ack(self.intent,replace(self.ack(ref),reload_state='READY'))

    def test_repeated_request_never_resends_or_changes_scope(self):
        self.flow.request(self.intent)
        with self.assertRaises(GpuYieldRefusal): self.flow.request(self.intent)
        with self.assertRaises(GpuYieldRefusal):
            self.journal.prepare(replace(self.intent,device_ref='other'),authorize=self.auth)
        self.assertEqual(len(self.port.sent),1)

    def test_restart_marks_uncertain_and_never_sends_all_clear(self):
        self.start()
        reopened=GpuYieldJournal(self.root,storage_guard=lambda p:p==self.root,clock_ms=lambda:self.now)
        self.assertEqual(reopened.recover_after_restart(authorize_owner=self.auth),['gpu-op-1'])
        self.assertEqual(reopened.inspect('gpu-op-1',authorize=self.auth)['state'],'UNCERTAIN')
        with self.assertRaises(GpuYieldRefusal):
            reopened.begin_processing(self.intent,verify_live_core_lease=self.auth,
                                      verify_nvp_native_launch=self.auth)
        with self.assertRaises(GpuYieldRefusal):
            reopened.mark_all_clear_sent('gpu-op-1',authorize_owner=self.auth)
        self.assertEqual(self.port.sent,[('request','gpu-op-1')])

    def test_restart_after_actual_all_clear_can_reconcile_exact_ack(self):
        self.ready();self.flow.send_all_clear(self.intent)
        ref=self.journal.inspect('gpu-op-1',authorize=self.auth)['release_ref']
        self.journal.recover_after_restart(authorize_owner=self.auth)
        self.assertEqual(self.flow.receive_release_ack(self.intent,self.ack(ref))['state'],'RELEASED')

    def test_owner_revocation_and_disk_guard_fail_closed(self):
        self.owner.fail.add('session')
        with self.assertRaises(GpuYieldRefusal): self.flow.request(self.intent)
        self.owner.fail.clear()
        self.flow.request(self.intent)
        self.journal._storage_guard=lambda _:False
        with self.assertRaises(GpuYieldRefusal): self.journal.inspect('gpu-op-1',authorize=self.auth)

    def test_no_transition_can_automatically_reload_lu_model(self):
        forbidden=[n for n in dir(self.flow) if 'reload' in n or 'unload_model' in n or 'kill_lu' in n]
        self.assertEqual(forbidden,[])

    def test_granted_but_never_launched_can_release_only_after_native_no_worker_proof(self):
        self.request_grant()
        self.owner.fail.add('no-worker')
        with self.assertRaises(GpuYieldRefusal): self.flow.cancel_before_launch(self.intent)
        self.owner.fail.remove('no-worker')
        self.flow.cancel_before_launch(self.intent)
        self.flow.after_verified_shutdown(self.intent,self.witness)
        self.assertEqual(self.flow.send_all_clear(self.intent),'AWAITING_LU_DURABLE_ACK')
        self.assertEqual(self.journal.inspect('gpu-op-1',authorize=self.auth)['state'],'ALL_CLEAR_SENT')

    def test_integrated_worker_runs_only_after_verified_grant_and_all_clear_waits_for_ack(self):
        events=[]
        with self.assertRaises(GpuYieldRefusal):
            self.flow.run_admitted_protected_diffusion(self.intent,run_worker=lambda:events.append('render'))
        self.assertEqual(events,[])
        self.request_grant()
        def protected_run():
            events.append('native-ltx-run')
            return {'picture':'awaiting filmmaker review'}
        result=self.flow.run_admitted_protected_diffusion(self.intent,run_worker=protected_run)
        self.assertEqual(events,['native-ltx-run'])
        self.assertEqual(result['picture'],'awaiting filmmaker review')
        self.assertEqual(self.journal.inspect('gpu-op-1',authorize=self.auth)['state'],'ALL_CLEAR_SENT')
        self.assertEqual(self.port.sent[-1][0],'all-clear')

    def test_integrated_worker_success_with_no_os_evidence_must_not_send_all_clear(self):
        self.request_grant(); self.owner.fail.add('scm')
        with self.assertRaises(GpuYieldRefusal):
            self.flow.run_admitted_protected_diffusion(self.intent,run_worker=lambda:'render returned')
        self.assertEqual(self.journal.inspect('gpu-op-1',authorize=self.auth)['state'],'QUIESCENCE_PENDING')
        self.assertEqual(len(self.port.sent),1)

    def test_failed_or_cancelled_worker_release_requires_real_os_proof(self):
        self.request_grant()
        with self.assertRaisesRegex(RuntimeError,'protected worker failed'):
            self.flow.run_admitted_protected_diffusion(self.intent,
                run_worker=lambda: (_ for _ in ()).throw(RuntimeError('protected worker failed')))
        self.assertEqual(self.port.sent[-1][0],'all-clear')
        self.assertEqual(self.journal.inspect('gpu-op-1',authorize=self.auth)['state'],'ALL_CLEAR_SENT')

    def test_failure_with_orphaned_gpu_worker_never_sends_all_clear(self):
        self.request_grant();self.owner.fail.add('scm')
        with self.assertRaisesRegex(RuntimeError,'worker orphaned'):
            self.flow.run_admitted_protected_diffusion(self.intent,
                run_worker=lambda: (_ for _ in ()).throw(RuntimeError('worker orphaned')))
        self.assertEqual(self.journal.inspect('gpu-op-1',authorize=self.auth)['state'],'QUIESCENCE_PENDING')
        self.assertEqual(len(self.port.sent),1)

    def test_duplicate_release_ack_still_requires_installed_core_identity(self):
        self.ready();self.flow.send_all_clear(self.intent)
        ref=self.journal.inspect('gpu-op-1',authorize=self.auth)['release_ref']
        self.flow.receive_release_ack(self.intent,self.ack(ref))
        self.owner.fail.add('lu-ack')
        with self.assertRaises(GpuYieldRefusal):self.flow.receive_release_ack(self.intent,self.ack(ref))

    def test_duplicate_original_request_requires_fresh_owner_permission(self):
        self.journal.prepare(self.intent,authorize=self.auth)
        with self.assertRaises(GpuYieldRefusal):
            self.journal.prepare(self.intent,authorize=lambda *_:False)

    def test_nonoriginal_job_and_nonbound_session_refuse(self):
        for changed in [
            {'native_job_ref':'bad'}, {'device_ref':'http://evil?model=foo'},
            {'project_id':'other'}, {'desired_free_vram_bytes':0},
            {'desired_free_vram_bytes':True}, {'duration_ms':0},
            {'origin':None}, {'session_ref':'not valid'},
        ]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                replace(self.intent,**changed)

    def test_exact_lu_legacy_request_is_advisory_only(self):
        cls=legacy_projected_frame();codec=LegacyResourceRequestCodec(cls)
        frame=codec.build_cooperative_unload(self.intent,request_id='req-1')
        self.assertEqual(frame.WhichOneof('body'),'resource_request')
        self.assertEqual(frame.resource_request.action,1)
        self.assertEqual(frame.resource_request.origin.user_turn_ref,'original-user-turn')
        self.assertEqual(frame.resource_request.desired_free_vram_bytes,15*1024**3)
        reply=cls(protocol_major=1,protocol_minor=2,request_id='req-1',session_ref='session-1')
        reply.resource_decision.operation_ref='gpu-op-1'
        reply.resource_decision.decision=1  # Lu allowed cooperative action, not VRAM receipt.
        self.assertEqual(codec.observe_decision(reply,self.intent,request_id='req-1'),'ADVISORY_ONLY')
        reply.resource_decision.decision=2
        self.assertEqual(codec.observe_decision(reply,self.intent,request_id='req-1'),'DENIED')
        reply.session_ref='other'
        with self.assertRaises(GpuYieldRefusal): codec.observe_decision(reply,self.intent,request_id='req-1')


if __name__=='__main__': unittest.main()
