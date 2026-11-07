"""WO3-02: strict JPEG2000 cinema-profile codestream evidence, not decoder proof.

Independent of OpenJPEG and any encoder backend: parses the JPEG2000 Part 1
SOC/SIZ/COD markers and enforces known 2K DCP component precision, dimensions,
tile and progression constraints. A passing header is NOT a fully decoded frame,
XYZ color validation, rate control or DCI compliance.
"""
from __future__ import annotations
import hashlib
import struct

FORMAT="nvp.wo3.jpeg2000_header.v1"
PROFILES={
    "2K_FLAT_24":(1998,1080,24),
    "2K_SCOPE_24":(2048,858,24),
    "2K_FULL_24":(2048,1080,24),
}
MAX_CODESTREAM=16*1024*1024

def inspect_j2k_header(blob,profile):
    if profile not in PROFILES:
        raise ValueError("Unsupported cinema source/profile")
    if type(blob) is not bytes or not 80<=len(blob)<=MAX_CODESTREAM:
        raise ValueError("Bounded native raw JPEG2000 codestream required")
    if blob[:2]!=b"\xff\x4f" or blob[2:4]!=b"\xff\x51":
        raise ValueError("JPEG2000 SOC/SIZ is required, not JP2 or fake bytes")
    length=struct.unpack_from(">H",blob,4)[0]
    if length<47 or 4+length>len(blob):
        raise ValueError("Invalid JPEG2000 SIZ marker length")
    rsiz=struct.unpack_from(">H",blob,6)[0]
    xsiz,ysiz,x0,y0,xt,yt,xt0,yt0=struct.unpack_from(">8I",blob,8)
    csiz=struct.unpack_from(">H",blob,40)[0]
    if csiz!=3 or length!=38+3*csiz:
        raise ValueError("D-Cinema requires exact 3-component SIZ")
    if (xsiz-x0,ysiz-y0)!=(PROFILES[profile][:2]) or (
        x0,y0,xt0,yt0)!=(0,0,0,0) or (
        xt,yt)!=(xsiz,ysiz):
        raise ValueError("Unverified DCI raster dimensions or multi-tile layout")
    components=[]
    for index in range(csiz):
        prec,subx,suby=struct.unpack_from(">BBB",blob,42+index*3)
        bits=(prec&127)+1
        if bits!=12 or prec&128 or subx!=1 or suby!=1:
            raise ValueError("Cinema XYZ components must be unsigned 12-bit 4:4:4")
        components.append({"precision":bits,"signed":False,"subsampling":[1,1]})
    cursor=4+length
    has_cod=False
    progression=None
    while cursor+4<=len(blob):
        if blob[cursor]!=255:
            raise ValueError("Malformed JPEG2000 marker ordering")
        marker=blob[cursor+1]
        if marker in (0x90,0x93):
            break
        marker_length=struct.unpack_from(">H",blob,cursor+2)[0]
        if marker_length<2 or cursor+2+marker_length>len(blob):
            raise ValueError("Broken JPEG2000 header segment")
        if marker==0x52:
            if marker_length<12 or has_cod:
                raise ValueError("Malformed or duplicate JPEG2000 COD marker")
            progression=blob[cursor+5]
            layers=struct.unpack_from(">H",blob,cursor+6)[0]
            # DCP: CPRL progression and one layer, no reversible MCT.
            if progression!=4 or layers!=1:
                raise ValueError("DCI requires CPRL progression and one layer")
            has_cod=True
        cursor+=2+marker_length
    if not has_cod or cursor+2>len(blob) or blob[cursor:cursor+2]!=b"\xff\x90":
        raise ValueError("No bounded JPEG2000 coding header and SOT")
    # Rsiz 3/4 generally denotes cinema 2K/4K profile. Independent
    # decoder and normative profile validation remain mandatory.
    if rsiz not in (3,4):
        raise ValueError("JPEG2000 codestream lacks cinema Rsiz profile")
    return {
        "format":FORMAT,"status":"HEADER_CONSTRAINTS_VERIFIED",
        "profile":profile,"width":xsiz,"height":ysiz,
        "fps":PROFILES[profile][2],"rsiz":rsiz,
        "components":components,"progression":"CPRL",
        "layers":1,"raw_codestream_sha256":hashlib.sha256(blob).hexdigest(),
        "full_codestream_decoded":False,
        "pixel_color_xyz_verified":False,
        "bitrate_verified":False,
        "dci_compliant":False,
    }
