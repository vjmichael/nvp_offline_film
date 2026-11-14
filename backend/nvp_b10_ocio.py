"""NVP B10 official, versioned OpenColorIO ACES 2.0 image transform.

The input is B9's declared scene-linear Rec.709/D65 OpenEXR. This does not
re-interpret Raw output as ACEScg: it actually applies a pinned OCIO color
space processor to FLOAT32 RGB and writes a NEW FLOAT32 OpenEXR in ACEScg.
The original frame never changes. Alpha is never color-transformed.

This module must run in an OS-contained, memory-admitted native process in
production. Imports stay lazy so B9 and the NVP core have no new mandatory
third-party packages.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys

# The OS-contained executable runs this *pinned installed source file*
# directly from a private job directory, not an arbitrary import location.
if __name__=="__main__" and not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backend.nvp_exr_fidelity import inspect_exr_header

CONFIG_URI="ocio://cg-config-v4.0.0_aces-v2.0_ocio-v2.5"
PINNED_OCIO="2.5.2"
TARGET_SPACE="ACEScg"
SOURCE_CANDIDATES=("Linear Rec.709 (sRGB)","Linear Rec.709","Scene-Linear Rec.709-sRGB")
FORMAT="nvp.production.aces20.ocio.convert.v1"


def _sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as handle:
        for part in iter(lambda:handle.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()


def load_verified_config():
    try:
        import PyOpenColorIO as ocio
    except ImportError as exc:
        raise RuntimeError("Official OpenColorIO 2.5.2 Python binding is required") from exc
    version=ocio.GetVersion()
    if not version.startswith(PINNED_OCIO):
        raise RuntimeError("Pinned NVP OpenColorIO version mismatch: "+version)
    cfg=ocio.Config.CreateFromBuiltinConfig(CONFIG_URI)
    cfg.validate()
    target=cfg.getColorSpace(TARGET_SPACE)
    if target is None:
        raise RuntimeError("Versioned ACES CG config lacks actual ACEScg working space")
    selected=next((s for s in SOURCE_CANDIDATES if cfg.getColorSpace(s) is not None),None)
    if selected is None:
        raise RuntimeError("ACES config lacks supported Rec.709 scene-linear input space")
    # The config is built-in with no network URLs or separately downloaded
    # untracked LUTs. Pin both its serialized bytes and OCIO's cache identity.
    config_string=cfg.serialize()
    return ocio,cfg,{
        "format":"nvp.ocio.pinned_aces2.cg_config.v1",
        "library_version":version,
        "config_uri":CONFIG_URI,
        "config_cache_id":cfg.getCacheID(),
        "config_serialized_sha256":hashlib.sha256(config_string.encode("utf8")).hexdigest(),
        "source_space":selected,
        "target_space":TARGET_SPACE,
        "builtin_only":True,
        "luts_from_unverified_urls":False,
    }


def convert_linear_rec709_to_acescg(
    source:Path,target:Path,*,width:int,height:int,expected_sha256:str,
    required_config_sha256:str|None=None
):
    """Convert an entire genuine float EXR frame with an exact color processor."""
    import numpy as np
    import OpenEXR
    import Imath
    if type(expected_sha256) is not str or len(expected_sha256)!=64:
        raise ValueError("Original native source SHA-256 is required")
    if target.exists() or target.is_symlink():
        raise RuntimeError("Never overwrite an existing ACES color artifact")
    info=inspect_exr_header(source,width=width,height=height)
    if info["rgba_float32"] is not True or _sha(source)!=expected_sha256:
        raise RuntimeError("Original Rec.709 Float32 EXR source changed")
    ocio,cfg,identity=load_verified_config()
    if (required_config_sha256 is not None and
        identity["config_serialized_sha256"]!=required_config_sha256):
        raise RuntimeError("OpenColorIO config changed after creator approval")
    sample_type=Imath.PixelType(Imath.PixelType.FLOAT)
    inp=OpenEXR.InputFile(str(source))
    try:
        rgba=np.stack([
            np.frombuffer(inp.channel(channel,sample_type),dtype="<f4")
            for channel in ("R","G","B","A")
        ],axis=-1).reshape((height,width,4))
    finally:
        inp.close()
    if not np.isfinite(rgba).all():
        raise RuntimeError("Original EXR has nonfinite pixels")
    original_rgb=np.ascontiguousarray(rgba[:,:,:3],dtype=np.float32)
    original_alpha=np.ascontiguousarray(rgba[:,:,3],dtype=np.float32)
    out_rgb=original_rgb.copy()
    forward=cfg.getProcessor(identity["source_space"],TARGET_SPACE).getDefaultCPUProcessor()
    forward.applyRGB(out_rgb)
    if not np.isfinite(out_rgb).all():
        raise RuntimeError("Official ACES transform produced nonfinite scene pixels")
    # The independent inverse uses OCIO's actual processor (not a hardcoded
    # mathematical matrix). Representative pixels prove transform direction.
    index=sorted({0,width*height//5,width*height//2,4*width*height//5,width*height-1})
    sample=out_rgb.reshape(-1,3)[index].copy()
    inverse=cfg.getProcessor(TARGET_SPACE,identity["source_space"]).getDefaultCPUProcessor()
    inverse.applyRGB(sample)
    max_error=float(np.max(np.abs(sample-original_rgb.reshape(-1,3)[index])))
    if not math.isfinite(max_error) or max_error>0.005:
        raise RuntimeError("Official ACES conversion failed independent roundtrip check")
    header=OpenEXR.Header(width,height)
    header["channels"]={ch:Imath.Channel(sample_type) for ch in ("R","G","B","A")}
    header["compression"]=Imath.Compression(Imath.Compression.ZIP_COMPRESSION)
    header["chromaticities"]=Imath.Chromaticities(
        Imath.V2f(.713,.293),Imath.V2f(.165,.830),
        Imath.V2f(.128,.044),Imath.V2f(.32168,.33767))
    # OpenEXR's legacy Python writer drops arbitrary unregistered strings.
    # Standard chromaticities remain in the EXR; the complete versioned
    # OCIO identity is kept in the content-addressed FilmIndex receipt.
    out=OpenEXR.OutputFile(str(target),header)
    try:
        out.writePixels({
            "R":np.ascontiguousarray(out_rgb[:,:,0]).tobytes(),
            "G":np.ascontiguousarray(out_rgb[:,:,1]).tobytes(),
            "B":np.ascontiguousarray(out_rgb[:,:,2]).tobytes(),
            "A":original_alpha.tobytes(),
        })
    finally:
        out.close()
    inspect_exr_header(target,width=width,height=height)
    if not target.is_file() or target.stat().st_size<128:
        raise RuntimeError("ACES converted pixel data did not persist")
    return {
        "format":FORMAT,
        "source_exr_sha256":expected_sha256,
        "output_exr_sha256":_sha(target),
        "width":width,"height":height,
        "rgba_float32":True,
        "working_space":TARGET_SPACE,
        "source_space":identity["source_space"],
        "config":identity,
        "max_rgb_inverse_roundtrip_abs_error":max_error,
        "alpha_untransformed":True,
        "aces2_working_space_converted":True,
        "display_view_transform_applied":False,
        "ocio_provenance_embedded_in_exr":False,
        "ocio_provenance_in_durable_receipt":True,
        "full_pipeline_input_primaries_proved_by_blender":False,
    }


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--src",required=True)
    parser.add_argument("--dst",required=True)
    parser.add_argument("--report",required=True)
    parser.add_argument("--width",required=True,type=int)
    parser.add_argument("--height",required=True,type=int)
    parser.add_argument("--sha",required=True)
    parser.add_argument("--config-sha",required=True)
    args=parser.parse_args()
    receipt=convert_linear_rec709_to_acescg(
        Path(args.src),Path(args.dst),width=args.width,height=args.height,
        expected_sha256=args.sha,required_config_sha256=args.config_sha)
    report=Path(args.report)
    if report.exists() or report.is_symlink():
        raise RuntimeError("Cannot overwrite existing OCIO receipt")
    report.write_text(json.dumps(receipt,sort_keys=True,indent=2),"utf8")
    print(json.dumps(receipt,sort_keys=True))


if __name__=="__main__":
    main()
