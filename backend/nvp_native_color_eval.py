"""DA-06B: consume immutable color decisions in DERIVED presentation pixels.

This intentionally modest 8-bit display-referred CPU transform is for
review AVI and PNG derivatives. It does not mutate camera/scene lighting,
original performance, source sound or color decision records. It is
NOT scene-linear ACES/HDR color science, a calibrated monitor transform,
or a professional mastering claim. No FFmpeg, ImageMagick or external
process is invoked.
"""
from __future__ import annotations

from io import BytesIO
from PIL import Image, ImageEnhance

from backend.nvp_native_color_decisions import validate_parameters

FORMAT="nvp.data_first.display_referred_grade_preview.v1"
MAX_PIXELS=4096*2160


def apply_display_grade(png_data,parameters):
    p=validate_parameters(parameters)
    if type(png_data) is not bytes or len(png_data)>24*1024*1024:
        raise ValueError("Bounded native source picture bytes required")
    with Image.open(BytesIO(png_data)) as original:
        if (original.format!="PNG" or original.mode!="RGB" or
                original.width*original.height>MAX_PIXELS):
            raise RuntimeError("Only verified bounded RGB native pictures are gradeable")
        original.load()
        image=original.copy()
    image=ImageEnhance.Color(image).enhance(p["saturation"])
    image=ImageEnhance.Contrast(image).enhance(p["contrast"])
    exposure=2.0**p["exposure_stops"]
    warmth=(p["temperature_kelvin"]-6500.0)/5500.0
    tint=p["tint_magenta_green"]
    gains=(exposure*(1.0-0.16*warmth+0.05*tint),
           exposure*(1.0-0.10*tint),
           exposure*(1.0+0.16*warmth+0.05*tint))
    channels=[]
    for channel,gain in zip(image.split(),gains):
        lut=[max(0,min(255,round(value*gain))) for value in range(256)]
        channels.append(channel.point(lut))
    image=Image.merge("RGB",tuple(channels))
    out=BytesIO()
    image.save(out,format="PNG",optimize=False)
    return out.getvalue()
