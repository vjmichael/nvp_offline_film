"""USD-FILM-01G: conform three source-verified actor shots into one film.

This is a FILM EDITOR, not a new renderer. Blender/Cycles must render each
source-pinned frame beforehand. Never substitute placeholder images, repeat a
still, invent camera motion, or label a source-only proof a finished film.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess

FPS = 24
FRAMES_PER_SHOT = 240
TOTAL_FRAMES = 720
FRAME_NAME = re.compile(r"^frame_[0-9]{4}\\.png$")
SHOT_NAMES = ("establishing", "action", "detail")


@dataclass(frozen=True)
class FilmShot:
    name: str
    take_id: str
    take_sha256: str
    camera_shot_sha256: str
    original_world_sha256: str
    camera_prim: str
    start_tick: int
    end_tick: int
    frames_dir: Path
    # Per-frame native Blender receipts. Each must be a distinct evaluated
    # film-time snapshot, not a repeated source still.
    frame_receipts: Path


def _sha(path: Path) -> str:
    h = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(command: list[str]) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True,
                            timeout=180)
    return result.stdout


def _probe(path: Path, ffprobe: str) -> dict:
    return json.loads(_run([ffprobe, "-v", "error",
        "-count_frames", "-show_streams", "-show_format", "-of", "json",
        str(path)]))


def _video_frames(probe: dict) -> int:
    video = [s for s in probe["streams"] if s["codec_type"] == "video"]
    if len(video) != 1:
        raise RuntimeError("Film must contain exactly one decoded video stream")
    if video[0].get("r_frame_rate") != "24/1":
        raise RuntimeError("Film video is not 24fps")
    return int(video[0]["nb_read_frames"])


def validate_shots(shots: list[FilmShot], *, ticks_per_second: int) -> list[dict]:
    """Fail closed if shots aren't a continuous 30s three-angle source edit."""
    if len(shots) != 3 or tuple(s.name for s in shots) != SHOT_NAMES:
        raise ValueError("The short must contain establishing, action, detail in order")
    if type(ticks_per_second) is not int or ticks_per_second <= 0:
        raise ValueError("Original Film Time clock required")
    world = {s.original_world_sha256 for s in shots}
    cameras = {s.camera_shot_sha256 for s in shots}
    takes = {s.take_sha256 for s in shots}
    prims = {s.camera_prim for s in shots}
    if len(world) != 1 or len(cameras) != 3 or len(takes) != 3 or len(prims) != 3:
        raise ValueError("Three different source Takes/cameras in the same world required")
    verified = []
    for i, shot in enumerate(shots):
        if (not re.fullmatch(r"[a-f0-9]{64}", shot.take_sha256)
            or not re.fullmatch(r"[a-f0-9]{64}", shot.camera_shot_sha256)
            or not re.fullmatch(r"[a-f0-9]{64}", shot.original_world_sha256)
            or not shot.camera_prim.startswith("/World/")
            or not shot.take_id or len(shot.take_id) > 128):
            raise ValueError("Malformed original Take/camera/world source identity")
        expected_start = i * 10 * ticks_per_second
        if (shot.start_tick != expected_start or
            shot.end_tick != expected_start + 10 * ticks_per_second):
            raise ValueError("Three non-overlapping continuous ten-second film intervals required")
        folder = Path(shot.frames_dir)
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Real rendered frame folder required")
        files = sorted(folder.iterdir())
        names = [f"frame_{n:04d}.png" for n in range(FRAMES_PER_SHOT)]
        if len(files) != FRAMES_PER_SHOT or [p.name for p in files] != names:
            raise ValueError("Exactly 240 sequential 24fps original frames per shot required")
        if any(p.is_symlink() or not p.is_file() for p in files):
            raise ValueError("Symlink or missing rendered film frame")
        receipt_file = Path(shot.frame_receipts)
        if not receipt_file.is_file() or receipt_file.is_symlink():
            raise ValueError("Per-frame original Blender provenance is required")
        receipts = json.loads(receipt_file.read_text("utf8"))
        if type(receipts) is not list or len(receipts) != FRAMES_PER_SHOT:
            raise ValueError("Each frame must have one native render receipt")
        frame_shas = []
        evaluated_ticks = []
        for n, (path, proof) in enumerate(zip(files, receipts)):
            frame_sha = _sha(path)
            # Film-time is read from the source-pinned Blender render receipt,
            # not deduced from a convenient sequential output filename.
            tick = shot.start_tick + (n * ticks_per_second) // FPS
            if (type(proof) is not dict or proof.get("actual_native_cycles_image") is not True
                or proof.get("original_world_take_sha256") != shot.take_sha256
                or proof.get("original_camera_shot_sha256") != shot.camera_shot_sha256
                or proof.get("original_world_sha256") != shot.original_world_sha256
                or proof.get("original_camera_path") != shot.camera_prim
                or proof.get("original_film_tick") != tick
                or proof.get("rendered_png_sha256") != frame_sha):
                raise PermissionError("Rendered frame lacks matching native source/tick receipt")
            frame_shas.append(frame_sha)
            evaluated_ticks.append(tick)
        if len(set(evaluated_ticks)) != FRAMES_PER_SHOT:
            raise ValueError("Original film-time quantization repeated a frame")
        if len(set(frame_shas)) != FRAMES_PER_SHOT:
            raise ValueError("Repeated static frame masquerading as moving film")
        verified.append({
            "shot": shot.name, "take_id": shot.take_id,
            "original_take_sha256": shot.take_sha256,
            "original_camera_shot_sha256": shot.camera_shot_sha256,
            "original_camera_prim": shot.camera_prim,
            "start_tick": shot.start_tick, "end_tick": shot.end_tick,
            "first_frame_sha256": frame_shas[0],
            "last_frame_sha256": frame_shas[-1],
            "distinct_native_frames": len(set(frame_shas)),
            "native_source_receipts_verified": True,
        })
    return verified


