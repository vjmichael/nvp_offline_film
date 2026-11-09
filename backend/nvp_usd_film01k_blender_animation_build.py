"""USD-FILM-01K: source-verified original 30s USD animation for Blender 5.2.

Reuses ONE immutable original 01I world/actor performance and all nine
source-authored native UsdGeom.Camera prims. Bakes NVP's high-resolution
Film Time to 24fps output ticks on a DERIVED USD stage without changing any
FilmIndex Take, scene, camera or world. Does not claim rendered film frames.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import shutil

from backend.nvp_film_index import FilmIndex
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_usd_film01i_ninecam_take import (
    OriginalNineCameraFilmSet,OriginalFilmPerformanceSampler,
    GRID,FPS,FRAMES_PER_CAMERA,T)

FORMAT="nvp.usd_film01k.original_one_performance_nine_camera_24fps_usd.v1"
STAGE="original_9cam_720frame_animation.usda"
PROOF="original_animation_source_audit.json"
MAX_USD_BYTES=128*1024*1024
MAX_TIMED_ATTRIBUTES=512


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _digest(path):
    hasher=sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda:file.read(1<<20),b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def author_original_blender_animation(index:FilmIndex,pid,rig_id,*,folder):
    from pxr import Sdf,Usd,UsdGeom
    if not isinstance(index,FilmIndex):
        raise TypeError("Original FilmIndex authority required")
    registry=OriginalNineCameraFilmSet(
        index,verify_creator_action=lambda *_:False)
    registry.verify(pid,rig_id)
    rig=index.read_revision(pid,rig_id,1)
    take=index.read_revision(pid,rig["data"]["world_take_id"],1)["data"]
    destination=Path(folder)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Do not overwrite original or prior derived USD")
    destination.mkdir(parents=True,mode=0o700)
    try:
        with OpenUSDWorldComposer(index).open(
            pid,take["world_id"],take["world_revision"]) as original:
            required=[take["original_scene_takes"][0]["set"]]
            original.load(required)
            original_world_sha=original.record["document_sha256"]
            if original_world_sha!=rig["data"]["original_world_sha256"]:
                raise RuntimeError("Original film world changed before Blender export")
            # Only a disposable in-memory flattened USD working set may be
            # converted into the renderer-friendly 24fps stage. FilmIndex
            # original layers and exact timestamp semantics remain unchanged.
            flattened=original.stage.Flatten(addSourceFileComment=False)
            output=Usd.Stage.Open(flattened)
            if not output:
                raise RuntimeError("Cannot reopen native source USD for animation bake")
            attr_count=0
            for prim in output.TraverseAll():
                for attribute in prim.GetAttributes():
                    if attribute.GetTypeName()==Sdf.ValueTypeNames.Asset:
                        asset=attribute.Get()
                        if asset is not None and asset.path:
                            raise PermissionError(
                                "Unbundled original external textures need reviewed MaterialX integration")
                    source_ticks=attribute.GetTimeSamples()
                    if not source_ticks:
                        continue
                    attr_count+=1
                    if attr_count>MAX_TIMED_ATTRIBUTES:
                        raise RuntimeError("Unbounded original animated source property count")
                    # Capture every evaluated original frame BEFORE clearing
                    # original enormous film tick time samples.
                    values=[]
                    for i in range(FRAMES_PER_CAMERA):
                        original_tick=i*T//FPS
                        value=attribute.Get(Usd.TimeCode(float(original_tick)))
                        if value is None:
                            raise RuntimeError("Missing actual original USD animation sample")
                        values.append(value)
                    for source_tick in source_ticks:
                        if not attribute.ClearAtTime(Usd.TimeCode(float(source_tick))):
                            raise RuntimeError("Cannot remove source ticks in disposable stage")
                    for i,value in enumerate(values):
                        if not attribute.Set(value,Usd.TimeCode(float(i+1))):
                            raise RuntimeError("Cannot author derived 24fps USD sample")
            output.SetTimeCodesPerSecond(float(FPS))
            output.SetFramesPerSecond(float(FPS))
            output.SetStartTimeCode(1.)
            output.SetEndTimeCode(float(FRAMES_PER_CAMERA))
            path=destination/STAGE
            if not output.Export(str(path)):
                raise RuntimeError("Native 24fps USD film stage export failed")
            size=path.stat().st_size
            if not 100<size<=MAX_USD_BYTES:
                raise RuntimeError("Original 9-camera stage export exceeds bounded source size")
            reopened=Usd.Stage.Open(str(path),load=Usd.Stage.LoadAll)
            if reopened is None:
                raise RuntimeError("Native Blender animation stage cannot reopen")
            if (reopened.GetTimeCodesPerSecond()!=24.0 or
                reopened.GetStartTimeCode()!=1.0 or
                reopened.GetEndTimeCode()!=float(FRAMES_PER_CAMERA)):
                raise RuntimeError("Blender animation clock differs from source 24fps")
            for camera in rig["data"]["cameras"]:
                prim=reopened.GetPrimAtPath(camera["native_composed_camera_path"])
                if not prim or not prim.IsA(UsdGeom.Camera):
                    raise RuntimeError("Nine original native film cameras did not survive bake")
            for actor in take["canonical_original_actors"]:
                if not reopened.GetPrimAtPath(
                    actor["composed_actor_prim"]).IsDefined():
                    raise RuntimeError("Original ActorID vanished from animation stage")
            checked=[]
            for frame in (0,1,239,240,479,480,719):
                original_time=Usd.TimeCode(float(frame*T//FPS))
                output_time=Usd.TimeCode(float(frame+1))
                poses=[]
                for actor in take["canonical_original_actors"]:
                    path=actor["composed_actor_prim"]
                    src=original.stage.GetPrimAtPath(path)
                    dst=reopened.GetPrimAtPath(path)
                    a=UsdGeom.Xformable(src).ComputeLocalToWorldTransform(
                        original_time)
                    b=UsdGeom.Xformable(dst).ComputeLocalToWorldTransform(
                        output_time)
                    for x in range(4):
                        for y in range(4):
                            if abs(float(a[x][y])-float(b[x][y]))>1e-6:
                                raise RuntimeError(
                                    "Derived Blender frame moved original performing actor")
                    poses.append(actor["actor_id"])
                checked.append({
                    "frame":frame,"original_tick":frame*T//FPS,
                    "derived_usd_timecode":frame+1,
                    "original_actor_ids_verified":poses})
        # Independent complete timeline source-state manifests. This samples
        # ONE original performance per frame, not nine separate scene takes.
        timeline=[]
        with OriginalFilmPerformanceSampler(index,pid,rig_id) as sampler:
            for frame in range(FRAMES_PER_CAMERA):
                state=sampler.frame(frame)
                timeline.append({
                    "frame":frame,
                    "original_film_tick":state["original_film_tick"],
                    "actor_state_sha256":state["source_actor_state_sha256"],
                    "source_actor_world_positions_m":state[
                        "source_actor_world_positions_m"]})
        if len({x["actor_state_sha256"] for x in timeline})<2:
            raise RuntimeError("The original actor performance did not animate")
        proof={
            "format":FORMAT,
            "source_rig_id":rig_id,
            "source_rig_sha256":rig["document_sha256"],
            "source_world_sha256":rig["data"]["original_world_sha256"],
            "source_performance_sha256":rig["data"]["source_performance_sha256"],
            "original_source_take_sha256":rig["data"]["source_scene_take_sha256"],
            "derived_usd_file":STAGE,
            "derived_usd_sha256":_digest(destination/STAGE),
            "derived_usd_bytes":size,
            "original_native_animated_attributes_resampled":attr_count,
            "native_actor_reopen_checkpoints":checked,
            "original_actor_state_per_frame":timeline,
            "camera_grid":[[x["angle"],x["framing"]] for x in rig["data"]["cameras"]],
            "source_camera_count":9,
            "original_frame_count_per_camera":FRAMES_PER_CAMERA,
            "film_fps":FPS,
            "original_film_time_ticks_per_second":T,
            "original_film_source_unchanged":(
                index.read_revision(pid,take["world_id"],
                                    take["world_revision"])["document_sha256"]==
                rig["data"]["original_world_sha256"]),
            "renderer_frames_created":False,
            "original_sound_mixed":False,
            "human_camera_quality_reviewed":False,
        }
        (destination/PROOF).write_bytes(_canonical(proof))
        return proof
    except Exception:
        shutil.rmtree(destination)
        raise
