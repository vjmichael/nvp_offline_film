"""USD-FILM-01O: one source-authentic 30-second 24fps USD for any 01M rig.

This is an immutable DERIVED render input for reviewed Blender workers.
Original FilmIndex world/Take/ActorIDs stay untouched. Every camera observes
the same evaluated scene at each frame. The full 720-state manifest lets a
later independent verifier reject individually consistent but false worker
frame receipts.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import MAX_USD_EXACT_TICK
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank

FORMAT="nvp.usd_film01o.original_720frame_director_rig_source.v1"
STAGE="original_camera_roll_source.usda"
MANIFEST="original_camera_roll_source.json"
FPS=24
FRAMES=720
MAX_ANIMATED_ATTRIBUTES=512
MAX_SOURCE_USD_BYTES=128*1024*1024


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def file_sha(path):
    h=sha256()
    with Path(path).open("rb") as inp:
        for part in iter(lambda:inp.read(1<<20),b""):
            h.update(part)
    return h.hexdigest()


def original_camera_roll_source(index:FilmIndex,pid,bank_id,*,revision,folder):
    """Capture source-verified full performance + virtual cameras ONCE."""
    from pxr import Sdf,Usd,UsdGeom
    if not isinstance(index,FilmIndex):
        raise TypeError("Authoritative original FilmIndex required")
    bank=DirectorCameraBank(index,verify_director_action=lambda *_:False)
    doc=bank.verify(pid,bank_id,revision)
    if not 1<=doc["camera_count"]<=96 or doc["source_duration_ticks"]<30*T:
        raise ValueError("One nonempty director camera rig and full 30s Take required")
    bank_record=index.read_revision(pid,bank_id,revision)
    take=index.read_revision(pid,doc["world_take_id"],1)
    target=Path(folder)
    if target.is_symlink() or target.exists():
        raise FileExistsError("Do not overwrite derived camera source evidence")
    target.mkdir(parents=True,mode=0o700)
    try:
        with bank.open_source_views(pid,bank_id,revision) as view:
            stage=view["stage"]
            cameras=view["camera_paths"]
            source_actors=take["data"]["canonical_original_actors"]
            original_frame_evidence=[]
            source_attributes=[]
            for prim in stage.TraverseAll():
                for attribute in prim.GetAttributes():
                    if attribute.GetTypeName()==Sdf.ValueTypeNames.Asset:
                        asset=attribute.Get()
                        if asset is not None and asset.path:
                            raise PermissionError("Unreviewed external source texture in USD")
                    if attribute.GetNumTimeSamples()>0:
                        source_attributes.append((str(prim.GetPath()),
                                                  attribute.GetName()))
            if len(source_attributes)>MAX_ANIMATED_ATTRIBUTES:
                raise RuntimeError("Bounded USD animation attribute cap exceeded")
            for frame in range(FRAMES):
                tick=frame*T//FPS
                if tick>MAX_USD_EXACT_TICK:
                    raise RuntimeError("Original precise Film Time cannot fit native USD")
                timestamp=Usd.TimeCode(float(tick))
                poses=[]
                for actor in source_actors:
                    original_path=actor["composed_actor_prim"]
                    prim=stage.GetPrimAtPath(original_path)
                    if not prim or not prim.IsDefined():
                        raise RuntimeError("Original ActorID source disappeared")
                    matrix=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
                        timestamp)
                    pos=matrix.ExtractTranslation()
                    timed=[]
                    for child in Usd.PrimRange(prim):
                        for attr in child.GetAttributes():
                            if attr.GetNumTimeSamples()>0:
                                value=attr.Get(timestamp)
                                if value is None:
                                    raise RuntimeError("Original actor timed attribute absent")
                                timed.append([str(child.GetPath()),
                                              attr.GetName(),str(value)])
                    poses.append({
                        "actor_id":actor["actor_id"],
                        "source_prim":original_path,
                        "position_m":[round(float(pos[j]),9) for j in range(3)],
                        "timed_source_sha256":digest(sorted(timed))})
                camera_evidence=[]
                for item in doc["cameras"]:
                    p=cameras[item["camera_id"]]
                    matrix=UsdGeom.Xformable(
                        stage.GetPrimAtPath(p)).ComputeLocalToWorldTransform(
                            timestamp)
                    pos=matrix.ExtractTranslation()
                    camera_evidence.append({
                        "camera_id":item["camera_id"],
                        "source_prim":p,
                        "position_m":[round(float(pos[j]),9) for j in range(3)]})
                original_frame_evidence.append({
                    "frame":frame,"original_film_tick":tick,
                    "original_actor_state_sha256":digest(poses),
                    "original_actor_positions":poses,
                    "original_camera_positions":camera_evidence})
            flattened=stage.Flatten(addSourceFileComment=False)
            derived=Usd.Stage.Open(flattened)
            if not derived:
                raise RuntimeError("Original USD camera source does not flatten")
            for original_path,attr_name in source_attributes:
                prim=derived.GetPrimAtPath(original_path)
                attr=prim.GetAttribute(attr_name)
                if not attr:
                    raise RuntimeError("USD source time-sampled attribute disappeared")
                values=[]
                for evidence in original_frame_evidence:
                    value=attr.Get(Usd.TimeCode(
                        float(evidence["original_film_tick"])))
                    if value is None:
                        raise RuntimeError("Original native source animation is incomplete")
                    values.append(value)
                old_times=attr.GetTimeSamples()
                for old in old_times:
                    if not attr.ClearAtTime(Usd.TimeCode(float(old))):
                        raise RuntimeError("Cannot clear derived-only old animation key")
                for i,value in enumerate(values):
                    if not attr.Set(value,Usd.TimeCode(float(i+1))):
                        raise RuntimeError("Cannot write new derived 24fps animation key")
            derived.SetTimeCodesPerSecond(24.)
            derived.SetFramesPerSecond(24.)
            derived.SetStartTimeCode(1.)
            derived.SetEndTimeCode(720.)
            dest=target/STAGE
            if not derived.Export(str(dest)):
                raise RuntimeError("Native source 720-frame USD export failed")
            size=dest.stat().st_size
            if not 100<size<=MAX_SOURCE_USD_BYTES:
                raise RuntimeError("Bounded source USD film file invalid")
            reopen=Usd.Stage.Open(str(dest),load=Usd.Stage.LoadAll)
            if not reopen or reopen.GetFramesPerSecond()!=24.:
                raise RuntimeError("Actual native USD 24fps source cannot reopen")
            for checkpoint in (0,239,240,479,480,719):
                tick=Usd.TimeCode(float(checkpoint))
                out=Usd.TimeCode(float(checkpoint+1))
                for actor in source_actors:
                    p=actor["composed_actor_prim"]
                    old=UsdGeom.Xformable(
                        stage.GetPrimAtPath(p)).ComputeLocalToWorldTransform(tick)
                    # Use original SOURCE tick (not output index) for parity.
                    old=UsdGeom.Xformable(
                        stage.GetPrimAtPath(p)).ComputeLocalToWorldTransform(
                            Usd.TimeCode(float(checkpoint*T//FPS)))
                    new=UsdGeom.Xformable(
                        reopen.GetPrimAtPath(p)).ComputeLocalToWorldTransform(out)
                    if any(abs(float(old[r][col])-float(new[r][col]))>1e-6
                           for r in range(4) for col in range(4)):
                        raise RuntimeError("Derived scene animation differs from source actor")
                for cam in doc["cameras"]:
                    if not reopen.GetPrimAtPath(cameras[
                            cam["camera_id"]]).IsA(UsdGeom.Camera):
                        raise RuntimeError("Director's native virtual camera missing")
        manifest={
            "format":FORMAT,
            "source_camera_bank_id":bank_id,
            "source_camera_bank_revision":revision,
            "source_camera_bank_sha256":bank_record["document_sha256"],
            "original_world_take_sha256":take["document_sha256"],
            "original_world_sha256":doc["source_world_sha256"],
            "original_performance_sha256":doc["source_performance_sha256"],
            "source_usd_file":STAGE,"source_usd_sha256":file_sha(target/STAGE),
            "source_usd_size_bytes":size,"frame_count":FRAMES,
            "fps":FPS,"original_ticks_per_second":T,
            "camera_count":doc["camera_count"],
            "cameras":[{"camera_id":c["camera_id"],
                "source_camera_prim":cameras[c["camera_id"]],
                "source_focal_length_mm":c["focal_length_mm"],
                "camera_ray_exclusions":c["camera_ray_exclusions"]}
                for c in doc["cameras"]],
            "original_frame_evidence":original_frame_evidence,
            "original_source_immutable":True,
            "native_cycles_pixels_rendered":False,
        }
        (target/MANIFEST).write_bytes(canonical(manifest))
        return manifest
    except Exception:
        shutil.rmtree(target)
        raise
