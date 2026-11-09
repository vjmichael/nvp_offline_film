"""CAM-FX-05A: exact-time, immutable ActorID shot + derived director rail camera.

This is *source staging only*. The original 01D camera, 01E actor/PCM Takes,
approved district and rail revision remain untouched. The additional rail
camera is authored only in a disposable USD render snapshot. No Blender
process is dispatched and no human render consent is inferred from a rail
publication receipt. A distinct audited rail-aware Blender worker is still
required for actual CAM-FX-05 Cycles image acceptance.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_blender_worker import sha_file
from backend.nvp_cam_fx01_camera_rails import OriginalCameraRails, evaluate_rail
from backend.nvp_cam_fx02_usd_camera_layer import (
    _read_strong_layer, camera_matrix_rows, camera_rail_path,
    MM_PER_CAMERA_UNIT, METERS_PER_UNIT)
from backend.nvp_usd_film02m_h_actor_camera_binding import OriginalDistrictShotBinding
from backend.nvp_usd_film02m_h_render_handoff import stage_approved_original_shot
from backend.nvp_usd_film01f_blender_host import USD, MANIFEST

FORMAT = "nvp.cam_fx05.source_verified_original_performance_rail_frame.v1"
RECEIPT = "cam_fx05_rail_source.json"


def _canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _reopened_prims(stage, actor_paths, source_camera_path, rail_path, time):
    from pxr import UsdGeom
    source_camera=stage.GetPrimAtPath(source_camera_path)
    rail_camera=stage.GetPrimAtPath(rail_path)
    if (not source_camera.IsA(UsdGeom.Camera) or
        not rail_camera.IsA(UsdGeom.Camera)):
        raise RuntimeError("Both original 01D and separate director cameras must compose")
    for path in actor_paths:
        if not stage.GetPrimAtPath(path).IsDefined():
            raise RuntimeError("An immutable original ActorID source prim was lost")
    original=UsdGeom.Xformable(source_camera).ComputeLocalToWorldTransform(time)
    rail=UsdGeom.Xformable(rail_camera).ComputeLocalToWorldTransform(time)
    return original,rail


def _actor_geometry_signature(stage,paths,at):
    from pxr import UsdGeom
    signature=[]
    for path in paths:
        prim=stage.GetPrimAtPath(path)
        if not prim.IsDefined() or not prim.IsA(UsdGeom.Gprim):
            raise RuntimeError("Original actor geometry is missing or no longer a USD Gprim")
        xform=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(at)
        row_data=[[float(xform[i][j]) for j in range(4)] for i in range(4)]
        if prim.IsA(UsdGeom.Mesh):
            points=UsdGeom.Mesh(prim).GetPointsAttr().Get(at)
            position_data=[[float(v) for v in p] for p in (points or [])]
        else:
            position_data=None
        signature.append([path,prim.GetTypeName(),row_data,position_data])
    return _canonical(signature)


def stage_approved_rail_frame(index: FilmIndex, pid: str, binding_id: str,
                              rail_id: str, rail_revision: int, folder: Path):
    """Stage a single approved original 02M-H source tick from an approved rail.

    This deliberately does NOT alter the 01F source camera fields in the
    manifest. Those fields describe the *original* camera even when a distinct
    director camera will be selected by a future rail-aware renderer.
    """
    from pxr import Sdf, Usd, UsdGeom, Gf
    if not isinstance(index, FilmIndex):
        raise TypeError("Native project-local FilmIndex required")
    _require_pid(pid)
    _id(binding_id, "exact approved original actor/district shot")
    _id(rail_id, "exact approved director camera rail")
    if type(rail_revision) is not int or rail_revision<1:
        raise ValueError("An immutable approved rail revision is required")
    job=Path(folder)
    if not job.is_absolute() or job.is_symlink() or not job.is_dir() or any(job.iterdir()):
        raise PermissionError("Only a fresh private native render staging directory")
    rail=OriginalCameraRails(index,verify_director_action=lambda *_:False).verify(
        pid,rail_id,rail_revision)
    binding=OriginalDistrictShotBinding(
        index,confirm=lambda *_:False).reopen(pid,binding_id)
    shot=binding["source_preview"]
    spec=rail["rail_spec"]
    tick=shot["film_tick"]
    if (shot["world_take_id"]!=rail["world_take_id"] or
        shot["world_take_sha256"]!=rail["world_take_sha256"] or
        not spec["film_start_tick"]<=tick<=spec["film_end_tick"]):
        raise PermissionError("Approved rail does not cover the exact frozen 01E shot")
    before_objects=index.list_objects(pid,kind="take")
    # All source snapshots are ordinary existing 02M-H independently reviewed
    # original actor+district+camera stages, never an AI-generated surrogate.
    staged=stage_approved_original_shot(index,pid,binding_id,job)
    original=staged["packet"]["source"]
    original_usd_sha=sha_file(job/USD)
    src=Usd.Stage.Open(str(job/USD),load=Usd.Stage.LoadAll)
    if not src:
        raise RuntimeError("Frozen approved source cannot reopen")
    source_camera=original["original_camera_path"]
    actor_paths=staged["district"]["original_actor_source_paths"]
    at=Usd.TimeCode(1.0)
    source_before=UsdGeom.Xformable(
        src.GetPrimAtPath(source_camera)).ComputeLocalToWorldTransform(at)
    actor_before=_actor_geometry_signature(src,actor_paths,at)
    source_layer_before=src.GetRootLayer().ExportToString()
    if src.GetPrimAtPath("/World/NVPDirectorRails").IsDefined():
        raise PermissionError("Authoritative source already owns the director rail namespace")
    stored=index.get_blob(pid,rail["rail_layer_sha256"])
    if sha256(stored).hexdigest()!=rail["rail_layer_sha256"]:
        raise RuntimeError("Approved rail layer bytes differ from pinned source")
    stronger=_read_strong_layer(stored)
    rail_path=camera_rail_path(rail_id)
    session=src.GetSessionLayer()
    session.subLayerPaths.insert(0,stronger.identifier)
    try:
        camera=UsdGeom.Camera.Get(src,rail_path)
        if not camera or not camera.GetPrim().IsDefined():
            raise RuntimeError("Native approved USD camera rail did not compose")
        position=evaluate_rail(spec,tick)
        rail_rows=camera_matrix_rows(position)
        camera_at=Usd.TimeCode(float(tick))
        observed=UsdGeom.Xformable(camera).GetLocalTransformation(camera_at)
        if any(abs(float(observed[i][j])-rail_rows[i][j])>1e-5
               for i in range(4) for j in range(4)):
            raise RuntimeError("Director camera does not agree with pinned Film Time")
        # Original snapshot is fixed at source time 1; freeze ONLY the derived
        # rail camera at that frame for Blender, retaining the original shot
        # and separately recording authoritative original Film Time ticks.
        composed=src.Flatten(addSourceFileComment=False)
        frozen=Usd.Stage.Open(composed)
        frozen_camera=UsdGeom.Camera.Get(frozen,rail_path)
        if not frozen_camera or not frozen_camera.GetPrim().IsDefined():
            raise RuntimeError("Derived camera disappeared when USD was flattened")
        rail_attrs=[
            frozen_camera.GetPrim().GetAttribute("xformOp:transform:NVPFilmTime"),
            frozen_camera.GetFocalLengthAttr(),
            frozen_camera.GetFocusDistanceAttr(),
            frozen_camera.GetFStopAttr(),
        ]
        if not all(rail_attrs):
            raise RuntimeError("Approved camera rail has incomplete optical/xform source")
        for attr in rail_attrs:
            value=attr.Get(camera_at)
            if value is None:
                raise RuntimeError("Approved rail sample was not defined at source tick")
            for old in attr.GetTimeSamples():
                if not attr.ClearAtTime(Usd.TimeCode(old)):
                    raise RuntimeError("Could not isolate disposable rail sample")
            if not attr.Set(value,at):
                raise RuntimeError("Could not freeze disposable rail sample")
        frozen.SetStartTimeCode(1.0)
        frozen.SetEndTimeCode(1.0)
        frozen.SetTimeCodesPerSecond(24.0)
        frozen.SetFramesPerSecond(24.0)
        prior,frozen_rail=_reopened_prims(
            frozen,actor_paths,source_camera,rail_path,at)
        if (_actor_geometry_signature(frozen,actor_paths,at)!=actor_before or
            prior!=source_before or any(
            abs(float(frozen_rail[i][j])-rail_rows[i][j])>1e-5
            for i in range(4) for j in range(4))):
            raise PermissionError("Disposable rail staging moved original camera or altered director pose")
        pending=job/"source.rail.pending.usda"
        if not frozen.Export(str(pending)):
            raise RuntimeError("Combined approved rail source cannot export")
        if not 100<pending.stat().st_size<=64*1024*1024:
            raise MemoryError("Source rail stage exceeds bounded native render size")
        physical=Sdf.Layer.CreateAnonymous("fx05-independent-physical-readback.usda")
        if not physical.ImportFromString(pending.read_text("utf8")):
            raise RuntimeError("Saved rail stage cannot reparse from physical bytes")
        independent=Usd.Stage.Open(physical,load=Usd.Stage.LoadAll)
        source_after,rail_after=_reopened_prims(
            independent,actor_paths,source_camera,rail_path,at)
        if (source_after!=source_before or
            _actor_geometry_signature(independent,actor_paths,at)!=actor_before or
            any(abs(float(rail_after[i][j])-rail_rows[i][j])>1e-5
                for i in range(4) for j in range(4))):
            raise RuntimeError("Independent physical OpenUSD readback differs from rail")
        os.replace(pending,job/USD)
    finally:
        if stronger.identifier in session.subLayerPaths:
            session.subLayerPaths.remove(stronger.identifier)
    if src.GetRootLayer().ExportToString()!=source_layer_before:
        raise RuntimeError("Source stage root mutated during derived camera opinion")
    packet=staged["packet"]
    packet["source"]["source_usd_sha256"]=sha_file(job/USD)
    packet["source"]["native_source_usd_size_bytes"]=(job/USD).stat().st_size
    packet["source_sha256"]=sha256(_canonical(packet["source"])).hexdigest()
    (job/MANIFEST).write_bytes(_canonical(packet))
    current=OriginalCameraRails(
        index,verify_director_action=lambda *_:False).verify(
            pid,rail_id,rail_revision)
    if (current!=rail or
        index.list_objects(pid,kind="take")!=before_objects):
        raise RuntimeError("Immutable original Takes or approved rail changed during stage")
    evidence={
        "format":FORMAT,"project_id":pid,
        "binding_id":binding_id,
        "binding_sha256":binding["binding_document_sha256"],
        "rail_id":rail_id,"rail_revision":rail_revision,
        "rail_revision_sha256":index.read_revision(
            pid,rail_id,rail_revision)["document_sha256"],
        "rail_layer_sha256":rail["rail_layer_sha256"],
        "source_camera_bank_sha256":rail["camera_bank_sha256"],
        "original_world_take_sha256":rail["world_take_sha256"],
        "original_camera_shot_sha256":original["original_camera_shot_sha256"],
        "original_camera_path":source_camera,
        "director_camera_path":rail_path,
        "director_camera_position_m":position["position_m"],
        "director_camera_matrix_rows":rail_rows,
        "director_camera_focal_length_mm":position["focal_length_mm"],
        "director_camera_focus_distance_m":position["focus_distance_m"],
        "director_camera_technique":position["technique"],
        "source_film_tick":tick,
        "derived_frame_timecode":1,
        "original_02mh_usd_sha256":original_usd_sha,
        "derived_with_rail_usd_sha256":sha_file(job/USD),
        "source_camera_matrix_unchanged":True,
        "original_actor_takes_and_pcm_unchanged":True,
        "original_01d_source_not_rewritten":True,
        "actual_blender_cycles_pixels":False,
        "director_film_quality_approved":False}
    (job/RECEIPT).write_bytes(_canonical(evidence))
    return {"receipt":evidence, "packet":packet,
            "director_camera_sample":position,
            "source_job_dir":str(job),
            "native_blender_workers_started":0}
