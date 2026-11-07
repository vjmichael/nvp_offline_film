"""Batch 3: strict read-only native cinema/HDR delivery preflight, no FFmpeg.

A true SMPTE/DCP is NOT an EXR folder, an AVI, or a PNG sequence.
NVP refuses to claim delivery readiness absent native validated
2K/4K XYZ JPEG2000 MXF picture, audio MXF, CPL/PKL/ASSETMAP, and
independent bitstream QC. Prior legacy DCP-o-matic/FFmpeg execution is
not imported here and is NOT permitted into the data-first app.

This reviewer verifies every original-derived image and PCM SHA and
reports exact unmet mastering gates. It cannot fabricate calibration,
projector ingest, spectrally measured lights, or cinema encoder binaries.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
import wave

from backend.nvp_final_2d_native import (
    FORMAT as PNG_FORMAT,FORMAT_EXR)
from backend.nvp_temporal_ledger import tick_from_frame

FORMAT="nvp.native_data_first.cinema_preflight.v1"
TARGETS={
    "SMPTE_2K_FLAT_24":{"picture_raster":[1998,1080],"fps":[24,1],
                        "image_codestream":"JPEG2000_XYZ_12BIT",
                        "audio_codestream":"PCM_24BIT_48000_MXF"},
    "SMPTE_2K_SCOPE_24":{"picture_raster":[2048,858],"fps":[24,1],
                         "image_codestream":"JPEG2000_XYZ_12BIT",
                         "audio_codestream":"PCM_24BIT_48000_MXF"},
    "HDR10_REC2100_PQ":{"picture_raster":[3840,2160],"fps":[24,1],
                        "image_codestream":"PQ_YCBCR_10BIT_REC2020",
                        "audio_codestream":"PCM_24BIT"},
}
MAX_ASSETS=7200
MAX_MANIFEST=16*1024*1024
REQUIRED_NO_FFMPEG_DCP=(
    "native_SMPTE_2K_XYZ_12bit_JPEG2000_encoder",
    "native_SMPTE_MXF_picture_and_PCM_sound_multiplexer",
    "independently_verified_CPL_PKL_ASSETMAP_and_essence",
    "independent_strict_SMPTE_DcpDoctor_QC",
    "measured_P3_XYZ_camera_display_color_acceptance",
    "theater_server_and_projector_ingest_acceptance",
)


def _digest(path):
    h=sha256()
    with path.open("rb") as handle:
        while block:=handle.read(1024*1024):
            h.update(block)
    return h.hexdigest()


def assess_unmastered_source_package(package,*,target="SMPTE_2K_FLAT_24",
                                     expected_take_sha256=None):
    if target not in TARGETS:
        raise ValueError("Unsupported native cinema/HDR delivery profile")
    folder=Path(package)
    if folder.is_symlink() or not folder.is_dir():
        raise PermissionError("Only an existing trusted native package directory")
    folder=folder.resolve(strict=True)
    manifest=folder/"manifest.json"
    if (manifest.is_symlink() or not manifest.is_file() or
        manifest.stat().st_size>MAX_MANIFEST):
        raise RuntimeError("No bounded original source package manifest")
    doc=json.loads(manifest.read_text("utf8"))
    if (doc.get("format") not in (PNG_FORMAT,FORMAT_EXR) or
        doc.get("original_data_modified") is not False or
        doc.get("source_frames_authoritative") is not False or
        doc.get("ffmpeg_used") is not False or
        doc.get("conventional_single_file_master") is not False or
        not re.fullmatch("[0-9a-f]{64}",doc.get("original_take_sha256",""))):
        raise RuntimeError("Not an authentic unmastered native data-first source derivative")
    if (expected_take_sha256 is not None and
        doc["original_take_sha256"]!=expected_take_sha256):
        raise RuntimeError("Cinema preflight source Take SHA differs")
    pictures=doc.get("pictures")
    if (type(pictures) is not list or
        not 1<=len(pictures)<=MAX_ASSETS or
        len(pictures)!=doc.get("output_picture_count")):
        raise RuntimeError("Source picture manifest is incomplete")
    source_format=("exr" if doc["format"]==FORMAT_EXR else "png")
    if doc.get("picture_format",source_format)!=source_format:
        raise RuntimeError("Source picture manifest format differs from originals")
    fps=[doc.get("fps_num"),doc.get("fps_den")]
    if (any(type(v) is not int or v<1 for v in fps) or
        fps[0]>120000 or fps[1]>1001):
        raise RuntimeError("Invalid exact original picture cadence")
    size=doc.get("picture_dimensions")
    if (type(size) not in (tuple,list) or len(size)!=2 or
        any(type(x) is not int or not 1<=x<=4096 for x in size)):
        raise RuntimeError("Source raster dimensions are not verified")
    folder_pictures=folder/"pictures"
    if folder_pictures.is_symlink() or not folder_pictures.is_dir():
        raise RuntimeError("Source picture directory is unsafe")
    for i,row in enumerate(pictures):
        name=f"{i+1:07d}.{source_format}"
        if (type(row) is not dict or
            row.get(source_format+"_file")!=name or
            row.get("sample_index")!=i or
            row.get("source_tick")!=str(
                tick_from_frame(i,fps[0],fps[1])) or
            not re.fullmatch("[0-9a-f]{64}",row.get("sha256","")) or
            row.get("camera_path") not in (None,*[
                value["camera_path"] for value in pictures
                if isinstance(value,dict) and
                    type(value.get("camera_path")) is str])):
            raise RuntimeError("Original data-first picture source identity invalid")
        original=folder_pictures/name
        if (original.is_symlink() or not original.is_file() or
            _digest(original)!=row["sha256"]):
            raise RuntimeError("Original derived picture changed before cinema inspection")
    if sorted(x.name for x in folder_pictures.iterdir())!=[
            row[source_format+"_file"] for row in pictures]:
        raise RuntimeError("Source output directory includes unapproved images")
    wav=folder/"soundtrack.wav"
    if (wav.is_symlink() or not wav.is_file() or
        _digest(wav)!=doc.get("audio_sha256")):
        raise RuntimeError("Native source PCM WAV checksum changed")
    with wave.open(str(wav),"rb") as audio:
        if (audio.getcomptype()!="NONE" or
            audio.getnchannels()!=2 or
            audio.getframerate()!=48000 or
            audio.getsampwidth()!=2 or
            audio.getnframes()!=doc.get("audio_samples")):
            raise RuntimeError("Original-derived native audio cadence/PCM invalid")
    blockers=[]
    spec=TARGETS[target]
    if fps!=spec["fps"]:
        blockers.append("native picture cadence must match "+str(spec["fps"]))
    if size!=spec["picture_raster"]:
        blockers.append("source raster "+str(size)+
                        " is below required cinema/HDR delivery "+str(spec["picture_raster"]))
    if target.startswith("SMPTE"):
        blockers+=list(REQUIRED_NO_FFMPEG_DCP)
    else:
        blockers+=list((
            "verified_Rec2100_PQ_10bit_encoder",
            "valid_mastering_display_CLL_FALL_metadata",
            "reference_colorimeter_HDR_PQ_and_Rec2020_measurements",
            "independent_HDR_master_QC_and_decoder_acceptance",
        ))
    blockers.append("source_48k_stereo_PCM16_is_not_24bit_master_sound")
    return {
        "format":FORMAT,
        "status":"NO_CINEMA_OR_HDR_MASTER_AUTHORIZED",
        "target":target,
        "source_take_sha256":doc["original_take_sha256"],
        "source_package_manifest_sha256":_digest(manifest),
        "source_image_format":source_format,
        "original_derived_image_count":len(pictures),
        "source_frame_rate":fps,
        "source_picture_raster":size,
        "source_pcm_sha256":doc["audio_sha256"],
        "source_integrity_verified":True,
        "unmastered_color_intermediate_verified":True,
        "required_master_color_and_delivery_capabilities":blockers,
        "dcp_delivered":False,
        "hdr10_master_approved":False,
        "projector_ingest_certified":False,
        "source_original_modified":False,
        "ffmpeg_used":False,
    }
