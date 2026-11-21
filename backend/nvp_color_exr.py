"""NVP-COLOR-01A: bounded OpenEXR HALF RGBA header and provenance audit.

The header alone does NOT prove decoded pixels, scene-linear colorimetry,
an OCIO/ACES transform, or theatrical mastering. Native acceptance must
also independently fully decode the original EXR frame bytes.
"""
from __future__ import annotations
import struct

MAGIC = b"\x76\x2f\x31\x01"
PIXEL_PNG = "png_srgb8"
PIXEL_EXR = "openexr_half_rgba_scene_linear"
PIXEL_CONTRACTS = frozenset((PIXEL_PNG, PIXEL_EXR))


def exr_info(raw: bytes) -> dict:
    if len(raw) < 32 or raw[:4] != MAGIC:
        raise RuntimeError("Invalid OpenEXR frame header")
    version = struct.unpack("<I", raw[4:8])[0]
    # Blender 5.2.3 sets the OpenEXR LONG_NAMES bit (0x400), including for
    # single-part scanline files. Reject tiled, deep, multipart, unknown flags.
    if (version & 0xff) != 2 or version & ~(0xff | 0x400):
        raise RuntimeError("Unsupported tiled/multipart/deep OpenEXR frame")
    p, attrs = 8, {}
    def cstr(start):
        end = raw.find(b"\x00", start)
        if end < 0 or end - start > 128:
            raise RuntimeError("Malformed OpenEXR attribute name")
        try:
            return raw[start:end].decode("ascii"), end + 1
        except UnicodeDecodeError as exc:
            raise RuntimeError("Non-ASCII OpenEXR attribute") from exc
    for _ in range(100):
        name, p = cstr(p)
        if not name:
            break
        typ, p = cstr(p)
        if p + 4 > len(raw):
            raise RuntimeError("Truncated OpenEXR attribute")
        size = struct.unpack("<I", raw[p:p+4])[0]
        p += 4
        if size > 1_048_576 or p + size > len(raw) or name in attrs:
            raise RuntimeError("Invalid OpenEXR attribute length or duplicate")
        attrs[name] = (typ, raw[p:p+size])
        p += size
    else:
        raise RuntimeError("Unbounded OpenEXR header attributes")
    window = attrs.get("dataWindow")
    if not window or window[0] != "box2i" or len(window[1]) != 16:
        raise RuntimeError("OpenEXR lacks valid dataWindow")
    x0, y0, x1, y1 = struct.unpack("<4i", window[1])
    width, height = x1-x0+1, y1-y0+1
    if not 1 <= width <= 16384 or not 1 <= height <= 16384:
        raise RuntimeError("Invalid OpenEXR frame dimensions")
    channels = attrs.get("channels")
    if not channels or channels[0] != "chlist":
        raise RuntimeError("OpenEXR lacks channels")
    buf = channels[1]
    cp, types = 0, {}
    for _ in range(64):
        end = buf.find(b"\x00", cp)
        if end < 0:
            raise RuntimeError("Truncated OpenEXR channel list")
        name = buf[cp:end].decode("ascii")
        cp = end + 1
        if not name:
            break
        if cp + 16 > len(buf) or name in types:
            raise RuntimeError("Invalid OpenEXR channel")
        types[name] = struct.unpack("<i", buf[cp:cp+4])[0]
        cp += 16
    else:
        raise RuntimeError("Unbounded OpenEXR channel list")
    if set(types) != {"R","G","B","A"} or set(types.values()) != {1}:
        raise RuntimeError("OpenEXR must be RGBA with 16-bit HALF channels")
    compression = attrs.get("compression")
    if not compression or compression[0] != "compression" or len(compression[1]) != 1:
        raise RuntimeError("OpenEXR compression declaration missing")
    if compression[1] != b"\x03":
        raise RuntimeError("OpenEXR frame must use configured ZIP compression")
    return {"width":width, "height":height, "channels":sorted(types),
            "pixel_type":"HALF", "compression":"ZIP"}


def check_frame(raw: bytes, contract: str, png_info):
    if contract == PIXEL_PNG:
        w, h = png_info(raw)
        return {"width":w, "height":h, "media_type":"image/png", "extension":".png"}
    if contract == PIXEL_EXR:
        return {**exr_info(raw), "media_type":"image/x-exr", "extension":".exr"}
    raise RuntimeError("Unsupported indexed source pixel contract")
