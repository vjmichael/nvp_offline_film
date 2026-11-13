"""Native-only P1-A process-custody probes. Never opens an audio device.

The worker creates a truly detached descendant. On Linux the descendant also
tries to migrate itself to the delegated parent cgroup by writing cgroup.procs;
only kernel denial is acceptable. Host-crash simulates ungraceful desktop
termination without finally blocks, so guardian/Job cleanup is independent.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent.parent


def native_descendant(output):
    output=Path(output)
    if sys.platform=="linux":
        for entry in Path("/proc/self/cgroup").read_text("utf8").splitlines():
            if entry.startswith("0::"):
                before=entry[3:]
                break
        else:
            raise RuntimeError("No cgroup v2 for native migration fixture")
        parent=Path("/sys/fs/cgroup")/before.lstrip("/")
        ancestor=parent.parent/"cgroup.procs"
        try:
            # This is an actual kernel migration write, NOT os.access() or
            # a simulated filesystem. The worker must remain inside its leaf.
            with ancestor.open("w",encoding="ascii") as out:
                out.write(str(os.getpid()))
            verdict={"attempt":"MIGRATED","errno":0}
        except OSError as exc:
            verdict={"attempt":"DENIED","errno":exc.errno}
        for entry in Path("/proc/self/cgroup").read_text("utf8").splitlines():
            if entry.startswith("0::"):
                verdict["after"]=entry[3:]
                break
        verdict["before"]=before
        (output/"ancestor-migration.json").write_text(json.dumps(verdict),"utf8")
    (output/"descendant.pid").write_text(str(os.getpid()),"ascii")
    (output/"descendant.ready").write_text(str(time.monotonic()),"ascii")
    while True:
        time.sleep(0.25)


def run_worker(output):
    output=Path(output)
    flags={}
    if os.name=="nt":
        flags["creationflags"]=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        flags["start_new_session"]=True
    subprocess.Popen(
        [sys.executable,str(Path(__file__).resolve()),"descendant",str(output)],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,close_fds=True,**flags)
    (output/"worker.pid").write_text(str(os.getpid()),"ascii")
    while True:
        time.sleep(0.25)


def crash_host(output):
    from backend.nvp_worker_containment import launch_contained
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    from backend.nvp_capture_recovery import OriginalCaptureJournal
    OriginalCaptureJournal(output.parent).begin(output,{
        "project_id":"P1NativeRecovery",
        "take_id":"InterruptedOriginalTake",
        "source_id":"OriginalMicSource",
        "scene_sha256":"a"*64,
        "camera_timeline_sha256":"b"*64,
        "sample_rate":48000,
    })
    script=Path(__file__).resolve()
    with (output/"host.log").open("wb") as logs:
        process=launch_contained(
            [sys.executable,str(script),"worker",str(output)],
            cwd=output,stdout=logs,stderr=logs,memory_mb=512,
            linux_cgroup_tree_required=True,
            linux_write_spool=output if sys.platform=="linux" else None)
        if sys.platform=="linux":
            (output/"leaf.path").write_text(str(process.cgroup),"utf8")
        (output/"producer.pid").write_text(str(process.pid),"ascii")
        end=time.monotonic()+12
        while not (output/"descendant.ready").exists():
            if process.poll() is not None or time.monotonic()>end:
                os._exit(80)
            time.sleep(0.05)
        # No finally, no process.close, no cgroup.kill, no Job termination.
        # Kernel handle closure or independent guardian must clean descendants.
        os._exit(79)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("role",choices=("worker","descendant","crash-host"))
    parser.add_argument("output")
    args=parser.parse_args(argv)
    if args.role=="worker":
        run_worker(args.output)
    elif args.role=="descendant":
        native_descendant(args.output)
    else:
        crash_host(args.output)


if __name__=="__main__":
    main()
