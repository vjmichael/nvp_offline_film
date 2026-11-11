"""G03: kernel-backed Windows AppContainer, no network capabilities.

Host launches an exact reviewed binary with STARTUPINFOEX
SECURITY_CAPABILITIES and an explicit three-handle allowlist. Windows
AppContainer SID denies other user files and network. Source and output stay
in anonymous pipes; process is assigned to a kill-on-close Job while suspended.
No unsandboxed fallback. Scoped code ACLs are removed after job closure.
"""
from __future__ import annotations
import ctypes as C
import hashlib
from ctypes import wintypes as W
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

class AppContainerFailure(RuntimeError):
    pass

class _Caps(C.Structure):
    _fields_=[("AppContainerSid",W.LPVOID),("Capabilities",W.LPVOID),
              ("CapabilityCount",W.DWORD),("Reserved",W.DWORD)]

class _Startup(C.Structure):
    _fields_=[("cb",W.DWORD),("lpReserved",W.LPWSTR),
              ("lpDesktop",W.LPWSTR),("lpTitle",W.LPWSTR),
              ("dwX",W.DWORD),("dwY",W.DWORD),("dwXSize",W.DWORD),
              ("dwYSize",W.DWORD),("dwXCountChars",W.DWORD),
              ("dwYCountChars",W.DWORD),("dwFillAttribute",W.DWORD),
              ("dwFlags",W.DWORD),("wShowWindow",W.WORD),
              ("cbReserved2",W.WORD),("lpReserved2",W.LPVOID),
              ("hStdInput",W.HANDLE),("hStdOutput",W.HANDLE),
              ("hStdError",W.HANDLE)]
class _StartupEx(C.Structure):
    _fields_=[("StartupInfo",_Startup),("lpAttributeList",W.LPVOID)]
class _ProcessInfo(C.Structure):
    _fields_=[("hProcess",W.HANDLE),("hThread",W.HANDLE),
              ("dwProcessId",W.DWORD),("dwThreadId",W.DWORD)]

def _check(step):
    raise AppContainerFailure("%s: Win32 error %d"%(step,C.get_last_error()))

def _api():
    k=C.WinDLL("kernel32",use_last_error=True)
    u=C.WinDLL("userenv",use_last_error=True)
    a=C.WinDLL("advapi32",use_last_error=True)
    k.InitializeProcThreadAttributeList.argtypes=[W.LPVOID,W.DWORD,W.DWORD,C.POINTER(C.c_size_t)]
    k.InitializeProcThreadAttributeList.restype=W.BOOL
    k.UpdateProcThreadAttribute.argtypes=[W.LPVOID,W.DWORD,C.c_size_t,W.LPVOID,
                                          C.c_size_t,W.LPVOID,W.LPVOID]
    k.UpdateProcThreadAttribute.restype=W.BOOL
    k.DeleteProcThreadAttributeList.argtypes=[W.LPVOID]
    k.CreateProcessW.argtypes=[W.LPCWSTR,W.LPWSTR,W.LPVOID,W.LPVOID,W.BOOL,W.DWORD,
        W.LPVOID,W.LPCWSTR,C.POINTER(_StartupEx),C.POINTER(_ProcessInfo)]
    k.CreateProcessW.restype=W.BOOL
    u.CreateAppContainerProfile.argtypes=[W.LPCWSTR,W.LPCWSTR,W.LPCWSTR,
                                           W.LPVOID,W.DWORD,C.POINTER(W.LPVOID)]
    u.CreateAppContainerProfile.restype=C.c_long
    u.GetAppContainerFolderPath.argtypes=[W.LPCWSTR,C.POINTER(W.LPWSTR)]
    u.GetAppContainerFolderPath.restype=C.c_long
    u.DeleteAppContainerProfile.argtypes=[W.LPCWSTR]
    u.DeleteAppContainerProfile.restype=C.c_long
    a.ConvertSidToStringSidW.argtypes=[W.LPVOID,C.POINTER(W.LPWSTR)]
    a.ConvertSidToStringSidW.restype=W.BOOL
    a.FreeSid.argtypes=[W.LPVOID]
    k.LocalFree.argtypes=[W.LPVOID]
    k.CloseHandle.argtypes=[W.HANDLE]
    return k,u,a

