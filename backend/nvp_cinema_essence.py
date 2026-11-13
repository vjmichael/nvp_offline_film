"""NVP-CINEMA-01B: independent unencrypted DCP JPEG 2000/MXF picture check.

This audit does not determine theatrical compatibility, DCI color accuracy,
sound-channel mapping, encryption validity, KDM operation, or projector ingest.
An independent FFprobe scan AND full FFmpeg decode must pass before a technical
DCP may receive a source-linked picture-evidence receipt.

No shell commands, model-generated executable scripts or network processing.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess

from backend.nvp_cinema_duration import validate_duration_contract

MAX_PICTURE_MXFS = 16


def _binary(name, override):
    found = shutil.which(override or name)
    if not found:
        raise RuntimeError("Independent DCP picture audit requires " + name)
    return found


def _run(args, timeout, label):
    try:
        result = run_owned_subprocess(
            args, capture_output=True, text=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(label + " timed out") from exc
    except OSError as exc:
        raise RuntimeError(label + " could not start") from exc
    if result.returncode:
        raise RuntimeError(label + " failed: " + result.stderr[-500:])
    return result.stdout

def _prove_black_tail(media, source_frames, padded_frames, raster, decode, timeout):
    """Decode *every* additional full-resolution frame to raw RGB24.

    A valid proof contains exactly the expected number of bytes and no
    nonzero RGB channels. This is a bounded (at most 23-frame) technical
    exception; full-picture decoding must already have passed.
    """
    if not (1 <= padded_frames < 24 and 1 <= source_frames < 24):
        raise RuntimeError("Refusing unbounded or nonsensical DCP black-tail audit")
    expected_bytes = padded_frames * raster[0] * raster[1] * 3
    if expected_bytes > 150 * 1024 * 1024:
        raise RuntimeError("DCP black-tail audit exceeds bounded memory budget")
    try:
        result = run_owned_subprocess(
            [
                decode, "-nostdin", "-v", "error", "-xerror", "-i", str(media),
                "-map", "0:v:0", "-vf", "select=gte(n\\," + str(source_frames) + ")",
                "-vsync", "0", "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
            ],
            capture_output=True, check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Independent black-tail decode timed out") from exc
    except OSError as exc:
        raise RuntimeError("Independent black-tail decoder could not start") from exc
    if result.returncode:
        raise RuntimeError("Independent black-tail decode failed: " +
                           result.stderr[-500:].decode("utf-8", "replace"))
    if len(result.stdout) != expected_bytes:
        raise RuntimeError("Black-tail decoded frame count or raw byte count mismatch")
    if result.stdout.count(0) != expected_bytes:
        raise RuntimeError("DCP padding is not completely black at full RGB resolution")
    return {
        "format": "nvp.dcp.zero.tail.proof.v1",
        "method": "full_resolution_rgb24_ffmpeg_decode_all_padded_frames",
        "source_frames": source_frames,
        "padded_frames": padded_frames,
        "decoded_black_bytes": expected_bytes,
        "rgb_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "status": "independent_exact_zero_tail",
    }


def audit_dcp_picture_essence(
    dcp_root,
    *,
    expected_raster,
    expected_fps,
    expected_frames,
    ffprobe_bin=None,
    ffmpeg_bin=None,
    duration_contract=None,
    timeout=300,
):
    """Independently inspect and decode each picture MXF on disk.

    Per-MXF decoded-frame counts, not filename extensions or encoder exit
    status, must sum to the exact frozen NVP presentation frame count.
    Accepts one or more reels; never guesses whether there is real sound.
    """
    if (
        type(expected_raster) not in (tuple, list)
        or len(expected_raster) != 2
        or any(type(n) is not int or n <= 0 for n in expected_raster)
        or type(expected_fps) is not int
        or expected_fps <= 0
        or type(expected_frames) is not int
        or expected_frames <= 0
        or type(timeout) is not int
        or not 20 <= timeout <= 7200
    ):
        raise ValueError("Invalid independent picture-audit specification")
    contract = (validate_duration_contract(duration_contract, expected_frames,
                                           expected_fps)
                if duration_contract is not None else None)
    output_frames = contract["dcp_frames"] if contract else expected_frames
    folder = Path(dcp_root)
    if folder.is_symlink() or not folder.is_dir():
        raise RuntimeError("Missing or symlinked DCP folder")
    folder = folder.resolve()
    probe = _binary("ffprobe", ffprobe_bin)
    decode = _binary("ffmpeg", ffmpeg_bin)
    paths = sorted(folder.rglob("*.mxf"))
    if not paths or len(paths) > 32:
        raise RuntimeError("Invalid bounded DCP MXF count")
    pictures = []
    total_frames = 0

    for media in paths:
        if media.is_symlink() or not media.resolve().is_relative_to(folder):
            raise RuntimeError("Unsafe MXF path")
        output = _run(
            [
                probe, "-v", "error", "-count_frames",
                "-show_entries",
                "stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_read_frames",
                "-of", "json", str(media),
            ],
            timeout,
            "Independent MXF probe",
        )
        try:
            details = json.loads(output)
            video = [s for s in details["streams"] if s.get("codec_type") == "video"]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise RuntimeError("Malformed or missing independent MXF probe data") from exc
        if not video:
            continue  # Legitimate sound MXF may have no picture stream.
        if len(video) != 1:
            raise RuntimeError("Ambiguous multiple picture streams in one MXF")
        if len(pictures) >= MAX_PICTURE_MXFS:
            raise RuntimeError("Unbounded DCP picture reels")
        stream = video[0]
        if stream.get("codec_name") != "jpeg2000":
            raise RuntimeError("DCP picture essence is not JPEG 2000")
        if [stream.get("width"), stream.get("height")] != list(expected_raster):
            raise RuntimeError("DCP picture raster does not match approved profile")
        try:
            actual_fps = Fraction(stream["r_frame_rate"])
            count = int(stream["nb_read_frames"])
        except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
            raise RuntimeError("DCP picture frame rate or decoded-frame count missing") from exc
        if actual_fps != expected_fps or count <= 0:
            raise RuntimeError("DCP picture frame rate or decoded-frame count mismatch")
        # Decoder must traverse the *whole* JPEG 2000 picture reel.
        _run(
            [
                decode, "-nostdin", "-v", "error", "-xerror", "-i", str(media),
                "-map", "0:v:0", "-f", "null", "-",
            ],
            timeout,
            "Independent complete JPEG 2000 decode",
        )
        total_frames += count
        if total_frames > output_frames:
            raise RuntimeError("DCP contains unapproved picture frames beyond duration contract")
        pictures.append({
            "path": media.relative_to(folder).as_posix(),
            "codec": "jpeg2000",
            "raster": list(expected_raster),
            "fps": expected_fps,
            "decoded_frames": count,
        })
    if not pictures:
        raise RuntimeError("DCP MXF folder lacks independently decoded picture essence")
    if total_frames != output_frames:
        raise RuntimeError("DCP picture frame count differs from approved duration contract")
    black_tail_evidence = None
    if contract and contract["black_tail_frames"]:
        if len(pictures) != 1:
            raise RuntimeError("Black-tail policy requires one independently decoded picture reel")
        media = folder / pictures[0]["path"]
        black_tail_evidence = _prove_black_tail(
            media, expected_frames, contract["black_tail_frames"],
            list(expected_raster), decode, timeout)
    return {
        "format": "nvp.dcp.picture.essence.audit.v1",
        "status": "independent_mxf_jpeg2000_decode_technical_only",
        "picture_reels": pictures,
        "total_decoded_frames": total_frames,
        "source_frames": expected_frames,
        "duration_contract": contract,
        "black_tail_evidence": black_tail_evidence,
        "raster": list(expected_raster),
        "fps": expected_fps,
        "limits": [
            "No color transform, XYZ 12-bit, projector, DCI/SMPTE or sound certification",
            "Technical unencrypted package only; must also pass separate DCP verifier",
        ],
    }
