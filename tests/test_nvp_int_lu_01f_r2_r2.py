"""R2-R2 Linux negative/fixture tests; NOT signed installed Windows evidence."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest

from backend.nvp_lu_operation_journal import (
    IPCOperationJournal, JournalRefusal, OriginRefs, OperationSpec,
)
from backend.nvp_lu_scm_picture_receipt import (
    InstalledWindowsScmPictureReceipt, ScmPictureNativeBinding,
    require_picture_binding,
)
from backend.nvp_lu_windows_native_admission import (
    WindowsProtectedIPCJournalOwner, open_installed_windows_ipc_journal,
)


def digest(raw): return sha256(raw).hexdigest()


class NativeReceiptHandoffR2R2(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)/'private'
        root.mkdir(mode=0o700)
        self.now=1_800_000_000_000
        self.journal=IPCOperationJournal(root,storage_guard=lambda p:p==root,
                                         clock_ms=lambda:self.now)
        self.spec=OperationSpec(
            OriginRefs('work','conv','user-turn','task','op-scm-1'),
            'nvp.film.render.shot',1,4,digest(b'input'),digest(b'refs'),
            self.now+30_000,'session','epoch', declared_effects=(4,3))
        self.journal.prepare(self.spec,authorize=lambda *_:True)
        self.claim=self.journal.claim_dispatch('op-scm-1',authorize=lambda *_:True)
        self.native=ScmPictureNativeBinding(
            self.spec.origin.operation_ref,self.claim['dispatch_ref'],
            self.spec.request_sha256,'ltx_'+('a'*24),'b'*32,
            digest(b'plan'),digest(b'picture'),digest(b'bootstrap'),
            digest(b'model'),digest(b'sid'),4242)
        self.kernel={
            'format':'nvp.post01f.scm_owned_kernel_result.v2',
            'scm_owned_job':True,'scm_service_custody_verified':True,
            'kernel_job_tree_reaped':True,'release_fence_closed':True,
            'worker_pid':4242,'appcontainer_sid_sha256':digest(b'sid')}

    def test_dispatch_binding_owner_guard_restart_and_no_retry(self):
        self.assertEqual(self.journal.dispatch_binding('op-scm-1',authorize=lambda *_:True),self.claim)
        with self.assertRaises(JournalRefusal):
            self.journal.dispatch_binding('op-scm-1',authorize=lambda *_:False)
        self.journal.reconcile_after_restart(authorize=lambda *_:True)
        self.assertEqual(self.journal.status('op-scm-1')['state'],'UNCERTAIN')
        self.assertEqual(self.journal.dispatch_binding('op-scm-1',authorize=lambda *_:True),self.claim)
        with self.assertRaises(JournalRefusal):
            self.journal.claim_dispatch('op-scm-1',authorize=lambda *_:True)

    def test_no_dispatch_binding_for_prepared_operation(self):
        spec=replace(self.spec,origin=replace(self.spec.origin,operation_ref='op-prepared'))
        self.journal.prepare(spec,authorize=lambda *_:True)
        with self.assertRaises(JournalRefusal):
            self.journal.dispatch_binding('op-prepared',authorize=lambda *_:True)

    def test_scm_requires_exact_original_dispatch_and_compound_effect(self):
        require_picture_binding(self.spec,self.claim,self.native)
        edits=[{'job_id':'old_'+('a'*24)},
               {'request_sha256':digest(b'other')},
               {'dispatch_ref':'other'},
               {'project_id':'not_a_project'},{'worker_pid':0}]
        for edit in edits:
            with self.subTest(edit=edit), self.assertRaises((JournalRefusal,ValueError)):
                require_picture_binding(self.spec,self.claim,replace(self.native,**edit))
        for edit in [{'capability_id':'nvp.film.edit.export'},
                     {'declared_effects':(3,)},
                     {'declared_effects':(4,)},
                     {'origin':replace(self.spec.origin,user_turn_ref='forged-turn')}]:
            with self.subTest(edit=edit),self.assertRaises((JournalRefusal,ValueError)):
                require_picture_binding(replace(self.spec,**edit),self.claim,self.native)

    def test_invalid_scm_native_identity_before_any_channel(self):
        with self.assertRaises(ValueError):
            replace(self.native,picture_sha256='0'*64)
        with self.assertRaises(ValueError):
            replace(self.native,appcontainer_sid_sha256='bad')
        with self.assertRaises(JournalRefusal):
            replace(self.native,worker_pid=True)

    def fake_gate(self, *, kernel=None, verified=True, approve=True, nonce=True,
                  native=None, owner_live=True):
        class FakeOwner:
            def __init__(self,outer):
                self.outer=outer
                self.native=native or outer.native
                self.live=owner_live
                self.consume=[]
            def require_native_owner(self):return self.live
            def original_spec(self,ref):return self.outer.spec
            def bind_picture_job(self,spec,durable):return self.native
            def kernel_exit_witness(self,binding):return dict(kernel or self.outer.kernel)
            def consume_native_nonce(self,binding,job,once,sha):
                self.consume.append((binding,job,once,sha))
                return nonce
            def approve_terminal(self,spec,binding,kernel,witness):return approve
        owner=FakeOwner(self)
        # Strictly TEST-ONLY: bypass Windows constructor; caller-supplied fake
        # signer MUST NEVER be used by installed code. Tests below validate
        # only the last-mile response/SQLite integration and refusals.
        gate=object.__new__(InstalledWindowsScmPictureReceipt)
        gate._journal=self.journal
        gate._owner=owner
        def fixture_channel(consume_once):
            def response(scope,observed_kernel):
                if not verified:
                    return {'scm_authenticated_receipt_verified':False}
                if not consume_once(scope['job_id'],'nonce',digest(b'signed')):
                    raise JournalRefusal('Simulated nonce refusal')
                return {'scm_authenticated_receipt_verified':True,
                        'scm_service_custody_verified':True,
                        'process_tree_custody_verified':True,
                        'wfp_no_egress_verified':True,'efs_verified':True,
                        'job_id':scope['job_id'],'project_id':scope['project_id'],
                        'worker_pid':observed_kernel['worker_pid'],
                        'plan_sha256':scope['plan_sha256'],
                        'picture_sha256':scope['picture_sha256'],
                        'scm_receipt_sha256':digest(b'signed')}
            return response
        gate._bind_channel=fixture_channel
        return gate,owner

    def test_fixture_only_last_mile_journal_commit(self):
        gate,owner=self.fake_gate()
        result=gate.reconcile_signed_picture('op-scm-1')
        self.assertEqual(result['state'],'TERMINAL')
        self.assertEqual(result['terminal_state'],'APPLIED')
        self.assertEqual(result['receipt_sha256'],digest(b'signed'))
        self.assertEqual(len(owner.consume),1)
        self.assertEqual(len([x for x in self.journal.events('op-scm-1')
                     if x['kind']=='HOST_TERMINAL_VERIFIED']),1)

    def test_fixture_deny_native_kernel_scope_and_owner(self):
        for kwargs in [dict(kernel={**self.kernel,'worker_pid':99}),
                       dict(kernel={**self.kernel,'kernel_job_tree_reaped':False}),
                       dict(kernel={**self.kernel,'scm_owned_job':False}),
                       dict(native=replace(self.native,dispatch_ref='other')),
                       dict(verified=False),dict(approve=False),dict(nonce=False),
                       dict(owner_live=False)]:
            with self.subTest(kwargs=kwargs):
                gate,_=self.fake_gate(**kwargs)
                with self.assertRaises((JournalRefusal,ValueError,PermissionError)):
                    gate.reconcile_signed_picture('op-scm-1')
                self.assertEqual(self.journal.status('op-scm-1')['state'],'IN_FLIGHT')

    def test_rejected_picture_operation_never_publishes_effect(self):
        self.journal.signal_revoke('op-scm-1',reason_code='REVOKED',authorize=lambda *_:True)
        gate,owner=self.fake_gate(approve=False)
        with self.assertRaises(JournalRefusal):gate.reconcile_signed_picture('op-scm-1')
        self.assertIsNone(self.journal.status('op-scm-1')['terminal_state'])

    def test_installed_scm_constructor_refuses_linux_test_host(self):
        if os.name=='nt':self.skipTest('Linux-only negative')
        with self.assertRaises(JournalRefusal):
            InstalledWindowsScmPictureReceipt(self.journal,object())

    def test_installed_windows_journal_owner_refuses_linux_test_host(self):
        if os.name=='nt':self.skipTest('Linux-only negative')
        with self.assertRaises(JournalRefusal):
            WindowsProtectedIPCJournalOwner(object(),object())
        with self.assertRaises(JournalRefusal):
            open_installed_windows_ipc_journal(object(),object())

    def test_provider_no_scm_gate_never_emits_terminal(self):
        from backend.nvp_lu_provider_bridge import NvpLuProviderBridge,CAPABILITIES
        from tests.nvp_lu_provider_fixture import lu_fixture,domain_fixture
        classes=domain_fixture()
        bridge=NvpLuProviderBridge(self.journal,lu_fixture()['WorkspaceFrame'],
                 {cap:classes[name] for cap,(name,_) in CAPABILITIES.items()})
        with self.assertRaises(JournalRefusal):
            bridge.supervisor_reconcile_signed_picture('op-scm-1')
        self.assertEqual(self.journal.status('op-scm-1')['state'],'IN_FLIGHT')


if __name__=='__main__': unittest.main()
