"""USD-FILM-01H: three camera rolls covering the SAME source performance.

Synchronized means one original film tick / ActorID state for all views.
GPU renders may execute sequentially; this does not claim parallel execution.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil

FPS=24
COUNT=720
ANGLES=("wide","side","detail")
CUTS=(("wide",0,240),("side",240,480),("detail",480,720))
HASH=re.compile(r"^[a-f0-9]{64}$")

def digest(path):
    h=sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda:file.read(1048576),b""):
            h.update(block)
    return h.hexdigest()

@dataclass(frozen=True)
class CameraRoll:
    angle:str
    camera_prim:str
    camera_shot_sha256:str
    original_world_sha256:str
    original_performance_sha256:str
    frames:Path
    receipts:Path

def verify_multicam(rolls, *, ticks_per_second):
    """All 2160 frame proofs must refer to one shared actor performance."""
    if type(ticks_per_second) is not int or ticks_per_second<=0:
        raise ValueError("Film Time clock required")
    if len(rolls)!=3 or tuple(r.angle for r in rolls)!=ANGLES:
        raise ValueError("Three complete wide/side/detail angles required")
    if (len({r.camera_prim for r in rolls})!=3 or
        len({r.camera_shot_sha256 for r in rolls})!=3 or
        len({r.original_world_sha256 for r in rolls})!=1 or
        len({r.original_performance_sha256 for r in rolls})!=1):
        raise ValueError("Different source cameras must observe one world/performance")
    states=[None]*COUNT
    cameras=[]
    for roll in rolls:
        if (not roll.camera_prim.startswith("/World/") or
            not all(HASH.fullmatch(s) for s in (
               roll.original_world_sha256,roll.original_performance_sha256,
               roll.camera_shot_sha256))):
            raise ValueError("Malformed source identity")
        folder=Path(roll.frames)
        receipt=Path(roll.receipts)
        if (folder.is_symlink() or not folder.is_dir() or
            receipt.is_symlink() or not receipt.is_file()):
            raise ValueError("Real bounded source frames/receipt required")
        files=sorted(folder.iterdir())
        if ([p.name for p in files]!=[f"frame_{i:04d}.png" for i in range(COUNT)]
            or any(p.is_symlink() or not p.is_file() for p in files)):
            raise ValueError("Exactly 720 consecutive frames per angle required")
        proofs=json.loads(receipt.read_text("utf8"))
        if type(proofs) is not list or len(proofs)!=COUNT:
            raise ValueError("Every camera frame needs a native source receipt")
        frame_hashes=set()
        for i,(frame,proof) in enumerate(zip(files,proofs)):
            tick=i*ticks_per_second//FPS
            image_hash=digest(frame)
            if (type(proof) is not dict or
                proof.get("actual_native_cycles_image") is not True or
                proof.get("original_world_sha256")!=roll.original_world_sha256 or
                proof.get("original_performance_sha256")!=roll.original_performance_sha256 or
                proof.get("original_camera_shot_sha256")!=roll.camera_shot_sha256 or
                proof.get("original_camera_path")!=roll.camera_prim or
                type(proof.get("original_film_tick")) is not int or
                proof["original_film_tick"]!=tick or
                proof.get("rendered_png_sha256")!=image_hash or
                type(proof.get("original_actor_state_sha256")) is not str or
                not HASH.fullmatch(proof["original_actor_state_sha256"])):
                raise PermissionError("Camera/world/performance/frame/tick receipt mismatch")
            if states[i] is None:
                states[i]=proof["original_actor_state_sha256"]
            elif states[i]!=proof["original_actor_state_sha256"]:
                raise PermissionError("Different actor state at same film tick across cameras")
            frame_hashes.add(image_hash)
        if len(frame_hashes)!=COUNT:
            raise ValueError("Repeated still frames are not a moving actor film")
        cameras.append({"angle":roll.angle,"camera_prim":roll.camera_prim,
                        "camera_shot_sha256":roll.camera_shot_sha256,
                        "frame_count":COUNT,"unique_frame_hashes":COUNT})
    return {"format":"nvp.usd_film01h.synchronized_multicam_source.v1",
            "world_sha256":rolls[0].original_world_sha256,
            "performance_sha256":rolls[0].original_performance_sha256,
            "camera_count":3,"frames_per_camera":COUNT,
            "total_frame_receipts_checked":COUNT*3,
            "all_camera_actor_states_identical_per_tick":True,
            "views_synchronized_not_parallel_gpu_claim":True,
            "cameras":cameras,"director_visual_approval":False}

def prepare_multicam_edit(rolls, *, ticks_per_second, out_dir):
    """Extract three ten-second cuts from full synchronized camera coverage."""
    evidence=verify_multicam(rolls,ticks_per_second=ticks_per_second)
    target=Path(out_dir)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Never overwrite previous film evidence")
    target.mkdir(parents=True)
    by_angle={r.angle:r for r in rolls}
    segments=[]
    try:
        for angle,start,end in CUTS:
            roll=by_angle[angle]
            folder=target/("cut_"+angle)
            folder.mkdir()
            original=json.loads(Path(roll.receipts).read_text("utf8"))
            receipts=[]
            for local,source_index in enumerate(range(start,end)):
                source=Path(roll.frames)/f"frame_{source_index:04d}.png"
                dest=folder/f"frame_{local:04d}.png"
                shutil.copyfile(source,dest)
                source_receipt=original[source_index]
                if digest(dest)!=source_receipt["rendered_png_sha256"]:
                    raise RuntimeError("Frame changed after verification")
                receipts.append(source_receipt)
            proof=target/("cut_"+angle+"_receipts.json")
            proof.write_text(json.dumps(receipts,sort_keys=True),"utf8")
            segments.append({"angle":angle,"first_source_frame":start,
                "end_source_frame_exclusive":end,"selected_frames":240,
                "frames":str(folder),"receipts":str(proof)})
        manifest={"format":"nvp.usd_film01h.multicam_edit_plan.v1",
                  "full_coverage":evidence,"cuts":segments,
                  "output_frames":720,"playable_film_created":False}
        (target/"multicam_edit_plan.json").write_text(
            json.dumps(manifest,indent=2,sort_keys=True),"utf8")
        return manifest
    except Exception:
        shutil.rmtree(target)
        raise

def conform_multicam(rolls, *, ticks_per_second, out_dir, ffmpeg, ffprobe):
    """Encode an independently probed 720-frame silent picture workprint."""
    from backend.nvp_usd_film01g_three_shot_conform import _run,_probe,_video_frames
    if not shutil.which(ffmpeg) or not shutil.which(ffprobe):
        raise RuntimeError("Real native FFmpeg/FFprobe required")
    root=Path(out_dir)
    if root.exists():
        raise FileExistsError("Film output exists")
    root.mkdir(parents=True)
    try:
        edit=prepare_multicam_edit(rolls,ticks_per_second=ticks_per_second,
                                   out_dir=root/"edit")
        picture_dir=root/"picture"
        picture_dir.mkdir()
        clips=[]
        for index,segment in enumerate(edit["cuts"]):
            clip=picture_dir/f"shot_{index:02d}.mkv"
            _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
                "-framerate","24","-start_number","0",
                "-i",str(Path(segment["frames"])/"frame_%04d.png"),
                "-frames:v","240","-an","-c:v","ffv1",str(clip)])
            if _video_frames(_probe(clip,ffprobe))!=240:
                raise RuntimeError("Camera shot missing encoded film frames")
            clips.append(clip)
        (picture_dir/"cuts.txt").write_text(
            "".join(f"file '{clip.name}'\n" for clip in clips),"utf8")
        film=picture_dir/"three_camera_silent_workprint.mkv"
        _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
            "-f","concat","-safe","1","-i",str(picture_dir/"cuts.txt"),
            "-c","copy",str(film)])
        if _video_frames(_probe(film,ffprobe))!=720:
            raise RuntimeError("Final picture is not exactly 720 decoded frames")
        result={"format":"nvp.usd_film01h.multicam_picture_workprint.v1",
            "coverage":edit["full_coverage"],"cuts":edit["cuts"],
            "decoded_final_frames":720,"film_path":str(film),
            "film_sha256":digest(film),"native_ffprobe_decoding_verified":True,
            "soundtrack_mixed":False,"visual_approval":False}
        (root/"multicam_picture_receipt.json").write_text(
            json.dumps(result,sort_keys=True,indent=2),"utf8")
        return result
    except Exception:
        shutil.rmtree(root)
        raise
