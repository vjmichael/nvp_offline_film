"""PLAN-03: native-approved one-shot original USD scene render, OS contained.

This host-only boundary consumes an *in-memory live* creator-reviewed
PLAN-02-D render intention plus a SECOND explicit OS render permission.
It launches only NVP's bundled trusted native raster module, never browser
or model commands, and verifies the derived PNG + independent source SHA.
Windows Job Object / Linux delegated cgroup-v2 are mandatory. The result is
a disposable derived source image, not a master or authority to export.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from backend.nvp_film_index import FilmIndex
from backend.nvp_plan02d_render_queue import DurableRenderIntentionQueue, APPROVED
from backend.nvp_worker_containment import launch_contained

RECEIPT_FORMAT="nvp.plan03.native_original_source_render_worker.v1"


def _sha(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as f:
        while part:=f.read(1024*1024):
            digest.update(part)
    return digest.hexdigest()


class NativeOriginalSceneRender:
    def __init__(self,index:FilmIndex,queue:DurableRenderIntentionQueue,
                 *,workspace:Path,ask_native,memory_mb=1024):
        if not isinstance(index,FilmIndex) or queue.index is not index:
            raise TypeError("Trusted source index and matching in-memory reviewed queue required")
        if not callable(ask_native):
            raise TypeError("Actual native OS render review callback required")
        self.root=Path(workspace)
        if (not self.root.is_absolute() or self.root.is_symlink() or
                self.root.is_relative_to(index.studio.db_path.resolve().parent)):
            raise PermissionError("Derived output workspace must be absolute, outside original source books")
        if type(memory_mb) is not int or not 256<=memory_mb<=65536:
            raise ValueError("Strict kernel memory budget required")
        self.index=index
        self.queue=queue
        self.ask_native=ask_native
        self.memory_mb=memory_mb

    def render_once(self,project_id:str,job_id:str,revision:int,
                    selection_sha256:str,source_tick:int,*,timeout=90):
        if (type(source_tick) is not int or type(timeout) is not int or
                not 1<=timeout<=180 or source_tick<0):
            raise ValueError("Bounded exact source time and worker timeout required")
        state=self.queue.inspect(project_id,job_id)
        if (state["revision"]!=revision or state["status"]!=APPROVED or
                state["selection_sha256"]!=selection_sha256):
            raise PermissionError("Source selection is not the exact approved revision")
        self.queue.require_live_worker_review(project_id,job_id,revision,selection_sha256)
        row,doc=self.queue._read(project_id,job_id)
        request=doc["selection"]
        selector=self.queue.selector
        scope=selector.preview(project_id,request)
        if (scope["selection_sha256"]!=selection_sha256 or
                not scope["first_tick"]<=source_tick<scope["last_tick_exclusive"]):
            raise PermissionError("Only live reviewed original source intervals")
        native_review={
            "operation":"nvp.plan03.render_original_source_once.v1",
            "project_id":project_id,"job_id":job_id,
            "review_revision":revision,
            "selection_sha256":selection_sha256,
            "take_document_sha256":scope["take_document_sha256"],
            "source_tick":source_tick,
            "memory_mb":self.memory_mb,
            "ffmpeg_used":False,
            "original_mutation_authorized":False,
            "cinema_master_published":False,
        }
        if self.ask_native(dict(native_review)) is not True:
            self.queue.consume_live_worker_review(project_id,job_id,revision,selection_sha256)
            raise PermissionError("Second native original-scene render consent refused")
        # Modals release the GUI thread. Revalidate exact source after consent,
        # then consume the one-use in-memory source review BEFORE launching.
        after=selector.preview(project_id,request)
        self.queue.consume_live_worker_review(project_id,job_id,revision,selection_sha256)
        if (after!=scope or self.queue.inspect(project_id,job_id)!=state):
            raise PermissionError("Source changed during native render authorization")
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        jobdir=self.root/("source_"+uuid.uuid4().hex)
        jobdir.mkdir(mode=0o700,exist_ok=False)
        manifest={
            "format":RECEIPT_FORMAT,"project_id":project_id,
            "request":request,"selection_sha256":selection_sha256,
            "source_tick":source_tick,
            "db_path":str(self.index.studio.db_path.resolve(strict=True)),
            "take_document_sha256":scope["take_document_sha256"],
        }
        raw=json.dumps(manifest,sort_keys=True,separators=(",",":"),
                       allow_nan=False).encode("utf8")
        path=jobdir/"source_manifest.json"
        with path.open("xb") as output:
            output.write(raw);output.flush();os.fsync(output.fileno())
        digest=_sha(path)
        if getattr(sys,"frozen",False):
            command=[str(Path(sys.executable).resolve(strict=True)),
                     "--plan03-original-render-worker","--manifest",str(path)]
        else:
            module=Path(__file__).resolve().parent.parent/"tools"/"nvp_plan03_original_render_worker.py"
            command=[str(Path(sys.executable).resolve(strict=True)),str(module),
                     "--manifest",str(path)]
        proc=None
        try:
            with (jobdir/"worker_stdout.log").open("xb") as stdout,(
                 jobdir/"worker_stderr.log").open("xb") as stderr:
                proc=launch_contained(command,cwd=str(jobdir),stdout=stdout,
                    stderr=stderr,memory_mb=self.memory_mb,
                    linux_cgroup_tree_required=sys.platform=="linux")
                try:
                    rc=proc.wait(timeout=timeout)
                    if rc!=0:
                        # The worker's own verified fail-closed exception was
                        # previously hidden when a TemporaryDirectory cleaned
                        # up on failure. Bound the trace to a private host
                        # diagnostic, never a browser-exposed process runner.
                        tail=(jobdir/"worker_stderr.log").read_bytes()[-2048:].decode(
                            "utf8","replace").replace("\\r"," ").replace("\\n"," ")
                        raise RuntimeError(
                            "Contained source renderer exited nonzero; native diagnostic: "+
                            tail[:1600])
                finally:
                    # Even a successful direct child may leave a detached
                    # descendant. Only OS custody cleanup closes the gate.
                    if proc.poll() is None:
                        proc.terminate_tree()
                    proc.close()
                    proc=None
            if _sha(path)!=digest:
                raise RuntimeError("Source render manifest modified during process execution")
            receipt_path=jobdir/"render_receipt.json"
            png=jobdir/"derived_source.png"
            if (receipt_path.is_symlink() or png.is_symlink() or
                    not receipt_path.is_file() or not png.is_file()):
                raise RuntimeError("Native renderer did not produce verified output")
            receipt=json.loads(receipt_path.read_text("utf8"))
            expected={
                "format":RECEIPT_FORMAT,
                "status":"DERIVED_OPENUSD_IMAGE_ONLY",
                "selection_sha256":selection_sha256,
                "project_id":project_id,
                "source_tick":source_tick,
                "take_document_sha256":scope["take_document_sha256"],
                "png_sha256":_sha(png),
                "png_bytes":png.stat().st_size,
                "creator_approval_conferred_by_child":False,
                "original_source_modified":False,
                "ffmpeg_used":False,
                "cinema_master_published":False,
            }
            if receipt!=expected:
                raise RuntimeError("Independent derived picture receipt mismatch")
            if not png.read_bytes().startswith(bytes.fromhex("89504e470d0a1a0a")):
                raise RuntimeError("Native source derivative is not a PNG")
            if selector.preview(project_id,request)!=scope:
                raise RuntimeError("Original source mutated during render")
            return {
                **receipt,
                "worker_process_tree_custody_verified":True,
                "custody_mode":("windows_job_object" if os.name=="nt"
                                else "linux_delegated_cgroup_v2"),
                "source_render_job_id":jobdir.name,
                "original_take_published":False,
                "original_source_immutable":True,
                "derived_image_path":str(png),
                "native_render_approval_observed_by_host":True,
            }
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                finally:
                    proc.close()
            # Leave logs and partial derivatives for review; never rewrite
            # original source or treat a failed renderer as accepted.
            raise
