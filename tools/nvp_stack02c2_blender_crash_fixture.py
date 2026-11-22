"""STACK-02C2B: REAL Blender + detached descendant + hard NVP host exit.

Run only inside an established systemd delegated user scope (Delegate=yes,
DelegateSubgroup=nvp.host). An actual Blender 5.2.3 executable starts a
separately-sessioned /usr/bin/sleep; the supervising Python host calls
os._exit(37) while Blender is running; a separate process verifies both
PIDs died, the cgroup leaf vanished, and FilmIndex worker journal recovers
INTERRUPTED rather than accepting abandoned output.

This is an intentionally destructive, bounded CI fixture. Do not invoke on
unrelated processes or a user's active project.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

from backend.nvp_blender_worker import (
    BlenderOperation, BlenderWorkerSupervisor, sha_file,
)

BYPY_SCRIPT=r'''import bpy, json, os, shutil, subprocess, sys, time
from pathlib import Path
opts=dict(zip(sys.argv[sys.argv.index("--")+1::2],sys.argv[sys.argv.index("--")+2::2]))
sleeper=shutil.which("sleep")
if not sleeper or not os.path.isabs(sleeper):
    raise RuntimeError("Trusted Linux 'sleep' binary not found")
child=subprocess.Popen([sleeper,"90"],stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
    close_fds=True,start_new_session=True)
group=next(line[3:] for line in Path("/proc/self/cgroup").read_text().splitlines()
           if line.startswith("0::"))
Path(opts["--audit"]).write_text(json.dumps({
    "passed":True,"format":"nvp.stack02c2.actual_blender.hardcrash.v1",
    "blender_pid":os.getpid(),"detached_descendant":child.pid,
    "worker_cgroup":group,"blender":bpy.app.version_string,
},sort_keys=True))
time.sleep(90)
'''


def _version(binary):
    return subprocess.run([str(binary),"-b","--version"],
        capture_output=True,text=True,timeout=15,check=True).stdout.splitlines()[0].strip()


def host(root,blender):
    root=Path(root).resolve()
    binary=Path(blender).resolve()
    version=_version(binary)
    workspace=root/"worker"
    sup=BlenderWorkerSupervisor(workspace,blender_executable=binary,
        blender_sha256=sha_file(binary),blender_version=version)
    jobdir=workspace/"real_blender_hardcrash"
    jobdir.mkdir()
    (jobdir/"trusted_script.py").write_text(BYPY_SCRIPT,"utf8")
    marker="real_blender_tree.json"
    op=BlenderOperation(job_id=jobdir.name,script="trusted_script.py",
        script_sha256=sha_file(jobdir/"trusted_script.py"),inputs={},
        outputs={marker:"json_audit"},arguments={"--audit":marker},
        memory_limit_mb=4096,timeout_seconds=135,require_linux_cgroup_v2=True)
    thread=threading.Thread(target=sup.run,args=(op,),daemon=True)
    thread.start()
    evidence=jobdir/marker
    ready=False
    for _ in range(1000):
        if evidence.is_file():
            try:
                d=json.loads(evidence.read_text("utf8"))
                ready=(d.get("passed") is True and
                       type(d.get("blender_pid")) is int and
                       type(d.get("detached_descendant")) is int)
                if ready and sup.inspect(op.job_id)["state"]=="RUNNING":
                    break
            except (OSError,ValueError,KeyError):
                pass
        if not thread.is_alive():break
        time.sleep(.05)
    if not ready:
        try:
            info=sup.inspect(op.job_id)
            sys.stderr.write("Actual Blender strict worker failure: "+str(info)+"\n")
        except KeyError:
            sys.stderr.write("Strict Blender worker never created journal\n")
        os._exit(69)
    # The independently acknowledged output exists, but the OS worker is
    # STILL running; no normal cancellation or finally code will execute.
    os._exit(37)


def running(pid):
    path=Path(f"/proc/{pid}/stat")
    try:
        return path.read_text("utf8").rsplit(")",1)[1].split()[0] not in ("Z","X","x")
    except FileNotFoundError:
        return False


def fixture(root,blender):
    if sys.platform!="linux":
        raise RuntimeError("This kernel hard-crash test is Linux only")
    root=Path(root).resolve()
    root.mkdir(parents=True,exist_ok=True)
    exe=Path(shutil.which(blender) or blender).resolve()
    if not exe.is_file():
        raise RuntimeError("Real Blender binary missing")
    env=dict(os.environ)
    env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])+os.pathsep+env.get("PYTHONPATH","")
    args=[sys.executable,"-m","tools.nvp_stack02c2_blender_crash_fixture",
          "--host","--out",str(root),"--blender",str(exe)]
    process=subprocess.Popen(args,cwd=str(root),env=env,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    marker=root/"worker"/"real_blender_hardcrash"/"real_blender_tree.json"
    data={}
    try:
        stdout,stderr=process.communicate(timeout=85)
        if process.returncode!=37:
            raise RuntimeError("Native Blender host did not reach deliberate hard-exit: "+
                               stderr.decode("utf8",errors="replace")[-4000:])
        data=json.loads(marker.read_text("utf8"))
        ids=[data["blender_pid"],data["detached_descendant"]]
        if (not all(type(pid) is int and pid>1 for pid in ids) or ids[0]==ids[1] or
            not data["worker_cgroup"].split("/")[-1].startswith("nvp-worker-")):
            raise RuntimeError("No authentic Blender + detached NVP cgroup membership")
        full=Path("/sys/fs/cgroup")/data["worker_cgroup"].lstrip("/")
        for _ in range(300):
            if all(not running(pid) for pid in ids) and not full.exists():
                break
            time.sleep(.05)
        if any(running(pid) for pid in ids) or full.exists():
            raise RuntimeError("cgroup guardian did not reap real Blender, detached descendant and leaf")
        supervisor=BlenderWorkerSupervisor(root/"worker",
            blender_executable=exe,blender_sha256=sha_file(exe),
            blender_version=_version(exe))
        changed=supervisor.recover_interrupted()
        if changed!=["real_blender_hardcrash"]:
            raise RuntimeError("Crashed Blender journal was not reconciled as INTERRUPTED")
        status=supervisor.inspect("real_blender_hardcrash")
        if status["state"]!="INTERRUPTED" or status["outputs"] is not None:
            raise RuntimeError("Abandoned Blender outputs were incorrectly accepted")
        try:
            supervisor.verify_completed("real_blender_hardcrash")
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Abandoned real Blender job was verified successfully")
        result={
            "format":"nvp.stack02c2.real.blender.crash.acceptance.v1",
            "status":"actual_blender_and_detached_descendant_killed_on_hard_host_exit",
            "blender_version":data["blender"],
            "blender_executable_sha256":sha_file(exe),
            "blender_pid":ids[0],"detached_descendant_pid":ids[1],
            "host_exit_code":process.returncode,
            "worker_cgroup":data["worker_cgroup"],
            "guardian_removed_leaf":True,
            "both_os_processes_terminated":True,
            "reopened_journal_state":"INTERRUPTED",
            "untrusted_output_accepted":False,
            "source_take_scope":"Not part of this worker-containment test",
            "creative_approval":False,
        }
        (root/"real_blender_hardcrash_report.json").write_text(
            json.dumps(result,indent=2,sort_keys=True),"utf8")
        return result
    finally:
        if process.poll() is None:
            process.kill();process.wait()
        for pid in (data.get("blender_pid"),data.get("detached_descendant")):
            if type(pid) is int and running(pid):
                try:os.kill(pid,signal.SIGKILL)
                except ProcessLookupError: pass


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--host",action="store_true")
    parser.add_argument("--out",required=True)
    parser.add_argument("--blender",default="blender")
    args=parser.parse_args()
    if args.host:host(args.out,args.blender)
    else:print(json.dumps(fixture(args.out,args.blender),indent=2,sort_keys=True))
