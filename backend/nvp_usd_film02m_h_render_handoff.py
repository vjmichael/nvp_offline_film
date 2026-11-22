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
import os
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
        # Do not write a live-cached Sdf layer in place and then mistake
        # another Stage.Open() of the cached identifier for disk readback.
        pending=job/"combined-original-shot.pending.usda"
        if not output.Export(str(pending)):
            raise RuntimeError("Combined original 3D USD shot cannot export")
        os.replace(pending,job/USD)
        derived.unlink()
        if not 100<(job/USD).stat().st_size<=MAX_RENDER_STAGE:
            raise MemoryError("Combined 3D film snapshot exceeds source render budget")
        # Anonymous imported bytes force an INDEPENDENT read of the exact
        # exported file even if the original Sdf layer is still cached.
        physical=Sdf.Layer.CreateAnonymous("original-district-disk-readback.usda")
        if not physical.ImportFromString((job/USD).read_text("utf8")):
            raise RuntimeError("Derived USD file could not parse from disk bytes")
        reopened=Usd.Stage.Open(physical,load=Usd.Stage.LoadAll)
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
                require_linux_cgroup_v2=True,require_private_isolation=True,gpu_memory_mb=0)
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
        try:
            granted=self.confirm(director_event,scope) is True
        except Exception:
            # No worker was dispatched, and the approved source is already
            # immutable. Do not leave rejected derived USD copies behind.
            shutil.rmtree(prepared["job_dir"])
            raise
        if not granted:
            shutil.rmtree(prepared["job_dir"])
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
        # The immutable originals are read *again* after both native Blender
        # workers. Neither first render nor independent reopen may mutate
        # the original 01E actor Take, scene Takes, authored 01D camera,
        # approved district layer or underlying world. This also guards
        # original PCM evidence, which is part of frozen Take source.
        immutable=OriginalDistrictShotBinding(
            self.index,confirm=lambda *_:False).reopen(pid,binding_id)
        if (immutable["binding_document_sha256"]!=district["binding_sha256"] or
            immutable["source_preview"]["world_take_sha256"]!=
                district["world_take_sha256"] or
            immutable["source_preview"]["shot_document_sha256"]!=
                district["source_camera_shot_sha256"] or
            immutable["source_preview"]["district_document_sha256"]!=
                district["district_document_sha256"] or
            sha_file(root/USD)!=district["derived_usd_sha256"]):
            raise RuntimeError("Original approved source changed while Cycles rendered")
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

    def compare_approved_revisions(self,pid,first_binding,second_binding,*,
                                   first_job_id,second_job_id,director_event):
        """Prove changed 3D environment over identical frozen actor/camera."""
        left=OriginalDistrictShotBinding(
            self.index,confirm=lambda *_:False).reopen(pid,first_binding)[
                "source_preview"]
        right=OriginalDistrictShotBinding(
            self.index,confirm=lambda *_:False).reopen(pid,second_binding)[
                "source_preview"]
        if (left["district_id"]!=right["district_id"] or
            left["district_document_sha256"]==
                right["district_document_sha256"] or
            left["world_take_id"]!=right["world_take_id"] or
            left["world_take_sha256"]!=right["world_take_sha256"] or
            left["shot_document_sha256"]!=
                right["shot_document_sha256"] or
            left["film_tick"]!=right["film_tick"] or
            left["original_actor_poses"]!=right["original_actor_poses"] or
            left["original_camera_position_m"]!=
                right["original_camera_position_m"]):
            raise PermissionError(
                "Only changed district over identical original performance/shot")
        if first_binding==second_binding or first_job_id==second_job_id:
            raise ValueError("Require two distinct approved district revisions")
        first=self.render(
            pid,first_binding,job_id=first_job_id,
            director_event=director_event)
        second=self.render(
            pid,second_binding,job_id=second_job_id,
            director_event=director_event)
        if (first["png_sha256"]==second["png_sha256"] or
            first["original_world_take_sha256"]!=
                second["original_world_take_sha256"] or
            first["original_camera_shot_sha256"]!=
                second["original_camera_shot_sha256"]):
            raise RuntimeError(
                "Reviewed district change did not produce a distinct original frame")
        from PIL import Image,ImageChops
        with (Image.open(self.supervisor.root/first_job_id/FRAME) as a,
              Image.open(self.supervisor.root/second_job_id/FRAME) as b):
            if a.size!=b.size or a.size!=(320,180):
                raise RuntimeError("Original comparison uses incompatible frames")
            delta=ImageChops.difference(a.convert("RGB"),b.convert("RGB"))
            changed=sum(1 for pixel in delta.getdata() if max(pixel)>12)
        if changed<250:
            raise RuntimeError(
                "Different district sources did not visibly change original shot pixels")
        return {
            "format":"nvp.usd_film02m_h.real_native_two_district_revision_comparison.v1",
            "original_world_take_sha256":left["world_take_sha256"],
            "original_camera_shot_sha256":left["shot_document_sha256"],
            "original_film_tick":left["film_tick"],
            "district_revision_shas":[left["district_document_sha256"],
                                      right["district_document_sha256"]],
            "native_cycles_png_shas":[first["png_sha256"],
                                     second["png_sha256"]],
            "real_pixels_changed_significantly":True,
            "changed_pixels_over_12_rgb":changed,
            "original_actor_take_pcm_unchanged":True,
            "independent_blender_reopened_both":True,
            "human_shot_quality_approved":False,
            "complete_film_accepted":False}

    def reopen_verified_render(self,pid,binding_id,job_id):
        """Restart-safe READ-ONLY review; never starts or approves a worker.

        The original binding is reverified from FilmIndex; both completed
        Blender jobs are independently journal-checked and their exact
        input/source SHA-256 re-opened before image bytes may be disclosed.
        """
        _id(binding_id,"immutable approved original film shot")
        _id(job_id,"bounded original Cycles job")
        binding=OriginalDistrictShotBinding(
            self.index,confirm=lambda *_:False).reopen(pid,binding_id)
        shot=binding["source_preview"]
        status=self.supervisor.verify_completed(job_id)
        job=self.supervisor.root/job_id
        if job.is_symlink():
            raise PermissionError("Untrusted native picture directory")
        source=json.loads((job/MANIFEST).read_text("utf8"))
        district=json.loads((job/DISTRICT_EVIDENCE).read_text("utf8"))
        if (type(source) is not dict or set(source)!={
                "format","source","source_sha256"} or
            source["format"]!=PACKET_FORMAT or
            source["source_sha256"]!=_hash(source["source"]) or
            district.get("format")!=FORMAT or
            district.get("project_id")!=pid or
            district.get("binding_id")!=binding_id or
            district.get("binding_sha256")!=binding[
                "binding_document_sha256"] or
            district.get("world_take_sha256")!=shot["world_take_sha256"] or
            district.get("source_camera_shot_sha256")!=shot[
                "shot_document_sha256"] or
            district.get("district_document_sha256")!=shot[
                "district_document_sha256"] or
            district.get("source_film_tick")!=shot["film_tick"] or
            district.get("derived_usd_sha256")!=sha_file(job/USD) or
            source["source"].get("source_usd_sha256")!=district[
                "derived_usd_sha256"]):
            raise RuntimeError("Native picture source or actor/district binding changed")
        audit=json.loads((job/AUDIT).read_text("utf8"))
        if (audit.get("format")!=AUDIT_FORMAT or
            audit.get("passed") is not True or
            audit.get("original_world_take_sha256")!=district[
                "world_take_sha256"] or
            audit.get("original_camera_shot_sha256")!=district[
                "source_camera_shot_sha256"] or
            audit.get("source_usd_sha256")!=district[
                "derived_usd_sha256"] or
            audit.get("rendered_png_sha256")!=sha_file(job/FRAME) or
            audit.get("saved_blend_sha256")!=sha_file(job/BLEND) or
            audit.get("actual_native_cycles_image") is not True):
            raise RuntimeError("No source-verified original actor/district Cycles frame")
        reopen_id=job_id+"_reopen"
        self.supervisor.verify_completed(reopen_id)
        reopen_root=self.supervisor.root/reopen_id
        if reopen_root.is_symlink():
            raise PermissionError("Untrusted independent Blender reopener")
        independent=json.loads((reopen_root/AUDIT).read_text("utf8"))
        if (independent.get("format")!=REOPEN_FORMAT or
            independent.get("passed") is not True or
            independent.get("source_blend_sha256")!=sha_file(job/BLEND) or
            independent.get("world_take_sha256")!=district[
                "world_take_sha256"] or
            independent.get("source_usd_sha256")!=district[
                "derived_usd_sha256"] or
            independent.get("district_document_sha256")!=district[
                "district_document_sha256"] or
            independent.get("source_district_meshes_expected")!=district[
                "district_render_meshes"] or
            independent.get("actor_count")!=district[
                "original_actor_count"] or
            independent.get("actual_saved_source_district_meshes_verified")
                is not True or
            independent.get("source_actor_camera_unchanged") is not True):
            raise RuntimeError("Saved native Cycles scene cannot be independently reopened")
        picture=job/FRAME
        if (picture.is_symlink() or not picture.is_file() or
            not 128<=picture.stat().st_size<=12*1024*1024):
            raise RuntimeError("Verified Cycles review PNG missing or oversized")
        return {
            "format":"nvp.usd_film02m_h.verified_native_cycles_picture.v1",
            "project_id":pid,"binding_id":binding_id,
            "binding_sha256":binding["binding_document_sha256"],
            "job_id":job_id,
            "picture_sha256":sha_file(picture),
            "saved_blend_sha256":sha_file(job/BLEND),
            "district_document_sha256":district["district_document_sha256"],
            "world_take_sha256":district["world_take_sha256"],
            "source_camera_shot_sha256":district[
                "source_camera_shot_sha256"],
            "film_tick":district["source_film_tick"],
            "original_actor_count":district["original_actor_count"],
            "original_district_meshes":district["district_render_meshes"],
            "native_worker_and_independent_reopen_verified":True,
            "original_actor_takes_and_pcm_unchanged":True,
            "director_picture_approved":False,
            "final_film_accepted":False}

    def _reopen_blend(self,pid,job_id,source,district,root):
        reopen_id=job_id+"_reopen"
        _id(reopen_id,"independent original district Blender reopen")
        if len(reopen_id)>80:
            raise ValueError("Independent reopened Blender job identity is unbounded")
        location=self.supervisor.root/reopen_id
        if location.exists() or location.is_symlink():
            raise FileExistsError("Cannot replace existing Blender source reopen receipt")
        location.mkdir(mode=0o700)
        shutil.copyfile(root/BLEND,location/BLEND)
        evidence={"source":source,"district":district,
                  "source_blend_sha256":sha_file(location/BLEND)}
        (location/MANIFEST).write_bytes(_json(evidence))
        script=Path(__file__).resolve().parents[1]/"tools"/REOPEN_SCRIPT_NAME
        if script.is_symlink() or not script.is_file():
            raise RuntimeError("Independent reviewed native district Blender verifier absent")
        shutil.copyfile(script,location/REOPEN_SCRIPT_NAME)
        operation=BlenderOperation(
            job_id=reopen_id,scene=BLEND,script=REOPEN_SCRIPT_NAME,
            script_sha256=sha_file(location/REOPEN_SCRIPT_NAME),
            inputs={BLEND:sha_file(location/BLEND),
                    MANIFEST:sha_file(location/MANIFEST)},
            outputs={AUDIT:"json_audit"},
            arguments={"--manifest":MANIFEST,"--audit":AUDIT},
            memory_limit_mb=8192,timeout_seconds=600,
            require_linux_cgroup_v2=True,require_private_isolation=True)
        self.supervisor._validate(operation)
        state=self.supervisor.run(operation)
        if state["state"]!="SUCCEEDED":
            raise RuntimeError("Independent native district/actor Cycles .blend reopen failed")
        self.supervisor.verify_completed(reopen_id)
        proof=json.loads((location/AUDIT).read_text("utf8"))
        if (proof.get("format")!=REOPEN_FORMAT or
            proof.get("passed") is not True or
            proof.get("source_blend_sha256")!=evidence["source_blend_sha256"] or
            proof.get("world_take_sha256")!=district["world_take_sha256"] or
            proof.get("source_usd_sha256")!=district["derived_usd_sha256"] or
            proof.get("district_document_sha256")!=district[
                "district_document_sha256"] or
            proof.get("actor_count")!=district["original_actor_count"] or
            proof.get("source_district_meshes_expected")!=district[
                "district_render_meshes"] or
            proof.get("actual_saved_source_district_meshes_verified") is not True or
            proof.get("source_actor_camera_unchanged") is not True):
            raise RuntimeError(
                "Independent Blender reopen lost original district/actor/camera source")
        return proof

REOPEN_SCRIPT_NAME="nvp_usd_film02mh_blender_reopen.py"
