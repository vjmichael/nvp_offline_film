"""DA-06B/C: FFmpeg-free non-destructive source-bound SDR review color.

The current 8-bit CPU raster is display-referred. We explicitly decode
its sRGB transfer, perform the creative controls in *linear light*, then
re-encode sRGB. This is a genuine color-managed preview improvement but
still NOT an OCIO ACES master: those require a true scene-linear native
renderer and run through nvp_native_aces_color.py, never this function.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image

from backend.nvp_native_color_decisions import validate_parameters
from backend.nvp_native_aces_color import grade_scene_linear

FORMAT="nvp.data_first.linearized_srgb_preview_grade.v2"
MAX_PIXELS=4096*2160


def apply_display_grade(png_data,parameters,*,return_audit=False):
    p=validate_parameters(parameters)
    if type(png_data) is not bytes or not 32<len(png_data)<=24*1024*1024:
        raise ValueError("Bounded native picture bytes required")
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Native NumPy linear-light color worker missing") from exc
    with Image.open(BytesIO(png_data)) as original:
        if (original.format!="PNG" or original.mode!="RGB" or
                not 1<=original.width*original.height<=MAX_PIXELS):
            raise RuntimeError("Only verified bounded RGB native pictures are gradeable")
        original.load()
        width,height=original.size
        rgb=np.asarray(original,dtype=np.float32)/255.
    # Genuine sRGB electro-optical conversion before applying exposure,
    # contrast and saturation. Brightness controls must not multiply
    # gamma-encoded bytes or silently reinterpret SDR as scene-linear HDR.
    linear=np.where(
        rgb<=0.04045,rgb/12.92,((rgb+0.055)/1.055)**2.4).astype(np.float32)
    rgba=np.ones((height,width,4),dtype=np.float32)
    rgba[:,:,:3]=linear
    graded=grade_scene_linear(rgba,p,np)
    light=graded[:,:,:3]
    clipped=(light<0)|(light>1)
    clip_count=int(np.count_nonzero(clipped))
    display=np.clip(light,0,1)
    display=np.where(
        display<=0.0031308,12.92*display,
        1.055*np.power(display,1/2.4)-0.055)
    quant=np.rint(np.clip(display,0,1)*255.).astype(np.uint8)
    out=BytesIO()
    Image.fromarray(quant,"RGB").save(out,format="PNG",optimize=False)
    audit={
        "format":FORMAT,
        "pixel_count":width*height,
        "color_channel_count":width*height*3,
        "channels_clipped":clip_count,
        "clipped_channel_fraction":clip_count/(width*height*3),
        "transfer_in":"IEC_61966_2_1_srgb_eotf",
        "creative_controls_space":"linearized_srgb_review",
        "transfer_out":"IEC_61966_2_1_srgb_oetf",
        "real_scene_linear_renderer":False,
        "aces2_output":False,
        "hdr_master":False,
        "original_modified":False,
        "ffmpeg_used":False,
    }
    return (out.getvalue(),audit) if return_audit else out.getvalue()
