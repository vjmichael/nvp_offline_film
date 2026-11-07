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
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_EDGE = 2048
MAX_PIXELS = 2048 * 2048
MAX_LIVE_PREVIEW_EDGE = 512
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
    png, (width,height,raw) = verified_texture(index, project_id, descriptor)
    preview=png
    pw,ph=width,height
    if max(width,height)>MAX_LIVE_PREVIEW_EDGE:
        # A disposable, deterministically derived display LOD, NEVER a new
        # source texture or substitute material authority. CPU source raster
        # continues to sample the original full-resolution FilmIndex PNG.
        from PIL import Image
        image=Image.frombytes("RGBA",(width,height),raw).convert("RGB")
        factor=MAX_LIVE_PREVIEW_EDGE/max(width,height)
        pw=max(1,round(width*factor))
        ph=max(1,round(height*factor))
        reduced=image.resize((pw,ph),Image.Resampling.LANCZOS)
        out=BytesIO()
        reduced.save(out,format="PNG",optimize=False)
        preview=out.getvalue()
    # Independent host-side CPU reference samples from the *actual*
    # verified GPU-preview PNG, not from a shader or JavaScript guess.
    _,_,pixels=decode_png(preview)
    expected=[]
    for u,v in ((.125,.125),(.875,.125),(.125,.875),(.875,.875)):
        px=min(pw-1,int(u*pw))
        py=ph-1-min(ph-1,int(v*ph))
        offset=(py*pw+px)*4
        expected.append(list(pixels[offset:offset+3]))
    return {
        "format": FORMAT, "sha256": descriptor["sha256"],
        "original_width":width,"original_height":height,
        "width":pw,"height":ph,
        "derived_preview":preview!=png,
        "preview_sha256":sha256(preview).hexdigest(),
        "gpu_reference_rgb":expected,
        "gpu_reference_uv":[[.125,.125],[.875,.125],
                            [.125,.875],[.875,.875]],
        "color_space": "sRGB", "wrap": "repeat",
        "png_base64": base64.b64encode(preview).decode("ascii"),
        "source_modified": False,
    }


def import_native_selected_png(index: FilmIndex, project_id, selected_path, *,
                               approve):
    """Only the host passes an OS-picked file; JavaScript cannot select paths."""
    from pathlib import Path
    import os
    import stat
    if not callable(approve) or type(selected_path) not in (str, Path):
        raise PermissionError("Trusted native picker and approval required")
    selected=Path(selected_path)
    if not selected.is_absolute() or selected.is_symlink():
        raise PermissionError("Native texture picker returned unsafe path")
    before=selected.stat()
    if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=MAX_SOURCE_BYTES:
        raise ValueError("Original source PNG exceeds bounded file limit")
    flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(selected,flags)
    try:
        opened=os.fstat(fd)
        identity=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)
        if not stat.S_ISREG(opened.st_mode) or identity(opened)!=identity(before):
            raise RuntimeError("Source PNG replaced during native selection")
        chunks=[]
        count=0
        while True:
            packet=os.read(fd,65536)
            if not packet:break
            count+=len(packet)
            if count>MAX_SOURCE_BYTES:
                raise ValueError("Original PNG exceeded trusted read bound")
            chunks.append(packet)
        if identity(os.fstat(fd))!=identity(opened) or count!=opened.st_size:
            raise RuntimeError("Original PNG changed during trusted read")
        png=b"".join(chunks)
    finally:
        os.close(fd)
    width,height,_=decode_png(png)
    digest=sha256(png).hexdigest()
    if approve({"sha256":digest,"width":width,"height":height,
                "size_bytes":len(png),"format":FORMAT}) is not True:
        return {"status":"DENIED","original_modified":False}
    descriptor=publish_texture(index,project_id,png)
    return {"status":"ORIGINAL_TEXTURE_IMPORTED",
            "texture":descriptor,"original_modified":False,
            "ffmpeg_used":False}


TILE_EDGE=256
MAX_MIP_LEVEL=3


def _tile_from_verified(descriptor,decoded,*,mip_level,tile_x,tile_y):
    """Encode a bounded tile from bytes verified in this native session."""
    if (type(mip_level) is not int or
        not 0<=mip_level<=MAX_MIP_LEVEL or
        type(tile_x) is not int or type(tile_y) is not int or
        tile_x<0 or tile_y<0):
        raise ValueError("Texture tile must have bounded integral coordinates")
    width,height,rgba=decoded
    if (type(width) is not int or type(height) is not int or
        not 1<=width<=MAX_EDGE or not 1<=height<=MAX_EDGE or
        type(rgba) is not bytes or len(rgba)!=width*height*4):
        raise RuntimeError("Decoded original texture cache is not valid")
    from PIL import Image
    source=Image.frombytes("RGBA",(width,height),rgba).convert("RGB")
    level_width=max(1,(width+2**mip_level-1)//(2**mip_level))
    level_height=max(1,(height+2**mip_level-1)//(2**mip_level))
    if mip_level:
        source=source.resize(
            (level_width,level_height),Image.Resampling.LANCZOS)
    columns=(level_width+TILE_EDGE-1)//TILE_EDGE
    rows=(level_height+TILE_EDGE-1)//TILE_EDGE
    if tile_x>=columns or tile_y>=rows:
        raise ValueError("Requested original PNG tile is out of range")
    left=tile_x*TILE_EDGE
    top=tile_y*TILE_EDGE
    tile=source.crop((left,top,min(left+TILE_EDGE,level_width),
                      min(top+TILE_EDGE,level_height)))
    encoded=BytesIO()
    tile.save(encoded,format="PNG",optimize=False)
    bytes_=encoded.getvalue()
    if len(bytes_)>MAX_SOURCE_BYTES:
        raise RuntimeError("Derived source tile exceeds bounded transport")
    return {
        "format":"nvp.original.usd_texture_tile.v1",
        "source_sha256":descriptor["sha256"],
        "source_width":width,"source_height":height,
        "mip_level":mip_level,
        "level_width":level_width,"level_height":level_height,
        "tile_x":tile_x,"tile_y":tile_y,
        "tile_columns":columns,"tile_rows":rows,
        "tile_width":tile.width,"tile_height":tile.height,
        "tile_sha256":sha256(bytes_).hexdigest(),
        "png_base64":base64.b64encode(bytes_).decode("ascii"),
        "derived_preview_only":True,"source_modified":False,
    }


def texture_tile_transport(index: FilmIndex, project_id, descriptor, *,
                           mip_level, tile_x, tile_y):
    """Stateless verified tile path for tests and independent native callers.

    The live Take controller uses one session-scoped decoded source cache
    to avoid re-decoding a 2K PNG for every one of up to 64 tiles.
    """
    _,decoded=verified_texture(index,project_id,descriptor)
    return _tile_from_verified(
        descriptor,decoded,mip_level=mip_level,
        tile_x=tile_x,tile_y=tile_y)
