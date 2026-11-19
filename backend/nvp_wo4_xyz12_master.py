"""WO4-02 approved source-linear sRGB-D65 to SMPTE ST 428-1 XYZ12.

Input: interleaved IEEE754 little-endian float32 *linear* sRGB D65 channels,
already graded and output-referred by the creator. No automatic tonemapping,
no OETF applied to linear RGB, no implicit chromatic adaptation. The D65
white intent is explicit, not mislabelled as the calibrated DCI reference
x=.314/y=.351 white. WO4-03 external calibration remains open.
"""
from __future__ import annotations
import hashlib
import numpy as np
from backend.nvp_wo3_j2k_audit import PROFILES
from backend.nvp_dci_color_reference import REVISION, verify_xyz12_reference

FORMAT = "nvp.wo4.xyz12_master_candidate.v1"
ST428_PEAK_NITS = 52.37
REFERENCE_WHITE_NITS = 48.0
CINEMA_WHITE_XY = (0.314,0.351)
SOURCE_D65_XY = (0.3127,0.3290)
BRADFORD=((0.8951,0.2664,-0.1614),(-0.7502,1.7135,0.0367),
          (0.0389,-0.0685,1.0296))
BRADFORD_INV=((0.9869929054667123,-0.1470542564209901,0.15996265166373122),
              (0.43230526972339445,0.5183602715367774,0.04929122821285559),
              (-0.00852866457517733,0.04004282165408486,0.96848669578755))

GAMMA = 2.6
# Derived from sRGB primary xy and the declared D65 (0.3127, 0.3290).
# Full precision, rather than the older rounded/alternate-D65 matrix.
RGB_D65_TO_XYZ = (
    (0.41239079926595945, 0.35758433938387796, 0.18048078840183426),
    (0.21263900587151033, 0.7151686787677559, 0.0721923153607337),
    (0.01933081871559185, 0.11919477979462599, 0.9505321522496605),
)


def _matvec(matrix,vector):
    return [sum(row[i]*vector[i] for i in range(3)) for row in matrix]


def _white_xyz(xy):
    x,y=xy
    return (x/y,1.0,(1.0-x-y)/y)


def _bradford_d65_to_dci(xyz):
    source=_matvec(BRADFORD,_white_xyz(SOURCE_D65_XY))
    target=_matvec(BRADFORD,_white_xyz(CINEMA_WHITE_XY))
    cones=_matvec(BRADFORD,xyz)
    return _matvec(BRADFORD_INV,
                   [cones[i]*(target[i]/source[i]) for i in range(3)])


def encode_linear_rgb_d65_to_xyz12(source_float32:bytes,*,profile:str,
        source_sha256:str,original_take_sha256:str,creator_approved:bool,
        output_white_intent:str="D65_UNADAPTED",
        mastering_reference_nits:float=48.0):
    if creator_approved is not True:
        raise PermissionError("Native approved picture-mastering decision required")
    if (profile not in PROFILES or output_white_intent not in (
            "D65_UNADAPTED","DCI_REFERENCE_BRADFORD")
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
    # Preserve the existing authoritative input and output byte contract, but
    # compute in bounded blocks; no full-frame float64 or per-pixel Python loop.
    pixels=width*height
    output=bytearray(pixels*6)
    rgb=np.frombuffer(source_float32,dtype='<f4').reshape(-1,3)
    codes=np.frombuffer(output,dtype='>u2').reshape(-1,3)
    matrix=RGB_D65_TO_XYZ
    if output_white_intent=="DCI_REFERENCE_BRADFORD":
        columns=[_bradford_d65_to_dci([row[i] for row in matrix])
                 for i in range(3)]
        matrix=tuple(zip(*columns))
    minimum=4095
    maximum=0
    for offset in range(0,pixels,16384):
        block=rgb[offset:offset+16384].astype(np.float64)
        if not np.isfinite(block).all() or (block<0.).any() or (block>1.).any():
            raise ValueError("Nonfinite or out-of-range linear RGB; manual grading required")
        # Explicit component products use the pre-reviewed producer matrix.
        # The independent audit instead derives it from primaries/white xy.
        xyz=np.column_stack([block[:,0]*row[0]+block[:,1]*row[1]+block[:,2]*row[2]
                            for row in matrix])
        if not np.isfinite(xyz).all() or (xyz<0.).any():
            raise ValueError("Source transform generated invalid XYZ")
        value=4095.*np.power(REFERENCE_WHITE_NITS*xyz/ST428_PEAK_NITS,1./GAMMA)
        if (value>4095.+1e-7).any():
            raise ValueError("XYZ output exceeds legal 12-bit cinema range")
        quantized=np.minimum(4095,np.floor(value+.5)).astype(np.uint16)
        codes[offset:offset+len(block)]=quantized
        minimum=min(minimum,int(quantized.min()))
        maximum=max(maximum,int(quantized.max()))
    raster=bytes(output)
    raster_sha=hashlib.sha256(raster).hexdigest()
    reference=verify_xyz12_reference(source_float32,raster,width=width,height=height,
        source_sha256=source_sha256,xyz12_sha256=raster_sha,
        output_white_intent=output_white_intent)
    return {
        "format":FORMAT,"status":"XYZ12_SOURCE_BOUND_CANDIDATE",
        "xyz12":raster,
        "xyz12_sha256":raster_sha,
        "color_transform_revision":REVISION,
        "color_reference_audit":reference,
        "source_linear_float32_sha256":source_sha256,
        "original_take_sha256":original_take_sha256,
        "profile":profile,"width":width,"height":height,
        "source_color_space":"linear_sRGB_D65",
        "output_color_space":"SMPTE_ST_428_1_XYZ12",
        "chromatic_adaptation":("BRADFORD_D65_TO_DCI_REFERENCE" if
             output_white_intent=="DCI_REFERENCE_BRADFORD" else "NONE"),
        "target_white_xy":(list(CINEMA_WHITE_XY) if
             output_white_intent=="DCI_REFERENCE_BRADFORD" else list(SOURCE_D65_XY)),
        "output_white_intent":output_white_intent,
        "reference_white_nits":REFERENCE_WHITE_NITS,
        "transfer_gamma":GAMMA,"peak_normalization_nits":ST428_PEAK_NITS,
        "minimum_code":minimum,"maximum_code":maximum,
        "source_modified":False,"independently_calibrated":False,
        "production_picture_accepted":False,"ffmpeg_used":False,
    }
