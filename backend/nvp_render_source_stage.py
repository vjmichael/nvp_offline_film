"""NVP STACK-02C3B6: stage exact approved proxy world for native rendering.

Only a trusted NVP host component can use this operation: it is NOT a FastAPI
route and creates NO authorization, worker process, model task, or reservation.
An approved downstream dispatcher must recheck project proof, source hashes,
resource admission and native creator consent before any Blender execution.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets
import shutil

from backend.nvp_blender_worker import BlenderOperation,BlenderWorkerSupervisor,sha_file
from backend.nvp_render_preflight import _capture,preflight_scene,verify_scene_preflight
from backend.nvp_studio import Studio

WORLD_FILE="approved_manifest.json"
SCRIPT_FILE="trusted_scene_build.py"
OUTPUT_FILE="approved_scene.blend"


def _write_exclusive(directory:Path,name:str,content:bytes):
    target=directory/name
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    descriptor=os.open(target,flags,0o600)
    try:
        with os.fdopen(descriptor,"wb") as stream:
            descriptor=-1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor!=-1:
            os.close(descriptor)
    if target.is_symlink() or sha_file(target)!=hashlib.sha256(content).hexdigest():
        raise RuntimeError("Staged render source failed immutable file audit")
    return target


def stage_proxy_render_source(
    studio:Studio,supervisor:BlenderWorkerSupervisor,proof:dict,
    *,ram_mb:int=8192,gpu_mb:int=0,device_id:str|None=None,
    timeout_seconds:int=240,require_linux_cgroup_v2:bool=False,
):
    """Freeze two exact approved source files; return an inert typed job.

    The caller cannot specify an arbitrary script/path or job ID. Inputs
    originate solely from NVP approved project state. Do not expose this
    function over the unprivileged web API. No worker starts here.
    """
    if not isinstance(studio,Studio) or not isinstance(supervisor,BlenderWorkerSupervisor):
        raise TypeError("Trusted native NVP studio and supervisor required")
    if type(ram_mb) is not int or not 256<=ram_mb<=65536:
        raise ValueError("Invalid expected native Blender RAM budget")
    if type(gpu_mb) is not int or not 0<=gpu_mb<=65536:
        raise ValueError("Invalid expected GPU resource budget")
    if gpu_mb and (not isinstance(device_id,str) or not device_id):
        raise ValueError("GPU request needs verified native device identity")
    if type(timeout_seconds) is not int or not 1<=timeout_seconds<=600:
        raise ValueError("Invalid Blender execution timeout")
    if type(require_linux_cgroup_v2) is not bool:
        raise ValueError("Invalid strict OS containment request")

    # Never read package bytes from the HTTP receipt itself. The trusted
    # world, its generated Blender script, and all hashes are recomputed.
    verify_scene_preflight(studio,proof)
    original=_capture(studio,proof["project_id"],proof["scene_id"])
    if (original["world_sha256"]!=proof["world_sha256"] or
        original["script_sha256"]!=proof["blender_script_sha256"]):
        raise RuntimeError("Approved production source was modified before staging")

    root=supervisor.root
    if not root.is_dir() or root.is_symlink() or root.resolve()!=root:
        raise RuntimeError("Unsafe native worker root")
    job_id="proxy_"+secrets.token_hex(16)
    job_dir=root/job_id
    job_dir.mkdir(mode=0o700,exist_ok=False)

    try:
        _write_exclusive(job_dir,WORLD_FILE,original["source"])
        _write_exclusive(job_dir,SCRIPT_FILE,original["script"])
        operation=BlenderOperation(
            job_id=job_id,script=SCRIPT_FILE,
            script_sha256=proof["blender_script_sha256"],
            inputs={WORLD_FILE:proof["world_sha256"]},
            outputs={OUTPUT_FILE:"blend"},
            arguments={"--output":OUTPUT_FILE},
            timeout_seconds=timeout_seconds,memory_limit_mb=ram_mb,
            require_linux_cgroup_v2=require_linux_cgroup_v2,
            gpu_memory_mb=gpu_mb,gpu_device_id=device_id,
        )

        # Check contract at the same native worker boundary eventually used
        # by the authorized dispatcher, but DO NOT admit memory or run it.
        supervisor._validate(operation)
        # A second source check after fsync prevents accepting a stale staged
        # job if a director edits the world while files were being copied.
        verify_scene_preflight(studio,proof)
        if (sha_file(job_dir/WORLD_FILE)!=proof["world_sha256"] or
            sha_file(job_dir/SCRIPT_FILE)!=proof["blender_script_sha256"]):
            raise RuntimeError("Staged files no longer match exact render source")
        return {
            "format":"nvp.production.staged_proxy_render.v1",
            "operation":operation,
            "project_id":proof["project_id"],"scene_id":proof["scene_id"],
            "project_revision":proof["project_revision"],
            "world_revision":proof["world_revision"],
            "world_sha256":proof["world_sha256"],
            "blender_script_sha256":proof["blender_script_sha256"],
            "stage_dir":job_dir,
            "execution":"not_started",
            "native_approval":"not_granted",
            "resource_admission":"not_checked",
        }
    except BaseException:
        # No process is ever launched during this operation, so the
        # freshly created path contains only our inert staged source files.
        shutil.rmtree(job_dir)
        raise


def verify_staged_proxy_source(studio:Studio,supervisor:BlenderWorkerSupervisor,
                               staged:dict,proof:dict)->bool:
    """Recheck staged contents and *live* approved source before dispatch.

    This deliberately does not grant a task to ApprovedBlenderDispatcher.
    """
    if not isinstance(staged,dict) or staged.get("format")!="nvp.production.staged_proxy_render.v1":
        raise ValueError("Unknown staged proxy source")
    if staged.get("native_approval")!="not_granted" or staged.get("execution")!="not_started":
        raise PermissionError("Staged render source cannot grant native authorization")
    if staged.get("resource_admission")!="not_checked":
        raise PermissionError("Staged render source cannot claim admission")
    op=staged.get("operation")
    if not isinstance(op,BlenderOperation) or not isinstance(supervisor,BlenderWorkerSupervisor):
        raise TypeError("Native Blender operation required")
    if staged.get("stage_dir")!=supervisor.root/op.job_id:
        raise PermissionError("Staged source is not within the trusted worker root")
    if (staged.get("project_id"),staged.get("scene_id"),
        staged.get("project_revision"),staged.get("world_revision"),
        staged.get("world_sha256"),staged.get("blender_script_sha256"))!=(
        proof.get("project_id"),proof.get("scene_id"),
        proof.get("project_revision"),proof.get("world_revision"),
        proof.get("world_sha256"),proof.get("blender_script_sha256")):
        raise RuntimeError("Staged render source metadata does not match approved proof")
    if (op.script!=SCRIPT_FILE or op.script_sha256!=proof["blender_script_sha256"] or
        op.inputs!={WORLD_FILE:proof["world_sha256"]} or
        op.outputs!={OUTPUT_FILE:"blend"} or op.arguments!={"--output":OUTPUT_FILE}):
        raise RuntimeError("Staged render native operation changed")
    supervisor._validate(op)
    verify_scene_preflight(studio,proof)
    return True
