"""Lu-connected LTX original SCM Job and cancellation source gates.

Portable SOURCE/negative tests. No installed SCM, CNG key or Radeon inference
can be claimed by this fixture.
"""
from __future__ import annotations
import inspect
import json
import tempfile
import threading
from pathlib import Path
import unittest

from backend.nvp_lu_scm_ltx_execution import (
    require_installed_scm_stage, verify_original_scm_kernel_result,
)
from backend.nvp_post01f_scm_cng_v2 import KERNEL_FORMAT
from backend.nvp_post01f_ltx_native_handoff import ProtectedLtxHandoff
from backend.nvp_lu_windows_gpu_binding import WindowsNvpGpuSupervisorBinding


class ScmOnlySourceGate(unittest.TestCase):
    def setUp(self):
        self.job = 'ltx_' + 'a'*24
        self.project = 'b'*32
        self.plan = 'c'*64
        self.kernel = {
            'format':KERNEL_FORMAT, 'job_id':self.job,
            'project_id':self.project, 'plan_sha256':self.plan,
            'worker_pid':4242, 'appcontainer_sid_sha256':'d'*64,
            'scm_owned_job':True, 'scm_service_custody_verified':True,
            'kernel_job_tree_reaped':True, 'release_fence_closed':True,
        }

    def check(self, report):
        return verify_original_scm_kernel_result(report,job_id=self.job,
                        project_id=self.project,plan_sha256=self.plan)

    def test_original_kernel_shape_never_claims_signature_proof(self):
        self.assertEqual(self.check(dict(self.kernel)),self.kernel)
        self.assertNotIn('signature',self.kernel)
        for key,bad in [('job_id','ltx_'+'f'*24),
                        ('project_id','e'*32),
                        ('plan_sha256','f'*64),
                        ('worker_pid',False),
                        ('appcontainer_sid_sha256','bad'),
                        ('scm_owned_job',False),
                        ('scm_service_custody_verified',False),
                        ('kernel_job_tree_reaped',False),
                        ('release_fence_closed',False)]:
            with self.subTest(key=key),self.assertRaises(PermissionError):
                self.check({**self.kernel,key:bad})
        with self.assertRaises(PermissionError):
            self.check({**self.kernel,'worker_path':'C:/fake'})
        with self.assertRaises(PermissionError):
            self.check({**self.kernel,'worker_pid':0})

    def test_cancel_contacts_only_original_scm_stop_and_never_claims_empty_job(self):
        handoff=object.__new__(ProtectedLtxHandoff)
        handoff._lock=threading.RLock()
        handoff._active={}
        called=[]
        handoff._scm_active={self.job:lambda job:(called.append(job) or True)}
        handoff._cancelled=set()
        self.assertTrue(handoff.cancel(self.job))
        self.assertEqual(called,[self.job])
        self.assertEqual(handoff._cancelled,{self.job})
        self.assertFalse(handoff.cancel('ltx_'+'e'*24))
        with self.assertRaises(ValueError):
            handoff.cancel('../untrusted')
        handoff._scm_active[self.job]=lambda job:False
        self.assertFalse(handoff.cancel(self.job))
        self.assertIn(self.job,handoff._cancelled)

    def test_crash_recovery_does_not_synthesize_scm_stop_or_gpu_clear(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            stage=root/self.job
            stage.mkdir()
            (stage/'journal.json').write_text(
                json.dumps({'format':'nvp.post01f.ltx_host_journal.v1',
                            'job_id':self.job,'state':'RUNNING',
                            'publishable':False}),encoding='utf8')
            handoff=object.__new__(ProtectedLtxHandoff)
            handoff.runtime_root=root
            self.assertEqual(handoff.reconcile(),[self.job])
            after=json.loads((stage/'journal.json').read_text('utf8'))
            self.assertEqual(after['state'],'INTERRUPTED_UNVERIFIED')
            self.assertIs(after['publishable'],False)
            self.assertNotIn('gpu_released',after)
            self.assertNotIn('worker_stop_receipt',after)
            self.assertEqual(handoff.reconcile(),[])

    def test_uninstalled_or_foreign_scm_stage_denied(self):
        with self.assertRaises(PermissionError):
            require_installed_scm_stage(Path('/tmp/ApprovedJobs'),
                max_memory_mb=24576,timeout_s=3600,
                scm_owned_launch=lambda _: self.kernel,
                scm_owned_cancel=lambda _:True)

    def test_connected_path_excludes_independent_python_launch(self):
        source=inspect.getsource(ProtectedLtxHandoff.run)
        self.assertIn('require_installed_scm_stage(',source)
        self.assertIn('if scm_mode:',source)
        self.assertIn('kernel = scm_owned_launch(dict(native_scope))',source)
        self.assertIn('verify_original_scm_kernel_result(',source)
        self.assertIn('else:\n                from backend.nvp_worker_containment import launch_contained',source)
        self.assertLess(source.index('if scm_mode:'),source.index('proc = launch_contained('))
        self.assertIn('scm_owned_cancel',source)

    def test_host_bindings_keep_original_turn_on_start_and_cancel(self):
        source=inspect.getsource(WindowsNvpGpuSupervisorBinding.run_preallocated_native_ltx)
        self.assertIn('scm_owned_launch=lambda scope:self.owner.run_original_scm_ltx_job(intent,scope)',source)
        self.assertIn('scm_owned_cancel=lambda job:self.owner.cancel_original_scm_ltx_job(intent,job)',source)
        self.assertIn('preallocated_job_id=intent.native_job_ref',source)
        required=WindowsNvpGpuSupervisorBinding.REQUIRED_NATIVE_OWNER_METHODS
        self.assertIn('run_original_scm_ltx_job',required)
        self.assertIn('cancel_original_scm_ltx_job',required)

    def test_scm_stop_never_bypasses_job_zero_and_signed_stop(self):
        root=Path(__file__).resolve().parents[1]
        native=(root/'tools/nvp_post01f_windows_scm_ltx_broker.cpp').read_text()
        self.assertIn('SHGetKnownFolderPath(id,KF_FLAG_DEFAULT,nullptr,&raw)',native)
        self.assertIn('known_folder(FOLDERID_ProgramData)',native)
        self.assertIn('known_folder(FOLDERID_ProgramFiles)',native)
        self.assertNotIn('GetEnvironmentVariableW(L"ProgramData"',native)
        self.assertNotIn('GetEnvironmentVariableW(L"ProgramFiles"',native)
        self.assertIn('std::atomic<bool> g_stop_requested',native)
        self.assertIn('SERVICE_ACCEPT_STOP',native)
        self.assertIn('SERVICE_CONTROL_STOP',native)
        self.assertIn('report(SERVICE_STOP_PENDING)',native)
        self.assertIn('g_stop_requested.store(true',native)
        self.assertIn('TerminateJobObject(h.job,worker_succeeded?0:13)',native)
        self.assertLess(native.index('TerminateJobObject(h.job,worker_succeeded?0:13)'),
                        native.index('issue_after_original_job_empty('))
        self.assertLess(native.index('issue_after_original_job_empty('),
                        native.index('must(worker_succeeded,'))
        self.assertIn('must(drained,"SCM Job still has child processes after 10s drain")',native)


if __name__ == '__main__':
    unittest.main()