def _acl(path,sid,permission,recursive=False,remove=False):
    if not re.fullmatch(r"S-1-15-2-(?:[0-9]+-){5,9}[0-9]+",sid):
        raise AppContainerFailure("Untrusted AppContainer SID")
    args=["icacls",str(path)]
    args += ["/remove:g","*"+sid] if remove else ["/grant","*"+sid+":"+permission]
    if recursive:
        args.append("/T")
    r=subprocess.run(args,capture_output=True,text=True,timeout=120,check=False)
    if r.returncode or "Failed processing" in r.stdout:
        raise AppContainerFailure("Native AppContainer DACL operation failed")

def _paths(command,cwd,code_roots,code_files):
    if sys.platform!="win32":
        raise AppContainerFailure("Windows AppContainer only")
    if not isinstance(command,list) or not command or any(
            not isinstance(x,str) or not x or "\x00" in x for x in command):
        raise AppContainerFailure("Fixed native process argv required")
    exe=Path(command[0]).resolve(strict=True)
    work=Path(cwd).resolve(strict=True)
    roots=[Path(x).resolve(strict=True) for x in (code_roots or ())]
    files=[Path(x).resolve(strict=True) for x in (code_files or ())]
    if (not exe.is_file() or not work.is_dir() or not roots and not files
            or any(not x.is_dir() or x==x.parent for x in roots)
            or any(not x.is_file() for x in files)
            or not (exe in files or any(exe.is_relative_to(x) for x in roots))):
        raise AppContainerFailure("Invalid reviewed code sandbox policy")
    if any(work==x or work.is_relative_to(x) or x.is_relative_to(work) for x in roots):
        raise AppContainerFailure("Code ACL overlaps private workspace")
    film=os.environ.get("NVP_HOME")
    if film:
        home=Path(film).resolve()
        if any(home==x or home.is_relative_to(x) or x.is_relative_to(home) for x in roots):
            raise AppContainerFailure("Code ACL overlaps original movie storage")
    return exe,work,roots,files

def _profile_folder(userenv,sid):
    """Resolve the exact OS AppContainer data directory, never guess its path."""
    location=W.LPWSTR()
    hr=userenv.GetAppContainerFolderPath(sid,C.byref(location))&0xffffffff
    if hr or not location or not location.value:
        raise AppContainerFailure("AppContainer profile data root not independently known")
    try:
        root=Path(location.value).resolve(strict=True)
        if not root.is_dir() or root==root.parent:
            raise AppContainerFailure("Invalid AppContainer data directory")
        film=os.environ.get("NVP_HOME")
        if film:
            home=Path(film).resolve()
            if root==home or root.is_relative_to(home) or home.is_relative_to(root):
                raise AppContainerFailure("Sandbox profile overlaps original film home")
        return root
    finally:
        ole=C.WinDLL("ole32")
        ole.CoTaskMemFree.argtypes=[W.LPVOID]
        ole.CoTaskMemFree(C.cast(location,W.LPVOID))


def _profile_inventory(folder):
    """Fail closed on unreviewed profile writes, not just scratch cwd writes."""
    result={}
    if not folder.exists():
        raise AppContainerFailure("Kernel AppContainer profile disappeared")
    seen=0
    for item in folder.rglob("*"):
        if item.is_symlink():
            raise AppContainerFailure("Sandbox profile contains reparse link")
        if item.is_dir():
            continue
        if not item.is_file():
            raise AppContainerFailure("Unexpected sandbox profile object")
        seen+=1
        stat=item.stat()
        if seen>1000 or stat.st_size>64*1024*1024:
            raise AppContainerFailure("Unbounded sandbox profile data")
        data=item.read_bytes()
        result[item.relative_to(folder).as_posix()]=(
            len(data),hashlib.sha256(data).hexdigest())
    return result


