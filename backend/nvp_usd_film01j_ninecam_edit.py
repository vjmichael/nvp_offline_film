"""USD-FILM-01J: nine complete source camera rolls -> one 30s film edit.

ONE frozen source performance, nine source-authored cameras, nine 30s rolls,
nine short editorial cuts. This independently verifies frame bytes/timing,
not claims of native Blender provenance or director visual approval. Render
provenance must come from supervised native Cycles workers separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil

from backend.nvp_usd_film01i_ninecam_take import (
    FORMAT as RIG_FORMAT, GRID, T, FPS, FRAMES_PER_CAMERA,
    OriginalNineCameraFilmSet,OriginalFilmPerformanceSampler)

FORMAT="nvp.usd_film01j.nine_source_rolls_conformed_film.v1"
CUT_FRAMES=80
FILM_FRAMES=720

@dataclass(frozen=True)
class FilmCameraRoll:
    angle:str
    framing:str
    frames_dir:Path
    native_frame_receipts:Path


def _sha(path):
    hash=sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda:stream.read(1024*1024),b""):
            hash.update(part)
    return hash.hexdigest()


def validate_coverage_contract(rig, rolls, *, expected_original_actor_states=None):
    """Contract-only validation; no self-issued 'real Blender' attestation.

    Production must first verify the original FilmIndex rig and independently
    inspect actual supervisor run receipts, not arbitrary JSON claims.
    """
    if (type(rig) is not dict or rig.get("format")!=RIG_FORMAT or
        rig.get("camera_count")!=9 or
        rig.get("source_performance_sha256") is None or
        type(rolls) is not list or len(rolls)!=9 or
        tuple((x.angle,x.framing) for x in rolls)!=GRID or
        len(rig.get("cameras",[]))!=9):
        raise ValueError("Nine original source cameras and full roll manifests required")
    if expected_original_actor_states is not None and (
        type(expected_original_actor_states) is not list or
        len(expected_original_actor_states)!=FRAMES_PER_CAMERA):
        raise ValueError("All original authoritative actor-state samples required")
    states=[None]*FRAMES_PER_CAMERA
    out=[]
    size=None
    for camera,roll in zip(rig["cameras"],rolls):
        if (camera["angle"]!=roll.angle or camera["framing"]!=roll.framing or
            camera["native_composed_camera_path"] is None):
            raise ValueError("Roll does not match source camera grid")
        folder=Path(roll.frames_dir)
        manifest=Path(roll.native_frame_receipts)
        if (folder.is_symlink() or not folder.is_dir() or
            manifest.is_symlink() or not manifest.is_file()):
            raise PermissionError("Original source frame paths must be regular local files")
        files=sorted(folder.iterdir())
        if (len(files)!=FRAMES_PER_CAMERA or
            [f.name for f in files]!=[
                f"frame_{i:04d}.png" for i in range(FRAMES_PER_CAMERA)] or
            any(f.is_symlink() or not f.is_file() for f in files)):
            raise RuntimeError("Nine-camera coverage has missing/foreign frame files")
        receipts=json.loads(manifest.read_text("utf8"))
        if type(receipts) is not list or len(receipts)!=FRAMES_PER_CAMERA:
            raise RuntimeError("Every original source frame needs a bounded receipt")
        observed=set()
        for i,(path,receipt) in enumerate(zip(files,receipts)):
            frame_sha=_sha(path)
            tick=i*T//FPS
            if (type(receipt) is not dict or
                receipt.get("actual_native_cycles_image") is not True or
                receipt.get("original_film_tick")!=tick or
                type(receipt.get("original_film_tick")) is not int or
                receipt.get("original_world_sha256")!=rig["original_world_sha256"] or
                receipt.get("original_performance_sha256")!=
                    rig["source_performance_sha256"] or
                receipt.get("original_camera_shot_sha256")!=
                    camera["camera_shot_sha256"] or
                receipt.get("original_camera_path")!=
                    camera["native_composed_camera_path"] or
                receipt.get("rendered_png_sha256")!=frame_sha or
                not isinstance(receipt.get("original_actor_state_sha256"),str) or
                len(receipt["original_actor_state_sha256"])!=64):
                raise PermissionError("Frame/tick/camera/performance/native receipt mismatch")
            actor=receipt["original_actor_state_sha256"]
            if (expected_original_actor_states is not None and
                actor!=expected_original_actor_states[i]):
                raise PermissionError("Original ActorID performance differs from source USD")
            if states[i] is None:
                states[i]=actor
            elif actor!=states[i]:
                raise RuntimeError("Actor positions/rig state differ across cameras at same tick")
            # The contract also requires actually decodable PNG data, rather
            # than only a matching SHA of text pretending to be a render.
            from PIL import Image
            with Image.open(path) as img:
                if img.format!="PNG" or img.width<16 or img.height<9:
                    raise RuntimeError("Not a native-sized PNG film frame")
                dims=img.size
                img.verify()
            if size is None:
                size=dims
            elif dims!=size:
                raise RuntimeError("Nine source rolls must use one picture raster size")
            observed.add(frame_sha)
        if len(observed)!=FRAMES_PER_CAMERA:
            raise RuntimeError("Repeated stills detected in original coverage")
        out.append({"angle":roll.angle,"framing":roll.framing,
                    "source_frames":FRAMES_PER_CAMERA,
                    "camera_shot_sha256":camera["camera_shot_sha256"],
                    "source_frame_0000_sha256":_sha(files[0]),
                    "source_frame_0719_sha256":_sha(files[-1])})
    return {"format":FORMAT,"frame_dimensions_px":list(size),
        "original_world_sha256":rig["original_world_sha256"],
        "source_performance_sha256":rig["source_performance_sha256"],
        "camera_roll_count":9,"frame_count_per_roll":FRAMES_PER_CAMERA,
        "original_coverage_frame_count":9*FRAMES_PER_CAMERA,
        "same_actor_state_at_each_tick_across_all_rolls":True,
        "contract_only_not_blender_supervisor_attestation":True,
        "all_nine_complete_source_rolls":out}


def verify_original_nine_rolls(index,pid,rig_id,rolls):
    """Verify authoritative original source bank before reviewing picture."""
    source=OriginalNineCameraFilmSet(
        index,verify_creator_action=lambda *_:False)
    source.verify(pid,rig_id)
    rig=index.read_revision(pid,rig_id,1)["data"]
    # Never accept nine mutually consistent but invented actor-state claims.
    # Reevaluate the actual original source USD once per frame, independent
    # of all renderer-provided JSON receipts.
    with OriginalFilmPerformanceSampler(index,pid,rig_id) as sampler:
        actual=[sampler.frame(i)["source_actor_state_sha256"]
                for i in range(FRAMES_PER_CAMERA)]
    return validate_coverage_contract(
        rig,rolls,expected_original_actor_states=actual)


def nine_camera_edit_decisions():
    """Nine cuts, one time-continuous actor performance; every camera used."""
    return [
        {"angle":angle,"framing":framing,
         "source_in_frame":i*CUT_FRAMES,
         "source_out_frame":(i+1)*CUT_FRAMES,
         "edit_in_frame":i*CUT_FRAMES,
         "edit_out_frame":(i+1)*CUT_FRAMES}
        for i,(angle,framing) in enumerate(GRID)
    ]


def conform_nine_camera_picture(index,pid,rig_id,rolls,*,out_dir,ffmpeg,ffprobe):
    """Create nine-shot, 30s lossless FFV1 silent edit from real render rolls."""
    from backend.nvp_usd_film01g_three_shot_conform import (
        _run,_probe,_video_frames)
    if not shutil.which(ffmpeg) or not shutil.which(ffprobe):
        raise RuntimeError("Native FFmpeg and FFprobe are required")
    coverage=verify_original_nine_rolls(index,pid,rig_id,rolls)
    root=Path(out_dir)
    if root.exists() or root.is_symlink():
        raise FileExistsError("Original multicam film evidence cannot be overwritten")
    root.mkdir(parents=True)
    clips=[]
    decisions=nine_camera_edit_decisions()
    try:
        for i,(row,roll) in enumerate(zip(decisions,rolls)):
            cut=root/f"cut_{i:02d}"
            cut.mkdir()
            for n,index_in_original in enumerate(range(
                row["source_in_frame"],row["source_out_frame"])):
                src=Path(roll.frames_dir)/f"frame_{index_in_original:04d}.png"
                out=cut/f"frame_{n:04d}.png"
                shutil.copyfile(src,out)
                if _sha(out)!=_sha(src):
                    raise RuntimeError("Selected multicam frame bytes changed on edit")
            clip=root/f"cut_{i:02d}.mkv"
            _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
                "-framerate",str(FPS),"-start_number","0",
                "-i",str(cut/"frame_%04d.png"),"-frames:v",str(CUT_FRAMES),
                "-an","-c:v","ffv1",str(clip)])
            if _video_frames(_probe(clip,ffprobe))!=CUT_FRAMES:
                raise RuntimeError("Original camera cut has incomplete encoded frames")
            clips.append(clip)
        (root/"edit_list.txt").write_text(
            "".join(f"file '{p.name}'\n" for p in clips),"utf8")
        picture=root/"multicam_9_camera_30s_silent_workprint.mkv"
        _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
            "-f","concat","-safe","1","-i",str(root/"edit_list.txt"),
            "-c","copy",str(picture)])
        if _video_frames(_probe(picture,ffprobe))!=FILM_FRAMES:
            raise RuntimeError("Nine-source picture must be exactly 720 decoded frames")
        result={**coverage,
            "edit_decisions":decisions,
            "final_picture_sha256":_sha(picture),
            "final_picture_file":picture.name,
            "final_picture_frames":FILM_FRAMES,
            "final_picture_duration_seconds":30,
            "final_picture_fps":FPS,
            "native_picture_decode_verified":True,
            "original_audio_mixed":False,
            "director_has_visually_approved":False,
            "independent_cycles_supervisor_proof_required":True}
        (root/"edit_evidence.json").write_text(
            json.dumps(result,sort_keys=True,indent=2),"utf8")
        return result
    except Exception:
        shutil.rmtree(root)
        raise
