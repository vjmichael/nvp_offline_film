"""PLAN-04: approved frozen OpenUSD -> actual Blender Cycles -> second-process audit.

This is host-only, not an arbitrary Blender/script/program runner. It consumes
the existing short-lived reviewed exact source selection, and a fresh one-use
creator OS decision covering the entire build+independent reopen. All code is
constant first-party NVP script, source is read from verified immutable
FilmIndex/Usd/PCM revisions, and all job outputs remain derived data.

This first production slice supports source-authoritative cube/sphere assets.
Skinned actor/MaterialX/complex Hydra paths require later distinct acceptance.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import threading

from backend.nvp_blender_worker import (
    BlenderOperation,BlenderWorkerSupervisor,sha_file)
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_plan02d_render_queue import DurableRenderIntentionQueue,APPROVED
from backend.nvp_plan04_cycles_scripts import (
    TRUSTED_CYCLES_SCRIPT,TRUSTED_REOPEN_SCRIPT)
from backend.nvp_studio import Studio

SOURCE_FORMAT="nvp.plan04.openusd_cycles_source.v1"


def _write_new(path:Path,data:bytes):
    if path.is_symlink() or path.exists() or len(data)>4*1024*1024:
        raise FileExistsError("Cannot replace a prior original/derived worker input")
    with path.open("xb") as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    return hashlib.sha256(data).hexdigest()


def _copy_verified(source:Path,target:Path):
    if source.is_symlink() or not source.is_file() or target.exists():
        raise RuntimeError("Independent Blender audit must read unmodified saved scene")
    expected=sha_file(source)
    with source.open("rb") as r, target.open("xb") as out:
        total=0
        while part:=r.read(1024*1024):
            total+=len(part)
            if total>512*1024*1024:
                raise RuntimeError("Blender scene exceeds native audit bounds")
            out.write(part)
        out.flush();os.fsync(out.fileno())
    if sha_file(target)!=expected:
        raise RuntimeError("Independent Blender .blend copy SHA differs")
    return expected


class OriginalCyclesProduction:
    """One reviewed source selection may start at most one Blender render."""

    def __init__(self,index:FilmIndex,queue:DurableRenderIntentionQueue,
                 blender:BlenderWorkerSupervisor,*,ask_native,cancel_event=None):
        if (not isinstance(index,FilmIndex) or
                not isinstance(queue,DurableRenderIntentionQueue) or
                queue.index is not index or
                not isinstance(blender,BlenderWorkerSupervisor) or
                not callable(ask_native) or
                (cancel_event is not None and not isinstance(cancel_event,threading.Event))):
            raise TypeError("Trusted frozen FilmIndex, live review queue and Blender host required")
        if blender.activity is None:
            raise RuntimeError("Cycles must use supervised NVP resource admission")
        db=Path(index.studio.db_path).resolve(strict=True)
        if blender.root.is_relative_to(db.parent):
            raise PermissionError("Blender job workspace cannot live in original source books")
        self.index=index
        self.queue=queue
        self.blender=blender
        self.ask_native=ask_native
        self.cancel_event=cancel_event

    def _source_at(self,project_id,request,selection_sha256,tick):
        scope=self.queue.selector.preview(project_id,request)
        if scope["selection_sha256"]!=selection_sha256:
            raise PermissionError("Blender source selection SHA changed")
        sample=self.queue.selector.sample_at(
            project_id,request,selection_sha256,tick)
        snap=sample["source_snapshot"]
        if (snap["scene_document_sha256"]!=scope["original_scene_sha256"] or
                snap["time_tick"]!=tick):
            raise RuntimeError("Frozen OpenUSD state was not sampled exactly")
        take=self.index.read_revision(project_id,request["take_id"],1)
        scene=self.index.read_revision(
            project_id,take["data"]["scene_id"],take["data"]["scene_revision"])
        if scene["document_sha256"]!=scope["original_scene_sha256"]:
            raise RuntimeError("OpenUSD scene revision mismatch")
        geo=[]
        from backend.nvp_openusd_assets import OpenUSDAssetRegistry
        assets=OpenUSDAssetRegistry(self.index)
        camera=None
        for row in snap["objects"]:
            point=row["world_translation"]
            if (not isinstance(point,list) or len(point)!=3 or
                    any(type(v) not in (int,float) or
                        not math.isfinite(v) or abs(v)>100000
                        for v in point)):
                raise RuntimeError("Nonfinite world pose is not an approved render input")
            if row["path"]==scope["source_camera_path"]:
                camera=list(point)
            binding=row["asset"]
            if binding is None:
                continue
            if row["semantic_role"] not in ("actor","prop","environment"):
                continue
            record,_=assets.open(
                project_id,binding["asset_id"],binding["asset_revision"])
            if (record["document_sha256"]!=binding["asset_document_sha256"] or
                    record["data"]["layer_sha256"]!=binding["asset_layer_sha256"]):
                raise PermissionError("Original USD asset failed independent SHA verification")
            geo.append({
                "path":row["path"],
                "shape":record["data"]["shape"],
                "size_m":record["data"]["size_m"],
                "position":list(point),
                "asset_sha256":record["document_sha256"],
            })
        if camera is None or not 1<=len(geo)<=32:
            raise ValueError("Cycles pilot requires an authored camera and 1-32 approved USD primitives")
        return {
            "format":SOURCE_FORMAT,
            "take_sha256":scope["take_document_sha256"],
            "scene_sha256":scope["original_scene_sha256"],
            "selection_sha256":scope["selection_sha256"],
            "source_tick":tick,
            "camera_path":scope["source_camera_path"],
            "camera_translation":camera,
            "geometry":geo,
            "engine":"CYCLES_CPU",
            "resolution":[400,240],
        },scope


    def _require_not_cancelled(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise InterruptedError("Creator cancelled one-use Cycles render")

    def _run_cancellable(self,operation):
        """Watch actual supervisor cancellation until its RUNNING token appears.

        A request arriving during PREPARED/probe must not miss the worker token.
        Never report termination from the request flag: the supervisor must
        return a settled terminal receipt, otherwise execution fails closed.
        """
        self._require_not_cancelled()
        if self.cancel_event is None:
            return self.blender.run(operation)
        stopped=threading.Event()
        def cancel_watch():
            while not stopped.is_set():
                if self.cancel_event.is_set():
                    # Cancellation can race worker admission; keep retrying
                    # until it is registered or the synchronous call exits.
                    if self.blender.cancel(operation.job_id):
                        return
                stopped.wait(0.04)
        watcher=threading.Thread(target=cancel_watch,
                                 name="NVP Cycles cancellation",daemon=True)
        watcher.start()
        try:
            self._require_not_cancelled()
            result=self.blender.run(operation)
            if self.cancel_event.is_set():
                if result.get("state")=="CANCELLED":
                    raise InterruptedError("Native Blender cancellation settled")
                # A late cancel cannot authorize a successful publication.
                raise RuntimeError("Cancellation requested without verified worker stop")
            return result
        finally:
            stopped.set()
            watcher.join(timeout=0.5)

    def render_once(self,project_id,job_id,revision,selection_sha256,tick):
        row=self.queue.inspect(project_id,job_id)
        if (row["status"]!=APPROVED or row["revision"]!=revision or
                row["selection_sha256"]!=selection_sha256 or
                type(tick) is not int):
            raise PermissionError("Only a live approved, exact source render intention")
        self.queue.require_live_worker_review(
            project_id,job_id,revision,selection_sha256)
        _,doc=self.queue._read(project_id,job_id)
        selection=doc["selection"]
        manifest,scope=self._source_at(
            project_id,selection,selection_sha256,tick)
        native_scope={
            "operation":"nvp.plan04.openusd_cycles_build_and_independent_reopen.v1",
            "project_id":project_id,
            "take_sha256":manifest["take_sha256"],
            "scene_sha256":manifest["scene_sha256"],
            "selection_sha256":selection_sha256,
            "source_tick":tick,
            "blender_binary_sha256":self.blender.binary_sha256,
            "render_engine":"BLENDER_CYCLES_CPU",
            "script_sha256":hashlib.sha256(
                TRUSTED_CYCLES_SCRIPT.encode("utf8")).hexdigest(),
            "independent_reopen_required":True,
            "original_source_modified":False,
            "output_publication_authorized":False,
        }
        try:
            if self.ask_native(dict(native_scope)) is not True:
                raise PermissionError("Native Blender/Cycles creator consent refused")
            fresh,row_scope=self._source_at(
                project_id,selection,selection_sha256,tick)
            if (fresh!=manifest or row_scope!=scope or
                    self.queue.inspect(project_id,job_id)!=row or
                    sha_file(self.blender.binary)!=self.blender.binary_sha256):
                raise PermissionError("Original source or Blender changed during OS review")
        finally:
            # A source review is never transferable to a second worker even
            # if cancelled, blocked by RAM, or the OS callback raises.
            self.queue.consume_live_worker_review(
                project_id,job_id,revision,selection_sha256)
        self._require_not_cancelled()
        build_id="CyclesSource_"+secrets.token_hex(12)
        jobdir=self.blender.root/build_id
        jobdir.mkdir(mode=0o700,exist_ok=False)
        code=_write_new(jobdir/"trusted_cycles.py",
                        TRUSTED_CYCLES_SCRIPT.encode("utf8"))
        data=_write_new(jobdir/"original_source.json",json.dumps(
            manifest,sort_keys=True,separators=(",",":"),
            allow_nan=False).encode("utf8"))
        op=BlenderOperation(
            job_id=build_id,script="trusted_cycles.py",script_sha256=code,
            inputs={"original_source.json":data},
            outputs={"derived_scene.blend":"blend",
                     "derived_cycles.png":"png","build_audit.json":"json_audit"},
            arguments={
                "--manifest":"original_source.json",
                "--output":"derived_scene.blend",
                "--render":"derived_cycles.png","--audit":"build_audit.json",
            },timeout_seconds=240,memory_limit_mb=4096,
            require_linux_cgroup_v2=True)
        built=self._run_cancellable(op)
        if built["state"]!="SUCCEEDED":
            diagnostic=(jobdir/"worker_stderr.log")
            tail=(diagnostic.read_bytes()[-2048:].decode("utf8","replace")
                  if diagnostic.is_file() else "no worker stderr")
            raise RuntimeError(
                "Cycles source build not independently accepted: "+
                str(built.get("state"))+
                "; OS supervisor: "+str(built.get("error",""))[:600]+
                "; bounded native stderr: "+tail[:1500])
        report=json.loads((jobdir/"build_audit.json").read_text("utf8"))
        if (report.get("passed") is not True or
                report.get("engine")!="CYCLES" or
                report.get("take_sha256")!=manifest["take_sha256"] or
                report.get("scene_sha256")!=manifest["scene_sha256"] or
                report.get("source_tick")!=tick or
                report.get("geometry_count")!=len(manifest["geometry"])):
            raise RuntimeError("Real Blender Cycles source audit disagrees with immutable Take")
        self._require_not_cancelled()
        reopened_id="CyclesReopen_"+secrets.token_hex(12)
        secondary=self.blender.root/reopened_id
        secondary.mkdir(mode=0o700,exist_ok=False)
        blend_sha=_copy_verified(
            jobdir/"derived_scene.blend",secondary/"source_scene.blend")
        audit_data={
            "take_sha256":manifest["take_sha256"],
            "scene_sha256":manifest["scene_sha256"],
            "selection_sha256":selection_sha256,
            "source_tick":tick,
            "geometry_count":len(manifest["geometry"]),
        }
        audit_manifest=_write_new(
            secondary/"source_check.json",
            json.dumps(audit_data,sort_keys=True).encode("utf8"))
        audit_script_sha=_write_new(
            secondary/"trusted_reopen.py",TRUSTED_REOPEN_SCRIPT.encode("utf8"))
        audit_op=BlenderOperation(
            job_id=reopened_id,script="trusted_reopen.py",
            script_sha256=audit_script_sha,scene="source_scene.blend",
            inputs={"source_scene.blend":blend_sha,
                    "source_check.json":audit_manifest},
            outputs={"reopen_audit.json":"json_audit","reopen_cycles.png":"png"},
            arguments={
                "--manifest":"source_check.json","--audit":"reopen_audit.json",
                "--preview":"reopen_cycles.png",
            },timeout_seconds=240,memory_limit_mb=4096,
            require_linux_cgroup_v2=True)
        audited=self._run_cancellable(audit_op)
        if audited["state"]!="SUCCEEDED":
            raise RuntimeError("Independent Blender reopen failed: "+str(audited.get("state")))
        reopened=json.loads((secondary/"reopen_audit.json").read_text("utf8"))
        if (reopened.get("passed") is not True or
                reopened.get("reopened_in_separate_native_blender_worker") is not True or
                reopened.get("source_take_sha256")!=manifest["take_sha256"] or
                reopened.get("source_tick")!=tick or
                reopened.get("geometry_count")!=len(manifest["geometry"])):
            raise RuntimeError("Independent Cycles reopen geometry/source proof failed")
        self._require_not_cancelled()
        if self.queue.selector.preview(project_id,selection)!=scope:
            raise RuntimeError("Original frozen source mutated during Cycles rendering")
        fresh_index=FilmIndex(Studio(self.index.studio.db_path))
        verify=OpenUSDTakeCapture(
            fresh_index,verify_creator_action=lambda *_:False).verify_take(
                project_id,selection["take_id"])
        if (verify["take_document_sha256"]!=manifest["take_sha256"] or
                verify["scene_document_sha256"]!=manifest["scene_sha256"]):
            raise RuntimeError("Independent original take/source reopen differs")
        self._require_not_cancelled()
        return {
            "format":"nvp.plan04.source_blender_cycles_verified.v1",
            "status":"REAL_BLENDER_CYCLES_AND_INDEPENDENT_REOPEN_VERIFIED",
            "project_id":project_id,
            "take_sha256":manifest["take_sha256"],
            "scene_sha256":manifest["scene_sha256"],
            "source_tick":tick,
            "blender_sha256":self.blender.binary_sha256,
            "real_cycles_engine_verified":True,
            "actual_geometry_count":len(manifest["geometry"]),
            "build_job_id":build_id,"audit_job_id":reopened_id,
            "blend_sha256":sha_file(jobdir/"derived_scene.blend"),
            "derived_png_sha256":sha_file(jobdir/"derived_cycles.png"),
            "independently_reopened_png_sha256":sha_file(
                secondary/"reopen_cycles.png"),
            "original_scene_take_immutable_after_restart_reopen":True,
            "windows_job_or_linux_delegated_cgroup_required":True,
            "creator_approval_physically_witnessed":False,
            "test_mode_native_callback_not_real_dialog":True,
            "ffmpeg_used":False,
            "cinema_master_published":False,
        }
