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
import time

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
    k.GetSystemWindowsDirectoryW.argtypes=[W.LPWSTR,W.UINT]
    k.GetSystemWindowsDirectoryW.restype=W.UINT
    k.GetSystemDirectoryW.argtypes=[W.LPWSTR,W.UINT]
    k.GetSystemDirectoryW.restype=W.UINT
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
    args=["icacls.exe",str(path)]
    args += ["/remove:g","*"+sid] if remove else ["/grant","*"+sid+":"+permission]
    if recursive:
        args.append("/T")
    r=subprocess.run(args,capture_output=True,text=True,errors="replace",
                     timeout=120,check=False)
    # icacls prints "Failed processing 0 files" on SUCCESS. Match the
    # final explicit native counters, not the mere words "Failed processing".
    # Nonzero exit, nonzero failed count, missing/ambiguous summary or stderr
    # remain a hard refusal; do not infer success from exit code alone.
    summaries=re.findall(
        r"^Successfully processed (\d+) files?; Failed processing (\d+) files?\s*$",
        r.stdout,re.MULTILINE|re.IGNORECASE)
    valid_summary=(len(summaries)==1 and int(summaries[0][0])>0
                   and int(summaries[0][1])==0)
    if r.returncode or not valid_summary or r.stderr.strip():
        # Preserve the actual Windows failing object and error; a denied ACL
        # must never turn into an unsandboxed or more broadly granted launch.
        operation="remove" if remove else "grant "+permission
        # Retain both the leading diagnostic and final native summary;
        # a recursive installation grant can emit thousands of file lines.
        message=("stderr="+r.stderr.strip()[:350]+
                 "; stdout tail="+r.stdout.strip()[-500:])
        raise AppContainerFailure(
            f"Native AppContainer DACL operation failed ({operation}, "
            f"path={path}, exit={r.returncode}): {message}")

def _grant_scoped_access(work,roots,files,sid,grants):
    """Only exact reviewed runtime objects and this one disposable workspace.

    Do not grant RX on Program Files, user profile, or ancestors of the
    film. Normal Windows traversal and pre-existing OS permissions apply.
    If traversal/access is denied, native launch fails closed rather than
    taking ownership of a system directory or granting broad access.
    Register cleanup before each potentially partial recursive ACL operation.
    """
    for root in roots:
        grants.append((root,True))
        _acl(root,sid,"(OI)(CI)RX",recursive=True)
    for file in files:
        grants.append((file,False))
        _acl(file,sid,"R")
    grants.append((work,False))
    _acl(work,sid,"(OI)(CI)M")

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


def _host_windows_paths(kernel):
    """Read the host's machine and user locations from native OS APIs."""
    def directory(api,label):
        value=C.create_unicode_buffer(32768)
        size=api(value,len(value))
        if not 0<size<len(value):
            raise AppContainerFailure("Cannot resolve native "+label)
        return value.value

    windows=directory(kernel.GetSystemWindowsDirectoryW,"SystemRoot")
    system=directory(kernel.GetSystemDirectoryW,"system directory")
    # CSIDL_LOCAL_APPDATA resolves the current token's known folder, not
    # arbitrary LOCALAPPDATA supplied by the parent/caller environment.
    shell=C.WinDLL("shell32")
    shell.SHGetFolderPathW.argtypes=[W.HWND,C.c_int,W.HANDLE,W.DWORD,W.LPWSTR]
    shell.SHGetFolderPathW.restype=C.c_long
    local=C.create_unicode_buffer(260)
    if shell.SHGetFolderPathW(None,0x001c,None,0,local)&0xffffffff or not local.value:
        raise AppContainerFailure("Cannot resolve native LOCALAPPDATA")
    return windows,system,local.value


