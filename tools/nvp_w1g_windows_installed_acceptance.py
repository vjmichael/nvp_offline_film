"""W1-G real installed Windows NVP.exe acceptance, OS Job Object controlled.

This runs the ACTUAL audited installed executable, not mocked PE headers:
create project in isolated scratch NVP_HOME, exit process tree under Job
Object, reopen project in a NEW installed process, then do WebView2 and
native data-first A/V smoke. Original creator projects remain unchanged.
No Docker, CI-only fake executable, network egress, or arbitrary command.

This is automated installed acceptance only, not physical human film review,
sustained-production, installer upgrade/rollback or license sign-off.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time

from backend.nvp_worker_containment import launch_contained
from backend.nvp_w1g_kernel_custody import verified_native_worker_exit
from tools.nvp_w1g_native_package import (
    verify_installed, original_film_snapshot, verify_original_films_preserved,
)

FORMAT="nvp.w1g.installed_windows_native_acceptance.v1"


def run_installed_windows_matrix(exe: Path, installed: Path, projects: Path,
                                 audited_receipt: dict, *, include_webview=True):
    if os.name!="nt":
        raise RuntimeError("W1-G genuine Windows acceptance requires actual Windows kernel")
    if (exe != installed/"NVP.exe" or
        exe.is_symlink() or not exe.is_file() or
        not projects.is_dir() or projects.is_symlink()):
        raise RuntimeError("Trusted dedicated install and original film directory required")
    first=verify_installed(audited_receipt,installed)
    originals=original_film_snapshot(projects)
    results=[]
    with tempfile.TemporaryDirectory(prefix="nvp-w1g-install-") as scratch:
        home=Path(scratch)/"OriginalProjectsTest"
        home.mkdir()
        # The original contained launcher inherits this host environment.
        # Do not overwrite user NVP_HOME, project data or global PATH.
        previous=os.environ.get("NVP_HOME")
        os.environ["NVP_HOME"]=str(home)
        try:
            modes=["--smoke-create","--smoke-reopen"]
            if include_webview:
                # The first-time Edge WebView2 cold-start is separately
                # tested as a real React mount before exercising the large
                # 23-method native camera+film JS IPC bridge.
                modes.extend([
                    "--smoke-window-basic",
                    "--smoke-window",
                    "--smoke-data-av",
                ])
            for index,mode in enumerate(modes):
                if verify_installed(audited_receipt,installed) != first:
                    raise RuntimeError("NVP installed executable changed before next native smoke")
                out=Path(scratch)/f"run{index}_stdout.log"
                err=Path(scratch)/f"run{index}_stderr.log"
                diagnostic=Path(scratch)/f"run{index}_native_stage.txt"
                os.environ["NVP_SMOKE_DIAGNOSTIC_PATH"]=str(diagnostic)
                with out.open("wb") as stdout,err.open("wb") as stderr:
                    proc=launch_contained(
                        [str(exe.resolve()),mode],
                        cwd=str(installed),stdout=stdout,stderr=stderr,
                        memory_mb=4096,linux_cgroup_tree_required=False)
                    try:
                        deadline=(
                            120 if mode in ("--smoke-window-basic","--smoke-window")
                            else 180)
                        result=proc.wait(timeout=deadline)
                        if result!=0:
                            stages=(diagnostic.read_text("utf8")[-3000:]
                                    if diagnostic.is_file() else "no native stage receipts")
                            raise RuntimeError(
                                "Real Windows Job-owned installed NVP.exe "+
                                mode+" returned "+str(result)+
                                "; last native stages: "+stages)
                        kernel=verified_native_worker_exit(proc)
                    except BaseException as error:
                        # Preserve the last deterministic native stage in
                        # the Actions log before the test-owned scratch is
                        # discarded. No original creator material is read.
                        if diagnostic.is_file():
                            print(
                                "FAILED_JOB_NATIVE_STAGES "+
                                mode+"\n"+diagnostic.read_text("utf8")[-3000:],
                                flush=True)
                        try:proc.terminate_tree()
                        finally:proc.close()
                        raise
                results.append({
                    "mode":mode,"native_process_exit":0,
                    "os_custody":kernel,
                    "stdout_sha256":sha256(out.read_bytes()).hexdigest(),
                    "stderr_sha256":sha256(err.read_bytes()).hexdigest(),
                })
        finally:
            os.environ.pop("NVP_SMOKE_DIAGNOSTIC_PATH",None)
            if previous is None: os.environ.pop("NVP_HOME",None)
            else:os.environ["NVP_HOME"]=previous
    if verify_installed(audited_receipt,installed)["app_sha256"]!=first["app_sha256"]:
        raise RuntimeError("Installed program identity changed during real native launch")
    film_result=verify_original_films_preserved(originals,projects)
    return {
        "format":FORMAT,
        "status":"NATIVE_WINDOWS_INSTALLED_SOURCES_VERIFIED",
        "program_sha256":first["app_sha256"],
        "completed_modes":results,
        "original_project_file_count":film_result["original_files_verified"],
        "real_job_object_execution":True,
        "physical_owner_accepted":False,
        "nsis_upgrade_rollback_accepted":False,
        "sustained_thirty_minute_film_accepted":False,
        "encrypted_project_authorization_accepted":False,
    }


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--installed",required=True,type=Path)
    ap.add_argument("--projects",required=True,type=Path)
    ap.add_argument("--build-receipt",required=True,type=Path)
    ap.add_argument("--without-webview",action="store_true")
    ap.add_argument("--output",type=Path)
    args=ap.parse_args(argv)
    receipt=json.loads(args.build_receipt.read_text("utf8"))
    result=run_installed_windows_matrix(
        args.installed/"NVP.exe",args.installed,args.projects,receipt,
        include_webview=not args.without_webview)
    data=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if args.output:
        with args.output.open("x",encoding="utf8") as f:
            f.write(data)
    print(data)


if __name__=="__main__":
    main()
