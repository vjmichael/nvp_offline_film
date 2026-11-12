"""W1-G protected first-party native executable admission and execution.

Installed runtime's reviewed worker roster pins executable SHA, architecture
and role. The native host constructs one sealed plan and supplies a real
one-use human authorization. Launch uses the existing Windows suspended
Job Object / mandatory Linux cgroup-v2 path. A log, PID or return code alone
is NEVER a verified result. No browser/model executable or filesystem path.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading
import time

from backend.nvp_worker_containment import launch_contained
from tools.nvp_w1g_worker_package import verify_native_workers
from tools.nvp_w1g_native_package import _digest

JOB = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{5,79}$")
ROLES = {"original_capture", "scene_render", "editorial", "audio", "delivery"}
FORMAT = "nvp.w1g.protected_worker_execution.v1"


def _atomic_json(path, doc):
    temp = path.with_suffix(".new")
    if temp.exists() or temp.is_symlink():
        raise RuntimeError("Pending native worker journal update unresolved")
    with temp.open("x", encoding="utf8") as sink:
        json.dump(doc, sink, sort_keys=True, separators=(",", ":"))
        sink.flush()
        os.fsync(sink.fileno())
    os.replace(temp, path)


class ProtectedNativeWorker:
    def __init__(self, bundle: Path, runtime: Path, *, platform: str,
                 native_approve, independent_verify, independent_os_custody):
        if (not callable(native_approve) or not callable(independent_verify) or
            not callable(independent_os_custody)):
            raise TypeError("Trusted native consent and independent result verifier required")
        self.bundle=Path(bundle)
        self.runtime=Path(runtime)
        self.platform=platform
        self.approve=native_approve
        self.verify=independent_verify
        self.kernel_custody=independent_os_custody
        if (self.bundle.is_symlink() or not self.bundle.is_dir() or
            self.runtime.is_symlink() or not self.runtime.is_dir() or
            self.runtime.resolve().is_relative_to(self.bundle.resolve())):
            raise RuntimeError("Worker runtime must be disjoint from installed executables")
        verify_native_workers(self.bundle, expected_platform=platform)
        self.directory=self.bundle/"_internal"/"nvp_workers"
        self.roster=json.loads((self.directory/"manifest.json").read_text("utf8"))
        self._guard=threading.RLock()
        self._active={}

    def _binary(self, role):
        if role not in ROLES:
            raise ValueError("Unrecognized native worker capability")
        matches=[w for w in self.roster["workers"] if w["role"]==role]
        if len(matches)!=1:
            raise PermissionError("Requested native worker role is not provisioned")
        worker=matches[0]
        path=self.directory/worker["filename"]
        if path.is_symlink() or _digest(path)!=worker["sha256"]:
            raise RuntimeError("Installed native executable no longer matches reviewed SHA")
        return path,worker["sha256"]

    def run(self, role: str, project_id: str, plan: dict, *,
            memory_mb: int = 4096, timeout_s: int = 600):
        if (type(plan) is not dict or type(project_id) is not str or
            not 1<=len(project_id)<=120 or
            type(memory_mb) is not int or not 512<=memory_mb<=32768 or
            type(timeout_s) is not int or not 5<=timeout_s<=3600):
            raise ValueError("Invalid finite native worker invocation")
        # A worker receives only its sealed first-party plan; no freeform
        # shell arguments, runtime script path or user-supplied executable.
        if plan.get("project_id")!=project_id or plan.get("role")!=role:
            raise ValueError("Native execution plan has a foreign project/role")
        binary,binary_sha=self._binary(role)
        job="w1g_"+secrets.token_hex(12)
        sealed_plan={**plan,"job_id":job}
        raw=json.dumps(sealed_plan, sort_keys=True, separators=(",", ":"),allow_nan=False).encode("ascii")
        if len(raw)>1024*1024:
            raise ValueError("Unbounded native task plan")
        digest=sha256(raw).hexdigest()
        directory=self.runtime/job
        if directory.exists() or directory.is_symlink():
            raise RuntimeError("Duplicate native worker task ID")
        scope={
            "operation":"nvp.native.protected_worker.execute.v1",
            "job_id":job, "project_id":project_id,
            "role":role, "worker_sha256":binary_sha,
            "plan_sha256":digest,"memory_mb":memory_mb,
            "timeout_seconds":timeout_s,
        }
        if self.approve(dict(scope)) is not True:
            raise PermissionError("Native creator refused exact worker execution")
        if self._binary(role)!=(binary,binary_sha):
            raise RuntimeError("Reviewed native worker changed during approval")
        directory.mkdir(mode=0o700)
        sealed=directory/"plan.json"
        with sealed.open("xb") as fd:
            fd.write(raw);fd.flush();os.fsync(fd.fileno())
        state={"format":FORMAT, **scope,"state":"PREPARED",
               "process_tree_custody_verified":False,
               "output_independently_verified":False}
        journal=directory/"journal.json"
        _atomic_json(journal,state)
        proc=None
        try:
            with (directory/"stdout.log").open("wb") as out, (
                    directory/"stderr.log").open("wb") as err:
                # Linux requires real delegated cgroup tree custody.
                proc=launch_contained(
                    [str(binary.resolve()),"--plan",str(sealed.resolve())],
                    cwd=str(directory),stdout=out,stderr=err,
                    memory_mb=memory_mb,linux_cgroup_tree_required=True)
                with self._guard:
                    self._active[job]=proc
                state["state"]="RUNNING";state["worker_pid"]=proc.pid
                _atomic_json(journal,state)
                try:
                    rc=proc.wait(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    proc.terminate_tree()
                    state["state"]="TIMED_OUT_UNVERIFIED"
                    _atomic_json(journal,state)
                    raise RuntimeError("Protected native worker exceeded time bound")
                if rc!=0:
                    raise RuntimeError("Native worker returned failure exit code")
                # Kernel custody and no descendants must be verified before
                # arbitrary worker receipt bytes may ever be accepted.
                proc.close()
                kernel=self.kernel_custody(dict(scope),proc)
                if (type(kernel) is not dict or
                    kernel.get("process_tree_custody_verified") is not True or
                    kernel.get("os_provenance") not in ("windows-job-object","linux-cgroup-v2") or
                    kernel.get("worker_pid")!=proc.pid):
                    raise RuntimeError("Independent OS process-tree custody remains unverified")
                if _digest(binary)!=binary_sha or _digest(sealed)!=digest:
                    raise RuntimeError("Pinned executable/task plan changed during execution")
                receipt=directory/"result.json"
                if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size>1024*1024:
                    raise RuntimeError("Native worker did not publish bounded result")
                result=json.loads(receipt.read_text("utf8"))
                if (type(result) is not dict or
                    result.get("job_id")!=job or
                    result.get("project_id")!=project_id or
                    result.get("plan_sha256")!=digest):
                    raise RuntimeError("Native result was not tied to exact authorized task")
                accepted=self.verify(dict(scope),dict(result),directory)
                if accepted is not True:
                    raise RuntimeError("Independent domain verification did not accept result")
                state["state"]="SUCCEEDED_VERIFIED"
                state["output_independently_verified"]=True
                state["process_tree_custody_verified"]=True
                state["os_custody_receipt"]=kernel
                state["result_sha256"]=_digest(receipt)
                _atomic_json(journal,state)
                return dict(state)
        except BaseException as error:
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.terminate_tree()
                    proc.close()
                except BaseException:
                    state["custody_uncertain"]=True
            if state["state"]!="TIMED_OUT_UNVERIFIED":
                state["state"]="FAILED_UNVERIFIED"
            state["failure_type"]=type(error).__name__
            _atomic_json(journal,state)
            raise
        finally:
            with self._guard:
                self._active.pop(job,None)

    def cancel(self, job_id):
        if type(job_id) is not str or not JOB.fullmatch(job_id):
            raise ValueError("Invalid native worker cancellation identity")
        with self._guard:
            active=self._active.get(job_id)
        if active is None:
            return False
        active.terminate_tree()
        return active.poll() is not None

    def reconcile(self):
        """No replay from PID/journal after host restart; OS evidence required."""
        unresolved=[]
        for directory in sorted(self.runtime.iterdir()):
            if not directory.is_dir() or directory.is_symlink() or not JOB.fullmatch(directory.name):
                continue
            journal=directory/"journal.json"
            if journal.is_symlink() or not journal.is_file():
                continue
            row=json.loads(journal.read_text("utf8"))
            if row.get("state") in ("PREPARED","RUNNING"):
                row["state"]="INTERRUPTED_OS_CUSTODY_UNVERIFIED"
                row["process_tree_custody_verified"]=False
                row["output_independently_verified"]=False
                _atomic_json(journal,row)
                unresolved.append(directory.name)
        return {"status":"RESTART_RECOVERY_REQUIRES_OS_CUSTODY",
                "unresolved_job_ids":unresolved}
