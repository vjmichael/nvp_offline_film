"""WO3 measured *relative* Hydra texture-color response, not calibration.

This verifier consumes receipts from TWO genuine external native Hydra image
renders of independently source-bound scenes. Its CIE Lab conversion assumes
RGB8 samples are sRGB only for diagnostic color separation. No ICC profile,
OCIO view, known radiance or calibrated display is established by this test.
"""
from __future__ import annotations

import math

FORMAT="nvp.wo3.native_hydra_relative_color_response.v1"


def _lab_d65(rgb):
    if (type(rgb) not in (list,tuple) or len(rgb)!=3 or
            any(type(c) not in (int,float) or not math.isfinite(c) or
                not 0<=c<=255 for c in rgb)):
        raise ValueError("Three bounded measured renderer RGB8 channels required")
    srgb=[float(c)/255 for c in rgb]
    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
            for v in srgb]
    x=(.4124564*linear[0]+.3575761*linear[1]+.1804375*linear[2])/.95047
    y=(.2126729*linear[0]+.7151522*linear[1]+.0721750*linear[2])
    z=(.0193339*linear[0]+.1191920*linear[1]+.9503041*linear[2])/1.08883
    def f(v):
        return v**(1/3) if v>(6/29)**3 else v/(3*(6/29)**2)+4/29
    fx,fy,fz=f(x),f(y),f(z)
    return (116*fy-16,500*(fx-fy),200*(fy-fz))


def verify_relative_hydra_swatch_response(red,blue,*,required_context="dual"):
    """Fail closed if a renderer ignores source color, or reports no pixels."""
    if required_context not in ("dual","mtlx_only"):
        raise ValueError("Unsupported bounded USD material audit context")
    if type(red) is not dict or type(blue) is not dict:
        raise ValueError("Two independent native Hydra receipts required")
    for receipt in (red,blue):
        if (receipt.get("status")!="HYDRA_FRAME_RENDERED" or
                receipt.get("real_independent_frame_rendered") is not True or
                receipt.get("derived_source_scope") is not True or
                receipt.get("physical_display_calibrated") is not False or
                receipt.get("renderer")!="Storm" or
                receipt.get("material_context_probe")!=required_context or
                type(receipt.get("renderer_executable_sha256")) is not str or
                len(receipt["renderer_executable_sha256"])!=64 or
                type(receipt.get("rendered_rgb_sha256")) is not str or
                len(receipt["rendered_rgb_sha256"])!=64 or
                not receipt.get("rendered_center_patch_pixels")):
            raise AssertionError("Real custody-bound external Hydra pixels required")
    if required_context=="mtlx_only" and any(
            r.get("materialx_only_terminal_isolated") is not True
            for r in (red,blue)):
        raise AssertionError("MaterialX-only probe retained universal shader fallback")
    if any(type(r.get("derived_render_layer_sha256")) is not str or
           len(r["derived_render_layer_sha256"])!=64
           for r in (red,blue)):
        raise AssertionError("Hash of actual temporary shader stage required")
    if red["renderer_executable_sha256"]!=blue["renderer_executable_sha256"]:
        raise AssertionError("Swatches came from different renderer binaries")
    if red["scene_document_sha256"]==blue["scene_document_sha256"]:
        raise AssertionError("Swatches cannot reuse one original scene")
    if red["rendered_rgb_sha256"]==blue["rendered_rgb_sha256"]:
        raise AssertionError("Independent Hydra frames are identical")
    a=red["rendered_center_patch_mean_rgb8"]
    b=blue["rendered_center_patch_mean_rgb8"]
    la=_lab_d65(a)
    lb=_lab_d65(b)
    delta_e=math.sqrt(sum((x-y)**2 for x,y in zip(la,lb)))
    red_dominance=float(a[0])-max(float(a[1]),float(a[2]))
    blue_dominance=float(b[2])-max(float(b[0]),float(b[1]))
    # This is a deliberately generous binary color-discrimination sanity
    # gate, NOT a target ΔE tolerance or measured accuracy vs the input PNG.
    if red_dominance<25 or blue_dominance<25 or delta_e<25:
        raise AssertionError(
            "Actual Hydra pixels did not preserve red/blue source separation:"
            f" red={a}, blue={b}, ΔE76={delta_e:.3f}")
    return {
        "format":FORMAT,
        "status":"REAL_HYDRA_RELATIVE_TEXTURE_COLOR_DISCRIMINATED",
        "red_source_scene_sha256":red["scene_document_sha256"],
        "blue_source_scene_sha256":blue["scene_document_sha256"],
        "renderer_executable_sha256":red["renderer_executable_sha256"],
        "red_derived_render_layer_sha256":red["derived_render_layer_sha256"],
        "blue_derived_render_layer_sha256":blue["derived_render_layer_sha256"],
        "materialx_only_terminal_isolated":required_context=="mtlx_only",
        "red_rendered_rgb_sha256":red["rendered_rgb_sha256"],
        "blue_rendered_rgb_sha256":blue["rendered_rgb_sha256"],
        "red_center_mean_rgb8":a,
        "blue_center_mean_rgb8":b,
        "red_dominance_rgb8":round(red_dominance,3),
        "blue_dominance_rgb8":round(blue_dominance,3),
        "between_rendered_swatches_delta_e76_assuming_srgb":round(delta_e,4),
        "center_patch_pixel_count":red["rendered_center_patch_pixels"],
        "actual_independent_hydra_pixels_verified":True,
        "material_context_probe":required_context,
        "dual_context_relative_color_response_verified":required_context=="dual",
        "materialx_only_relative_color_response_verified":required_context=="mtlx_only",
        "usd_preview_surface_relative_color_response_verified":False,
        "materialx_openpbr_shading_parity_verified":False,
        "absolute_reference_color_accuracy_verified":False,
        "reference_ocio_display_view_verified":False,
        "physical_gpu_accepted":False,
        "physical_display_calibrated":False,
        "theatrical_color_accepted":False,
    }
