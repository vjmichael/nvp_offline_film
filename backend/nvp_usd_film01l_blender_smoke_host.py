"""USD-FILM-01L: host-supervised native nine-camera smoke rendering.

Source-verified USD timeline built by 01K. Reuses NVP's SHA-pinned Blender
worker supervisor with real OS worker containment, full journal and bounded
outputs. Three preview film ticks x nine real original cameras = 27 true
Cycles frames WHEN actually run with reviewed Blender. Not 6480-frame acceptance.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from backend.nvp_blender_worker import (
    BlenderOperation,BlenderWorkerSupervisor,sha_file)
from backend.nvp_film_index import FilmIndex,_id
from backend.nvp_usd_film01i_ninecam_take import (
    GRID,OriginalNineCameraFilmSet)
from backend.nvp_usd_film01k_blender_animation_build import (
    author_original_blender_animation,STAGE)

FORMAT="nvp.usd_film01l.native_cycles_nine_camera_smoke_packet.v1"
AUDIT="nvp.usd_film01l.native_cycles_nine_camera_smoke_receipt.v1"
SCRIPT="nvp_usd_film01l_blender_ninecam_worker.py"
FRAMES=(0,360,719)

def _canonical(payload):
    return json.dumps(payload,sort_keys=True,
        ensure_ascii=True,allow_nan=False,
        separators=(",",":")).encode("ascii")

class ReviewedNineCameraCyclesSmoke:
    def __init__(self,index:FilmIndex, supervisor:BlenderWorkerSupervisor,
                 *,verify_director_action):
        if (not isinstance(index,FilmIndex) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not callable(verify_director_action)):
            raise TypeError("Verified original sources and existing Blender supervisor required")
        self.index=index
        self.supervisor=supervisor
        self._approve=verify_director_action

    def render_smoke(self,pid,rig_id,*,job_prefix,director_event):
        _id(rig_id,"original nine-camera source")
        _id(job_prefix,"original camera worker prefix")
        if len(job_prefix)>46:
            raise ValueError("Three Blender job IDs must fit a bounded journal")
        source_host=OriginalNineCameraFilmSet(
            self.index,verify_creator_action=lambda *_:False)
        proof=source_host.verify(pid,rig_id)
        rig=self.index.read_revision(pid,rig_id,1)
        take=self.index.read_revision(pid,rig["data"]["world_take_id"],1)
        script=Path(__file__).resolve().parents[1]/"tools"/SCRIPT
        if not script.is_file() or script.is_symlink():
            raise RuntimeError("Reviewed original nine-camera Blender worker absent")
        scope={
            "operation":"nvp.render.usd_film01l_ninecam_native_smoke.v1",
            "project_id":pid,"rig_sha256":rig["document_sha256"],
            "original_world_take_sha256":take["document_sha256"],
            "original_performance_sha256":rig["data"]["source_performance_sha256"],
            "source_frame_indices":list(FRAMES),
            "native_camera_shas":[
                c["camera_shot_sha256"] for c in rig["data"]["cameras"]]}
        if self._approve(director_event,scope) is not True:
            raise PermissionError("Exact original multicamera Blender render not authorized")
        completed=[]
        with TemporaryDirectory(prefix="nvp-nine-cam-animation-") as tmp:
            stage=Path(tmp)/"source_stage"
            original=author_original_blender_animation(
                self.index,pid,rig_id,folder=stage)
            for frame in FRAMES:
                job_id=f"{job_prefix}_{frame:04d}"
                job=self.supervisor.root/job_id
                if job.exists() or job.is_symlink():
                    raise FileExistsError("Worker journal/job IDs cannot be reused")
                job.mkdir(mode=0o700)
                frame_source=original["original_actor_state_per_frame"][frame]
                packet_source={
                    "source_usd_file":"source.usda",
                    "source_usd_sha256":original["derived_usd_sha256"],
                    "original_world_sha256":rig["data"]["original_world_sha256"],
                    "original_world_take_sha256":take["document_sha256"],
                    "original_performance_sha256":rig["data"]["source_performance_sha256"],
                    "original_rig_sha256":rig["document_sha256"],
                    "original_film_tick":frame_source["original_film_tick"],
                    "original_render_frame":frame,
                    "original_actor_state_sha256":frame_source["actor_state_sha256"],
                    "original_actor_positions":frame_source[
                        "source_actor_world_positions_m"],
                    "original_camera_rig":rig["data"]["cameras"],
                }
                packet={"format":FORMAT,"source":packet_source,
                    "source_sha256":sha256(_canonical(packet_source)).hexdigest()}
                shutil.copyfile(stage/STAGE,job/"source.usda")
                (job/"source.json").write_bytes(_canonical(packet))
                shutil.copyfile(script,job/SCRIPT)
                outputs={f"{angle}_{framing}.png":"png"
                         for angle,framing in GRID}
                outputs.update({"scene.blend":"blend","audit.json":"json_audit"})
                op=BlenderOperation(
                    job_id=job_id,script=SCRIPT,
                    script_sha256=sha_file(job/SCRIPT),
                    inputs={
                        "source.usda":sha_file(job/"source.usda"),
                        "source.json":sha_file(job/"source.json")},
                    outputs=outputs,
                    arguments={
                        "--manifest":"source.json",
                        "--output":"scene.blend",
                        "--audit":"audit.json"},
                    memory_limit_mb=8192,timeout_seconds=600,
                    gpu_memory_mb=0,require_linux_cgroup_v2=False)
                self.supervisor._validate(op)
                result=self.supervisor.run(op)
                if result["state"]!="SUCCEEDED":
                    raise RuntimeError("Actual original nine-camera Blender worker failed: "+
                        str(result.get("error") or result["state"]))
                self.supervisor.verify_completed(job_id)
                audit=json.loads((job/"audit.json").read_text("utf8"))
                if (audit.get("format")!=AUDIT or audit.get("passed") is not True
                    or audit.get("original_rig_sha256")!=rig["document_sha256"]
                    or audit.get("original_world_take_sha256")!=take["document_sha256"]
                    or audit.get("source_usd_sha256")!=original["derived_usd_sha256"]
                    or audit.get("original_actor_state_sha256")!=
                        frame_source["actor_state_sha256"]
                    or audit.get("original_film_tick")!=
                        frame_source["original_film_tick"]
                    or audit.get("actual_native_cycles_image_count")!=9
                    or len(audit.get("camera_views",[]))!=9
                    or audit.get("actual_original_actor_motion_at_frame_verified") is not True
                    or audit.get("saved_blend_sha256")!=sha_file(job/"scene.blend")):
                    raise RuntimeError("Native Cycles camera coverage source audit failed")
                for desc,shot in zip(rig["data"]["cameras"],audit["camera_views"]):
                    framefile=job/f"{desc['angle']}_{desc['framing']}.png"
                    if (shot.get("angle")!=desc["angle"] or
                        shot.get("framing")!=desc["framing"] or
                        shot.get("camera_prim")!=
                            desc["native_composed_camera_path"] or
                        shot.get("camera_shot_sha256")!=
                            desc["camera_shot_sha256"] or
                        shot.get("rendered_png_sha256")!=sha_file(framefile) or
                        shot.get("original_actor_state_sha256")!=
                            frame_source["actor_state_sha256"] or
                        shot.get("actual_native_cycles_image") is not True):
                        raise RuntimeError("Native camera source/frame was substituted")
                completed.append({
                    "source_frame":frame,"source_tick":frame_source["original_film_tick"],
                    "job_id":job_id,"job_dir":job,
                    "rendered_original_camera_frames":9,
                    "actual_native_supervisor_verified":True})
        return {
            "state":"RENDERED_27_ORIGINAL_NATIVE_CAMERA_SMOKE_FRAMES",
            "original_rig_sha256":rig["document_sha256"],
            "original_world_take_sha256":take["document_sha256"],
            "original_performance_sha256":rig["data"]["source_performance_sha256"],
            "independently_supervised_job_count":3,
            "rendered_original_cycles_frames":27,
            "jobs":completed,
            "all_6480_source_camera_frames_produced":False,
            "director_visual_approval":False}
