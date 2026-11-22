"""CAM-FX-05B: OS-approved protected Cycles director camera with independent reopen.

The approved 01E actor/PCM Take, 01D source camera and 02M-H district
remain immutable. A fresh reviewed render scope admits only an exact
source SHA + reviewed CAM-FX rail SHA into an already pinned first-party
BlenderWorkerSupervisor. No model/draft or previous approval can dispatch it.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_blender_worker import BlenderOperation,BlenderWorkerSupervisor,sha_file
from backend.nvp_cam_fx01_camera_rails import OriginalCameraRails
from backend.nvp_cam_fx05_verified_shot_source import (
    stage_approved_rail_frame,RECEIPT,FORMAT as SOURCE_FORMAT)
from backend.nvp_usd_film02m_h_actor_camera_binding import OriginalDistrictShotBinding
from backend.nvp_usd_film02m_h_render_handoff import DISTRICT_EVIDENCE
from backend.nvp_usd_film01f_blender_host import (
    USD,MANIFEST,FRAME,BLEND,AUDIT,PACKET_FORMAT)

WORKER="nvp_cam_fx05_blender_rail_worker.py"
REOPENER="nvp_cam_fx05_blender_rail_reopen.py"
AUDIT_FORMAT="nvp.cam_fx05.native_cycles_director_rail_frame.v1"
REOPEN_FORMAT="nvp.cam_fx05.native_independent_saved_director_rail.v1"
PICTURE_FORMAT="nvp.cam_fx05.native_verified_director_camera_cycles_picture.v1"
MAX_FRAME_BYTES=12*1024*1024


def _canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _read(path):
    if path.is_symlink() or not path.is_file():
        raise PermissionError("Only independently verified first-party worker evidence")
    return json.loads(path.read_text("utf8"))


class ReviewedCameraRailCyclesHost:
    """Host-owned worker dispatch, one fresh OS decision per exact rail frame."""

    def __init__(self,index:FilmIndex,supervisor:BlenderWorkerSupervisor,
                 *,verify_director_action):
        if (not isinstance(index,FilmIndex) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not callable(verify_director_action)):
            raise TypeError("Actual FilmIndex, protected native worker and director approval")
        self.index=index
        self.supervisor=supervisor
        self.confirm=verify_director_action

    def stage(self,pid,binding_id,rail_id,rail_revision,*,job_id):
        _id(job_id,"bounded native reviewed virtual camera render")
        if len(job_id)>60:
            raise ValueError("One bounded native rail job identity")
        root=self.supervisor.root/job_id
        if root.exists() or root.is_symlink():
            raise FileExistsError("Original protected camera rail job cannot be replaced")
        root.mkdir(mode=0o700)
        try:
            prepared=stage_approved_rail_frame(
                self.index,pid,binding_id,rail_id,rail_revision,root)
            script=Path(__file__).resolve().parents[1]/"tools"/WORKER
            if script.is_symlink() or not script.is_file():
                raise RuntimeError("Reviewed native rail-aware Cycles worker absent")
            shutil.copyfile(script,root/WORKER)
            operation=BlenderOperation(
                job_id=job_id,script=WORKER,
                script_sha256=sha_file(root/WORKER),
                inputs={
                    USD:sha_file(root/USD),
                    MANIFEST:sha_file(root/MANIFEST),
                    DISTRICT_EVIDENCE:sha_file(root/DISTRICT_EVIDENCE),
                    RECEIPT:sha_file(root/RECEIPT)},
                outputs={FRAME:"png",BLEND:"blend",AUDIT:"json_audit"},
                arguments={"--manifest":MANIFEST,
                           "--output":BLEND,"--preview":FRAME,"--audit":AUDIT},
                memory_limit_mb=8192,timeout_seconds=600,
                require_linux_cgroup_v2=True,require_private_isolation=True,gpu_memory_mb=0)
            self.supervisor._validate(operation)
            return {**prepared,"operation":operation}
        except Exception:
            shutil.rmtree(root)
            raise

    def _current(self,pid,binding_id,rail_id,rail_revision):
        binding=OriginalDistrictShotBinding(
            self.index,confirm=lambda *_:False).reopen(pid,binding_id)
        rail=OriginalCameraRails(
            self.index,verify_director_action=lambda *_:False).verify(
            pid,rail_id,rail_revision)
        return binding,rail

    def render(self,pid,binding_id,rail_id,rail_revision,*,job_id,director_event):
        data=self.stage(
            pid,binding_id,rail_id,rail_revision,job_id=job_id)
        root=self.supervisor.root/job_id
        receipt=data["receipt"]
        scope={
            "operation":"nvp.cam_fx05.render_reviewed_director_rail_frame.v1",
            "project_id":pid,
            "binding_id":binding_id,
            "binding_sha256":receipt["binding_sha256"],
            "rail_id":rail_id,"rail_revision":rail_revision,
            "rail_revision_sha256":receipt["rail_revision_sha256"],
            "rail_layer_sha256":receipt["rail_layer_sha256"],
            "original_world_take_sha256":receipt["original_world_take_sha256"],
            "original_camera_shot_sha256":receipt["original_camera_shot_sha256"],
            "original_district_usd_sha256":receipt["original_02mh_usd_sha256"],
            "source_usd_sha256":receipt["derived_with_rail_usd_sha256"],
            "original_film_tick":receipt["source_film_tick"],
            "director_camera_path":receipt["director_camera_path"],
            "job_id":job_id}
        try:
            allowed=self.confirm(director_event,scope) is True
        except Exception:
            shutil.rmtree(root)
            raise
        if not allowed:
            shutil.rmtree(root)
            raise PermissionError(
                "A fresh source- and revision-bound OS director render approval is required")
        fresh_binding,fresh_rail=self._current(
            pid,binding_id,rail_id,rail_revision)
        if (fresh_binding["binding_document_sha256"]!=receipt["binding_sha256"] or
            fresh_rail["rail_layer_sha256"]!=receipt["rail_layer_sha256"] or
            self.index.read_revision(pid,rail_id,rail_revision)[
                "document_sha256"]!=receipt["rail_revision_sha256"] or
            sha_file(root/USD)!=receipt["derived_with_rail_usd_sha256"] or
            sha_file(root/RECEIPT)!=data["operation"].inputs[RECEIPT]):
            raise PermissionError("Approved camera render source changed after native consent")
        state=self.supervisor.run(data["operation"])
        if state["state"]!="SUCCEEDED":
            raise RuntimeError("Protected source-bound CAM-FX Cycles worker failed: "+
                               str(state.get("error") or state["state"]))
        self.supervisor.verify_completed(job_id)
        source=data["packet"]["source"]
        audit=_read(root/AUDIT)
        if (audit.get("format")!=AUDIT_FORMAT or
            audit.get("passed") is not True or
            audit.get("actual_native_cycles_image") is not True or
            audit.get("source_usd_sha256")!=receipt["derived_with_rail_usd_sha256"] or
            audit.get("original_world_take_sha256")!=receipt["original_world_take_sha256"] or
            audit.get("original_camera_shot_sha256")!=receipt["original_camera_shot_sha256"] or
            audit.get("director_camera_path")!=receipt["director_camera_path"] or
            audit.get("rail_revision_sha256")!=receipt["rail_revision_sha256"] or
            audit.get("original_actor_roots_found")!=len(source["actor_sources"]) or
            audit.get("rendered_png_sha256")!=sha_file(root/FRAME) or
            audit.get("saved_blend_sha256")!=sha_file(root/BLEND)):
            raise RuntimeError("Actual rendered pixels lack pinned original and rail camera")
        proof=self._reopen(pid,job_id,source,_read(root/DISTRICT_EVIDENCE),receipt)
        final_binding,final_rail=self._current(
            pid,binding_id,rail_id,rail_revision)
        if (final_binding!=fresh_binding or final_rail!=fresh_rail or
            sha_file(root/USD)!=receipt["derived_with_rail_usd_sha256"]):
            raise RuntimeError("Immutable original performer/district or rail changed during render")
        return {
            "state":"CAM_FX05_REAL_DIRECTOR_RAIL_CYCLES_FRAME",
            "job_id":job_id,"png_sha256":sha_file(root/FRAME),
            "blend_sha256":sha_file(root/BLEND),
            "rail_revision_sha256":receipt["rail_revision_sha256"],
            "source_usd_sha256":receipt["derived_with_rail_usd_sha256"],
            "original_world_take_sha256":receipt["original_world_take_sha256"],
            "original_camera_shot_sha256":receipt["original_camera_shot_sha256"],
            "original_film_tick":receipt["source_film_tick"],
            "director_camera_path":receipt["director_camera_path"],
            "actual_native_cycles_picture":True,
            "independent_saved_scene_reopened":proof[
                "native_selected_director_camera_verified"],
            "original_actor_take_pcm_unchanged":True,
            "human_quality_approved":False,"complete_film_accepted":False}

    def _reopen(self,pid,job_id,source,district,receipt):
        reopen_id=job_id+"_reopen"
        _id(reopen_id,"protected camera rail independent source reopen")
        if len(reopen_id)>80:
            raise ValueError("Unbounded independent native reopen job")
        root=self.supervisor.root/job_id
        target=self.supervisor.root/reopen_id
        if target.exists() or target.is_symlink():
            raise FileExistsError("Independent original film camera reopen exists")
        target.mkdir(mode=0o700)
        shutil.copyfile(root/BLEND,target/BLEND)
        proof={
            "source":source,"district":district,"rail":receipt,
            "source_blend_sha256":sha_file(target/BLEND)}
        (target/MANIFEST).write_bytes(_canonical(proof))
        script=Path(__file__).resolve().parents[1]/"tools"/REOPENER
        if script.is_symlink() or not script.is_file():
            raise RuntimeError("First-party saved Cycles rail camera reopener missing")
        shutil.copyfile(script,target/REOPENER)
        operation=BlenderOperation(
            job_id=reopen_id,scene=BLEND,script=REOPENER,
            script_sha256=sha_file(target/REOPENER),
            inputs={BLEND:sha_file(target/BLEND),
                    MANIFEST:sha_file(target/MANIFEST)},
            outputs={AUDIT:"json_audit"},
            arguments={"--manifest":MANIFEST,"--audit":AUDIT},
            memory_limit_mb=8192,timeout_seconds=600,
            require_linux_cgroup_v2=True,require_private_isolation=True)
        self.supervisor._validate(operation)
        status=self.supervisor.run(operation)
        if status["state"]!="SUCCEEDED":
            raise RuntimeError("Independent real Blender rail-frame scene reopen failed")
        self.supervisor.verify_completed(reopen_id)
        result=_read(target/AUDIT)
        if (result.get("format")!=REOPEN_FORMAT or
            result.get("passed") is not True or
            result.get("native_selected_director_camera_verified") is not True or
            result.get("actual_saved_source_district_meshes_verified") is not True or
            result.get("source_actor_camera_unchanged") is not True or
            result.get("source_blend_sha256")!=proof["source_blend_sha256"] or
            result.get("source_usd_sha256")!=receipt["derived_with_rail_usd_sha256"] or
            result.get("original_02mh_usd_sha256")!=receipt["original_02mh_usd_sha256"] or
            result.get("rail_revision_sha256")!=receipt["rail_revision_sha256"] or
            result.get("director_camera_path")!=receipt["director_camera_path"] or
            result.get("actor_count")!=len(source["actor_sources"])):
            raise RuntimeError("Saved original ActorID district or rail camera cannot reverify")
        return result

    def reopen_verified_render(self,pid,binding_id,rail_id,revision,job_id):
        """Never auto-reruns interrupted worker or reuses prior OS approval."""
        _id(job_id,"original reviewed virtual camera picture job")
        self.supervisor.verify_completed(job_id)
        self.supervisor.verify_completed(job_id+"_reopen")
        root=self.supervisor.root/job_id
        if root.is_symlink():
            raise PermissionError("Untrusted original rail image directory")
        receipt=_read(root/RECEIPT)
        packet=_read(root/MANIFEST)
        audit=_read(root/AUDIT)
        proof=_read(self.supervisor.root/(job_id+"_reopen")/AUDIT)
        binding,rail=self._current(pid,binding_id,rail_id,revision)
        if (packet.get("format")!=PACKET_FORMAT or
            packet.get("source_sha256")!=sha256(
                _canonical(packet.get("source"))).hexdigest() or
            packet["source"].get("source_usd_sha256")!=sha_file(root/USD) or
            receipt.get("format")!=SOURCE_FORMAT or
            receipt.get("project_id")!=pid or
            receipt.get("binding_id")!=binding_id or
            receipt.get("binding_sha256")!=binding["binding_document_sha256"] or
            receipt.get("rail_id")!=rail_id or
            receipt.get("rail_revision")!=revision or
            receipt.get("rail_revision_sha256")!=self.index.read_revision(
                pid,rail_id,revision)["document_sha256"] or
            receipt.get("rail_layer_sha256")!=rail["rail_layer_sha256"] or
            receipt.get("original_world_take_sha256")!=rail["world_take_sha256"] or
            receipt.get("derived_with_rail_usd_sha256")!=sha_file(root/USD) or
            audit.get("format")!=AUDIT_FORMAT or
            audit.get("actual_native_cycles_image") is not True or
            audit.get("rendered_png_sha256")!=sha_file(root/FRAME) or
            audit.get("saved_blend_sha256")!=sha_file(root/BLEND) or
            audit.get("rail_revision_sha256")!=receipt["rail_revision_sha256"] or
            proof.get("format")!=REOPEN_FORMAT or
            proof.get("native_selected_director_camera_verified") is not True or
            proof.get("source_blend_sha256")!=sha_file(root/BLEND) or
            proof.get("source_usd_sha256")!=sha_file(root/USD)):
            raise RuntimeError("Previously accepted native camera frame is no longer source-verified")
        picture=root/FRAME
        if (picture.is_symlink() or not picture.is_file() or
            not 128<=picture.stat().st_size<=MAX_FRAME_BYTES):
            raise RuntimeError("Real source-verified Cycles PNG missing or oversized")
        return {
            "format":PICTURE_FORMAT,"project_id":pid,"job_id":job_id,
            "binding_id":binding_id,"rail_id":rail_id,
            "rail_revision":revision,"rail_revision_sha256":receipt["rail_revision_sha256"],
            "picture_sha256":sha_file(picture),
            "saved_blend_sha256":sha_file(root/BLEND),
            "original_world_take_sha256":receipt["original_world_take_sha256"],
            "original_camera_shot_sha256":receipt["original_camera_shot_sha256"],
            "original_film_tick":receipt["source_film_tick"],
            "source_actor_pcm_unchanged":True,
            "independent_blender_reopen_verified":True,
            "director_picture_quality_approved":False}

    def compare_revisions(self,pid,binding_id,rail_id,rev_a,rev_b,*,
                          job_a,job_b,director_event):
        if rev_a==rev_b or job_a==job_b:
            raise ValueError("Require two different immutable rail revisions and jobs")
        a,b=[self.index.read_revision(pid,rail_id,x)["document_sha256"]
             for x in (rev_a,rev_b)]
        if a==b:
            raise RuntimeError("Camera source revision did not actually change")
        first=self.render(pid,binding_id,rail_id,rev_a,
                          job_id=job_a,director_event=director_event)
        second=self.render(pid,binding_id,rail_id,rev_b,
                           job_id=job_b,director_event=director_event)
        if (first["png_sha256"]==second["png_sha256"] or
            first["original_world_take_sha256"]!=second["original_world_take_sha256"] or
            first["original_camera_shot_sha256"]!=second["original_camera_shot_sha256"] or
            first["original_film_tick"]!=second["original_film_tick"]):
            raise RuntimeError("Revised rail failed to change actual original shot picture")
        from PIL import Image,ImageChops
        with (Image.open(self.supervisor.root/job_a/FRAME) as left,
              Image.open(self.supervisor.root/job_b/FRAME) as right):
            if left.size!=(320,180) or right.size!=(320,180):
                raise RuntimeError("Unverified original director rail output resolution")
            delta=ImageChops.difference(left.convert("RGB"),right.convert("RGB"))
            changed=sum(1 for pixel in delta.getdata() if max(pixel)>12)
        if changed<250:
            raise RuntimeError("Edited digital camera did not visibly change native film frame")
        return {
            "format":"nvp.cam_fx05.real_two_revisions_original_source_rail_cycles.v1",
            "world_take_sha256":first["original_world_take_sha256"],
            "original_camera_shot_sha256":first["original_camera_shot_sha256"],
            "rail_revision_sha256":[a,b],
            "native_cycles_png_sha256":[first["png_sha256"],second["png_sha256"]],
            "pixels_changed_over_rgb12":changed,
            "independent_blender_reopen_each":True,
            "original_actor_pcm_unchanged":True,
            "human_artistic_approval":False,
            "complete_film_accepted":False}
