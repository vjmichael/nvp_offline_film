"""NVP SYSTEM-READY-01 — native runtime/package discovery and approved repair.

NVP's normal user should NOT install Python, FFmpeg, FFprobe or a DLL
separately: the Windows NSIS installer bundles and hashes those binaries.
Missing machine components are inventoried, not assumed. Actual OS
package installation needs a physical NVP confirmation AND the OS package
manager's own authorization. No browser-controlled command, package name,
installer URL, shell, pip, Docker, surprise elevation, or third-party repo.
"""
from __future__ import annotations

import ctypes.util
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

FORMAT="nvp.system_ready.native_packages.v1"
SAFE_COMPONENTS=frozenset(("webview2","ffmpeg","linux_webkit"))
MAX_REPAIR_SECONDS=600
MIN_FREE_DISK_MB=1024

def _webview2_windows():
    if os.name!="nt":return False
    import winreg
    guid="{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    keys=(
        (winreg.HKEY_CURRENT_USER,
         chr(92).join(("Software","Microsoft","EdgeUpdate","Clients",guid))),
        (winreg.HKEY_LOCAL_MACHINE,
         chr(92).join(("SOFTWARE","WOW6432Node","Microsoft",
                       "EdgeUpdate","Clients",guid))),
        (winreg.HKEY_LOCAL_MACHINE,
         chr(92).join(("SOFTWARE","Microsoft","EdgeUpdate","Clients",guid))),
    )
    for hive,path in keys:
        try:
            with winreg.OpenKey(hive,path) as registry:
                text=str(winreg.QueryValueEx(registry,"pv")[0])
                if any(int(x) for x in text.split(".") if x.isdecimal()):
                    return True
        except (OSError,ValueError,TypeError):
            continue
    return False

def _linux_gui():
    # GTK/WebKit are system libraries, not pip packages. Never download
    # untrusted .so files or silently alter system Python/virtualenv.
    if not sys.platform.startswith("linux"):
        return False
    gtk=ctypes.util.find_library("gtk-3")
    webkit=ctypes.util.find_library("webkit2gtk-4.1")
    return bool(gtk and webkit and importlib.util.find_spec("gi"))

def _installed_binaries():
    from backend.nvp_index_time06_native_desktop import discover_video_tools
    pair=discover_video_tools()
    if pair is None:return False,False
    return all(Path(p).is_file() for p in pair),bool(
        getattr(sys,"frozen",False) and all(
            Path(p).is_file() for p in pair))

def _manager():
    if os.name=="nt":
        path=shutil.which("winget")
        return ("winget",str(Path(path).resolve())) if path else (None,None)
    if sys.platform.startswith("linux"):
        # Repair is initially automated only on Debian/Ubuntu using apt.
        # Other distros receive diagnostics rather than guessed commands.
        manager=Path("/usr/bin/apt-get")
        polkit=Path("/usr/bin/pkexec")
        if (manager.is_file() and not manager.is_symlink() and
            polkit.is_file() and not polkit.is_symlink()):
            return "apt+polkit",str(polkit)
    return None,None

def inventory(*,studio_path=None):
    """Safe read-only system inventory; never return absolute binary paths."""
    windows=os.name=="nt"
    linux=sys.platform.startswith("linux")
    try:media_ok,bundled=_installed_binaries()
    except (OSError,RuntimeError):media_ok,bundled=False,False
    try:webview_ok=_webview2_windows() if windows else _linux_gui() if linux else False
    except (ImportError,OSError,ValueError):webview_ok=False
    manager,_=_manager()
    free_mb=None
    if studio_path is not None:
        try:
            root=Path(studio_path)
            if not root.exists():root=root.parent
            free_mb=shutil.disk_usage(root).free//(1024*1024)
        except OSError:pass
    rows=[
        {"id":"video_tools","name":"FFmpeg and FFprobe",
         "status":"ready" if media_ok else "missing",
         "supplied_by":"NVP installer" if bundled else "system" if media_ok else "not found",
         "required":True,
         "repair":"reinstall_nvp" if windows else "ffmpeg" if manager and linux else None},
        {"id":"desktop_shell","name":"Windows WebView2" if windows else "Linux GTK/WebKit" if linux else "Supported desktop shell",
         "status":"ready" if webview_ok else "missing" if windows or linux else "unsupported",
         "supplied_by":"operating system" if webview_ok else "not found",
         "required":True,
         "repair":"webview2" if windows and manager else
                  "linux_webkit" if linux and manager else None},
        {"id":"disk_cache","name":"Temporary picture/sound review disk space",
         "status":"ready" if free_mb is not None and free_mb>=MIN_FREE_DISK_MB
                  else "low_space" if free_mb is not None else "unknown",
         "required":True,"free_mb":free_mb,
         "supplied_by":"local disk","repair":None},
    ]
    return {
        "format":FORMAT,"status":"READY" if all(
            x["status"]=="ready" for x in rows) else "ACTION_NEEDED",
        "platform":"windows" if windows else "linux" if linux else "unsupported",
        "components":rows,"manager_available":manager is not None,
        "auto_install":False,"os_authorization_required":True,
        "bundled_video_tools":bundled,
        "source_media_modified":False,
    }

