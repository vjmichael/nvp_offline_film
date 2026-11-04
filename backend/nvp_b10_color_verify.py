"""B10 independent OCIO color conversion verification from actual float pixels.

An EXR header or claimed ACEScg tag alone is not evidence. The verifier
rechecks the original frozen Float32 frame, exact source/output SHA, ACES AP1
chromaticities, pinned official ACES2 OCIO config and processor output at
independent spatial samples. The writer process and verification call are
separate; a downstream master may only reference independently verified data.
"""
from __future__ import annotations
import math
from pathlib import Path

from backend.nvp_b10_ocio import (
    CONFIG_URI,TARGET_SPACE,_sha,load_verified_config)
from backend.nvp_exr_fidelity import inspect_exr_header


def verify_acescg_frame(source:Path,target:Path,receipt:dict,
                        *,width:int,height:int):
    import numpy as np
    import OpenEXR
    import Imath
    if receipt.get("format")!="nvp.production.aces20.ocio.convert.v1":
        raise RuntimeError("B10 source has no authenticated OCIO conversion receipt")
    if (receipt.get("width")!=width or receipt.get("height")!=height or
        receipt.get("working_space")!=TARGET_SPACE or
        receipt.get("alpha_untransformed") is not True or
        receipt.get("aces2_working_space_converted") is not True or
        receipt.get("display_view_transform_applied") is not False):
        raise RuntimeError("ACEScg native conversion specification changed")
    for path in (source,target):
        inspect_exr_header(path,width=width,height=height)
    if (_sha(source)!=receipt.get("source_exr_sha256") or
        _sha(target)!=receipt.get("output_exr_sha256")):
        raise RuntimeError("Native ACEScg image bytes changed since conversion")
    ocio,cfg,identity=load_verified_config()
    if receipt.get("config")!=identity or receipt.get("source_space")!=identity["source_space"]:
        raise RuntimeError("OpenColorIO binary/config identity changed since render")
    pt=Imath.PixelType(Imath.PixelType.FLOAT)
    def read(path):
        image=OpenEXR.InputFile(str(path))
        try:
            head=image.header()
            data=[np.frombuffer(image.channel(c,pt),dtype="<f4") for c in ("R","G","B","A")]
            return head,data
        finally:
            image.close()
    header,output=read(target)
    _,original=read(source)
    # Custom EXR string attributes are not portable with this writer.
    # We independently verify the exact OCIO library/config against the
    # immutable conversion receipt; the file carries standard chromaticities.
    if (receipt.get("ocio_provenance_embedded_in_exr") is not False or
        receipt.get("ocio_provenance_in_durable_receipt") is not True):
        raise RuntimeError("ACEScg color provenance receipt is incomplete")
    chroma=header.get("chromaticities")
    if chroma is None:
        raise RuntimeError("Missing ACEScg AP1/D60 primaries header")
    for key,expected in (("red",(.713,.293)),("green",(.165,.830)),
                         ("blue",(.128,.044)),("white",(.32168,.33767))):
        point=getattr(chroma,key)
        if max(abs(point.x-expected[0]),abs(point.y-expected[1]))>.0002:
            raise RuntimeError("EXR ACEScg color primaries were substituted")
    pixels=width*height
    if any(arr.size!=pixels for arr in original+output):
        raise RuntimeError("Truncated decoded EXR float pixel plane")
    numbers=sorted({0,pixels//11,pixels//5,pixels//3,pixels//2,
                    2*pixels//3,4*pixels//5,10*pixels//11,pixels-1})
    src=np.ascontiguousarray(
        np.stack([arr[numbers] for arr in original[:3]],axis=-1),dtype=np.float32)
    dst=np.ascontiguousarray(
        np.stack([arr[numbers] for arr in output[:3]],axis=-1),dtype=np.float32)
    cfg.getProcessor(identity["source_space"],TARGET_SPACE).getDefaultCPUProcessor().applyRGB(src)
    if (not np.isfinite(dst).all() or
        np.max(np.abs(src-dst))>.002 or
        not np.allclose(original[3][numbers],output[3][numbers],atol=1e-6)):
        raise RuntimeError("Actual Float32 color-managed pixel readback differs from OCIO")
    return {"format":"nvp.production.aces20.independent_pixel_proof.v1",
            "verified":True,"source_exr_sha256":_sha(source),
            "acescg_exr_sha256":_sha(target),
            "config_serialized_sha256":identity["config_serialized_sha256"],
            "processor_cache_id":identity["config_cache_id"],
            "color_space":TARGET_SPACE,"sampled_pixels":len(numbers),
            "max_spot_color_error":float(np.max(np.abs(src-dst))),
            "alpha_preserved":True,
            "acescg_chromaticities_verified":True,
            "float32_channel_and_dimensions_verified":True}