class AppContainerJobProcess:
    def __init__(self,wrapped,profile,sid,grants,userenv,profile_folder,baseline):
        self._worker=wrapped
        self._profile=profile
        self._sid=sid
        self._grants=grants
        self._userenv=userenv
        self._profile_folder=profile_folder
        self._baseline=baseline
        self.pid=wrapped.pid
        self.returncode=None
        self.sandbox_identity="windows-appcontainer-with-zero-network-capabilities"
    def poll(self):
        result=self._worker.poll()
        if result is not None:self.returncode=result
        return result
    def wait(self,timeout=None):
        result=self._worker.wait(timeout=timeout)
        self.returncode=result
        return result
    def terminate_tree(self):
        self._worker.terminate_tree()
    def close(self):
        if self._worker is None:return
        try:
            if self._worker.poll() is None:
                self._worker.terminate_tree()
            self._worker.close()
        finally:
            self._worker=None
            errors=[]
            try:
                if _profile_inventory(self._profile_folder)!=self._baseline:
                    errors.append("Native worker wrote AppContainer profile data")
            except Exception as exc:
                errors.append(str(exc))
            for path,recursive in reversed(self._grants):
                try:_acl(path,self._sid,"",recursive,remove=True)
                except Exception as exc:errors.append(str(exc))
            result=self._userenv.DeleteAppContainerProfile(self._profile)&0xffffffff
            if errors or result:
                raise AppContainerFailure("AppContainer teardown not independently established")

