"""NVP B14 edited professional picture candidate from true scene-linear sources.

Worker-side only: no creator permission, scheduler admission or OS containment.
A native host MUST authorize and supervise this routine before production use.
Output is a technically audited, unapproved, silent MOV candidate—not a film
master, not calibrated grading, and not a picture-locked presentation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil

from backend.nvp_b12_editorial_delivery import _master_rgb48_from_original_float32
from backend.nvp_b14_picture_conform import _source_rows, verify_conformed_sdr16
from backend.nvp_color_ocio import _ffmpeg_bin
from backend.nvp_color_mastering import PROFILES, MAX_RASTER_PIXELS, _yuv_reference, encode_mov, video_audit
from backend.nvp_film_index import _id

FORMAT = "nvp.presentation.b14.edited_technical_mov_candidate.v1"
MAX_MOV_FRAMES = 480
MAX_STAGED_RGB_BYTES = 1024 * 1024 * 1024


def _sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_manifest(path, document):
    raw = json.dumps(document, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf8")
    with path.open("xb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def build_edited_technical_mov(capture, project_id, conform_id, package: Path,
                               conform_dir: Path, output_dir: Path, candidate_id: str,
                               *, profile="prores_422_hq_mov", ffmpeg=None,
                               ffprobe="ffprobe"):
    """Produce source-linear ACES2→Rec1886/709 edited silent technical MOV.

    One bounded short-film fixture, not yet the streaming production-length
    encoder. The trusted native B14 master host is a separate next gate.
    """
    _id(candidate_id, "edited technical MOV identity")
    if profile not in PROFILES:
        raise ValueError("Unsupported professional video profile")
    try:
        capture.index.read_revision(project_id, candidate_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Edited MOV candidate identity already committed")
    output_dir = Path(output_dir)
    if (output_dir.exists() or output_dir.is_symlink() or
        not output_dir.parent.is_dir() or output_dir.parent.is_symlink()):
        raise RuntimeError("Output must be an absent directory under trusted native parent")
    if not shutil.which(ffprobe) or not shutil.which(ffmpeg or "ffmpeg"):
        raise RuntimeError("An installed native FFmpeg/FFprobe pair is required")
    native = _ffmpeg_bin(ffmpeg)
    conform_record = capture.index.read_revision(project_id, conform_id, 1)
    conform_data = conform_record["data"]
    checked = verify_conformed_sdr16(
        capture, project_id, conform_id, Path(package), Path(conform_dir),
        edit_revision=conform_data["edit_revision"])
    if checked["status"] != "VERIFIED_SDR16_PICTURE_CONFORM":
        raise RuntimeError("B14 edited picture source is not independently verified")
    edit_id, revision = conform_data["edit_id"], conform_data["edit_revision"]
    edit = capture.index.read_revision(project_id, edit_id, revision)
    delivery_id = conform_data["source_delivery_id"]
    original = capture.index.read_revision(project_id, delivery_id, 1)
    width, height = conform_data["resolution"]
    frame_rows = [dict(src) for _, src in _source_rows(edit["data"], original["data"])]
    frames = len(frame_rows)
    if (not 2 <= frames <= MAX_MOV_FRAMES or width % 2 or height % 2 or
        width * height > MAX_RASTER_PIXELS or
        width * height * 6 * frames > MAX_STAGED_RGB_BYTES):
        raise RuntimeError("B14 technical MOV exceeds bounded initial encoder policy")
    output_dir.mkdir(mode=0o700)
    raw = output_dir / "intermediate_graded_rgb48le.raw"
    ref = output_dir / "intermediate_reference_yuv422p10le.raw"
    movie = output_dir / (profile + ".mov")
    try:
        policy, grade = _master_rgb48_from_original_float32(
            capture, project_id, frame_rows, raw, native, width, height)
        if raw.stat().st_size != frames * width * height * 6:
            raise RuntimeError("Scene-linear edited conform generated incorrect frame count")
        _yuv_reference(raw, ref, width=width, height=height, frames=frames, ffmpeg=native)
        encode_mov(raw, movie, profile, width=width, height=height,
                   frames=frames, ffmpeg=native)
        audit = video_audit(movie, profile=profile, width=width, height=height,
                            frames=frames, ffmpeg=native, ffprobe=ffprobe,
                            reference_yuv=ref)
        indexed = capture.index.put_media_file(project_id, movie, "video/quicktime")
        if indexed["sha256"] != _sha_file(movie):
            raise RuntimeError("Native MOV changed between audit and FilmIndex ingest")
        manifest = {
            "format": FORMAT, "status": "unapproved_silent_technical_edited_movie",
            "project_id": project_id, "candidate_id": candidate_id,
            "source_conform_id": conform_id,
            "source_conform_sha256": conform_record["document_sha256"],
            "source_edit_id": edit_id, "source_edit_revision": revision,
            "source_edit_sha256": edit["document_sha256"],
            "source_delivery_id": delivery_id,
            "source_delivery_sha256": original["document_sha256"],
            "source_take_id": conform_data["source_take_id"],
            "source_take_sha256": conform_data["source_take_sha256"],
            "profile": profile, "fps": 24, "resolution": [width, height],
            "frame_count": frames, "movie_path": movie.name,
            "movie_sha256": indexed["sha256"], "movie_bytes": indexed["size_bytes"],
            "original_scene_linear_exr_frames": [
                {"output_frame": i, "source_frame": row["frame"],
                 "source_exr_sha256": row["source_exr_sha256"],
                 "master_rgb48_sha256": row["master_rgb48_sha256"]}
                for i, row in enumerate(frame_rows, 1)],
            "mastering_policy": policy, "grade": grade, "decoded_audit": audit,
            "source_rgb48": "original_float32_EXR_through_ACES2_Rec1886",
            "audio_included": False, "picture_locked": False,
            "approved_final_master": False, "dcp_delivered": False,
        }
        _write_manifest(output_dir / "technical_movie_manifest.json", manifest)
        dependencies = [
            {"object_id": conform_id, "revision": 1, "role": "presentation"},
            {"object_id": edit_id, "revision": revision, "role": "timeline"},
            {"object_id": delivery_id, "revision": 1, "role": "presentation"},
            {"object_id": conform_data["source_take_id"], "revision": 1,
             "role": "source_take"},
        ]
        committed = capture.index.register_revision(
            project_id, candidate_id, "presentation", manifest,
            expected_revision=0, dependencies=dependencies)
        return {"status": "VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE",
                "candidate_id": candidate_id,
                "document_sha256": committed["document_sha256"],
                "frames": frames, "profile": profile,
                "movie_sha256": indexed["sha256"], "audio_included": False}
    finally:
        raw.unlink(missing_ok=True)
        ref.unlink(missing_ok=True)


def verify_edited_technical_mov(capture, project_id, candidate_id, package,
                                conform_dir, output_dir, *, ffmpeg=None,
                                ffprobe="ffprobe"):
    record = capture.index.read_revision(project_id, candidate_id, 1)
    data = record["data"]
    if (record["kind"] != "presentation" or data.get("format") != FORMAT or
        data.get("status") != "unapproved_silent_technical_edited_movie" or
        data.get("audio_included") is not False or
        data.get("picture_locked") is not False or
        data.get("approved_final_master") is not False):
        raise RuntimeError("Edited technical movie incorrectly claims approved master")
    conform_record = capture.index.read_revision(project_id, data["source_conform_id"], 1)
    if conform_record["document_sha256"] != data["source_conform_sha256"]:
        raise RuntimeError("Original edited conform identity changed")
    verified = verify_conformed_sdr16(
        capture, project_id, data["source_conform_id"], package, conform_dir,
        edit_revision=data["source_edit_revision"])
    if verified["frames"] != data["frame_count"]:
        raise RuntimeError("Edited source frame count differs from MOV candidate")
    original = capture.index.read_revision(project_id, data["source_delivery_id"], 1)
    edit = capture.index.read_revision(project_id, data["source_edit_id"],
                                        data["source_edit_revision"])
    if (original["document_sha256"] != data["source_delivery_sha256"] or
        edit["document_sha256"] != data["source_edit_sha256"]):
        raise RuntimeError("Original edited source hashes changed")
    rows = [src for _, src in _source_rows(edit["data"], original["data"])]
    if [(i, row["frame"], row["source_exr_sha256"]) for i, row in enumerate(rows, 1)] != [
        (r["output_frame"], r["source_frame"], r["source_exr_sha256"])
            for r in data["original_scene_linear_exr_frames"]]:
        raise RuntimeError("Original scene-linear frame lineage was altered")
    output_dir = Path(output_dir)
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise RuntimeError("Missing or unsafe technical movie directory")
    manifest = output_dir / "technical_movie_manifest.json"
    if (manifest.is_symlink() or not manifest.is_file() or
        json.loads(manifest.read_text("utf8")) != data):
        raise RuntimeError("Movie manifest no longer matches FilmIndex")
    movie = output_dir / (data["profile"] + ".mov")
    if (movie.is_symlink() or not movie.is_file() or
        _sha_file(movie) != data["movie_sha256"] or
        movie.stat().st_size != data["movie_bytes"]):
        raise RuntimeError("Edited technical movie bytes changed")
    registered = capture.index.verify_media_file(
        project_id, data["movie_sha256"], "video/quicktime")
    if registered["sha256"] != data["movie_sha256"]:
        raise RuntimeError("Edited technical movie missing indexed media")
    audited = video_audit(movie, profile=data["profile"],
                          width=data["resolution"][0],
                          height=data["resolution"][1],
                          frames=data["frame_count"],
                          ffmpeg=_ffmpeg_bin(ffmpeg), ffprobe=ffprobe)
    if (audited["metadata"] != data["decoded_audit"]["metadata"] or
        audited["decoded"]["decoded_yuv10_sha256"] !=
            data["decoded_audit"]["decoded"]["decoded_yuv10_sha256"]):
        raise RuntimeError("Edited MOV no longer decodes to expected validated pixels")
    return {"status": "VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE",
            "frames": data["frame_count"], "movie_sha256": data["movie_sha256"],
            "profile": data["profile"], "audio_included": False,
            "approved_final_master": False}
