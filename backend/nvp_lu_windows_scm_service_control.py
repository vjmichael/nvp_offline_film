"""Read-only installed Windows SCM LTX control for NVP's original GPU job.

This does NOT issue creator approval, write HKLM, provision keys, attest GPU
quiescence, or return a kernel Job witness. Only the independently installed
SCM service can do those things. The real NVP owner must reconcile the
separately pinned CNG picture + Lu GPU-stop receipts before any all-clear.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import sys
import threading
import time

from backend.nvp_lu_gpu_yield import YieldIntent, CoreYieldGrant

_SERVICE = "NVP-POST01F-SCM-LTX-Picture"
_IMAGE = "nvp_scm_ltx_gpu.exe"
_INSTALL_KEY = r"SOFTWARE\NVP\POST01F\InstalledScmOwner"
_APPROVAL_KEY = r"SOFTWARE\NVP\POST01F\ApprovedLtxPicture"
_FORMAT = "nvp.post01f.installed_scm_owner.v1"
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_EXPECTED_SCOPE = frozenset((
    "job_id", "project_id", "plan_sha256", "bootstrap_sha256",
    "model_stack_sha256", "layout_sha256", "look_sha256",
    "conditioning_sha256", "take_sha256", "camera_id",
))


def original_approval_matches(intent: YieldIntent, grant: CoreYieldGrant,
                              scope: dict, values: dict) -> bool:
    """Compare every native HKLM one-shot binding before calling StartService.

    A match is NOT itself creator authorization or an SCM receipt. The native
    service independently consumes the ticket and validates the CMS signature.
    """
    if (type(intent) is not YieldIntent or type(grant) is not CoreYieldGrant or
            type(scope) is not dict or set(scope) != _EXPECTED_SCOPE or
            type(values) is not dict or grant.operation_ref != intent.origin.operation_ref or
            grant.intent_sha256 != intent.intent_sha256 or
            grant.native_job_ref != intent.native_job_ref or
            grant.device_ref != intent.device_ref or
            grant.session_ref != intent.session_ref or
            grant.core_epoch_ref != intent.core_epoch_ref or
            scope["job_id"] != intent.native_job_ref or
            scope["project_id"] != intent.project_id):
        return False
    for key in ("plan_sha256", "bootstrap_sha256", "model_stack_sha256",
                "layout_sha256", "look_sha256", "conditioning_sha256",
                "take_sha256"):
        if type(scope[key]) is not str or not _HEX64.fullmatch(scope[key]):
            return False
    if type(scope["camera_id"]) is not str or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,80}\Z", scope["camera_id"]):
        return False
    expected = {
        "JobId": intent.native_job_ref,
        "ProjectId": intent.project_id,
        "PlanSha256": scope["plan_sha256"],
        "BootstrapSha256": scope["bootstrap_sha256"],
        "ModelStackSha256": scope["model_stack_sha256"],
        "LayoutSha256": scope["layout_sha256"],
        "LookSha256": scope["look_sha256"],
        "ConditioningSha256": scope["conditioning_sha256"],
        "GpuLeaseRef": grant.lease_ref,
        "GpuDeviceRef": intent.device_ref,
        "GpuOriginalJobRef": intent.native_job_ref,
        "GpuWorkspaceRef": intent.origin.workspace_ref,
        "GpuConversationRef": intent.origin.conversation_ref,
        "GpuUserTurnRef": intent.origin.user_turn_ref,
        "GpuTaskRef": intent.origin.task_ref,
        "GpuCoreEpochRef": intent.core_epoch_ref,
        "GpuNvpSessionRef": intent.session_ref,
    }
    if any(type(values.get(k)) is not str or values[k] != v
           for k, v in expected.items()):
        return False
    pending = values.get("PendingId")
    return (type(pending) is str and _HEX32.fullmatch(pending) is not None and
            values.get("ConsumedId") != pending and
            type(values.get("ReceiptNonce")) is str and
            _HEX32.fullmatch(values["ReceiptNonce"]) is not None)


def _require_windows():
    if os.name != "nt" or sys.platform != "win32":
        raise PermissionError("Only an installed Windows SCM owner may start protected LTX")


def _program_files() -> Path:
    """FOLDERID_ProgramFiles, not an attacker-overridable environment string."""
    _require_windows()
    import ctypes
    from ctypes import wintypes
    import uuid
    from backend.nvp_post01f_installed_receipt_transport import _GUID
    guid = _GUID.from_buffer_copy(uuid.UUID(
        "905e63b6-c1bf-494e-b29c-65b732d3d21a").bytes_le)
    out = ctypes.c_void_p()
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    if shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None,
                                  ctypes.byref(out)) != 0 or not out.value:
        raise PermissionError("ProgramFiles machine known-folder identity unavailable")
    try:
        return Path(ctypes.wstring_at(out.value))
    finally:
        ole.CoTaskMemFree(out)


def _native_pin():
    _require_windows()
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _INSTALL_KEY, 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        version, version_kind = winreg.QueryValueEx(key, "Format")
        digest, digest_kind = winreg.QueryValueEx(key, "ImageSha256")
    if (version_kind != winreg.REG_SZ or digest_kind != winreg.REG_SZ or
            version != _FORMAT or type(digest) is not str or
            not _HEX64.fullmatch(digest)):
        raise PermissionError("Installer-owned native SCM executable pin unavailable")
    return digest


def _read_original_approval() -> dict:
    _require_windows()
    import winreg
    names = (
        "PendingId", "ConsumedId", "ReceiptNonce", "JobId", "ProjectId",
        "PlanSha256", "BootstrapSha256", "ModelStackSha256",
        "LayoutSha256", "LookSha256", "ConditioningSha256",
        "GpuLeaseRef", "GpuDeviceRef", "GpuOriginalJobRef",
        "GpuWorkspaceRef", "GpuConversationRef", "GpuUserTurnRef",
        "GpuTaskRef", "GpuCoreEpochRef", "GpuNvpSessionRef",
    )
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _APPROVAL_KEY, 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        values = {}
        for name in names:
            try:
                value, kind = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                if name == "ConsumedId":
                    continue
                raise PermissionError("Protected original SCM ticket is incomplete")
            if kind != winreg.REG_SZ or type(value) is not str:
                raise PermissionError("Noncanonical original SCM approval value")
            values[name] = value
    return values


def _require_native_image(image: Path, expected_sha256: str):
    _require_windows()
    from backend.nvp_post01f_installed_receipt_transport import (
        _attributes, _FILE_ATTRIBUTE_DIRECTORY,
    )
    # Every existing path component is reparse-point checked via Win32.
    parts = list(image.parents)
    for parent in reversed(parts):
        if parent.is_absolute() and not (_attributes(parent) & _FILE_ATTRIBUTE_DIRECTORY):
            raise PermissionError("Installed SCM path traverses an untrusted directory")
    if _attributes(image) & _FILE_ATTRIBUTE_DIRECTORY:
        raise PermissionError("SCM service image is a directory")
    before = image.stat()
    if not image.is_file() or before.st_size <= 0 or before.st_size > 64 * 1024 * 1024:
        raise PermissionError("Installed SCM image size/type invalid")
    digest = sha256()
    with image.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    after = image.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise PermissionError("Installed SCM image changed during owner preflight")
    if digest.hexdigest() != expected_sha256:
        raise PermissionError("Installed SCM binary diverged from trusted installer pin")


class InstalledScmLtxServiceControl:
    """Fixed Service Control Manager start/stop transport, never a signer.

    Win32 service ACLs and a separately installer-owned pinned image are
    required. This object does not offer a kernel witness or a GPU all-clear.
    The NVP native owner must integrate authenticated SCM Job/receipt observers.
    """
    def __init__(self):
        _require_windows()
        self._lock = threading.RLock()
        self._active = None
        self._image_sha = _native_pin()
        self._image = _program_files() / "NVP" / "LTX" / _IMAGE
        self._verify_service()

    def _service(self, access):
        import win32service
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        try:
            service = win32service.OpenService(scm, _SERVICE, access)
        except BaseException:
            win32service.CloseServiceHandle(scm)
            raise
        return win32service, scm, service

    def _verify_service(self):
        _require_native_image(self._image, self._image_sha)
        import win32service
        api, scm, svc = self._service(
            win32service.SERVICE_QUERY_CONFIG | win32service.SERVICE_QUERY_STATUS)
        try:
            config = api.QueryServiceConfig(svc)
            # Service image and SCM account cannot be chosen by a UI/worker.
            expected = '"' + str(self._image) + '" --service'
            if (config[0] != win32service.SERVICE_WIN32_OWN_PROCESS or
                    config[3] != expected or
                    config[7] != "LocalSystem"):
                raise PermissionError("Wrong SCM executable, command or service account")
        finally:
            api.CloseServiceHandle(svc)
            api.CloseServiceHandle(scm)

    @staticmethod
    def _status(api, service) -> dict:
        """Accept the documented pywin32 service-status tuple or status dict."""
        raw = api.QueryServiceStatusEx(service)
        if type(raw) is tuple and len(raw) >= 7:
            state, exit_code = raw[1], raw[3]
        elif type(raw) is dict:
            state, exit_code = raw.get("CurrentState"), raw.get("Win32ExitCode")
        else:
            raise PermissionError("SCM service status representation changed")
        if type(state) is not int or type(exit_code) is not int:
            raise PermissionError("SCM service status fields not independently observed")
        return {"CurrentState":state, "Win32ExitCode":exit_code}

    def require_installed_service(self) -> bool:
        """Reverify immutable installed SCM image, account and service config."""
        self._verify_service()
        return True

    def start_and_wait_without_claiming_gpu_release(self, intent: YieldIntent,
                                                     grant: CoreYieldGrant,
                                                     source_scope: dict) -> dict:
        """Start exact one-use SCM ticket, wait terminal, but never attest Job-zero."""
        _require_windows()
        if not original_approval_matches(intent, grant, source_scope,
                                         _read_original_approval()):
            raise PermissionError("Original SCM one-use creator/GPU scope not pinned")
        self._verify_service()
        import win32service
        api, scm, svc = self._service(
            win32service.SERVICE_QUERY_CONFIG | win32service.SERVICE_QUERY_STATUS |
            win32service.SERVICE_START | win32service.SERVICE_STOP)
        job = intent.native_job_ref
        try:
            with self._lock:
                if self._active is not None:
                    raise PermissionError("Original SCM LTX operation already active")
                initial = self._status(api, svc)
                if initial["CurrentState"] != win32service.SERVICE_STOPPED:
                    raise PermissionError("Cannot rebind an already active SCM service")
                self._active = (job, intent.intent_sha256)
            started = False
            terminal = False
            try:
                api.StartService(svc, [])
                started = True
                deadline = time.monotonic() + 3620
                while time.monotonic() < deadline:
                    status = self._status(api, svc)
                    if status["CurrentState"] == win32service.SERVICE_STOPPED:
                        terminal = True
                        if status["Win32ExitCode"] != 0:
                            raise PermissionError("Original SCM service failed or was cancelled")
                        self._verify_service()
                        return {
                            "job_id": job, "scm_process_stopped": True,
                            "native_job_zero_verified": False,
                            "gpu_contexts_quiescent": False,
                            "core_release_authorized": False,
                        }
                    time.sleep(0.2)
                raise TimeoutError("Original SCM service remained active after deadline")
            finally:
                # A timed-out or ambiguous *running* service must remain
                # cancelable. Never lose the original in-process stop handle
                # or claim that a timer proved GPU quiescence.
                if not started or terminal:
                    with self._lock:
                        self._active = None
        finally:
            api.CloseServiceHandle(svc)
            api.CloseServiceHandle(scm)

    def request_original_stop(self, intent: YieldIntent, job_id: str) -> bool:
        """SCM STOP is a request, NEVER proof of terminated descendants/VRAM."""
        _require_windows()
        if (type(intent) is not YieldIntent or type(job_id) is not str or
                job_id != intent.native_job_ref):
            raise PermissionError("SCM STOP cannot target a foreign LTX Job")
        with self._lock:
            if self._active != (job_id, intent.intent_sha256):
                raise PermissionError("No original live SCM service custody")
        self._verify_service()
        import win32service
        api, scm, svc = self._service(
            win32service.SERVICE_QUERY_STATUS | win32service.SERVICE_STOP)
        try:
            status = self._status(api, svc)
            if status["CurrentState"] != win32service.SERVICE_RUNNING:
                return False
            api.ControlService(svc, win32service.SERVICE_CONTROL_STOP)
            # The native service will terminate/reap the original Job and
            # issue its own protected receipt. STOP itself proves nothing.
            return True
        finally:
            api.CloseServiceHandle(svc)
            api.CloseServiceHandle(scm)
