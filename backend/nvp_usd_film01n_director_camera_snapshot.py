"""USD-FILM-01N: derived one-tick world/virtual-camera snapshot for Blender.

Uses the director's revisioned, source-locked 01M camera bank and original
01E actor-world Take; never overwrites actor/camera source. A camera mask
is a per-render instruction, NOT global USD visibility.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_openusd_scene import MAX_USD_EXACT_TICK
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank

FORMAT = "nvp.usd_film01n.director_camera_native_frame_snapshot.v1"
STAGE = "source.usda"
MANIFEST = "source.json"
MAX_NATIVE_STAGE = 128 * 1024 * 1024


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _sha(path):
    hasher=sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1<<20),b""):
            hasher.update(block)
    return hasher.hexdigest()


def stage_original_director_camera_frame(index:FilmIndex,pid,bank_id,
                                         *,revision,camera_id,tick,folder):
    from pxr import Sdf,Usd,UsdGeom
    if not isinstance(index, FilmIndex):
        raise TypeError("Source-verified NVP FilmIndex required")
    _id(camera_id, "virtual director camera")
    bank=DirectorCameraBank(index, verify_director_action=lambda *_:False)
    doc=bank.verify(pid,bank_id,revision)
    if not doc["cameras"]:
        raise RuntimeError("Cannot render a film with zero active director cameras")
    cameras=[c for c in doc["cameras"] if c["camera_id"]==camera_id]
    if len(cameras)!=1:
        raise PermissionError("Requested camera absent from exact source bank revision")
    camera=cameras[0]
    if type(tick) is not int or not 0<=tick<doc["source_duration_ticks"] or (
        tick>MAX_USD_EXACT_TICK):
        raise ValueError("Native source film tick outside original Take")
    bank_row=index.read_revision(pid,bank_id,revision)
    take=index.read_revision(pid,doc["world_take_id"],1)
    actor_source=take["data"]["canonical_original_actors"]
    root=Path(folder)
    if root.exists() or root.is_symlink():
        raise FileExistsError("Never overwrite a source camera render stage")
    root.mkdir(mode=0o700,parents=True)
    try:
        with bank.open_source_views(pid,bank_id,revision) as view:
            world=view["original_world"]
            camera_path=view["camera_paths"][camera_id]
            time=Usd.TimeCode(float(tick))
            actor_positions=[]
            for original in actor_source:
                prim=world.stage.GetPrimAtPath(original["composed_actor_prim"])
                if not prim or not prim.IsDefined():
                    raise RuntimeError("Canonical original ActorID disappeared")
                matrix=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(time)
                xyz=matrix.ExtractTranslation()
                actor_positions.append({
                    "actor_id":original["actor_id"],
                    "source_prim":original["composed_actor_prim"],
                    "position_m":[float(xyz[i]) for i in range(3)]})
            cprim=world.stage.GetPrimAtPath(camera_path)
            cmatrix=UsdGeom.Xformable(cprim).ComputeLocalToWorldTransform(time)
            camera_position=[float(cmatrix.ExtractTranslation()[i])
                             for i in range(3)]
            native=world.stage.Flatten(addSourceFileComment=False)
            frozen=Usd.Stage.Open(native)
            if not frozen:
                raise RuntimeError("Flattened source USD could not reopen")
            source_time=Usd.TimeCode(float(tick))
            for prim in frozen.TraverseAll():
                for attribute in prim.GetAttributes():
                    if attribute.GetTypeName()==Sdf.ValueTypeNames.Asset:
                        asset=attribute.Get()
                        if asset is not None and asset.path:
                            raise PermissionError("Unreviewed external texture source")
                    samples=attribute.GetTimeSamples()
                    if not samples:
                        continue
                    value=attribute.Get(source_time)
                    if value is None:
                        raise RuntimeError("Source animation undefined at director frame")
                    for sample in samples:
                        if not attribute.ClearAtTime(Usd.TimeCode(sample)):
                            raise RuntimeError("Cannot freeze source USD time sample")
                    if not attribute.Set(value):
                        raise RuntimeError("Cannot author frozen camera-view source value")
            frozen.SetTimeCodesPerSecond(24.)
            frozen.SetFramesPerSecond(24.)
            frozen.SetStartTimeCode(1.)
            frozen.SetEndTimeCode(1.)
            dest=root/STAGE
            if not frozen.Export(str(dest)):
                raise RuntimeError("Real native USD camera snapshot export failed")
            size=dest.stat().st_size
            if not 100<size<=MAX_NATIVE_STAGE:
                raise ValueError("Bounded original source camera stage exceeded")
            reopened=Usd.Stage.Open(str(dest),load=Usd.Stage.LoadAll)
            if not reopened or not reopened.GetPrimAtPath(
                camera_path).IsA(UsdGeom.Camera):
                raise RuntimeError("Derived stage lost actual native camera")
            for actor in actor_positions:
                prim=reopened.GetPrimAtPath(actor["source_prim"])
                if not prim or not prim.IsDefined():
                    raise RuntimeError("Derived USD lost canonical ActorID geometry")
                sample=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
                    Usd.TimeCode.Default()).ExtractTranslation()
                if any(abs(float(sample[i])-actor["position_m"][i])>1e-6
                       for i in range(3)):
                    raise RuntimeError("Blender source camera freeze changed original actor pose")
            snapshot={
                "format":FORMAT,
                "source_bank_id":bank_id,
                "source_bank_revision":revision,
                "source_bank_sha256":bank_row["document_sha256"],
                "source_world_take_sha256":take["document_sha256"],
                "source_world_sha256":doc["source_world_sha256"],
                "source_performance_sha256":doc["source_performance_sha256"],
                "source_usd_file":STAGE,
                "source_usd_sha256":_sha(dest),
                "source_usd_size_bytes":size,
                "source_camera_id":camera_id,
                "source_camera_prim":camera_path,
                "source_camera_position_m":camera_position,
                "source_camera_focal_length_mm":camera["focal_length_mm"],
                "source_camera_ray_exclusions":camera["camera_ray_exclusions"],
                "source_actor_positions":actor_positions,
                "original_film_tick":tick,
                "original_actor_source_not_replaced":True,
                "source_world_visibility_not_modified":True,
                "native_cycles_frame_rendered":False,
            }
            packet={"format":FORMAT,"source":snapshot,
                    "source_sha256":sha256(_canonical(snapshot)).hexdigest()}
            (root/MANIFEST).write_bytes(_canonical(packet))
            return packet
    except Exception:
        shutil.rmtree(root)
        raise
