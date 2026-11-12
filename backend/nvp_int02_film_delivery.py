"""INT-02: independently reopen one authentic 30-second Digital Take derivative.

The installed native host must already supply creator authorization and a real
OpenUSD raster worker to Approved2DPackage. This verifier grants neither.
Only 720 exact 24-fps PNG samples + original-derived 48-kHz stereo PCM are
accepted; this is not a conventional single-file or theatrical film master.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import wave

from backend.nvp_film_index import FilmIndex, _require_pid, _id, _sha
from backend.nvp_final_2d_native import (
    Approved2DPackage, FORMAT as DERIVATIVE_FORMAT, _file_sha256, _png_header,
)
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_temporal_ledger import TICKS_PER_SECOND, tick_from_frame

FORMAT = "nvp.int02.verified_30s_derivative.v1"
FRAMES = 720
SAMPLES = 30 * 48000
DURATION_TICKS = 30 * TICKS_PER_SECOND


def verify_original_30s_derivative(index: FilmIndex, project_id: str,
                                   take_id: str, expected_take_sha256: str,
                                   directory: str | Path) -> dict:
    """Independently inspect every derived asset against frozen FilmIndex source."""
    if not isinstance(index, FilmIndex):
        raise TypeError("Actual original FilmIndex required")
    _require_pid(project_id)
    _id(take_id, "source Digital Take")
    _sha(expected_take_sha256)
    package = Path(directory)
    if not package.is_dir() or package.is_symlink():
        raise RuntimeError("Delivery directory missing or linked")
    manifest_path = package / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RuntimeError("Missing original derived-film manifest")
    if manifest_path.stat().st_size > 4 * 1024 * 1024:
        raise RuntimeError("Native delivery manifest exceeds bounded scope")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if type(manifest) is not dict:
        raise RuntimeError("Invalid derived-film manifest")
    required = {
        "format": DERIVATIVE_FORMAT,
        "status": "DERIVED_2D_PACKAGE",
        "original_project_id": project_id,
        "original_take_id": take_id,
        "original_take_sha256": expected_take_sha256,
        "film_duration_tick": str(DURATION_TICKS),
        "fps_num": 24,
        "fps_den": 1,
        "output_picture_count": FRAMES,
        "audio_file": "soundtrack.wav",
        "audio_sample_rate": 48000,
        "audio_samples": SAMPLES,
        "original_data_modified": False,
        "source_frames_authoritative": False,
        "ffmpeg_used": False,
        "conventional_single_file_master": False,
    }
    if any(type(manifest.get(key)) is not type(value) or manifest[key] != value
           for key, value in required.items()):
        raise RuntimeError("Delivery does not match exact original 30-second contract")
    original = index.read_revision(project_id, take_id, 1)
    if (original["kind"] != "take" or
        original["document_sha256"] != expected_take_sha256 or
        original["data"].get("frozen") is not True or
        original["data"].get("format") != "nvp.digital_take.openusd_temporal.v1" or
        original["data"].get("duration_tick") != DURATION_TICKS):
        raise RuntimeError("Source is not the expected immutable 30-second Take")
    verified = OpenUSDTakeCapture(
        index, verify_creator_action=lambda event, scope: False
    ).verify_take(project_id, take_id)
    if verified["take_document_sha256"] != expected_take_sha256:
        raise RuntimeError("Original scene/timeline verification changed")
    pictures = manifest.get("pictures")
    dimensions = manifest.get("picture_dimensions")
    folder = package / "pictures"
    if (type(pictures) is not list or len(pictures) != FRAMES or
        type(dimensions) is not list or len(dimensions) != 2 or
        not folder.is_dir() or folder.is_symlink()):
        raise RuntimeError("Incomplete native picture sequence")
    if len(list(folder.iterdir())) != FRAMES:
        raise RuntimeError("Extra or missing files in original picture sequence")
    for i, item in enumerate(pictures):
        name = f"{i+1:07d}.png"
        if (type(item) is not dict or
            type(item.get("sample_index")) is not int or
            item["sample_index"] != i or item.get("png_file") != name or
            item.get("source_tick") != str(tick_from_frame(i, 24, 1))):
            raise RuntimeError("Derived picture order or exact Film Time is invalid")
        path = folder / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Missing or linked native picture")
        if path.stat().st_size > 24 * 1024 * 1024:
            raise RuntimeError("Native picture exceeds bounded raster size")
        encoded = path.read_bytes()
        if sha256(encoded).hexdigest() != item.get("sha256"):
            raise RuntimeError("Derived picture SHA mismatch")
        if list(_png_header(encoded)) != dimensions:
            raise RuntimeError("Derived picture dimensions changed")
    wav_path = package / "soundtrack.wav"
    if not wav_path.is_file() or wav_path.is_symlink():
        raise RuntimeError("Missing original-derived PCM soundtrack")
    if _file_sha256(wav_path) != manifest.get("audio_sha256"):
        raise RuntimeError("Derived soundtrack SHA mismatch")
    with wave.open(str(wav_path), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(),
            audio.getframerate(), audio.getnframes(),
            audio.getcomptype()) != (2, 2, 48000, SAMPLES, "NONE"):
            raise RuntimeError("Original-derived soundtrack duration or PCM changed")
    # A read-only derivative inspection must also leave the authoritative
    # immutable source at the same exact revision after all disk I/O.
    if index.read_revision(project_id, take_id, 1)["document_sha256"] != expected_take_sha256:
        raise RuntimeError("Original Take identity changed during inspection")
    return {
        "format": FORMAT,
        "status": "VERIFIED_30S_DERIVED_PICTURE_AND_PCM",
        "source_take_sha256": expected_take_sha256,
        "source_duration_tick": str(DURATION_TICKS),
        "picture_count": FRAMES,
        "pcm_samples": SAMPLES,
        "manifest_sha256": sha256(manifest_bytes).hexdigest(),
        "original_modified": False,
        "single_file_master": False,
        "production_renderer_accepted": False,
    }


def deliver_approved_30s_take(exporter: Approved2DPackage, project_id: str,
                              take_id: str, expected_take_sha256: str,
                              presentation_id: str, output_parent: str | Path,
                              *, listener_path: str) -> dict:
    """Connect existing native-approved raster+audio export to independent reopen."""
    if not isinstance(exporter, Approved2DPackage):
        raise TypeError("Trusted native-approved 2D package exporter required")
    produced = exporter.export(
        project_id, take_id, expected_take_sha256, presentation_id,
        output_parent, listener_path=listener_path, fps_num=24, fps_den=1)
    reopened = verify_original_30s_derivative(
        exporter.index, project_id, take_id, expected_take_sha256,
        produced["directory"])
    if reopened["manifest_sha256"] != produced["manifest_sha256"]:
        raise RuntimeError("Native delivery manifest changed after publication")
    return {**reopened, "directory": produced["directory"]}
