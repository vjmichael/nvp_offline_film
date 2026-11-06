"""Independent native INDEX-TIME-09 acceptance harness (no GitHub required).

Runs real source/audio/video and worker tests on the current machine, not
against mocks or a GitHub Actions status API. May additionally verify a
separately installed Windows NVP.exe using its bundled actual native worker.
This is an engineering QA harness; filmmakers should use the GUI directly.
Never touches camera footage; every test synthesizes originals in tempdirs.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


def _sha(path):
    h=sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(
        description="Independent off-GitHub native original A/V assembly acceptance")
    parser.add_argument("--installed-exe",type=Path,
                        help="Optional actual installed Windows NVP.exe; NEVER builds NSIS here")
    parser.add_argument("--report",type=Path,
                        help="Optional JSON audit report destination")
    args=parser.parse_args(argv)
    repo=Path(__file__).resolve().parents[1]
    evidence={
        "format":"nvp.index_time09.independent_native_acceptance.v1",
        "status":"UNVERIFIED",
        "started_at_utc":datetime.now(timezone.utc).isoformat(),
        "platform":platform.platform(),
        "python":platform.python_version(),
        "github_runner":bool(os.environ.get("GITHUB_ACTIONS")),
        "real_native_ffmpeg":None,
        "real_native_ffprobe":None,
        "tests":[],
        "installer":None,
        "source_camera_recordings_modified":False,
    }
    commands=[
        ("trusted_private_media_range",[
            sys.executable,"-m","unittest","discover","-s","tests",
            "-p","test_nvp_index_time09_media_range.py","-v"]),
        ("approved_package_discovery",[
            sys.executable,"-m","unittest","discover","-s","tests",
            "-p","test_nvp_system_packages.py","-v"]),
        ("original_vfr_av_proxy",[
        sys.executable,"-m","unittest","discover","-s","tests",
        "-p","test_nvp_index_time09_av_proxy.py","-v"]),
        ("frozen_original_editor",[
        sys.executable,"-m","unittest","discover","-s","tests",
        "-p","test_nvp_index_time07_assembly.py","-v"]),
        ("native_original_pts_review",[
        sys.executable,"-m","unittest","discover","-s","tests",
        "-p","test_nvp_index_time08_playback.py","-v"]),
    ]
    try:
        for name in ("ffmpeg","ffprobe"):
            path=shutil.which(name)
            if not path or Path(path).is_symlink() or not Path(path).is_file():
                raise RuntimeError("An actual installed native "+name+" is required")
            version=subprocess.run([path,"-version"],stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,timeout=20,check=True)
            evidence["real_native_"+name]={
                "path":str(Path(path).resolve()),
                "sha256":_sha(path),
                "version":version.stdout.decode("utf8","replace").splitlines()[0],
            }
        for label,cmd in commands:
            start=time.monotonic()
            run=subprocess.run(
                cmd,cwd=str(repo),stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                timeout=900,check=False)
            result={
                "name":label,"status":"PASSED" if run.returncode==0 else "FAILED",
                "returncode":run.returncode,
                "duration_seconds":round(time.monotonic()-start,3),
                "log_sha256":sha256(run.stdout+run.stderr).hexdigest(),
                "log_tail":(run.stdout+run.stderr).decode(
                    "utf8","replace")[-3000:],
            }
            evidence["tests"].append(result)
            if run.returncode:
                raise RuntimeError(label+" native acceptance failed")
        if args.installed_exe is not None:
            exe=args.installed_exe.resolve()
            if (os.name!="nt" or not exe.is_file() or exe.is_symlink() or
                exe.name.lower()!="nvp.exe"):
                raise RuntimeError("Installed acceptance needs an actual Windows NVP.exe")
            acceptance=[]
            for switch in ("--smoke-source","--smoke-window"):
                start=time.monotonic()
                p=subprocess.run([str(exe),switch],cwd=str(exe.parent),
                                 stdin=subprocess.DEVNULL,timeout=900,check=False)
                acceptance.append({
                    "command":switch,"exitcode":p.returncode,
                    "duration_seconds":round(time.monotonic()-start,3),
                })
                if p.returncode:
                    evidence["installer"]={
                        "exe_sha256":_sha(exe),"tests":acceptance,
                        "status":"FAILED",
                    }
                    raise RuntimeError("Real installed NVP "+switch+" failed")
            evidence["installer"]={
                "exe_sha256":_sha(exe),
                "tests":acceptance,"status":"PASSED",
                "note":"Automated actual installed EXE, NOT human clickthrough or a guarantee of real listener audio.",
            }
        evidence["status"]="PASSED"
    except BaseException as error:
        evidence["status"]="FAILED"
        evidence["failure"]=type(error).__name__+":"+str(error)[:320]
    finally:
        evidence["completed_at_utc"]=datetime.now(timezone.utc).isoformat()
        output=json.dumps(evidence,sort_keys=True,indent=2)
        if args.report:
            out=args.report.resolve()
            if out.is_symlink() or not out.parent.is_dir():
                raise PermissionError("Independent report needs trusted existing directory")
            out.write_text(output,encoding="utf8")
        print(output)
    return 0 if evidence["status"]=="PASSED" else 1


if __name__=="__main__":
    raise SystemExit(main())
