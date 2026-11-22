"""NVP B9 independent bounded OpenEXR header/channel inspection.

Official OpenEXR layout: magic/version followed by bounded named attributes;
'chlist' encodes IEEE FLOAT=2, HALF=1, UINT=0. Checking the *real*
header is necessary but not sufficient; the contained Blender audit must also
decode the floating-point pixel payload and produce a verifiable readback.
"""
from __future__ import annotations
import struct
from pathlib import Path

MAGIC=bytes.fromhex("762f3101")
LIMIT=64*1024
REQUIRED={"channels":"chlist","compression":"compression","dataWindow":"box2i",
          "displayWindow":"box2i","lineOrder":"lineOrder",
          "pixelAspectRatio":"float","screenWindowCenter":"v2f",
          "screenWindowWidth":"float"}


def _cstr(data:bytes, offset:int, max_len:int=255):
    end=data.find(b"\0",offset,min(len(data),offset+max_len+1))
    if end<0 or end==offset:
        raise ValueError("Malformed/bounded OpenEXR C string")
    try:
        value=data[offset:end].decode("ascii")
    except UnicodeDecodeError as e:
        raise ValueError("Non-ASCII OpenEXR attribute string") from e
    return value,end+1


def inspect_exr_header(path:Path,*,width:int,height:int):
    """Prove real single-part scanline RGBA FLOAT32 and exact dimensions.

    Does not claim decoded pixels or color management provenance. A second
    independent native Blender audit is required for those properties.
    """
    if type(width) is not int or type(height) is not int or not (1<=width<=8192 and 1<=height<=8192):
        raise ValueError("Invalid bounded EXR dimensions")
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size<100:
        raise RuntimeError("Missing, symlinked or truncated EXR")
    with p.open("rb") as inp:
        prefix=inp.read(LIMIT)
    if prefix[:4]!=MAGIC or len(prefix)<24:
        raise RuntimeError("Not a real OpenEXR image")
    version=struct.unpack_from("<I",prefix,4)[0]
    if (version & 255) not in (2,3) or version>>8:
        raise RuntimeError("Unsupported OpenEXR version/flags or multipart/tile/deep image")
    fields={}
    pos=8
    while pos<len(prefix):
        if prefix[pos]==0:
            pos+=1
            break
        name,pos=_cstr(prefix,pos)
        kind,pos=_cstr(prefix,pos)
        if pos+4>len(prefix):
            raise RuntimeError("Truncated OpenEXR field length")
        size=struct.unpack_from("<I",prefix,pos)[0]
        pos+=4
        if name in fields or size>LIMIT or pos+size>len(prefix):
            raise RuntimeError("Duplicate, excessive or truncated OpenEXR header attribute")
        fields[name]=(kind,prefix[pos:pos+size])
        pos+=size
    else:
        raise RuntimeError("Unterminated OpenEXR header")
    for name,kind in REQUIRED.items():
        if name not in fields or fields[name][0]!=kind:
            raise RuntimeError("OpenEXR missing required "+name+" attribute")
    channels=fields["channels"][1]
    cursor=0
    found={}
    while cursor<len(channels):
        if channels[cursor]==0:
            cursor+=1
            break
        name,cursor=_cstr(channels,cursor)
        if cursor+16>len(channels) or name in found:
            raise RuntimeError("Invalid OpenEXR channel declaration")
        pixel,p_linear,x_sample,y_sample=struct.unpack_from("<iB3xii",channels,cursor)
        cursor+=16
        if pixel not in (0,1,2) or x_sample!=1 or y_sample!=1:
            raise RuntimeError("OpenEXR channel type or sampling invalid")
        found[name]=pixel
    else:
        raise RuntimeError("Unterminated OpenEXR channel list")
    if cursor!=len(channels):
        raise RuntimeError("Trailing invalid OpenEXR channel data")
    for name in ("R","G","B","A"):
        if found.get(name)!=2:
            raise RuntimeError("OpenEXR RGBA channel is not genuine 32-bit IEEE float: "+name)
    box=struct.unpack("<iiii",fields["dataWindow"][1])
    display=struct.unpack("<iiii",fields["displayWindow"][1])
    for label,(x0,y0,x1,y1) in (("dataWindow",box),("displayWindow",display)):
        if x1-x0+1!=width or y1-y0+1!=height:
            raise RuntimeError("OpenEXR "+label+" dimensions differ from approved render")
    return {"format":"nvp.exr.float32.header.v1",
            "width":width,"height":height,
            "rgba_float32":True,"channel_names":sorted(found),
            "compression_code":fields["compression"][1][0],
            "header_bytes":pos}