def repair(component,*,confirm,studio_path=None):
    """Run only from a physically approved trusted desktop window.

    The caller cannot choose a command, package, repository, host URL,
    arbitrary installer, or elevation path. All approved commands are
    fixed at build time and pass through OS authentication.
    """
    if component not in SAFE_COMPONENTS or type(component) is not str:
        raise ValueError("Unknown NVP system component")
    if not callable(confirm):
        raise PermissionError("Native OS approval callback required")
    before=inventory(studio_path=studio_path)
    item=next((x for x in before["components"]
               if x["repair"]==component),None)
    if item is None:
        return {"format":FORMAT,"status":"NOT_REQUIRED_OR_UNSUPPORTED",
                "component":component,"source_media_modified":False}
    if not confirm(
        "NVP needs "+item["name"]+
        ". Install the missing operating-system package?\n"+
        "NVP will ask your OS package manager to install an exact known"+
        " package from its configured trusted repository.\n"+
        "This can require OS authentication and internet access.\n"+
        "No Python environment, footage, or film assembly will change."):
        return {"format":FORMAT,"status":"DECLINED",
                "component":component,"source_media_modified":False}
    manager,path=_manager()
    if component=="webview2" and os.name=="nt" and manager=="winget":
        # Microsoft Edge WebView2 is the only approved Windows runtime
        # action. Use official winget source and the exact Microsoft ID.
        command=[path,"install","--exact","--id",
                 "Microsoft.EdgeWebView2Runtime","--source","winget",
                 "--accept-package-agreements","--accept-source-agreements",
                 "--disable-interactivity"]
    elif component in ("ffmpeg","linux_webkit") and manager=="apt+polkit":
        names=(["ffmpeg"] if component=="ffmpeg" else
               ["libwebkit2gtk-4.1-0","gir1.2-webkit2-4.1",
                "gir1.2-gtk-3.0","python3-gi"])
        command=[path,"/usr/bin/apt-get","install","-y",*names]
    else:
        raise RuntimeError("No approved native OS package installer available")
    if not Path(command[0]).is_absolute() or Path(command[0]).is_symlink():
        raise RuntimeError("Untrusted system package manager location")
    try:
        finished=subprocess.run(
            command,cwd=str(Path.home()),stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            shell=False,timeout=MAX_REPAIR_SECONDS,check=False)
    except (OSError,subprocess.TimeoutExpired) as error:
        return {"format":FORMAT,"status":"FAILED_OR_TIMED_OUT",
                "component":component,"source_media_modified":False}
    after=inventory(studio_path=studio_path)
    fixed=any(x["repair"]!=component and (
        x["id"]=="desktop_shell" if component in ("webview2","linux_webkit")
        else x["id"]=="video_tools") and x["status"]=="ready"
        for x in after["components"])
    return {
        "format":FORMAT,
        "status":"INSTALLED" if finished.returncode==0 and fixed else
                  "RESTART_OR_RECHECK" if finished.returncode==0 else "FAILED",
        "component":component,
        "system_exit_code":finished.returncode,
        "source_media_modified":False,
    }
