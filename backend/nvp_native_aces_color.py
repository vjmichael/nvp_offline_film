"""DA-06C: real FFmpeg-free OCIO/ACES2 scene-linear SDR picture processing.

This is a *separate native in-memory route*, not the legacy EXR/FFmpeg
processor. It takes explicitly declared scene-linear FLOAT32 RGBA from a
trusted future renderer, applies a SHA-pinned ACES 2.0 display/view
processor and writes genuine 16-bit RGB PNG in-process. No subprocesses,
input image filenames, generic color-space assumptions or frame authority.

The present primitive WebGL/CPU picture renderer is NOT a validated
scene-linear HDR source. It must NOT be silently routed through this
function. A real HDR scene-linear renderer, shot calibration and physical
display acceptance are still required for professional mastering.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import math
import struct
import zlib

from backend.nvp_native_color_decisions import (
    NativeColorDecisions,validate_parameters)
from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha

FORMAT="nvp.native_ocio.aces2_sdr_png16.v1"
CONFIG_URI="ocio://cg-config-v4.0.0_aces-v2.0_ocio-v2.5"
PINNED_VERSION="2.5.2"
SOURCE="Linear Rec.709 (sRGB)"
DISPLAY="sRGB - Display"
VIEW="ACES 2.0 - SDR 100 nits (Rec.709)"
MAX_PIXELS=1920*1080
MAX_CLIP_FRACTION=0.02


def _deps():
    try:
        import PyOpenColorIO as ocio
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Native OCIO 2.5.2 and NumPy must be packaged; no fallback color path"
        ) from exc
    if not ocio.GetVersion().startswith(PINNED_VERSION):
        raise RuntimeError("Native OCIO runtime no longer matches approved version")
    return ocio,np


def policy():
    ocio,_=_deps()
    cfg=ocio.Config.CreateFromBuiltinConfig(CONFIG_URI)
    cfg.validate()
    if (cfg.getColorSpace(SOURCE) is None or
            DISPLAY not in list(cfg.getDisplays()) or
            VIEW not in list(cfg.getViews(DISPLAY))):
        raise RuntimeError("Pinned built-in ACES2 source or SDR view absent")
    xform=ocio.DisplayViewTransform(
        src=SOURCE,display=DISPLAY,view=VIEW,
        looksBypass=False,dataBypass=False)
    proc=cfg.getProcessor(xform)
    info={
        "format":"nvp.native_ocio.pinned_aces2_policy.v1",
        "runtime_version":ocio.GetVersion(),
        "configuration":CONFIG_URI,
        "configuration_sha256":sha256(
            cfg.serialize().encode("utf8")).hexdigest(),
        "processor_cache_id":proc.getCacheID(),
        "source_color_space":SOURCE,
        "source_space_declared_not_verified":True,
        "output_display":DISPLAY,"output_view":VIEW,
        "output_encoding":"RGB16_PNG_SDR",
        "approved_display_calibration":False,
        "scene_linear_renderer_verified":False,
        "uses_ffmpeg":False,
    }
    return info,proc.getDefaultCPUProcessor()


def _chunk(tag,data):
    return (struct.pack(">I",len(data))+tag+data+
            struct.pack(">I",zlib.crc32(tag+data)))


def png16_rgb(channels):
    """Genuine PNG 16-bit truecolor, streamed scanlines, no codec executable."""
    _,np=_deps()
    if (type(channels) is not np.ndarray or channels.dtype.kind!="u" or
            channels.dtype.itemsize!=2 or channels.ndim!=3 or
            channels.shape[-1]!=3):
        raise ValueError("Expected bounded native unsigned 16-bit RGB buffer")
    h,w,_=channels.shape
    if not 1<=h*w<=MAX_PIXELS:
        raise ValueError("Native PNG16 source exceeds bounded raster budget")
    raw=np.ascontiguousarray(channels,dtype=">u2")
    sink=BytesIO()
    sink.write(b"\x89PNG\r\n\x1a\n")
    sink.write(_chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,16,2,0,0,0)))
    compressor=zlib.compressobj(level=6)
    payload=bytearray()
    for row in raw:
        payload.extend(compressor.compress(b"\x00"+row.tobytes()))
        if len(payload)>=1024*1024:
            sink.write(_chunk(b"IDAT",bytes(payload)))
            payload.clear()
    payload.extend(compressor.flush())
    if payload:sink.write(_chunk(b"IDAT",bytes(payload)))
    sink.write(_chunk(b"IEND",b""))
    return sink.getvalue()


def grade_scene_linear(pixels,parameters,np):
    """Non-destructive creative decisions in the *declared linear* working RGB."""
    p=validate_parameters(parameters)
    out=np.array(pixels,dtype=np.float32,order="C",copy=True)
    rgb=out[:,:,:3]
    rgb*=float(2.0**p["exposure_stops"])
    # Working-space contrast about scene middle gray (not gamma-encoded 8-bit).
    rgb[:]=(rgb-0.18)*p["contrast"]+0.18
    luma=rgb[:,:,0]*0.2126+rgb[:,:,1]*0.7152+rgb[:,:,2]*0.0722
    rgb[:]=luma[:,:,None]+(rgb-luma[:,:,None])*p["saturation"]
    warmth=(p["temperature_kelvin"]-6500.)/5500.
    tint=p["tint_magenta_green"]
    rgb[:]*=np.array([1.-0.16*warmth+0.05*tint,
                       1.-0.10*tint,
                       1.+0.16*warmth+0.05*tint],dtype=np.float32)
    if not np.isfinite(out).all():
        raise RuntimeError("Creative color decision produced nonfinite scene light")
    return out


class NativeACESColor:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Real original FilmIndex required for managed color")
        self.index=index

    def process_scene_linear(self,project_id,take_id,take_sha256,
                             grade_id,grade_revision,grade_sha256,
                             scene_linear_rgba,*,expected_config_sha256):
        _require_pid(project_id)
        _id(take_id,"original Digital Take")
        _id(grade_id,"saved immutable color decision")
        _sha(take_sha256);_sha(grade_sha256);_sha(expected_config_sha256)
        take=self.index.read_revision(project_id,take_id,1)
        if (take["kind"]!="take" or
                take["document_sha256"]!=take_sha256 or
                take["data"].get("frozen") is not True):
            raise RuntimeError("Native ACES color input is not a frozen Digital Take")
        grade=NativeColorDecisions(self.index).read(
            project_id,grade_id,grade_revision)
        if (grade["take_id"]!=take_id or
                grade["take_sha256"]!=take_sha256 or
                grade["document_sha256"]!=grade_sha256):
            raise RuntimeError("Requested color revision changed or belongs to another Take")
        ocio,np=_deps()
        if (type(scene_linear_rgba) is not np.ndarray or
                scene_linear_rgba.dtype!=np.float32 or
                scene_linear_rgba.ndim!=3 or
                scene_linear_rgba.shape[-1]!=4 or
                not 1<=scene_linear_rgba.shape[0]*scene_linear_rgba.shape[1]<=
                    MAX_PIXELS or
                not scene_linear_rgba.flags.c_contiguous or
                not np.isfinite(scene_linear_rgba).all() or
                not np.allclose(scene_linear_rgba[:,:,3],1.0,rtol=0,atol=1e-6)):
            raise ValueError("Verified opaque packed FLOAT32 scene-linear RGBA required")
        source_sha=sha256(scene_linear_rgba.tobytes()).hexdigest()
        information,cpu=policy()
        if information["configuration_sha256"]!=expected_config_sha256:
            raise RuntimeError("Native ACES configuration changed after approval")
        processed=grade_scene_linear(
            scene_linear_rgba,grade["parameters"],np)
        cpu.applyRGBA(processed)
        if (not np.isfinite(processed).all() or
                not np.allclose(processed[:,:,3],1.0,rtol=0,atol=2e-6)):
            raise RuntimeError("OCIO produced invalid RGB or changed original alpha")
        rgb=processed[:,:,:3]
        outside=(rgb<0)|(rgb>1)
        count=int(np.count_nonzero(outside))
        fraction=count/rgb.size
        if fraction>MAX_CLIP_FRACTION:
            raise RuntimeError("ACES SDR view exceeds approved clipping budget")
        output=np.rint(np.clip(rgb,0,1)*65535).astype(np.uint16)
        png=png16_rgb(output)
        if sha256(scene_linear_rgba.tobytes()).hexdigest()!=source_sha:
            raise RuntimeError("Original scene-linear input mutated")
        receipt={
            "format":FORMAT,"status":"UNMASTERED_OCIO_SDR_DERIVATIVE",
            "take_id":take_id,"take_sha256":take_sha256,
            "grade_id":grade_id,"grade_revision":grade_revision,
            "grade_sha256":grade_sha256,
            "declared_source_rgb_sha256":source_sha,
            "png16_sha256":sha256(png).hexdigest(),
            "width":int(rgb.shape[1]),"height":int(rgb.shape[0]),
            "bit_depth":16,"channels":3,
            "clipped_channels":count,"clipped_channel_fraction":fraction,
            "processor":information,
            "original_modified":False,"ffmpeg_used":False,
            "cinema_master_approved":False,
        }
        return png,receipt
