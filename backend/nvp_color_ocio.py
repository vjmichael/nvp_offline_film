"""NVP-COLOR-01B: pinned ACES 2 OCIO display-referred 16-bit SDR review frames.

An EXR is scene-referred; an SDR output is display-referred. A view transform
must be baked, not merely a source/destination ColorSpaceTransform.

This code DOES NOT perform cinema XYZ mastering, calibrate a physical display,
approve creative grading, or certify ProRes/DNxHR masters. The one declared
output is an immutable 16-bit SDR PNG sequence with explicit OCIO provenance.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

from backend.nvp_color_exr import exr_info, PIXEL_EXR
from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_presentation_pipeline import PresentationPipeline, _png_info
from backend.nvp_studio import Studio

OCIO_VERSION = "2.5.2"
CONFIG_NAME = "cg-config-v4.0.0_aces-v2.0_ocio-v2.5"
SOURCE_COLOR_SPACE = "Linear Rec.709 (sRGB)"
OUTPUT_PROFILE = "aces2_srgb_sdr100_review_png16"
# This is an output/view recipe, NOT a colorspace conversion or direct 709 gamma tag.
OUTPUT_DISPLAY = "sRGB - Display"
OUTPUT_VIEW = "ACES 2.0 - SDR 100 nits (Rec.709)"
RECEIPT_FORMAT = "nvp.presentation.color.ocio_sdr.v1"
MAX_REVIEW_FRAMES = 120
MAX_DIMENSION = 1920
MAX_RAW_BYTES = MAX_DIMENSION * MAX_DIMENSION * 4 * 4


def _deps():
    try:
        import PyOpenColorIO as ocio
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("NVP-COLOR-01B requires pinned opencolorio==2.5.2 and numpy") from exc
    if ocio.GetVersion() != OCIO_VERSION:
        raise RuntimeError("NVP OCIO runtime version differs from frozen color-management policy")
    return ocio, np


def _config():
    ocio, _ = _deps()
    cfg = ocio.Config.CreateFromBuiltinConfig(CONFIG_NAME)
    spaces = [space.getName() for space in cfg.getColorSpaces()]
    if SOURCE_COLOR_SPACE not in spaces:
        raise RuntimeError("Pinned ACES 2 config lacks expected linear Rec.709 source space")
    if OUTPUT_DISPLAY not in list(cfg.getDisplays()):
        raise RuntimeError("Pinned ACES 2 config lacks expected sRGB output display")
    if OUTPUT_VIEW not in list(cfg.getViews(OUTPUT_DISPLAY)):
        raise RuntimeError("Pinned ACES 2 config lacks expected ACES 2 SDR view")
    return ocio, cfg


def color_policy():
    ocio, cfg = _config()
    xform = ocio.DisplayViewTransform(
        src=SOURCE_COLOR_SPACE, display=OUTPUT_DISPLAY, view=OUTPUT_VIEW,
        looksBypass=False, dataBypass=False)
    processor = cfg.getProcessor(xform)
    cpu = processor.getDefaultCPUProcessor()
    fingerprint = hashlib.sha256(cfg.serialize().encode("utf-8")).hexdigest()
    return {
        "format": "nvp.color.ocio.policy.v1",
        "ocio_version": OCIO_VERSION,
        "config": CONFIG_NAME,
        "config_sha256": fingerprint,
        "source_space": SOURCE_COLOR_SPACE,
        "source_transfer": "scene_linear",
        "display": OUTPUT_DISPLAY,
        "view": OUTPUT_VIEW,
        "output_profile": OUTPUT_PROFILE,
        "output_transfer": "display_referred_srgb",
        "output_precision": "16bit_unsigned_rgb",
        "processor_cache_id": processor.getCacheID(),
        "intent": "sdr_color_managed_review_not_final_graded_master",
    }, cpu


def _ffmpeg_bin(override=None):
    name = override or "ffmpeg"
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Invalid FFmpeg executable")
    binary = shutil.which(name)
    if not binary:
        raise RuntimeError("Independent FFmpeg decoder/encoder unavailable")
    return binary


def _run(args, *, timeout=120, input_bytes=None, label):
    # Retired legacy FFmpeg color decode/export is not an authorized
    # production Windows NVP process tree. Original native picture
    # data is rendered/processed without this fallback.
    import os
    if os.name=="nt":
        raise RuntimeError("Legacy FFmpeg color subprocess is blocked in Windows production")
    try:
        p = subprocess.run(args, input=input_bytes, capture_output=True,
                           timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(label + " did not complete") from exc
    if p.returncode:
        raise RuntimeError(label + " failed: " +
                           p.stderr[-500:].decode("utf-8", "replace"))
    return p.stdout


def decode_scene_linear_exr(exr: Path, ffmpeg: str, expected):
    """Decode RGBA to planar float32 GBRAP, preserving HDR values beyond 1.0.

    Do not ask swscale for GBR24/RGB48 before OCIO; that can clip HDR.
    """
    import numpy as np
    w,h = expected
    raw = _run([
        ffmpeg,"-nostdin","-v","error","-xerror","-i",str(exr),
        "-frames:v","1","-pix_fmt","gbrapf32le","-f","rawvideo","-"
    ], label="Full precision RGBA EXR decode")
    if len(raw) != w*h*4*4 or len(raw) > MAX_RAW_BYTES:
        raise RuntimeError("Decoded EXR RGBA float count differs from approved raster")
    planes = np.frombuffer(raw,dtype="<f4").reshape((4,h,w))
    pixels = np.stack([planes[2],planes[0],planes[1],planes[3]], axis=-1)
    if not np.isfinite(pixels).all():
        raise RuntimeError("Scene-linear EXR contains nonfinite decoded channels")
    return np.ascontiguousarray(pixels, dtype=np.float32)


def apply_view(pixels, cpu, *, clip_threshold=0.02):
    """Apply approved ACES display/view processing and report *all* clipping."""
    _, np = _deps()
    if pixels.dtype != np.float32 or pixels.ndim != 3 or pixels.shape[-1] != 4:
        raise ValueError("Expected float32 RGBA scene-linear buffer")
    if not np.isfinite(pixels).all():
        raise RuntimeError("Untrusted scene-linear pixels contain NaN/Infinity")
    graded = np.array(pixels, dtype=np.float32, copy=True, order="C")
    alpha_before = graded[...,3].copy()
    if not np.allclose(alpha_before, 1.0, atol=1e-6, rtol=0):
        raise RuntimeError("Opaque RGB mastering refuses transparent EXR without approved compositing")
    cpu.applyRGBA(graded)
    if not np.isfinite(graded).all():
        raise RuntimeError("OCIO output has nonfinite pixels")
    if not np.allclose(graded[...,3],alpha_before,atol=2e-6,rtol=0):
        raise RuntimeError("OCIO unexpectedly modified alpha; unsafe mastering transform")
    rgb = graded[...,:3]
    out_of_range = (rgb < 0) | (rgb > 1)
    clipped_fraction = float(np.count_nonzero(out_of_range)/rgb.size)
    if not 0 <= clip_threshold <= 0.02 or clipped_fraction > clip_threshold:
        raise RuntimeError("SDR view would clip too many color channels: " +
                           repr(clipped_fraction))
    # Explicit bounded quantization after a logged view transform, never before.
    quant = np.rint(np.clip(rgb,0.0,1.0)*65535).astype("<u2")
    return quant, {
        "raw_channel_min": float(rgb.min()),
        "raw_channel_max": float(rgb.max()),
        "clip_channel_fraction": clipped_fraction,
        "clip_channel_count": int(np.count_nonzero(out_of_range)),
        "pixels": int(rgb.shape[0]*rgb.shape[1]),
        "rounding": "nearest_even_16bit_with_explicit_clip_accounting",
    }


def _encode_png16(quant, path, ffmpeg):
    _, np = _deps()
    height,width,_=quant.shape
    if height < 1 or width < 1 or max(height,width)>MAX_DIMENSION:
        raise ValueError("PNG color export exceeds bounded raster")
    raw=np.ascontiguousarray(quant,dtype="<u2").tobytes()
    path=Path(path)
    if path.exists():
        raise RuntimeError("SDR PNG output already exists")
    _run([
        ffmpeg,"-nostdin","-v","error","-xerror",
        "-f","rawvideo","-pixel_format","rgb48le",
        "-video_size",f"{width}x{height}","-i","pipe:0",
        "-frames:v","1","-pix_fmt","rgb48be","-f","image2",str(path),
    ], input_bytes=raw, label="16-bit SDR PNG encoder")
    data=path.read_bytes()
    if _png_info(data)!=(width,height) or data[24]!=16 or data[25]!=2:
        raise RuntimeError("SDR PNG is not 16-bit truecolor RGB")
    decoded=_run([
        ffmpeg,"-nostdin","-v","error","-xerror","-i",str(path),
        "-frames:v","1","-pix_fmt","rgb48le","-f","rawvideo","-",
    ], label="Independent 16-bit SDR PNG readback")
    if decoded!=raw:
        raise RuntimeError("16-bit SDR PNG readback differs from quantized OCIO output")
    return {
        "sha256":hashlib.sha256(data).hexdigest(),
        "raw_rgb48le_sha256":hashlib.sha256(raw).hexdigest(),
        "size_bytes":len(data),
        "width":width,"height":height,
        "bit_depth":16,"channels":"RGB",
        "full_decode_exact":True,
    }


class ColorReviewPipeline:
    """Produce immutable 16-bit SDR review frames from indexed Cycles EXR source."""
    def __init__(self, studio: Studio, index: FilmIndex | None = None):
        self.studio=studio
        self.index=index if index is not None else FilmIndex(studio)
        self.frames=PresentationPipeline(studio,self.index)

    def render(self, project_id, source_exr_id, review_id, output_dir, *,
               assumed_source_space=SOURCE_COLOR_SPACE,
               director_source_space_approval=False,
               ffmpeg=None):
        _id(source_exr_id,"scene-linear source ID")
        _id(review_id,"color review ID")
        if assumed_source_space!=SOURCE_COLOR_SPACE or not director_source_space_approval:
            raise RuntimeError("Creator must explicitly confirm Blender linear Rec.709 source primaries")
        try:
            self.index.read_revision(project_id,review_id)
        except KeyError:
            pass
        else:
            raise RuntimeError("Color review identity exists; never overwrite")
        frozen=self.frames.reopen(project_id,source_exr_id)
        data=frozen["record"]["data"]
        if data.get("pixel_contract")!=PIXEL_EXR or data.get("frame_mode") not in ("keyframes","full"):
            raise RuntimeError("COLOR-01B requires verified scene-linear HALF EXR frames")
        ordered=data["rendered_frames"]
        if not 1<=len(ordered)<=MAX_REVIEW_FRAMES:
            raise RuntimeError("COLOR-01B frame review is not a bounded short job")
        if max(data["width"],data["height"])>MAX_DIMENSION:
            raise RuntimeError("COLOR-01B source image exceeds bounded review raster")
        policy,cpu=color_policy()
        binary=_ffmpeg_bin(ffmpeg)
        root=Path(output_dir)
        if root.is_symlink():
            raise RuntimeError("Color review output directory is a symlink")
        root=root.resolve()
        root.mkdir(parents=True,exist_ok=True)
        workspace=root/("ocio_"+hashlib.sha256(
            (project_id+"|"+review_id).encode("utf8")).hexdigest()[:24])
        workspace.mkdir(exist_ok=False)
        output=[]
        for row in ordered:
            source_bytes=self.index.get_blob(project_id,row["image_sha256"])
            info=exr_info(source_bytes)
            if (info["width"],info["height"])!=(data["width"],data["height"]):
                raise RuntimeError("EXR source raster does not match frozen presentation")
            src=workspace/f"source_{row['frame']:06d}.exr"
            src.write_bytes(source_bytes)
            pixels=decode_scene_linear_exr(src,binary,(data["width"],data["height"]))
            graded,statistics=apply_view(pixels,cpu)
            dst=workspace/f"review_{row['frame']:06d}.png"
            measured=_encode_png16(graded,dst,binary)
            sha=self.index.put_blob(project_id,dst.read_bytes(),"image/png")
            if sha!=measured["sha256"]:
                raise RuntimeError("Stored output PNG differs from measured color result")
            output.append({
                "frame":row["frame"],"shot_id":row["shot_id"],
                "source_exr_sha256":row["image_sha256"],
                "png16_sha256":sha,
                "decoded_rgb48le_sha256":measured["raw_rgb48le_sha256"],
                "size_bytes":measured["size_bytes"],
                "width":measured["width"],"height":measured["height"],
                "bit_depth":16,"clip_audit":statistics,
            })
        if self.frames.reopen(project_id,source_exr_id)["record"]["document_sha256"]!=frozen["record"]["document_sha256"]:
            raise RuntimeError("Frozen EXR presentation changed during color export")
        receipt_data={
            "format":RECEIPT_FORMAT,
            "status":"unreviewed_color_managed_sdr_candidate",
            "source_presentation_id":source_exr_id,
            "source_presentation_sha256":frozen["record"]["document_sha256"],
            "source_take_id":data["source_take_id"],
            "source_take_sha256":data["source_take_sha256"],
            "creator_source_primaries_approval":True,
            "color_policy":policy,
            "frame_mode":data["frame_mode"],
            "fps":data["frame_rate"],
            "width":data["width"],"height":data["height"],
            "graded_frames":output,
            "limitations":[
                "SDR 16-bit still review, not a graded picture lock or master MOV",
                "No independently measured display, ICC profile or calibration",
                "Source color primaries explicitly declared by creator, not measured by colorimeter",
                "No approved audio, HDR/PQ or DCP XYZ conversion",
            ],
        }
        record=self.index.register_revision(
            project_id,review_id,"presentation",receipt_data,
            dependencies=[
                {"object_id":source_exr_id,"revision":1,"role":"presentation"},
                {"object_id":data["source_take_id"],"revision":1,"role":"source_take"},
            ],
        )
        self.reopen(project_id,review_id)
        return {"record":record,"graded_frames":output,
                "policy":policy,"workspace":str(workspace),
                "screening_ready":False}

    def reopen(self,project_id,review_id,*,check_decode=False,ffmpeg=None):
        record=self.index.read_revision(project_id,review_id)
        data=record["data"]
        if record["kind"]!="presentation" or data.get("format")!=RECEIPT_FORMAT:
            raise RuntimeError("Not an indexed NVP OCIO SDR review")
        if data.get("status")!="unreviewed_color_managed_sdr_candidate" or data.get("creator_source_primaries_approval") is not True:
            raise RuntimeError("Missing approved COLOR-01B preview policy")
        source=self.frames.reopen(project_id,data["source_presentation_id"])
        if source["record"]["document_sha256"]!=data["source_presentation_sha256"]:
            raise RuntimeError("Color review source EXR revision changed")
        src=source["record"]["data"]
        if src.get("pixel_contract")!=PIXEL_EXR or (src["source_take_id"],src["source_take_sha256"])!=(data["source_take_id"],data["source_take_sha256"]):
            raise RuntimeError("Color review changed its immutable source take or EXR contract")
        edges=sorted([
            {"object_id":data["source_presentation_id"],"revision":1,"role":"presentation"},
            {"object_id":data["source_take_id"],"revision":1,"role":"source_take"},
        ],key=lambda x:(x["object_id"],x["revision"],x["role"]))
        if record["dependencies"]!=edges:
            raise RuntimeError("Color review FilmIndex source dependency mismatch")
        if (data["frame_mode"]!=src["frame_mode"] or
            data["fps"]!=src["frame_rate"] or
            (data["width"],data["height"])!=(src["width"],src["height"])):
            raise RuntimeError("Color review frame timing or raster disagrees with source")
        expected_policy,_=color_policy()
        if data["color_policy"]!=expected_policy:
            raise RuntimeError("Color review OCIO config/processor identity has changed")
        rows=data["graded_frames"]
        sources=src["rendered_frames"]
        if len(rows)!=len(sources) or not rows or len(rows)>MAX_REVIEW_FRAMES:
            raise RuntimeError("Color review frame count differs from frozen EXR frames")
        binary=_ffmpeg_bin(ffmpeg) if check_decode else None
        for source_row,row in zip(sources,rows):
            if ((row["frame"],row["shot_id"],row["source_exr_sha256"])!=
                (source_row["frame"],source_row["shot_id"],source_row["image_sha256"])):
                raise RuntimeError("Color review frame order/source hash mismatch")
            raw=self.index.get_blob(project_id,row["png16_sha256"])
            if (_png_info(raw)!=(data["width"],data["height"]) or
                raw[24]!=16 or raw[25]!=2 or
                len(raw)!=row["size_bytes"] or row["bit_depth"]!=16):
                raise RuntimeError("Stored color-managed PNG has wrong precision or dimensions")
            if check_decode:
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    p=Path(d)/"graded.png"
                    p.write_bytes(raw)
                    decoded=_run([
                        binary,"-nostdin","-v","error","-xerror","-i",str(p),
                        "-frames:v","1","-pix_fmt","rgb48le","-f","rawvideo","-",
                    ],label="Independent stored SDR RGB48 full decode")
                    if hashlib.sha256(decoded).hexdigest()!=row["decoded_rgb48le_sha256"]:
                        raise RuntimeError("Reopened 16-bit SDR pixels changed")
        return {"record":record,"frame_count":len(rows),
                "output_profile":OUTPUT_PROFILE,
                "decoded":bool(check_decode),"screening_ready":False}