def launch_appcontainer(command,*,cwd,stdin,stdout,stderr,memory_mb,env,
                        code_roots,code_files):
    """Create real AppContainer token + restricted pipes + suspended Job.

    Code roots MUST contain reviewed standalone binaries only, never a film
    workspace or personal data. No capabilities (network, camera, etc) granted.
    """
    exe,work,roots,files=_paths(command,cwd,code_roots,code_files)
    if (type(memory_mb) is not int or not 128<=memory_mb<=65536
            or any(f is None or not hasattr(f,"fileno") for f in (stdin,stdout,stderr))):
        raise AppContainerFailure("Bounded native pipes and Job limit required")
    import msvcrt,pywintypes,win32job,win32process
    from backend.nvp_worker_containment import WindowsJobProcess
    kernel,userenv,advapi=_api()
    profile="NVP-Film-"+secrets.token_hex(12)
    sidptr=W.LPVOID()
    hr=userenv.CreateAppContainerProfile(profile,profile,"NVP private film worker",
                                           None,0,C.byref(sidptr))&0xffffffff
    if hr:raise AppContainerFailure("CreateAppContainerProfile 0x%08x"%hr)
    sidstr=W.LPWSTR()
    grants=[];job=None;ph=None;thread=None;attrs=None;initialized=False
    try:
        if not advapi.ConvertSidToStringSidW(sidptr,C.byref(sidstr)):
            _check("Read AppContainer SID")
        sid=sidstr.value
        if not sid or not sid.startswith("S-1-15-2-"):
            raise AppContainerFailure("Not a package SID")
        profile_folder=_profile_folder(userenv,sid)
        baseline=_profile_inventory(profile_folder)
        # Traverse-only on ancestors; recursive RX ONLY for trusted binary
        # distributions and exact read access ONLY for a vetted worker script.
        for root in roots:
            _acl(root,sid,"(OI)(CI)RX",recursive=True);grants.append((root,True))
        for file in files:
            _acl(file,sid,"R");grants.append((file,False))
        visited=set()
        for item in [work]+[x.parent for x in roots+files]:
            for folder in [item]+list(item.parents):
                if folder==folder.parent or folder in visited:continue
                visited.add(folder)
                _acl(folder,sid,"(OI)(CI)M" if folder==work else "RX")
                grants.append((folder,False))
        # Workspace is disposable and writable only for this package SID.
        # It must carry low mandatory integrity as AppContainer is Low-IL.
        integrity=subprocess.run(["icacls",str(work),"/setintegritylevel",
                                  "(OI)(CI)L"],capture_output=True,text=True,
                                 timeout=30)
        if integrity.returncode:
            raise AppContainerFailure("Disposable cwd low-integrity label failed")
        handles=[msvcrt.get_osfhandle(x.fileno()) for x in (stdin,stdout,stderr)]
        original=[os.get_handle_inheritable(h) for h in handles]
        try:
            for h in handles:os.set_handle_inheritable(h,True)
            size=C.c_size_t()
            kernel.InitializeProcThreadAttributeList(None,2,0,C.byref(size))
            if C.get_last_error()!=122 or size.value<64:
                _check("Size STARTUPINFOEX attributes")
            attrs=C.create_string_buffer(size.value)
            if not kernel.InitializeProcThreadAttributeList(attrs,2,0,C.byref(size)):
                _check("Initialize STARTUPINFOEX attributes")
            initialized=True
            caps=_Caps(sidptr,None,0,0) # no network capability
            if not kernel.UpdateProcThreadAttribute(attrs,0,0x20009,
                     C.byref(caps),C.sizeof(caps),None,None):
                _check("Apply AppContainer security capabilities")
            allowed=(W.HANDLE*3)(*handles)
            if not kernel.UpdateProcThreadAttribute(attrs,0,0x20002,
                     allowed,C.sizeof(allowed),None,None):
                _check("Restrict inherited handles")
            si=_StartupEx()
            si.StartupInfo.cb=C.sizeof(_StartupEx)
            si.StartupInfo.dwFlags=0x100
            si.StartupInfo.hStdInput=handles[0]
            si.StartupInfo.hStdOutput=handles[1]
            si.StartupInfo.hStdError=handles[2]
            si.lpAttributeList=C.cast(attrs,W.LPVOID)
            argv=C.create_unicode_buffer(subprocess.list2cmdline(command))
            clean=dict(env or {})
            clean.update({"TEMP":str(work),"TMP":str(work),
                          "PYTHONDONTWRITEBYTECODE":"1"})
            block=C.create_unicode_buffer("\0".join(
                key+"="+value for key,value in sorted(clean.items()))+"\0\0")
            pi=_ProcessInfo()
            flags=0x4|0x08000000|0x400|0x80000
            if not kernel.CreateProcessW(str(exe),argv,None,None,True,flags,
                   C.cast(block,W.LPVOID),str(work),C.byref(si),C.byref(pi)):
                _check("CreateProcessW AppContainer")
            ph=pywintypes.HANDLE(pi.hProcess.value)
            thread=pywintypes.HANDLE(pi.hThread.value)
            job=win32job.CreateJobObject(None,"NVP-AC-"+secrets.token_hex(10))
            info=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
            info["BasicLimitInformation"]["LimitFlags"]|=0x2000|0x200
            info["JobMemoryLimit"]=memory_mb*1024*1024
            win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,info)
            win32job.AssignProcessToJobObject(job,ph)
            if not win32job.IsProcessInJob(ph,job):
                raise AppContainerFailure("Suspended child not in kernel Job")
            if win32process.ResumeThread(thread)==0xffffffff:
                raise AppContainerFailure("AppContainer child resume failed")
            wrapped=WindowsJobProcess(job,ph,pi.dwProcessId)
            ph=None;job=None
            return AppContainerJobProcess(wrapped,profile,sid,grants,userenv,
                                          profile_folder,baseline)
        finally:
            for handle,inherit in zip(handles,original):
                os.set_handle_inheritable(handle,inherit)
    except BaseException:
        if job is not None:
            try:win32job.TerminateJobObject(job,13)
            except Exception:pass
            job.Close()
        if ph is not None:ph.Close()
        for path,recursive in reversed(grants):
            try:_acl(path,sidstr.value or "","",recursive,remove=True)
            except Exception:pass
        userenv.DeleteAppContainerProfile(profile)
        raise
    finally:
        if thread is not None:thread.Close()
        if initialized:kernel.DeleteProcThreadAttributeList(attrs)
        if sidstr:kernel.LocalFree(sidstr)
        if sidptr:advapi.FreeSid(sidptr)
