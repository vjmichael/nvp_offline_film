"""WO2 immutable, project-scoped PNG texture authority (not a file resolver).

A trusted native caller supplies already approved PNG bytes. Decoding is
bounded and verified before SHA registration. USD stores only an opaque
nvp-blob URI; no external file, browser path or network URL is resolved.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import base64

from backend.nvp_film_index import FilmIndex, _sha

MEDIA = "image/png"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_EDGE = 512
MAX_PIXELS = 512 * 512
PREFIX = "nvp-blob://texture/"
FORMAT = "nvp.original.usd_texture_png.v1"


def decode_png(png: bytes):
    if type(png) is not bytes or not 0 < len(png) <= MAX_SOURCE_BYTES:
        raise ValueError("Native source texture must be bounded PNG bytes")
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Original texture source must be PNG")
    from PIL import Image, ImageFile
    with Image.open(BytesIO(png)) as image:
        if image.format != "PNG" or image.width > MAX_EDGE or (
                image.height > MAX_EDGE or
                image.width * image.height > MAX_PIXELS or
                image.width < 1 or image.height < 1 or
                getattr(image, "n_frames", 1) != 1):
            raise ValueError("Unsupported source image shape or animation")
        image.load()
        if image.mode not in ("RGB", "RGBA"):
            raise ValueError("Original texture must have RGB/RGBA channels")
        rgba = image.convert("RGBA")
        raw = rgba.tobytes()
        # Transparent texels require a separately validated alpha blending
        # contract. Never silently render invisible source as opaque color.
        if image.mode == "RGBA" and any(a != 255 for a in raw[3::4]):
            raise ValueError("Source transparency requires future alpha compositor")
        return rgba.width, rgba.height, raw


def publish_texture(index: FilmIndex, project_id, png: bytes):
    if not isinstance(index, FilmIndex):
        raise TypeError("Project-owned FilmIndex required")
    width, height, _ = decode_png(png)
    digest = index.put_blob(project_id, png, media_type=MEDIA)
    return {
        "format": FORMAT, "sha256": digest,
        "width": width, "height": height,
        "color_space": "sRGB", "wrap": "repeat",
        "usd_asset_path": PREFIX + digest,
        "source_modified": False,
    }


def verified_texture(index: FilmIndex, project_id, descriptor):
    if (type(descriptor) is not dict or set(descriptor) != {
            "format", "sha256", "width", "height", "color_space", "wrap",
            "usd_asset_path", "source_modified"} or
            descriptor["format"] != FORMAT or
            descriptor["color_space"] != "sRGB" or
            descriptor["wrap"] != "repeat" or
            descriptor["source_modified"] is not False):
        raise RuntimeError("Original texture descriptor cannot be trusted")
    digest = _sha(descriptor["sha256"])
    if descriptor["usd_asset_path"] != PREFIX + digest:
        raise RuntimeError("Original USD texture path differs from FilmIndex")
    png = index.get_blob(project_id, digest)
    w, h, rgba = decode_png(png)
    if descriptor["width"] != w or descriptor["height"] != h:
        raise RuntimeError("Frozen original image dimensions changed")
    return png, (w, h, rgba)


def texture_transport(index: FilmIndex, project_id, descriptor):
    png, _ = verified_texture(index, project_id, descriptor)
    # This is an ephemeral UI transport of an independently SHA-verified
    # frozen original. It is never saved as a new source image.
    return {
        "format": FORMAT, "sha256": descriptor["sha256"],
        "width": descriptor["width"], "height": descriptor["height"],
        "color_space": "sRGB", "wrap": "repeat",
        "png_base64": base64.b64encode(png).decode("ascii"),
        "source_modified": False,
    }
