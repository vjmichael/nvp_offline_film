"""USD-FILM-01N: host-approved, journaled native director-camera ray test.

Two different camera selections may observe the same original actor source
at the same film tick, with exactly scoped, reversible primary-ray walls.
The renderer script and mask helper are fixed, SHA-locked first-party files.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

from backend.nvp_blender_worker import (
    BlenderOperation,BlenderWorkerSupervisor,sha_file)
from backend.nvp_film_index import FilmIndex,_id
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_usd_film01n_director_camera_snapshot import (
    stage_original_director_camera_frame)

SCRIPT="nvp_usd_film01n_blender_director_camera_worker.py"
MASK="nvp_usd_film01m_camera_ray_mask.py"
IMAGE="frame.png"
BLEND="scene.blend"
AUDIT="audit.json"


class ReviewedDirectorCameraCycles:
    def __init__(self,index:FilmIndex,supervisor:BlenderWorkerSupervisor,
                 *,verify_director_action):
        if (not isinstance(index,FilmIndex) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not callable(verify_director_action)):
            raise TypeError("Trusted original FilmIndex, Blender supervisor and director required")
        self.index=index
        self.supervisor=supervisor
        self._approve=verify_director_action

    def render_views(self,pid,bank_id,*,revision,tick,requests,director_event):
        _id(bank_id,"original director camera rig")
        if (type(requests) is not list or not 1<=len(requests)<=8 or
            any(type(x) is not dict or set(x)!={"camera_id","job_id"}
                for x in requests) or
            len({x["job_id"] for x in requests})!=len(requests) or
            len({x["camera_id"] for x in requests})!=len(requests)):
            raise ValueError("One to eight unique native camera jobs per reviewed batch")
        doc=DirectorCameraBank(
            self.index,verify_director_action=lambda *_:False).verify(
                pid,bank_id,revision)
        bank=self.index.read_revision(pid,bank_id,revision)
        take=self.index.read_revision(pid,doc["world_take_id"],1)
        script=Path(__file__).resolve().parents[1]/"tools"/SCRIPT
        mask=Path(__file__).resolve().parents[1]/"tools"/MASK
        if (not script.is_file() or script.is_symlink() or
            not mask.is_file() or mask.is_symlink()):
            raise RuntimeError("Fixed first-party Cycles/mask workers missing")
        allowed={c["camera_id"]:c for c in doc["cameras"]}
        prepared=[]
        try:
            for q in requests:
                camera_id=_id(q["camera_id"],"source virtual film camera")
                job_id=_id(q["job_id"],"bounded Cycles worker identity")
                if len(job_id)>64 or camera_id not in allowed:
                    raise PermissionError("Camera job not in original approved camera rig")
                job=self.supervisor.root/job_id
                if job.exists() or job.is_symlink():
                    raise FileExistsError("Director camera render job cannot be reused")
                packet=stage_original_director_camera_frame(
                    self.index,pid,bank_id,revision=revision,
                    camera_id=camera_id,tick=tick,folder=job)
                prepared.append({"job":job,"job_id":job_id,
                                 "packet":packet,"camera":allowed[camera_id]})
            scope={
                "operation":"nvp.render.usd_film01n_director_camera_views.v1",
                "project_id":pid,
                "camera_bank_sha256":bank["document_sha256"],
                "original_world_take_sha256":take["document_sha256"],
                "original_performance_sha256":doc["source_performance_sha256"],
                "original_film_tick":tick,
                "camera_ids":[p["camera"]["camera_id"] for p in prepared],
                "source_snapshot_shas":[p["packet"]["source"][
                    "source_usd_sha256"] for p in prepared],
                "per_camera_primary_ray_exclusions":[
                    p["camera"]["camera_ray_exclusions"] for p in prepared],
            }
            if self._approve(director_event,scope) is not True:
                raise PermissionError("Director refused exact original multicamera render scope")
            result=[]
            for p in prepared:
                job=p["job"]
                shutil.copyfile(script,job/SCRIPT)
                shutil.copyfile(mask,job/MASK)
                operation=BlenderOperation(
                    job_id=p["job_id"],script=SCRIPT,
                    script_sha256=sha_file(job/SCRIPT),
                    inputs={"source.usda":sha_file(job/"source.usda"),
                            "source.json":sha_file(job/"source.json"),
                            MASK:sha_file(job/MASK)},
                    outputs={
                        IMAGE:"png",BLEND:"blend",AUDIT:"json_audit"},
                    arguments={
                        "--manifest":"source.json",
                        "--output":BLEND,
                        "--preview":IMAGE,
                        "--audit":AUDIT},
                    memory_limit_mb=8192,timeout_seconds=600,
                    require_linux_cgroup_v2=False,gpu_memory_mb=0)
                self.supervisor._validate(operation)
                state=self.supervisor.run(operation)
                if state["state"]!="SUCCEEDED":
                    raise RuntimeError(
                        "Protected original director camera Cycles worker failed: "+
                        str(state.get("error") or state["state"]))
                self.supervisor.verify_completed(p["job_id"])
                audit=json.loads((job/AUDIT).read_text("utf8"))
                source=p["packet"]["source"]
                if (audit.get("passed") is not True or
                    audit.get("format")!=
                        "nvp.usd_film01n.native_cycles_director_camera_view.v1" or
                    audit.get("original_camera_bank_sha256")!=
                        bank["document_sha256"] or
                    audit.get("original_world_take_sha256")!=
                        take["document_sha256"] or
                    audit.get("source_performance_sha256")!=
                        doc["source_performance_sha256"] or
                    audit.get("source_usd_sha256")!=source["source_usd_sha256"] or
                    audit.get("camera_id")!=p["camera"]["camera_id"] or
                    audit.get("original_film_tick")!=tick or
                    audit.get("actual_camera_ray_excluded_prims")!=
                        p["camera"]["camera_ray_exclusions"] or
                    audit.get("actual_native_cycles_image") is not True or
                    audit.get("actual_cameras_not_rendered_as_geometry") is not True or
                    audit.get("per_camera_ray_mask_restored") is not True or
                    audit.get("rendered_png_sha256")!=sha_file(job/IMAGE) or
                    audit.get("saved_blend_sha256")!=sha_file(job/BLEND)):
                    raise RuntimeError("Real original director camera pixels lack source integrity")
                if (source["source_camera_ray_exclusions"] and
                    audit.get("actual_ray_masked_meshes",0)<1):
                    raise RuntimeError("Camera-ray source wall exclusion did not execute")
                result.append({"job_id":p["job_id"],
                    "camera_id":p["camera"]["camera_id"],
                    "original_film_tick":tick,
                    "camera_ray_exclusions":p["camera"]["camera_ray_exclusions"],
                    "png_sha256":sha_file(job/IMAGE),
                    "blend_sha256":sha_file(job/BLEND),
                    "native_supervisor_reverified":True,
                    "job_dir":job})
            return {
                "state":"NATIVE_DIRECTOR_CAMERA_SMOKE_RENDERED",
                "source_bank_sha256":bank["document_sha256"],
                "original_world_take_sha256":take["document_sha256"],
                "original_performance_sha256":doc["source_performance_sha256"],
                "original_film_tick":tick,
                "camera_views":result,
                "real_cycles_image_count":len(result),
                "full_camera_rolls_rendered":False,
                "finished_film_approved":False}
        except Exception:
            # Only source-derived *undispatched* directories may be removed
            # here. Preserve all job/journal evidence for any launched worker.
            for p in prepared:
                job=p["job"]
                try:
                    self.supervisor.inspect(p["job_id"])
                except KeyError:
                    if job.exists() and not job.is_symlink():
                        shutil.rmtree(job)
            raise
