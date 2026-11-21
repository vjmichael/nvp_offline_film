"""R4 source-contract tests for exact AppContainer wrapper type and Job lifetime.

Mocked Windows module classes: POSITIVE TEST IS NOT KERNEL/SCM EVIDENCE.
"""
from hashlib import sha256
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.nvp_post01f_native_custody import verified_ltx_appcontainer_exit

class NativeCustodyExactType(unittest.TestCase):
    def test_missing_native_kernel_platform_refuses(self):
        with self.assertRaises(PermissionError):
            verified_ltx_appcontainer_exit(object())

    def test_actual_appcontainer_wrapper_class_contract_mocked(self):
        app=types.ModuleType('backend.nvp_g03_windows_appcontainer')
        worker=types.ModuleType('backend.nvp_worker_containment')
        job=types.ModuleType('win32job')
        class WindowsJobProcess:
            def __init__(self):
                self.pid=12345
                self._job=object()
                self._release_slot=object()
                self._original_journal=object()
        class AppContainerJobProcess:
            def __init__(self):
                self.sandbox_identity='windows-appcontainer-with-zero-network-capabilities'
                self._worker=WindowsJobProcess()
                self._sid='S-1-15-2-123'
                self.pid=12345
            def poll(self):return 0
            def close(self):
                self._worker._job=None
                self._worker._release_slot=None
                self._worker._original_journal=None
                self._worker=None
        app.AppContainerJobProcess=AppContainerJobProcess
        worker.WindowsJobProcess=WindowsJobProcess
        job.JobObjectBasicAccountingInformation=2
        job.QueryInformationJobObject=lambda a,b:{'ActiveProcesses':0}
        with patch.dict(sys.modules,{'backend.nvp_g03_windows_appcontainer':app,
                    'backend.nvp_worker_containment':worker,'win32job':job}),\
            patch('backend.nvp_post01f_native_custody.os.name','nt'):
            p=AppContainerJobProcess()
            r=verified_ltx_appcontainer_exit(p)
            self.assertEqual(r['worker_pid'],12345)
            self.assertTrue(r['kernel_job_tree_reaped'])
            self.assertTrue(r['release_fence_closed'])
            self.assertEqual(r['appcontainer_sid_sha256'],sha256(b'S-1-15-2-123').hexdigest())
            # A generic WindowsJobProcess is NOT an AppContainer, refuse.
            with self.assertRaises(PermissionError):
                verified_ltx_appcontainer_exit(WindowsJobProcess())

    def test_missing_or_pending_job_refuses(self):
        app=types.ModuleType('backend.nvp_g03_windows_appcontainer')
        worker=types.ModuleType('backend.nvp_worker_containment')
        class WindowsJobProcess:
            def __init__(self):
                self.pid=42
                self._job=object()
                self._release_slot=None
                self._original_journal=object()
        class AppContainerJobProcess:
            def __init__(self):
                self.sandbox_identity='windows-appcontainer-with-zero-network-capabilities'
                self._worker=WindowsJobProcess()
                self._sid='S-1-15-2-123'
                self.pid=42
            def poll(self):return None
        app.AppContainerJobProcess=AppContainerJobProcess
        worker.WindowsJobProcess=WindowsJobProcess
        with patch.dict(sys.modules,{'backend.nvp_g03_windows_appcontainer':app,
                'backend.nvp_worker_containment':worker}),\
             patch('backend.nvp_post01f_native_custody.os.name','nt'):
            with self.assertRaises(RuntimeError):
                verified_ltx_appcontainer_exit(AppContainerJobProcess())
