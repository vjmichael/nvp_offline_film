"""WO2 independent image-pair measurements, not physical color certification.

Accepts *actual* rasterized RGB byte planes and immutable provenance for
both engines. Does not treat equal hashes or a passing test pattern as proof
of calibrated HDR, ACES, camera/lens or film-level Hydra parity.
"""
from __future__ import annotations
from hashlib import sha256
import math
import numpy as np

FORMAT="nvp.wo2.independent_renderer_image_comparison.v1"

def compare_rendered_rgb(*,native_rgb,independent_rgb,width,height,
                         source_scene_sha256,native_receipt_sha256,
                         independent_receipt_sha256,
                         max_mean_absolute_error=8.,
                         max_p95_absolute_error=24.):
    if (type(width) is not int or type(height) is not int or
        not 1<=width<=4096 or not 1<=height<=4096 or
        width*height>1024*1024 or
        type(source_scene_sha256) is not str or
        len(source_scene_sha256)!=64 or
        any(c not in "0123456789abcdef" for c in source_scene_sha256) or
        any(type(x) is not str or len(x)!=64 or
            any(c not in "0123456789abcdef" for c in x)
            for x in (native_receipt_sha256,independent_receipt_sha256)) or
        type(max_mean_absolute_error) not in (int,float) or
        type(max_p95_absolute_error) not in (int,float) or
        not math.isfinite(max_mean_absolute_error) or
        not math.isfinite(max_p95_absolute_error) or
        not 0<=max_mean_absolute_error<=32 or
        not 0<=max_p95_absolute_error<=64):
        raise ValueError("Unsafe or unverified renderer comparison scope")
    count=width*height*3
    if (type(native_rgb) is not bytes or
        type(independent_rgb) is not bytes or
        len(native_rgb)!=count or len(independent_rgb)!=count):
        raise ValueError("Actual matched RGB8 image planes required")
    a=np.frombuffer(native_rgb,dtype=np.uint8).astype(np.float32)
    b=np.frombuffer(independent_rgb,dtype=np.uint8).astype(np.float32)
    diff=np.abs(a-b)
    err=float(diff.mean())
    p95=float(np.percentile(diff,95))
    rmse=float(np.sqrt(np.square(diff).mean()))
    threshold_pass=(err<=max_mean_absolute_error and
                    p95<=max_p95_absolute_error)
    return {
        "format":FORMAT,
        "status":"NUMERIC_COMPARISON_RECORDED",
        "source_scene_sha256":source_scene_sha256,
        "native_render_receipt_sha256":native_receipt_sha256,
        "independent_render_receipt_sha256":independent_receipt_sha256,
        "native_image_rgb_sha256":sha256(native_rgb).hexdigest(),
        "independent_image_rgb_sha256":sha256(independent_rgb).hexdigest(),
        "width":width,"height":height,
        "pixel_format":"RGB8",
        "mean_absolute_error":round(err,5),
        "p95_absolute_error":round(p95,5),
        "root_mean_square_error":round(rmse,5),
        "max_channel_error":int(diff.max(initial=0)),
        "within_requested_numeric_tolerance":threshold_pass,
        "physical_display_calibrated":False,
        "scene_linear_hydra_parity_proven":False,
        "camera_lens_parity_proven":False,
        "physical_gpu_hardware_verified":False,
        "original_modified":False,
    }