def conform_short(shots: list[FilmShot], *, ticks_per_second: int,
                  out_dir: Path, ffmpeg: str, ffprobe: str,
                  original_48khz_mix: Path | None = None) -> dict:
    """Stitch three ten-second 24fps shots, optionally with a real PCM mix.

    Audio is optional only for an explicitly labeled SILENT PICTURE WORKPRINT.
    This routine does not invent, retime or synthesize a soundtrack.
    """
    audit = validate_shots(shots, ticks_per_second=ticks_per_second)
    if not shutil.which(ffmpeg) or not shutil.which(ffprobe):
        raise RuntimeError("Real local FFmpeg and FFprobe executables required")
    output = Path(out_dir)
    if output.exists():
        raise FileExistsError("Conform destination must be new")
    output.mkdir(parents=True)
    try:
        clips = []
        for index, shot in enumerate(shots):
            clip = output / f"shot_{index:02d}_{shot.name}.mkv"
            _run([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
                  "-framerate", str(FPS), "-start_number", "0",
                  "-i", str(Path(shot.frames_dir)/"frame_%04d.png"),
                  "-frames:v", str(FRAMES_PER_SHOT), "-an",
                  "-c:v", "ffv1", "-level", "3", str(clip)])
            if _video_frames(_probe(clip, ffprobe)) != FRAMES_PER_SHOT:
                raise RuntimeError("Rendered shot has incomplete encoded frames")
            clips.append(clip)
        # Use an explicit safe concat list of files created inside the new
        # output directory; no external text is evaluated by FFmpeg.
        concat = output/"edit_list.txt"
        concat.write_text("".join(f"file '{p.name}'\\n" for p in clips), "utf8")
        picture = output/"picture_workprint.mkv"
        _run([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
              "-f", "concat", "-safe", "1", "-i", str(concat),
              "-c", "copy", str(picture)])
        if _video_frames(_probe(picture, ffprobe)) != TOTAL_FRAMES:
            raise RuntimeError("Picture edit must decode exactly 720 native frames")
        final = picture
        audio_verified = False
        if original_48khz_mix is not None:
            import wave
            source = Path(original_48khz_mix)
            with wave.open(str(source), "rb") as wav:
                if (wav.getframerate() != 48000 or wav.getnchannels() not in (1, 2)
                    or wav.getsampwidth() != 2 or wav.getnframes() != 30*48000):
                    raise ValueError("Original edit mix must be exact 30s 48k PCM16")
            final = output/"three_shot_short.mkv"
            _run([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
                  "-i", str(picture), "-i", str(source), "-map", "0:v:0",
                  "-map", "1:a:0", "-c:v", "copy", "-c:a", "pcm_s16le",
                  "-shortest", str(final)])
            inspected = _probe(final, ffprobe)
            audio = [s for s in inspected["streams"] if s["codec_type"] == "audio"]
            if (len(audio) != 1 or audio[0].get("sample_rate") != "48000"
                or audio[0].get("codec_name") != "pcm_s16le"
                or _video_frames(inspected) != TOTAL_FRAMES):
                raise RuntimeError("Final decoded native picture/sound streams disagree")
            audio_verified = True
        receipt = {
            "format": "nvp.usd_film01g.three_shot_source_conform.v1",
            "film_length_seconds": 30, "fps": FPS, "shot_count": 3,
            "decoded_original_render_frames": TOTAL_FRAMES,
            "source_world_sha256": shots[0].original_world_sha256,
            "shots": audit,
            "picture_file": final.name, "picture_sha256": _sha(final),
            "actual_ffmpeg_three_shot_stitch_verified": True,
            "original_48khz_pcm_mux_verified": audio_verified,
            "silent_picture_workprint_only": not audio_verified,
            "director_visual_approval": False,
            "cinema_quality_accepted": False,
        }
        (output/"edit_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), "utf8")
        return receipt
    except Exception:
        shutil.rmtree(output)
        raise
