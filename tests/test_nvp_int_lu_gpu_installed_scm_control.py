"""NVP Lu original SCM service control: portable refusal and scope regressions.

All native service mocks here are explicitly source-only. They cannot prove
SCM installation, a Windows Job, a real signer or physical Radeon VRAM.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import inspect
import sys
import threading
import types
import unittest
from unittest.mock import patch

from backend.nvp_lu_operation_journal import OriginRefs
from backend.nvp_lu_gpu_yield import YieldIntent, CoreYieldGrant
from backend.nvp_lu_windows_scm_service_control import (
    InstalledScmLtxServiceControl, original_approval_matches,
)

H = lambda data: sha256(data).hexdigest()


class InstalledScmOwnerNegativeSource(unittest.TestCase):
    def setUp(self):
        self.intent = YieldIntent(
            origin=OriginRefs("workspace1", "conv1", "turn1", "task1", "op1"),
            session_ref="nvp-session1", core_epoch_ref="epoch1",
            project_id="a"*32, native_job_ref="ltx_"+"b"*24,
            device_ref="dxgi:luid_0x12345678_0x12345678_phys_0",
            desired_free_vram_bytes=2**30,
            duration_ms=600_000, deadline_unix_ms=1_900_000_000_000)
        self.grant = CoreYieldGrant(
            "op1", self.intent.intent_sha256, "nvp-session1", "epoch1",
            self.intent.native_job_ref, self.intent.device_ref,
            "gpu-lease1", "model-gen1", 2**30, 1_800_000_000_000,
            1_800_000_060_000, H(b"core-receipt"))
        self.scope = {
            "job_id":self.intent.native_job_ref,
            "project_id":self.intent.project_id,
            "plan_sha256":H(b"plan"),
            "bootstrap_sha256":H(b"bootstrap"),
            "model_stack_sha256":H(b"stack"),
            "layout_sha256":H(b"layout"),
            "look_sha256":H(b"look"),
            "conditioning_sha256":H(b"conditioning"),
            "take_sha256":H(b"take"),
            "camera_id":"cam1",
        }
        self.values = {
            "PendingId":"f"*32, "ConsumedId":"e"*32,
            "ReceiptNonce":"d"*32,
            "JobId":self.intent.native_job_ref,
            "ProjectId":self.intent.project_id,
            "PlanSha256":self.scope["plan_sha256"],
            "BootstrapSha256":self.scope["bootstrap_sha256"],
            "ModelStackSha256":self.scope["model_stack_sha256"],
            "LayoutSha256":self.scope["layout_sha256"],
            "LookSha256":self.scope["look_sha256"],
            "ConditioningSha256":self.scope["conditioning_sha256"],
            "GpuLeaseRef":self.grant.lease_ref,
            "GpuDeviceRef":self.intent.device_ref,
            "GpuOriginalJobRef":self.intent.native_job_ref,
            "GpuWorkspaceRef":self.intent.origin.workspace_ref,
            "GpuConversationRef":self.intent.origin.conversation_ref,
            "GpuUserTurnRef":self.intent.origin.user_turn_ref,
            "GpuTaskRef":self.intent.origin.task_ref,
            "GpuCoreEpochRef":self.intent.core_epoch_ref,
            "GpuNvpSessionRef":self.intent.session_ref,
        }

    def match(self, *, intent=None, grant=None, scope=None, values=None):
        return original_approval_matches(
            intent if intent is not None else self.intent,
            grant if grant is not None else self.grant,
            scope if scope is not None else self.scope,
            values if values is not None else self.values)

    def test_exact_original_host_and_core_lease_comparison(self):
        self.assertTrue(self.match())
        self.assertFalse(self.match(grant=replace(
            self.grant, core_epoch_ref="different")))
        self.assertFalse(self.match(grant=replace(
            self.grant, native_job_ref="ltx_"+"c"*24)))
        self.assertFalse(self.match(grant=replace(
            self.grant, lease_ref="gpu-other")))
        self.assertFalse(self.match(scope={
            **self.scope, "job_id":"ltx_"+"c"*24}))
        self.assertFalse(self.match(scope={
            **self.scope, "unapproved_extra":True}))

    def test_wrong_signed_ticket_and_original_scope_never_start(self):
        for key,value in (
            ("GpuLeaseRef","gpu-foreign"),
            ("GpuOriginalJobRef","ltx_"+"c"*24),
            ("GpuDeviceRef","gpu-0"),
            ("GpuUserTurnRef","foreign-turn"),
            ("GpuCoreEpochRef","epoch2"),
            ("GpuNvpSessionRef","foreign-session"),
            ("PlanSha256","0"*64),
            ("ProjectId","c"*32),
            ("ConsumedId","f"*32),
            ("PendingId","../untrusted"),
            ("ReceiptNonce","bad"),
        ):
            with self.subTest(key=key):
                self.assertFalse(self.match(values={**self.values,key:value}))
        missing=dict(self.values)
        del missing["GpuLeaseRef"]
        self.assertFalse(self.match(values=missing))

    def test_linux_or_uninstalled_windows_refuses_native_owner(self):
        if sys.platform != "win32":
            with self.assertRaises(PermissionError):
                InstalledScmLtxServiceControl()
        else:
            from backend import nvp_lu_windows_scm_service_control as src
            with patch.object(src, "_native_pin", side_effect=PermissionError("missing pin")):
                with self.assertRaises(PermissionError):
                    InstalledScmLtxServiceControl()

    def test_source_no_installer_write_or_worker_control(self):
        import backend.nvp_lu_windows_scm_service_control as module
        source=inspect.getsource(module)
        self.assertIn("win32service.StartService(svc, [])", source.replace(
            "api.StartService(svc, [])", "win32service.StartService(svc, [])"))
        self.assertIn("api.ControlService(svc, win32service.SERVICE_CONTROL_STOP)",source)
        self.assertIn("SERVICE_WIN32_OWN_PROCESS",source)
        self.assertIn('config[7] != "LocalSystem"',source)
        self.assertIn("ImageSha256",source)
        self.assertIn("original_approval_matches(",source)
        self.assertIn("native_job_zero_verified",source)
        self.assertIn("core_release_authorized",source)
        self.assertNotIn("RegSetValueEx",source)
        self.assertNotIn("CreateProcess",source)
        self.assertNotIn("shell=True",source)
        self.assertNotIn("return {\"gpu_contexts_quiescent\": True",source)

    def test_timeout_keeps_original_stop_custody_not_an_all_clear(self):
        api=types.SimpleNamespace(
            SERVICE_QUERY_CONFIG=1,SERVICE_QUERY_STATUS=4,
            SERVICE_START=16,SERVICE_STOP=32,SERVICE_STOPPED=1,
            SERVICE_RUNNING=4)
        status=[
            {"CurrentState":1,"Win32ExitCode":0},
            {"CurrentState":4,"Win32ExitCode":0},
        ]
        api.QueryServiceStatusEx=lambda h:status.pop(0)
        api.StartService=lambda h,args:None
        api.CloseServiceHandle=lambda h:None
        controller=object.__new__(InstalledScmLtxServiceControl)
        controller._lock=threading.RLock()
        controller._active=None
        controller._service=lambda access:(api,object(),"SCM-FAKE")
        controller._verify_service=lambda:None
        import backend.nvp_lu_windows_scm_service_control as module
        with patch.object(module,"_require_windows",return_value=None), \
             patch.object(module,"_read_original_approval",return_value=self.values), \
             patch.object(module.time,"monotonic",side_effect=[100.0,4000.0]), \
             patch.dict(sys.modules,{"win32service":api}):
            with self.assertRaises(TimeoutError):
                controller.start_and_wait_without_claiming_gpu_release(
                    self.intent,self.grant,dict(self.scope))
            self.assertEqual(controller._active,
                (self.intent.native_job_ref,self.intent.intent_sha256))

    def test_python_callback_only_owner_cannot_borrow_lu_gpu(self):
        from backend.nvp_lu_windows_gpu_binding import WindowsNvpGpuSupervisorBinding
        from backend.nvp_lu_gpu_yield import GpuYieldRefusal
        binding=object.__new__(WindowsNvpGpuSupervisorBinding)
        binding.owner=types.SimpleNamespace(
            reserve_original_ltx_job=lambda _:self.intent.native_job_ref,
            run_original_scm_ltx_job=lambda *args:{},
            cancel_original_scm_ltx_job=lambda *args:True)
        with self.assertRaises(GpuYieldRefusal):
            binding._require_original_scm_control()

    def test_native_lu_gpu_stop_uses_real_known_folder_and_blocks_reparse(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'tools/nvp_int_lu_gpu_stop_issuer.hpp').read_text()
        self.assertIn('SHGetKnownFolderPath(',source)
        self.assertIn('FOLDERID_ProgramData',source)
        self.assertIn('FILE_ATTRIBUTE_REPARSE_POINT',source)
        self.assertNotIn('GetEnvironmentVariableW(L"ProgramData"',source)

    def test_pywin32_tuple_status_and_invalid_status_fail_closed(self):
        controller=object.__new__(InstalledScmLtxServiceControl)
        api=types.SimpleNamespace(
            QueryServiceStatusEx=lambda _: (16,4,1,0,0,0,1000,42,0))
        self.assertEqual(controller._status(api,"mock"),
                         {"CurrentState":4,"Win32ExitCode":0})
        api.QueryServiceStatusEx=lambda _:{"CurrentState":1,"Win32ExitCode":97}
        self.assertEqual(controller._status(api,"mock"),
                         {"CurrentState":1,"Win32ExitCode":97})
        for invalid in ([],(16,4),{"CurrentState":True,"Win32ExitCode":0}):
            api.QueryServiceStatusEx=lambda _, value=invalid:value
            with self.subTest(value=invalid),self.assertRaises(PermissionError):
                controller._status(api,"mock")

    def test_mocked_scm_stop_is_not_gpu_stop_evidence(self):
        """Mock SCM is never a physical acceptance receipt."""
        api=types.SimpleNamespace(SERVICE_QUERY_STATUS=4,SERVICE_STOP=16,
                                  SERVICE_RUNNING=4,SERVICE_CONTROL_STOP=1)
        calls=[]
        api.QueryServiceStatusEx=lambda h: {"CurrentState":4,"ProcessId":1234}
        api.ControlService=lambda h,mode:calls.append((h,mode))
        api.CloseServiceHandle=lambda h:None
        controller=object.__new__(InstalledScmLtxServiceControl)
        controller._lock=threading.RLock()
        controller._active=(self.intent.native_job_ref,
                            self.intent.intent_sha256)
        controller._service=lambda access:(api,object(),"SCM-FAKE")
        controller._verify_service=lambda:None
        import backend.nvp_lu_windows_scm_service_control as module
        with patch.object(module,"_require_windows",return_value=None), \
             patch.dict(sys.modules,{"win32service":api}):
            self.assertTrue(controller.request_original_stop(
                self.intent,self.intent.native_job_ref))
            self.assertEqual(calls,[("SCM-FAKE",1)])
            with self.assertRaises(PermissionError):
                controller.request_original_stop(self.intent,"ltx_"+"c"*24)
            self.assertFalse(hasattr(controller,"issue_gpu_stop_receipt"))


if __name__ == "__main__":
    unittest.main()
