"""USD-FILM-02M-HR: source-locked approved district + frozen Take Cycles shot.

One disposable, native USD snapshot combines REAL original 01D/01E
actor/camera source with E2's bounded *derived* Blender-compatible
representation of the approved 02M district. It does not alter any original
FilmIndex source, district USD layer, ActorID Take, camera or PCM.
Rendering requires an independent per-operation host director approval and
the existing protected Blender worker supervisor. Never interpret a source
snapshot or a model completion as approved film pixels.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import shutil

from backend.nvp_blender_worker import BlenderOperation,BlenderWorkerSupervisor,sha_file
from backend.nvp_film_index import FilmIndex,_id
from backend.nvp_usd_film01f_blender_host import (
    _snapshot_usd,PACKET_FORMAT,AUDIT_FORMAT,
    SCRIPT as ORIGINAL_WORKER,FRAME,BLEND,AUDIT,USD,MANIFEST,
    MAX_RENDER_STAGE)
from backend.nvp_usd_film02m_e2_district_render_view import (
    source_district_render_view)
from backend.nvp_usd_film02m_h_actor_camera_binding import (
    OriginalDistrictShotBinding)

FORMAT="nvp.usd_film02m_h.real_original_actor_district_cycles_source.v1"
REOPEN_FORMAT="nvp.usd_film02m_h.independent_cycles_district_reopen.v1"
REOPEN_SCRIPT="nvp_usd_film02mh_blender_reopen.py"
DISTRICT_EVIDENCE="district.json"
MAX_ACTUAL_MESHES=384


def _json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,
                      separators=(",",":"),allow_nan=False).encode("ascii")


def _hash(value):
    return sha256(_json(value)).hexdigest()


def _view_material_count(stage,part):
    from pxr import Usd,UsdGeom,UsdShade
    prim=stage.GetPrimAtPath(part)
    if not prim or not prim.IsDefined():
        raise RuntimeError("Original approved district render view is missing")
    meshes=[p for p in Usd.PrimRange(prim) if p.IsA(UsdGeom.Mesh)]
    if not meshes or len(meshes)>MAX_ACTUAL_MESHES:
        raise MemoryError("Approved native district mesh count outside render bound")
    bound=sum(bool(UsdShade.MaterialBindingAPI(
        p).ComputeBoundMaterial()[0]) for p in meshes)
    if bound!=len(meshes):
        raise RuntimeError("Original district USD PBR bindings were not preserved")
    return len(meshes),bound


def stage_approved_original_shot(index:FilmIndex,pid,binding_id,folder):
    """Build only a derived verified USD frame; NO worker grant/picture."""
    if not isinstance(index,FilmIndex):
        raise TypeError("Only native original FilmIndex source")
    _id(binding_id,"already-approved original actor/district shot")
    job=Path(folder)
    if not job.is_absolute() or job.is_symlink() or not job.is_dir():
        raise PermissionError("Only a host-owned existing render job directory")
    if any(job.iterdir()):
        raise FileExistsError("Original actor/district render staging must start empty")
    binding=OriginalDistrictShotBinding(
        index,confirm=lambda *_:False).reopen(pid,binding_id)
    shot=binding["source_preview"]
    # Exact approved FilmIndex binding is the sole authority for selecting
    # district, original performer, authored camera and film checkpoint.
    original=_snapshot_usd(index,pid,shot["world_take_id"],shot["film_tick"],job)
    if (original["original_world_take_sha256"]!=shot["world_take_sha256"] or
        original["original_camera_shot_sha256"]!=
            shot["shot_document_sha256"] or
        original["original_camera_path"]!=shot["original_camera_path"] or
        original["original_film_tick"]!=shot["film_tick"]):
        raise RuntimeError("01F source frame does not match approved 02M-H binding")
    from pxr import Usd,UsdGeom,Sdf,Gf
    src=Usd.Stage.Open(str(job/USD),load=Usd.Stage.LoadAll)
    if src is None:
        raise RuntimeError("Frozen original film frame failed independent USD load")
    camera=src.GetPrimAtPath(original["original_camera_path"])
    if not camera.IsA(UsdGeom.Camera):
        raise RuntimeError("No original authored camera in render stage")
    clock=Usd.TimeCode(1.0)
    original_camera=UsdGeom.Xformable(camera).ComputeLocalToWorldTransform(clock)
    actor_geometry={}
    for actor in original["actor_sources"]:
        for path in actor["geometry_prims"]:
            prim=src.GetPrimAtPath(path)
            if not prim or not prim.IsDefined():
                raise RuntimeError("Original source actor mesh was lost before staging")
            if prim.IsA(UsdGeom.Mesh):
                actor_geometry[path]=list(UsdGeom.Mesh(prim).GetPointsAttr().Get() or [])
            else:
                actor_geometry[path]=prim.GetTypeName()
    initial_actor_paths=set(actor_geometry)
    district_path="/World/OriginalFilmDistricts/"+shot["district_id"]
    with source_district_render_view(
            index,pid,shot["district_id"],shot["district_revision"]) as prepared:
        manifest=prepared["manifest"]
        if (manifest["original_district_document_sha256"]!=
                shot["district_document_sha256"] or
            manifest["original_point_instancer_root_sha256"]!=
                shot["district_original_usd_root_sha256"] or
            manifest["source_approved_world_origin_m"]!=
                shot["district_world_origin_m"]):
            raise RuntimeError("Derived district source no longer matches immutable shot")
        original_district=Usd.Stage.Open(
            str(prepared["root"]/"district_render_view.usda"),load=Usd.Stage.LoadAll)
        if not original_district:
            raise RuntimeError("Original district view did not compose")
        if len([p for p in original_district.Traverse()
                if p.IsA(UsdGeom.Mesh)])!=manifest["expected_actual_original_meshes"]:
            raise RuntimeError("Original USD PointInstancer expansion lost source meshes")
        # Flatten only the verified bounded E2 renderer view. No authored
        # source data are modified; the temporary authored view is discarded.
        derived=job/"district_render_derived.usda"
        if not original_district.Flatten(
                addSourceFileComment=False).Export(str(derived)):
            raise RuntimeError("Derived original district render layer cannot export")
        with Usd.EditContext(src,src.GetRootLayer()):
            UsdGeom.Scope.Define(src,"/World/OriginalFilmDistricts")
            prim=UsdGeom.Xform.Define(src,district_path)
            if not prim.GetPrim().GetReferences().AddReference(
                    "./"+derived.name,Sdf.Path("/World")):
                raise RuntimeError("Original source district could not join the film shot")
            if not UsdGeom.XformCommonAPI(prim).SetTranslate(
                    Gf.Vec3d(*shot["district_world_origin_m"])):
                raise RuntimeError("Approved source district origin cannot compose")
        mesh_count,material_count=_view_material_count(src,district_path)
        if mesh_count!=manifest["expected_actual_original_meshes"]:
            raise RuntimeError("Derived actual district geometry changed on composition")
        # Retain the 01D shot camera and 01E actor polygons and matrices
        # byte/data-for-data: no virtual worker is allowed to recast them.
        post_camera=UsdGeom.Xformable(
            src.GetPrimAtPath(original["original_camera_path"])
        ).ComputeLocalToWorldTransform(clock)
        if post_camera!=original_camera:
            raise PermissionError("Original film camera moved during district overlay")
        for path,previous in actor_geometry.items():
            prim=src.GetPrimAtPath(path)
            observed=(list(UsdGeom.Mesh(prim).GetPointsAttr().Get() or [])
                      if prim.IsA(UsdGeom.Mesh) else prim.GetTypeName())
            if observed!=previous:
                raise PermissionError("Original actor geometry changed during district staging")
        if set(actor_geometry)!=initial_actor_paths:
            raise RuntimeError("Original actor source shape changed")
        output=src.Flatten(addSourceFileComment=False)
        if not output.Export(str(job/USD)):
            raise RuntimeError("Combined original 3D USD shot cannot export")
        derived.unlink()
        if not 100<(job/USD).stat().st_size<=MAX_RENDER_STAGE:
            raise MemoryError("Combined 3D film snapshot exceeds source render budget")
        reopened=Usd.Stage.Open(str(job/USD),load=Usd.Stage.LoadAll)
        if not reopened:
            raise RuntimeError("Combined original native USD shot cannot reopen")
        checked,materials=_view_material_count(reopened,district_path)
        if checked!=mesh_count or materials!=material_count:
            raise RuntimeError("Independently reopened USD lost original district meshes")
        if not reopened.GetPrimAtPath(
                original["original_camera_path"]).IsA(UsdGeom.Camera):
            raise RuntimeError("Independently reopened shot lost camera source")
        for path in actor_geometry:
            if not reopened.GetPrimAtPath(path).IsDefined():
                raise RuntimeError("Independently reopened shot lost ActorID source geometry")
        evidence={
            "format":FORMAT,
            "project_id":pid,"binding_id":binding_id,
            "binding_sha256":binding["binding_document_sha256"],
            "world_take_id":shot["world_take_id"],
            "world_take_sha256":shot["world_take_sha256"],
            "source_camera_shot_sha256":shot["shot_document_sha256"],
            "source_camera_path":original["original_camera_path"],
            "source_film_tick":shot["film_tick"],
            "original_actor_count":len(original["actor_sources"]),
            "original_actor_source_paths":sorted(initial_actor_paths),
            "district_id":shot["district_id"],
            "district_revision":shot["district_revision"],
            "district_document_sha256":shot["district_document_sha256"],
            "original_district_usd_sha256":shot[
                "district_original_usd_root_sha256"],
            "district_origin_m":shot["district_world_origin_m"],
            "district_native_derived_view_sha256":prepared[
                "native_source_view_sha256"],
            "district_render_meshes":mesh_count,
            "district_render_bound_materials":material_count,
            "district_approved_instance_count":manifest[
                "source_visible_and_hand_placed_instances"],
            "derived_usd_sha256":sha_file(job/USD),
            "original_camera_matrix_unchanged":True,
            "actor_takes_and_pcm_unchanged":True,
            "source_district_point_instancer_not_rewritten":True,
            "actual_cycles_png_rendered":False,
        }
    original["source_usd_sha256"]=sha_file(job/USD)
    original["native_source_usd_size_bytes"]=(job/USD).stat().st_size
    packet={"format":PACKET_FORMAT,"source":original,
            "source_sha256":_hash(original)}
    (job/MANIFEST).write_bytes(_json(packet))
    (job/DISTRICT_EVIDENCE).write_bytes(_json(evidence))
    return {"packet":packet,"district":evidence,"job_dir":job,
            "has_real_rendered_pixels":False}


class ReviewedDistrictShotCyclesHost:
    """Existing protected Blender supervisor, separate one-use human grant."""

    def __init__(self,index:FilmIndex,supervisor:BlenderWorkerSupervisor,
                 *,verify_director_action):
        if (not isinstance(index,FilmIndex) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not callable(verify_director_action)):
            raise TypeError("Native FilmIndex, host supervisor and human review required")
        self.index=index
        self.supervisor=supervisor
        self.confirm=verify_director_action

    def stage(self,pid,binding_id,*,job_id):
        _id(job_id,"bounded original film source render job")
        if len(job_id)>60:
            raise ValueError("One bounded native film render job identity")
        job=self.supervisor.root/job_id
        if job.exists() or job.is_symlink():
            raise FileExistsError("Immutable original district render job already exists")
        job.mkdir(mode=0o700)
        try:
            data=stage_approved_original_shot(
                self.index,pid,binding_id,job)
            script=Path(__file__).resolve().parents[1]/"tools"/ORIGINAL_WORKER
            if script.is_symlink() or not script.is_file():
                raise RuntimeError("Existing reviewed original-source Blender worker absent")
            shutil.copyfile(script,job/ORIGINAL_WORKER)
            operation=BlenderOperation(
                job_id=job_id,script=ORIGINAL_WORKER,
                script_sha256=sha_file(job/ORIGINAL_WORKER),
                inputs={USD:sha_file(job/USD),
                        MANIFEST:sha_file(job/MANIFEST),
                        DISTRICT_EVIDENCE:sha_file(job/DISTRICT_EVIDENCE)},
                outputs={FRAME:"png",BLEND:"blend",AUDIT:"json_audit"},
                arguments={"--manifest":MANIFEST,
                           "--output":BLEND,
                           "--preview":FRAME,
                           "--audit":AUDIT},
                memory_limit_mb=8192,timeout_seconds=600,
                require_linux_cgroup_v2=False,gpu_memory_mb=0)
            self.supervisor._validate(operation)
            return {**data,"operation":operation}
        except Exception:
            shutil.rmtree(job)
            raise

    def render(self,pid,binding_id,*,job_id,director_event):
        prepared=self.stage(pid,binding_id,job_id=job_id)
        packet=prepared["packet"]
        source=packet["source"]
        district=prepared["district"]
        scope={
            "operation":"nvp.render.usd_film02m_h.original_district_actor_shot.v1",
            "project_id":pid,"binding_id":binding_id,
            "binding_sha256":district["binding_sha256"],
            "approved_district_sha256":district["district_document_sha256"],
            "original_world_take_sha256":district["world_take_sha256"],
            "original_camera_shot_sha256":district["source_camera_shot_sha256"],
            "source_usd_sha256":district["derived_usd_sha256"],
            "original_film_tick":district["source_film_tick"],
            "actual_district_meshes":district["district_render_meshes"],
            "original_actor_count":district["original_actor_count"],
        }
        if self.confirm(director_event,scope) is not True:
            raise PermissionError("Native source render requires fresh exact director approval")
        # Reopen the approved binding and immutable original source AGAIN
        # after consent and immediately before executing the reviewed worker.
        current=OriginalDistrictShotBinding(
            self.index,confirm=lambda *_:False).reopen(pid,binding_id)
        if (current["binding_document_sha256"]!=district["binding_sha256"] or
            current["source_preview"]["world_take_sha256"]!=
                district["world_take_sha256"] or
            current["source_preview"]["district_document_sha256"]!=
                district["district_document_sha256"] or
            sha_file(prepared["job_dir"]/USD)!=district["derived_usd_sha256"]):
            raise PermissionError("Original approved source changed before native render")
        state=self.supervisor.run(prepared["operation"])
        if state["state"]!="SUCCEEDED":
            raise RuntimeError("Protected district/actor Cycles render failed: "+
                               str(state.get("error") or state["state"]))
        self.supervisor.verify_completed(job_id)
        root=prepared["job_dir"]
        audit=json.loads((root/AUDIT).read_text("utf8"))
        if (audit.get("format")!=AUDIT_FORMAT or audit.get("passed") is not True or
            audit.get("original_world_take_sha256")!=source[
                "original_world_take_sha256"] or
            audit.get("original_camera_shot_sha256")!=source[
                "original_camera_shot_sha256"] or
            audit.get("source_usd_sha256")!=district["derived_usd_sha256"] or
            audit.get("original_actor_roots_found")!=district[
                "original_actor_count"] or
            audit.get("actual_native_cycles_image") is not True or
            audit.get("rendered_png_sha256")!=sha_file(root/FRAME) or
            audit.get("saved_blend_sha256")!=sha_file(root/BLEND)):
            raise RuntimeError("Native Cycles rendered image lacks original source evidence")
        # Independent second Blender session reopens saved .blend, verifies
        # original ActorID/camera source and REAL building mesh/materials.
        proof=self._reopen_blend(
            pid,job_id,source,district,root)
        return {
            "state":"RENDERED_REAL_ORIGINAL_DISTRICT_ACTOR_CAMERA_SHOT",
            "job_id":job_id,"png_sha256":sha_file(root/FRAME),
            "blend_sha256":sha_file(root/BLEND),
            "original_world_take_sha256":district["world_take_sha256"],
            "original_camera_shot_sha256":district["source_camera_shot_sha256"],
            "approved_original_district_sha256":district[
                "district_document_sha256"],
            "binding_sha256":district["binding_sha256"],
            "original_film_tick":district["source_film_tick"],
            "native_supervisor_reverified":True,
            "independent_saved_blend_reopened":proof[
                "actual_saved_source_district_meshes_verified"],
            "actual_original_district_meshes":district["district_render_meshes"],
            "source_actor_take_pcm_unchanged":True,
            "actual_film_frame_rendered":True,
            "actor_appearance_photorealism_approved":False,
            "final_film_accepted":False}

    def _reopen_blend(self,pid,job_id,source,district,root):
        from backend.nvp_usd_film01f_blender_host import REOPEN_SCRIPT
        reopen_id=job_id+"_reopen"
        _id(reopen_id,"independent original district Blender reopen")
        if len(reopen_id)>80:
            raise ValueError("Independent reopen ID too long")
        location=self.supervisor.root/reopen_id
        if location.exists() or location.is_symlink():
            raise FileExistsError("Independent Blender reopen job already exists")
        location.mkdir(mode=0o700)
        shutil.copyfile(root/BLEND,location/BLEND)
        evidence={
            "source":source,
            "district":district,
            "source_blend_sha256":sha_file(location/BLEND)}
        (location/MANIFEST).write_bytes(_json(evidence))
        worker=Path(__file__).resolve().parents[1]/"tools"/REOPEN_SCRIPT
        if worker.is_symlink() or not worker.is_file():
            raise RuntimeError("Independent first-party Blender source reopener unavailable")
        shutil.copyfile(worker,location/REOPEN_SCRIPT)
        # This second worker deliberately verifies existing 01F actor/camera
        # scene source. District geometry is additionally checked by the
        # distinct dedicated 02MH reopener below.
        old_operation=BlenderOperation(
            job_id=reopen_id,scene=BLEND,script=REOPEN_SCRIPT,
            script_sha256=sha_file(location/REOPEN_SCRIPT),
            inputs={BLEND:sha_file(location/BLEND),
                    MANIFEST:sha_file(location/MANIFEST)},
            outputs={AUDIT:"json_audit"},
            arguments={"--manifest":MANIFEST,"--audit":AUDIT},
            memory_limit_mb=8192,timeout_seconds=600,
            require_linux_cgroup_v2=False)
        self.supervisor._validate(old_operation)
        # The separate dedicated 02MH verifier is used instead of the 01F
        # contract because we also require native district mesh readback.
        dedicated=Path(__file__).resolve().parents[1]/"tools"/REOPEN_SCRIPT_NAME
        return self._run_district_reopen(
            pid,job_id,location,evidence,old_operation,dedicated)

    def _run_district_reopen(self,pid,job_id,location,evidence,operation,worker):
        if worker.is_symlink() or not worker.is_file():
            raise RuntimeError("Reviewed district/camera Blender verifier is missing")
        shutil.copyfile(worker,location/REOPEN_SCRIPT_NAME)
        job=BlenderOperation(
            job_id=operation.job_id,scene=BLEND,
            script=REOPEN_SCRIPT_NAME,
            script_sha256=sha_file(location/REOPEN_SCRIPT_NAME),
            inputs={BLEND:sha_file(location/BLEND),
                    MANIFEST:sha_file(location/MANIFEST)},
            outputs={AUDIT:"json_audit"},
            arguments={"--manifest":MANIFEST,"--audit":AUDIT},
            memory_limit_mb=8192,timeout_seconds=600,
            require_linux_cgroup_v2=False)
        self.supervisor._validate(job)
        state=self.supervisor.run(job)
        if state["state"]!="SUCCEEDED":
            raise RuntimeError("Independent native Cycles district .blend reopen failed")
        self.supervisor.verify_completed(operation.job_id)
        proof=json.loads((location/AUDIT).read_text("utf8"))
        if (proof.get("format")!=REOPEN_FORMAT or
            proof.get("passed") is not True or
            proof.get("source_blend_sha256")!=evidence["source_blend_sha256"] or
            proof.get("world_take_sha256")!=evidence["district"][
                "world_take_sha256"] or
            proof.get("source_usd_sha256")!=evidence["district"][
                "derived_usd_sha256"] or
            proof.get("actual_saved_source_district_meshes_verified") is not True or
            proof.get("source_actor_camera_unchanged") is not True):
            raise RuntimeError("Independent Cycles reopen lost original district/actor/camera source")
        return proof


REOPEN_SCRIPT_NAME="nvp_usd_film02mh_blender_reopen.py"