def _native_environment(kernel,work,profile_folder,env):
    """Build an explicit minimal Unicode environment for native lowbox creation.

    SystemRoot is necessary for Windows loader/side-by-side activation.
    CreateProcess also uses the user's actual LOCALAPPDATA to resolve and
    redirect the AppContainer profile. Neither is caller-overridable.
    Do not inherit a creator's PATH, credentials, Python/Blender search paths,
    drive working-directory entries or arbitrary environment variables.
    """
    work=work.resolve(strict=True)
    windows,system,local=(Path(x) for x in _host_windows_paths(kernel))
    packages=(local/"Packages").resolve()
    profile_root=profile_folder.resolve()
    if (any(not x.is_absolute() or not x.is_dir() or ";" in str(x)
            for x in (windows,system,local))
            or not windows.drive
            or not system.resolve().is_relative_to(windows.resolve())
            or profile_root==packages
            or not profile_root.is_relative_to(packages)):
        raise AppContainerFailure("Native Windows environment/profile paths unverified")
    clean={"SystemRoot":str(windows),"WINDIR":str(windows),
           "SystemDrive":windows.drive,
           "PATH":str(system)+";"+str(windows),
           "LOCALAPPDATA":str(local),
           "TEMP":str(work),"TMP":str(work),
           "PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"}
    # Historical protected Cycles caller may explicitly request its three
    # private configuration paths. Nothing else may be forwarded unchanged.
    blender={"BLENDER_USER_CONFIG":"config",
             "BLENDER_USER_SCRIPTS":"scripts",
             "BLENDER_USER_DATAFILES":"datafiles"}
    reserved={key.upper() for key in clean}
    seen=set()
    if env is not None and type(env) is not dict:
        raise AppContainerFailure("Invalid AppContainer environment")
    for key,value in (env or {}).items():
        if (type(key) is not str or type(value) is not str
                or not key or "\0" in key or "\0" in value or "=" in key):
            raise AppContainerFailure("Invalid AppContainer environment entry")
        name=key.upper()
        if name in seen:
            raise AppContainerFailure("Duplicate AppContainer environment entry")
        seen.add(name)
        if name in reserved:
            continue # Always use trusted values above, never caller overrides.
        if name not in blender:
            raise AppContainerFailure("Unreviewed AppContainer environment entry")
        target=work/blender[name]
        # Canonicalize DOS short names from temporary-directory callers,
        # but refuse a symlink/junction that would redirect the fixed target.
        if Path(value).resolve()!=target or target.resolve()!=target:
            raise AppContainerFailure("Unreviewed AppContainer environment path")
        clean[name]=str(target)
    # Windows environment names are case-insensitive; sort accordingly.
    return C.create_unicode_buffer("\0".join(
        key+"="+value for key,value in sorted(
            clean.items(),key=lambda item:item[0].upper()))+"\0\0")


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
        worker=self._worker
        self._worker=None
        errors=[]
        try:
            # Exact native Job accounting before publication; never treat
            # primary child exit as proof that descendants are gone.
            import win32job
            job=worker._job
            if job is None:
                raise AppContainerFailure("Native AppContainer Job unavailable")
            info=win32job.QueryInformationJobObject(
                job,win32job.JobObjectBasicAccountingInformation)
            if info["ActiveProcesses"]:
                win32job.TerminateJobObject(job,13)
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    info=win32job.QueryInformationJobObject(
                        job,win32job.JobObjectBasicAccountingInformation)
                    if info["ActiveProcesses"]==0:break
                    time.sleep(.03)
                if info["ActiveProcesses"]:
                    raise AppContainerFailure("Native AppContainer descendant remains active")
        except Exception as exc:
            errors.append("Native process custody: "+str(exc))
        finally:
            # On ANY failure to query the Job, closing its kernel handle
            # still invokes JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
            try:worker.close()
            except Exception as exc:errors.append("Job close: "+str(exc))
        try:
            if _profile_inventory(self._profile_folder)!=self._baseline:
                errors.append("Worker changed AppContainer profile file bytes")
        except Exception as exc:
            errors.append("Profile forensic audit: "+str(exc))
        for path,recursive in reversed(self._grants):
            try:_acl(path,self._sid,"",recursive,remove=True)
            except Exception as exc:errors.append("ACL recovery: "+str(exc))
        result=self._userenv.DeleteAppContainerProfile(self._profile)&0xffffffff
        if errors or result:
            raise AppContainerFailure(
                "AppContainer process/profile cleanup unverified; do not publish")


def launch_appcontainer(command,*,cwd,stdin,stdout,stderr,memory_mb,env,
                        code_roots,code_files,release_slot,original_journal,machine_codec_pin=None):
    """Create real AppContainer token + restricted pipes + suspended Job.

    Code roots MUST contain reviewed standalone binaries only, never a film
    workspace or personal data. No capabilities (network, camera, etc) granted.
    """
    exe,work,roots,files=_paths(command,cwd,code_roots,code_files)
    if machine_codec_pin is not None:
        from backend._nvp_wo5_release_pin import RELEASE_CODEC_MANIFEST_SHA256
        from backend.nvp_wo5_codec_provision import require_machine_codec_scope
        require_machine_codec_scope(roots,files,exe,pin=machine_codec_pin,
            compiled_pin=RELEASE_CODEC_MANIFEST_SHA256,frozen=getattr(sys,"frozen",False))
    if release_slot is None or original_journal is None:
        raise AppContainerFailure("Native AppContainer requires independent release slot and original durable journal")
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
        # No ACL mutation on protected machine or creator ancestors.
        # Exactly the reviewed runtime and one disposable job receive grants.
        # A frozen, independently pinned public codec release already has
        # machine-provisioned package RX. A standard-user host must not
        # mutate that DACL. Private media always retains the exact job SID.
        if machine_codec_pin is not None:
            require_machine_codec_scope(roots,files,exe,pin=machine_codec_pin,
                compiled_pin=RELEASE_CODEC_MANIFEST_SHA256,frozen=getattr(sys,"frozen",False))
        _grant_scoped_access(work,roots if machine_codec_pin is None else (),files,sid,grants)
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
            block=_native_environment(kernel,work,profile_folder,env)
            pi=_ProcessInfo()
            flags=0x4|0x08000000|0x400|0x80000
            if not kernel.CreateProcessW(str(exe),argv,None,None,True,flags,
                   C.cast(block,W.LPVOID),str(work),C.byref(si),C.byref(pi)):
                _check("CreateProcessW AppContainer")
            ph=pywintypes.HANDLE(int(pi.hProcess))
            thread=pywintypes.HANDLE(int(pi.hThread))
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
            # The suspended child is in the actual AppContainer Job and has
            # been resumed; the independent W1-G source journal must reach
            # RUNNING before publication or the Job is destroyed fail-closed.
            original_journal.started(pi.dwProcessId)
            wrapped=WindowsJobProcess(
                job,ph,pi.dwProcessId,release_slot=release_slot,
                original_journal=original_journal)
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
