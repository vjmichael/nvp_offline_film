"""PLAN-02-D3: genuine OS process-tree custody witness.

This CLI is executed by the grouped Windows/Linux native acceptance gate,
never exposed to NVP browser/model. It launches a real worker that spawns a
*detached* descendant heartbeat. It proves cancel AND abrupt host death stop
the descendant, using the kernel Job Object / strict cgroup v2 guardian.

No Linux delegation -> exit FAILURE (not a misleading process-group pass).
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time

from backend.nvp_worker_containment import launch_contained

REPORT="nvp.plan02d.real_native_process_tree_custody.v1"
MEMORY_MB=1024


def _wait_marker(path,timeout=12):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if path.exists() and path.stat().st_size:
            return
        time.sleep(.05)
    raise TimeoutError("Real descendant never demonstrated its heartbeat")


def _stable_after_custody(path):
    # A detached process writes and fsyncs a counter frequently. A stopped
    # heartbeat is one independently observed positive witness, not a
    # general-purpose OS orphan-inventory/attestation service.
    a=path.read_bytes()
    time.sleep(.75)
    b=path.read_bytes()
    if a!=b:
        raise RuntimeError("Detached grandchild continued after tree cleanup")
    return sha256(b).hexdigest()


def _write_scripts(root):
    child = root/"grandchild.py"
    child.write_text(
        "import os,sys,time\n"
        "from pathlib import Path\n"
        "p=Path(sys.argv[1])\n"
        "for i in range(10000):\n"
        " with p.open('ab') as f:\n"
        "  f.write(b'x');f.flush();os.fsync(f.fileno())\n"
        " time.sleep(.07)\n", encoding="utf8")
    launcher = root/"parent.py"
    launcher.write_text(
        "import os,sys,time,subprocess\n"
        "from pathlib import Path\n"
        "root=Path(sys.argv[1])\n"
        "flags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)\n"
        "p=subprocess.Popen([sys.executable,str(root/'grandchild.py'),"
        "str(root/'heartbeat')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
        "stderr=subprocess.DEVNULL,close_fds=True,"
        "start_new_session=os.name!='nt',creationflags=flags)\n"
        "Path(root/'descendant.pid').write_text(str(p.pid),encoding='ascii')\n"
        "time.sleep(40)\n", encoding="utf8")
    host = root/"crash_host.py"
    host.write_text(
        "import os,sys,time\n"
        "from pathlib import Path\n"
        "from backend.nvp_worker_containment import launch_contained\n"
        "root=Path(sys.argv[1]);stdout=(root/'host.stdout').open('wb');"
        "stderr=(root/'host.stderr').open('wb')\n"
        "proc=launch_contained([sys.executable,str(root/'parent.py'),str(root)],"
        "cwd=str(root),stdout=stdout,stderr=stderr,memory_mb=1024,"
        "linux_cgroup_tree_required=sys.platform=='linux')\n"
        "limit=time.monotonic()+12\n"
        "while time.monotonic()<limit and not (root/'heartbeat').exists():"
        "time.sleep(.05)\n"
        "if not (root/'heartbeat').exists():raise RuntimeError('no descendant')\n"
        "os._exit(47)\n", encoding="utf8")


def cancellation(root):
    root.mkdir()
    _write_scripts(root)
    heartbeat=root/"heartbeat"
    proc=None
    with (root/"cancel.stdout").open("wb") as out, (
            root/"cancel.stderr").open("wb") as err:
        try:
            proc=launch_contained(
                [sys.executable,str(root/"parent.py"),str(root)],
                cwd=str(root),stdout=out,stderr=err,
                memory_mb=MEMORY_MB,
                linux_cgroup_tree_required=sys.platform=="linux")
            _wait_marker(heartbeat)
            proc.terminate_tree()
        finally:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                finally:proc.close()
    return _stable_after_custody(heartbeat)


def crash(root):
    root.mkdir()
    _write_scripts(root)
    host=subprocess.Popen(
        [sys.executable,str(root/"crash_host.py"),str(root)],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        shell=False,close_fds=True)
    out,err=host.communicate(timeout=25)
    if host.returncode!=47:
        raise RuntimeError("Abrupt host-death witness failed: "+
                           err.decode("utf8",errors="replace")[-1600:])
    heartbeat=root/"heartbeat"
    _wait_marker(heartbeat)
    # Guardian (Linux) or the last Job handle (Windows) must reap the
    # escaped process even though the host did not call close().
    time.sleep(.8)
    return _stable_after_custody(heartbeat)


def run(report_path):
    path=Path(report_path)
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("Create NEW exact absolute process-tree witness report")
    if sys.platform=="linux":
        from backend.nvp_worker_linux_cgroup import current_delegated_parent
        current_delegated_parent() # no fallback to process group
    elif os.name!="nt":
        raise RuntimeError("No accepted NVP native custody backend")
    with tempfile.TemporaryDirectory(prefix="nvp-plan02d-kernel-") as temp:
        root=Path(temp)
        cancel_sha=cancellation(root/"cancel")
        crash_sha=crash(root/"crash")
    evidence={
        "format":REPORT,
        "status":"ACTUAL_NATIVE_DESCENDANT_CANCEL_AND_HOST_CRASH_PASS",
        "os":sys.platform,
        "custody_backend":("windows_suspend_job_kill_on_close" if os.name=="nt"
                           else "linux_delegated_cgroup_v2_guardian"),
        "detached_descendant_observed":True,
        "cancel_heartbeat_stopped_sha256":cancel_sha,
        "crash_heartbeat_stopped_sha256":crash_sha,
        "untrusted_restart_outputs_automatically_accepted":False,
        "independent_general_orphan_inventory_claimed":False,
        "output_publication_authorized":False,
    }
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(evidence,sort_keys=True,indent=2),encoding="utf8")
    print("NVP_PLAN02D_NATIVE_TREE_CUSTODY_PASS="+sys.platform,flush=True)
    return evidence


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",required=True)
    args=parser.parse_args()
    run(args.report)
