"""NVP-owned Windows Lu Core read-only named-pipe client *admission foundation*.

Scope: observed OS pipe identity, bounded Win32 transport, fail-closed enrollment.
No caller-chosen endpoint, unsafe localhost fallback, Protobuf effect invoke, or
credential-by-argument production connection. This module deliberately cannot
make a production connection until the installed NVP/Lu credential + signer
brokers are wired and independently qualified on actual Windows.

Separate systems: Lu authenticates the NVP client and owns its model/journal;
NVP authenticates Lu Core's installed process before sending even a Hello.
A PID, SHA-only fixture, claimed Hello and an HMAC from test code are not
sufficient installed package enrollment.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import hashlib
import ntpath
import os
import re
import sys

from backend.nvp_lu_ipc_v0 import validate_windows_pipe_name

# External broker/installer-owned, not present or writable by a normal NVP user.
# The exact key/format must be matched with actual accepted installer source.
TRUST_PATH = r'SOFTWARE\NVP\LuCore\InstalledPeer'
TRUST_FORMAT = 'nvp.lu.installed_peer.v1'
EXPECTED_SHA = re.compile('[a-f0-9]{64}\\Z')
EXPECTED_SID = re.compile('S-1-[0-9-]{3,180}\\Z')
GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
OPEN_EXISTING, FILE_FLAG_OVERLAPPED = 3, 0x40000000
SECURITY_SQOS_PRESENT, SECURITY_IDENTIFICATION = 0x00100000, 0x00010000
PROCESS_QUERY_LIMITED_INFORMATION, SYNCHRONIZE = 0x1000, 0x00100000
WAIT_OBJECT_0, WAIT_TIMEOUT, ERROR_IO_PENDING = 0, 258, 997
INFINITE = 0xffffffff
MAX_IMAGE_BYTES = 1024 * 1024 * 1024  # bound hashing for an actual Core PE


@dataclass(frozen=True)
class InstallerPinnedLuCore:
    image_path: str
    image_sha256: str
    service_sid: str

    def __post_init__(self):
        if (type(self.image_path) is not str or not ntpath.isabs(self.image_path)
            or self.image_path.startswith('\\\\') or '..' in self.image_path.split('\\')
            or ntpath.normpath(self.image_path) != self.image_path
            or type(self.image_sha256) is not str
            or EXPECTED_SHA.fullmatch(self.image_sha256) is None
            or type(self.service_sid) is not str
            or EXPECTED_SID.fullmatch(self.service_sid) is None):
            raise PermissionError('Invalid installer-owned Lu Core process pin')


def read_installed_peer_pin() -> InstallerPinnedLuCore:
    """Use only fixed HKLM 64-bit installer-owned pin, never env/CLI/project/UI."""
    if sys.platform != 'win32':
        raise PermissionError('Windows-only native Lu IPC trust')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, TRUST_PATH, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as h:
            def field(name):
                v, ty = winreg.QueryValueEx(h, name)
                if ty != winreg.REG_SZ or type(v) is not str:
                    raise PermissionError('Installed Lu Core pin type mismatch')
                return v
            if field('Format') != TRUST_FORMAT:
                raise PermissionError('Unapproved Lu Core installer trust schema')
            return InstallerPinnedLuCore(field('ImagePath'), field('ImageSha256'),
                                         field('ServiceSID'))
    except OSError as exc:
        raise PermissionError('No installed, protected Lu Core pin') from exc


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [('Internal',ctypes.c_size_t),('InternalHigh',ctypes.c_size_t),
                ('Offset',wintypes.DWORD),('OffsetHigh',wintypes.DWORD),
                ('hEvent',wintypes.HANDLE)]


class _Win32:
    """Initialize native signatures *only* in real Windows (no simulation)."""
    def __init__(self):
        if sys.platform != 'win32' or not hasattr(ctypes, 'WinDLL'):
            raise PermissionError('Native Windows named-pipe API unavailable')
        k=ctypes.WinDLL('kernel32', use_last_error=True)
        a=ctypes.WinDLL('advapi32', use_last_error=True)
        self.k,self.a=k,a
        self.invalid=ctypes.c_void_p(-1).value
        def bind(lib,name,args,res):
            fn=getattr(lib,name);fn.argtypes=args;fn.restype=res
            return fn
        H=wintypes.HANDLE;D=wintypes.DWORD;P=ctypes.c_void_p
        self.CreateFileW=bind(k,'CreateFileW',[wintypes.LPCWSTR,D,D,P,D,D,H],H)
        self.GetNamedPipeServerProcessId=bind(k,'GetNamedPipeServerProcessId',[H,ctypes.POINTER(D)],wintypes.BOOL)
        self.GetNamedPipeServerSessionId=bind(k,'GetNamedPipeServerSessionId',[H,ctypes.POINTER(D)],wintypes.BOOL)
        self.OpenProcess=bind(k,'OpenProcess',[D,wintypes.BOOL,D],H)
        self.GetProcessTimes=bind(k,'GetProcessTimes',[H,P,P,P,P],wintypes.BOOL)
        self.QueryFullProcessImageNameW=bind(k,'QueryFullProcessImageNameW',[H,D,P,ctypes.POINTER(D)],wintypes.BOOL)
        self.CloseHandle=bind(k,'CloseHandle',[H],wintypes.BOOL)
        self.ReadFile=bind(k,'ReadFile',[H,P,D,ctypes.POINTER(D),P],wintypes.BOOL)
        self.WriteFile=bind(k,'WriteFile',[H,P,D,ctypes.POINTER(D),P],wintypes.BOOL)
        self.CreateEventW=bind(k,'CreateEventW',[P,wintypes.BOOL,wintypes.BOOL,wintypes.LPCWSTR],H)
        self.WaitForSingleObject=bind(k,'WaitForSingleObject',[H,D],D)
        self.CancelIoEx=bind(k,'CancelIoEx',[H,P],wintypes.BOOL)
        self.GetOverlappedResult=bind(k,'GetOverlappedResult',[H,P,ctypes.POINTER(D),wintypes.BOOL],wintypes.BOOL)
        self.OpenProcessToken=bind(a,'OpenProcessToken',[H,D,ctypes.POINTER(H)],wintypes.BOOL)
        self.GetTokenInformation=bind(a,'GetTokenInformation',[H,D,P,D,ctypes.POINTER(D)],wintypes.BOOL)
        self.ConvertSidToStringSidW=bind(a,'ConvertSidToStringSidW',[P,ctypes.POINTER(P)],wintypes.BOOL)
        self.LocalFree=bind(k,'LocalFree',[P],P)

    def _invalid(self,handle):
        return handle is None or handle==self.invalid or handle==0

    def close(self,handle):
        if not self._invalid(handle):self.CloseHandle(handle)

    def error(self,where):
        return PermissionError(f'Native Lu Core {where} refused (Win32 {ctypes.get_last_error()})')


def _sid_for_process(api, process_handle:int) -> str:
    token=wintypes.HANDLE()
    if not api.OpenProcessToken(process_handle,0x0008,ctypes.byref(token)):
        raise api.error('process-token query')
    try:
        size=wintypes.DWORD()
        api.GetTokenInformation(token,1,None,0,ctypes.byref(size))
        if not 16<=size.value<=16384:
            raise PermissionError('Invalid Lu Core token size')
        # Native TOKEN_USER begins with aligned pointer-sized SID.
        buf=ctypes.create_string_buffer(size.value)
        actual=wintypes.DWORD()
        if not api.GetTokenInformation(token,1,buf,size.value,ctypes.byref(actual)):
            raise api.error('process-token read')
        if actual.value<ctypes.sizeof(ctypes.c_void_p):
            raise PermissionError('Incomplete Lu Core process SID')
        sid_ptr=ctypes.c_void_p.from_buffer(buf).value
        if not sid_ptr:
            raise PermissionError('Missing Lu Core process SID')
        psid=ctypes.c_void_p()
        if not api.ConvertSidToStringSidW(sid_ptr,ctypes.byref(psid)):
            raise api.error('SID conversion')
        try:
            sid=ctypes.wstring_at(psid.value)
            if EXPECTED_SID.fullmatch(sid) is None:
                raise PermissionError('Invalid observed Lu Core SID')
            return sid
        finally:
            api.LocalFree(psid)
    finally:
        api.close(token.value)


def _creation_time(api,process_handle:int) -> int:
    chunks=[(wintypes.DWORD*2)() for _ in range(4)]
    if not api.GetProcessTimes(process_handle,*[ctypes.byref(x) for x in chunks]):
        raise api.error('process creation-time')
    return chunks[0][0] | (chunks[0][1]<<32)


def _image_path(api,process_handle:int) -> str:
    buf=ctypes.create_unicode_buffer(32768)
    count=wintypes.DWORD(len(buf))
    if not api.QueryFullProcessImageNameW(process_handle,0,buf,ctypes.byref(count)):
        raise api.error('process image path')
    if not 0<count.value<32768:
        raise PermissionError('Invalid Lu Core image path')
    return buf.value


def _pinned_image_hash(image_path:str,pin:InstallerPinnedLuCore) -> None:
    """Exact installed image bytes; native signer verification still required.

    Production remains disabled until a protected installer-owned native
    broker also verifies Authenticode signer/WinTrust on the *pinned file
    handle*, signer revocation, file identity/ACL/reparse, and returns a sealed
    credential. This Python-side hash is only an early negative filter.
    """
    if ntpath.normcase(ntpath.normpath(image_path)) != ntpath.normcase(pin.image_path):
        raise PermissionError('Lu Core observed process image differs from installed pin')
    # A read-only cheap filter, NOT cryptographic signer provenance on its own.
    st=os.stat(image_path,follow_symlinks=False)
    if st.st_size<=0 or st.st_size>MAX_IMAGE_BYTES or os.path.islink(image_path):
        raise PermissionError('Invalid/reparse/unbounded installed Lu Core binary')
    h=hashlib.sha256()
    with open(image_path,'rb') as source:
        while block:=source.read(1024*1024):h.update(block)
    if h.hexdigest()!=pin.image_sha256:
        raise PermissionError('Installed Lu Core image hash is not approved')


class WinPipeStream:
    """Win32 overlapped byte-mode stream compatible with NVP bounded framing.

    Each ReadFile/WriteFile uses a native event and deadline. Timeout cancels
    and *reaps* pending I/O before local buffers/events can be released.
    Handles are owned; no raw capability/effect dispatch is exposed.
    """
    def __init__(self, api:_Win32,handle:int):
        if api._invalid(handle):raise PermissionError('Invalid native Lu pipe')
        self._api,self._handle,self._timeout=api,handle,3.0
    def settimeout(self,seconds):
        if type(seconds) not in (float,int) or not 0<seconds<=3.0:
            raise ValueError('Unbounded Lu pipe I/O timeout')
        self._timeout=float(seconds)
    def close(self):
        if self._handle is not None:
            self._api.CancelIoEx(self._handle,None)
            self._api.close(self._handle)
            self._handle=None
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
    def _io(self,payload:bytes|int,read:bool)->bytes|int:
        if self._handle is None:raise ConnectionError('Lu pipe closed')
        size=payload if read else len(payload)
        if type(size) is not int or not 0<size<=262144+4:
            raise ValueError('Invalid bounded Lu read/write size')
        api=self._api
        event=api.CreateEventW(None,True,False,None)
        if api._invalid(event):raise api.error('overlapped event creation')
        ov=_OVERLAPPED();ov.hEvent=event
        actual=wintypes.DWORD(0)
        buffer=ctypes.create_string_buffer(size) if read else ctypes.create_string_buffer(payload,size)
        try:
            op=api.ReadFile if read else api.WriteFile
            success=op(self._handle,buffer,size,ctypes.byref(actual),ctypes.byref(ov))
            if not success:
                err=ctypes.get_last_error()
                if err!=ERROR_IO_PENDING:raise api.error('overlapped I/O start')
                milliseconds=max(1,min(3000,int(self._timeout*1000)))
                result=api.WaitForSingleObject(event,milliseconds)
                if result!=WAIT_OBJECT_0:
                    api.CancelIoEx(self._handle,ctypes.byref(ov))
                    # Drain the pending native I/O before the buffers/OVERLAPPED
                    # go out of scope, even if cancellation raced completion.
                    api.WaitForSingleObject(event,INFINITE)
                    api.GetOverlappedResult(self._handle,ctypes.byref(ov),ctypes.byref(actual),False)
                    if result==WAIT_TIMEOUT:raise TimeoutError('Lu pipe I/O deadline expired')
                    raise api.error('I/O wait')
                if not api.GetOverlappedResult(self._handle,ctypes.byref(ov),ctypes.byref(actual),False):
                    raise api.error('overlapped I/O result')
            if actual.value>size:raise PermissionError('Native I/O count out of bound')
            return buffer.raw[:actual.value] if read else actual.value
        finally:api.close(event)
    def recv(self,size):return self._io(size,True)
    def send(self,payload):
        if not isinstance(payload,(bytes,memoryview)):
            raise TypeError('Lu pipe write requires bounded bytes')
        return self._io(bytes(payload),False)


class ObservedWindowsLuPipe:
    """Pre-admission OS process-handle lease; NOT an authenticated Lu peer.

    Retain the exact kernel process handle while retaining the pipe. A PID
    alone can be recycled; the process generation and handle remain bound.
    No public method here sends a Health/Hello or creates a trust witness.
    """
    def __init__(self,stream:WinPipeStream,process_handle:int,pid:int,
                 creation_filetime:int,session:int,image_path:str,user_sid:str):
        self.stream=stream
        self._process_handle=process_handle
        self.server_pid=pid
        self.creation_filetime=creation_filetime
        self.server_session=session
        self.image_path=image_path
        self.user_sid=user_sid

    def __enter__(self):
        self.assert_observed_process_alive()
        return self

    def __exit__(self, *_):
        self.close()

    def assert_observed_process_alive(self):
        """Repeat kernel observations only; a positive result is NOT trust."""
        if self._process_handle is None:
            raise PermissionError('Lu pipe observation lease closed')
        api=self.stream._api
        pid=wintypes.DWORD(0)
        session=wintypes.DWORD(0)
        if (not api.GetNamedPipeServerProcessId(self.stream._handle,ctypes.byref(pid))
            or pid.value!=self.server_pid
            or not api.GetNamedPipeServerSessionId(self.stream._handle,ctypes.byref(session))
            or session.value!=self.server_session
            or _creation_time(api,self._process_handle)!=self.creation_filetime
            or api.WaitForSingleObject(self._process_handle,0)!=WAIT_TIMEOUT):
            raise PermissionError('Lu Core observed pipe/process generation changed')
        return True

    def close(self):
        try:
            self.stream.close()
        finally:
            if self._process_handle is not None:
                self.stream._api.close(self._process_handle)
                self._process_handle=None


def observe_installed_lu_pipe() -> ObservedWindowsLuPipe:
    """Can OBSERVE only a fixed installed endpoint; NEVER transmit any data.

    Must be followed by signed provenance/ACL/file identity, protection of
    credential provision and session-lifetime admission in a trusted native
    broker. Without that broker no Health, model, tool or effect is allowed.
    """
    pin=read_installed_peer_pin()
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,TRUST_PATH,0,
                        winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as h:
        endpoint,kind=winreg.QueryValueEx(h,'PipeName')
    if kind!=winreg.REG_SZ or type(endpoint) is not str:
        raise PermissionError('Invalid installed Lu pipe endpoint record')
    validate_windows_pipe_name(endpoint)
    api=_Win32()
    handle=api.CreateFileW(endpoint,GENERIC_READ|GENERIC_WRITE,0,None,
             OPEN_EXISTING,FILE_FLAG_OVERLAPPED|SECURITY_SQOS_PRESENT|SECURITY_IDENTIFICATION,None)
    if api._invalid(handle):raise api.error('named-pipe open')
    process=None
    try:
        pid=wintypes.DWORD(0);session=wintypes.DWORD(0)
        if not api.GetNamedPipeServerProcessId(handle,ctypes.byref(pid)) or pid.value<=0:
            raise api.error('pipe-server identity')
        if not api.GetNamedPipeServerSessionId(handle,ctypes.byref(session)):
            raise api.error('pipe-server session')
        process=api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,False,pid.value)
        if api._invalid(process):raise api.error('installed Lu process-open')
        created=_creation_time(api,process)
        image=_image_path(api,process)
        user_sid=_sid_for_process(api,process)
        if user_sid!=pin.service_sid:
            raise PermissionError('Wrong Lu Core service account')
        _pinned_image_hash(image,pin)
        # Re-query handle-bound PID/created identity to rule out process exit
        # or a PID-reuse race *during this preliminary observation*.
        pid_after=wintypes.DWORD(0)
        session_after=wintypes.DWORD(0)
        if (not api.GetNamedPipeServerProcessId(handle,ctypes.byref(pid_after))
            or pid_after.value!=pid.value
            or not api.GetNamedPipeServerSessionId(handle,ctypes.byref(session_after))
            or session_after.value!=session.value
            or _creation_time(api,process)!=created
            or api.WaitForSingleObject(process,0)!=WAIT_TIMEOUT):
            raise PermissionError('Lu Core pipe process changed while observed')
        observed=ObservedWindowsLuPipe(WinPipeStream(api,handle),process,
                  pid.value,created,session.value,image,user_sid)
        process=None # Transfer the original process handle into the lease.
        return observed
    except BaseException:
        api.close(handle)
        raise
    finally:api.close(process)


def connect_authenticated_read_only(*_args,**_kwargs):
    """Deny until real installed signed-image and credential broker is wired.

    A Python-created witness/callback or cached HMAC is not installer custody.
    The NVP client has NO public argument that can override this refusal.
    Do not call handshake() on an observed-only WinPipeStream.
    """
    raise PermissionError('Installed native signer/credential broker not yet qualified')
