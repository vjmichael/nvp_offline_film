"""WO4-02 approved source-linear sRGB-D65 to SMPTE ST 428-1 XYZ12.

Input: interleaved IEEE754 little-endian float32 *linear* sRGB D65 channels,
already graded and output-referred by the creator. No automatic tonemapping,
no OETF applied to linear RGB, no implicit chromatic adaptation. The D65
white intent is explicit, not mislabelled as the calibrated DCI reference
x=.314/y=.351 white. WO4-03 external calibration remains open.
"""
from __future__ import annotations
import hashlib
import math
import struct
from backend.nvp_wo3_j2k_audit import PROFILES

FORMAT = "nvp.wo4.xyz12_master_candidate.v1"
ST428_PEAK_NITS = 52.37
REFERENCE_WHITE_NITS = 48.0
GAMMA = 2.6
# IEC 61966-2-1 D65 linear RGB -> CIE 1931 XYZ, Y normalized to 1.
RGB_D65_TO_XYZ = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)


def encode_linear_rgb_d65_to_xyz12(source_float32:bytes,*,profile:str,
        source_sha256:str,original_take_sha256:str,creator_approved:bool,
        output_white_intent:str="D65_UNADAPTED",
        mastering_reference_nits:float=48.0):
    if creator_approved is not True:
        raise PermissionError("Native approved picture-mastering decision required")
    if (profile not in PROFILES or output_white_intent!="D65_UNADAPTED"
            or type(mastering_reference_nits) not in (int,float)
            or mastering_reference_nits!=REFERENCE_WHITE_NITS):
        raise ValueError("Explicit supported cinema color and luminance intent required")
    for digest in (source_sha256,original_take_sha256):
        if type(digest) is not str or len(digest)!=64 or any(
                c not in "0123456789abcdef" for c in digest):
            raise PermissionError("Exact immutable source SHA required")
    width,height,_=PROFILES[profile]
    if (type(source_float32) is not bytes
            or len(source_float32)!=width*height*12
            or hashlib.sha256(source_float32).hexdigest()!=source_sha256):
        raise PermissionError("Exact approved float32 image size/source SHA required")
    output=bytearray(width*height*6)
    minimum=4095
    maximum=0
    offset=0
    for rgb in struct.iter_unpack("<fff",source_float32):
        if any(not math.isfinite(c) or c<0.0 or c>1.0 for c in rgb):
            raise ValueError("Nonfinite or out-of-range linear RGB; manual grading required")
        xyz=[sum(matrix[i]*rgb[i] for i in range(3))
             for matrix in RGB_D65_TO_XYZ]
        for component in xyz:
            if component<0 or not math.isfinite(component):
                raise ValueError("Source transform generated invalid XYZ")
            value=4095.0*((REFERENCE_WHITE_NITS*component/
                             ST428_PEAK_NITS)**(1.0/GAMMA))
            if value>4095.0+1e-7:
                raise ValueError("XYZ output exceeds legal 12-bit cinema range")
            quantized=min(4095,int(value+0.5))
            output[offset:offset+2]=quantized.to_bytes(2,"big")
            offset+=2
            minimum=min(minimum,quantized)
            maximum=max(maximum,quantized)
    return {
        "format":FORMAT,"status":"XYZ12_SOURCE_BOUND_CANDIDATE",
        "xyz12":bytes(output),
        "xyz12_sha256":hashlib.sha256(output).hexdigest(),
        "source_linear_float32_sha256":source_sha256,
        "original_take_sha256":original_take_sha256,
        "profile":profile,"width":width,"height":height,
        "source_color_space":"linear_sRGB_D65",
        "output_color_space":"SMPTE_ST_428_1_XYZ12",
        "chromatic_adaptation":"NONE",
        "output_white_intent":output_white_intent,
        "reference_white_nits":REFERENCE_WHITE_NITS,
        "transfer_gamma":GAMMA,"peak_normalization_nits":ST428_PEAK_NITS,
        "minimum_code":minimum,"maximum_code":maximum,
        "source_modified":False,"independently_calibrated":False,
        "production_picture_accepted":False,"ffmpeg_used":False,
    }
