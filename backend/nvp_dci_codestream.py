"""Independent bounded audit of NVP's 24fps cinema codestream subset.

DCSS 1.5.1 section 4.3.3 (not 4.4); ISO/IEC 15444-1 referenced there.
No encoder, external process, image decoder or trust in encoder metadata.
The SOT/TLM byte budget is measured, but packet-to-component membership and
entropy-code validity require a separate packet parser/decoder. Do not turn
this evidence into a claim of complete codestream or DCP conformity.

NVP intentionally accepts the canonical emitted subset: no component coding or
quantization overrides, no SOP/EPH, explicit precincts, scalar expounded QCD,
no other optional headers than COM. A rejected alternate syntax is *unsupported*
by this audit, not necessarily nonconforming under the full JPEG2000 standard.
"""
from __future__ import annotations
import hashlib
import re
import struct
from backend.nvp_wo3_j2k_audit import PROFILES, inspect_j2k_header

FORMAT = "nvp.dci.codestream_constraints.v1"
MAX_FRAME_BYTES = 1_302_083
MAX_2K_COMPONENT_BYTES = 1_041_666
MAX_HEADERS = 256
# With this subset SOP/EPH and all other in-packet markers are prohibited.
_UNEXPECTED_MARKER = re.compile(rb"\xff[\x90-\xff]")


def _segment(blob, pos, end):
    if pos + 4 > end or blob[pos] != 0xff:
        raise ValueError("Missing or truncated JPEG2000 marker segment")
    marker = blob[pos+1]
    length = int.from_bytes(blob[pos+2:pos+4], "big")
    stop = pos + 2 + length
    if length < 2 or stop > end:
        raise ValueError("Invalid JPEG2000 marker segment length")
    return marker, blob[pos+4:stop], stop


def _qcd(payload, levels):
    # scalar expounded: one exponent/mantissa per subband (1+3D)
    if (len(payload) != 1 + 2*(1+3*levels) or payload[0]&31 != 2):
        raise ValueError("Unsupported cinema quantization syntax")


def _coding(payload, is4k):
    if len(payload) < 11:
        raise ValueError("Truncated COD")
    flags, progression, hi, lo, mct, levels, bx, by, style, transform = payload[:10]
    if not (0 if not is4k else 1) <= levels <= (6 if is4k else 5):
        raise ValueError("Cinema wavelet level count outside profile")
    if (flags != 1 or progression != 4 or (hi,lo)!=(0,1) or
            mct != 0 or (bx,by,style,transform)!=(3,3,0,0)):
        raise ValueError("Unsupported cinema COD: require CPRL, one layer, 32x32, 9/7, XYZ without MCT")
    if payload[10:] != bytes([0x77]+[0x88]*levels):
        raise ValueError("Cinema precinct sizes must be 128 then 256")
    return levels


def _tlm_entries(payload, idx, max_parts):
    if len(payload)<2 or payload[0]!=idx:
        raise ValueError("Missing or unordered TLM segment index")
    st = payload[1]
    # Stlm bits 4-5: tile index field width; bit 6: length field width.
    ti = (st >> 4)&3
    size = 4 if st&64 else 2
    if ti==3 or st&0x8f:
        raise ValueError("Illegal TLM field coding")
    step=ti+size
    if (len(payload)-2)%step or len(payload)==2 or (len(payload)-2)//step>max_parts:
        raise ValueError("Invalid TLM entry count")
    lengths=[]
    for p in range(2,len(payload),step):
        if ti and int.from_bytes(payload[p:p+ti],"big")!=0:
            raise ValueError("TLM names a nonzero tile")
        n=int.from_bytes(payload[p+ti:p+step],"big")
        if n<=14:
            raise ValueError("TLM tile-part too short")
        lengths.append(n)
    return lengths


def inspect_cinema_codestream(blob, profile):
    """Audit one bounded raw frame. Raises on failure/unsupported syntax.

    The first three tile-part lengths are the *declared* 2K component budgets;
    their packet membership is not decoded here. Return explicit evidence
    fields rather than a generic 'DCI compliant' result.
    """
    if type(blob) is not bytes or len(blob)>MAX_FRAME_BYTES:
        raise ValueError("24fps cinema frame exceeds 1,302,083-byte bound")
    head=inspect_j2k_header(blob,profile)
    is4k=profile.startswith("4K_")
    count=6 if is4k else 3
    pos=4+int.from_bytes(blob[4:6],"big")
    seen={}; tlm=[]; tlm_idx=0; segments=0
    while blob[pos:pos+2]!=b"\xff\x90":
        marker,payload,pos=_segment(blob,pos,len(blob))
        segments+=1
        if segments>MAX_HEADERS:
            raise ValueError("Excessive cinema header segments")
        if marker==0x55:
            tlm.extend(_tlm_entries(payload,tlm_idx,count-len(tlm)))
            tlm_idx+=1
        elif marker==0x64:
            if len(payload)<2:
                raise ValueError("Truncated COM")
        elif marker in (0x52,0x5c,0x5f):
            if marker in seen:
                raise ValueError("Duplicate cinema coding marker")
            seen[marker]=payload
        else:
            raise ValueError(f"Forbidden or unsupported main-header marker FF{marker:02X}")
    if not {0x52,0x5c}<=seen.keys() or len(tlm)!=count:
        raise ValueError("Missing COD, QCD or complete required TLM")
    levels=_coding(seen[0x52],is4k)
    _qcd(seen[0x5c],levels)
    pocs=(bytes([0,0,0,1,levels,3,4, levels,0,0,1,levels+1,3,4]) if is4k else None)
    if seen.get(0x5f)!=pocs:
        raise ValueError("Invalid cinema 4K POC or forbidden 2K POC")
    main_header=pos
    sizes=[]
    for index, length in enumerate(tlm):
        if pos+12>len(blob) or blob[pos:pos+2]!=b"\xff\x90":
            raise ValueError("Missing declared SOT")
        lsot,tile,psot,part,total=struct.unpack_from(">HHIBB",blob,pos+2)
        if (lsot,tile,psot,part,total)!=(10,0,length,index,count):
            raise ValueError("SOT identity/order/count or TLM length mismatch")
        end=pos+psot
        if end>len(blob)-2:
            raise ValueError("Tile-part extends beyond codestream")
        cursor=pos+12; tile_headers=0
        while blob[cursor:cursor+2]!=b"\xff\x93":
            marker,payload,cursor=_segment(blob,cursor,end)
            tile_headers+=1
            if marker!=0x64 or len(payload)<2 or tile_headers>MAX_HEADERS:
                raise ValueError("Forbidden or unsupported tile-header marker")
        cursor+=2
        if cursor>=end or _UNEXPECTED_MARKER.search(blob,cursor,end):
            raise ValueError("Empty tile-part or unexpected marker in packet bytes")
        sizes.append(psot)
        pos=end
    if blob[pos:]!=b"\xff\xd9":
        raise ValueError("Missing exact EOC or trailing bytes")
    if any(n>MAX_2K_COMPONENT_BYTES for n in sizes[:3]):
        raise ValueError("Declared 2K component exceeds per-component byte limit")
    embedded=main_header+sum(sizes[:3])+2
    if embedded>MAX_FRAME_BYTES:
        raise ValueError("Embedded 2K portion exceeds frame limit")
    return {"format":FORMAT,"status":"DECLARED_CINEMA_STRUCTURE_AND_RATE_BOUNDS_VERIFIED",
            "profile":profile,"raw_codestream_sha256":head["raw_codestream_sha256"],
            "bytes":len(blob),"main_header_bytes":main_header,"tile_part_bytes":sizes,
            "declared_2k_component_bytes":sizes[:3],"declared_2k_portion_bytes":embedded,
            "wavelet_levels":levels,"frame_byte_limit_verified":True,
            "declared_component_byte_limits_verified":True,
            "tile_part_lengths_verified":True,"coding_constraints_verified":True,
            "packet_membership_verified":False,"entropy_decoded":False,
            "full_dci_codestream_conformity_verified":False,"dci_compliant":False}


class ReelCodestreamAudit:
    """Constant-memory ordered per-frame audit; also binds a reel digest."""
    def __init__(self,profile):
        if profile not in PROFILES:
            raise ValueError("Unsupported cinema profile")
        self.profile=profile
        self.count=0; self.levels=None; self.max_frame=0; self.max_component=0
        self.max_2k=0; self.digest=hashlib.sha256(b"NVP-DCI-P4A-v1\0"+profile.encode("ascii"))

    def add(self,raw):
        report=inspect_cinema_codestream(raw,self.profile)
        if self.levels is not None and self.levels!=report["wavelet_levels"]:
            raise ValueError("Wavelet levels changed within cinema reel")
        self.levels=report["wavelet_levels"]
        self.max_frame=max(self.max_frame,report["bytes"])
        self.max_component=max(self.max_component,*report["declared_2k_component_bytes"])
        self.max_2k=max(self.max_2k,report["declared_2k_portion_bytes"])
        self.digest.update(bytes.fromhex(report["raw_codestream_sha256"]))
        self.count+=1
        return report

    def finish(self,expected_frames):
        if type(expected_frames) is not int or expected_frames<1 or self.count!=expected_frames:
            raise ValueError("Incomplete audit coverage")
        return {"format":"nvp.dci.reel_rate_constraints.v1","profile":self.profile,
                "frames_audited":self.count,"wavelet_levels":self.levels,
                "max_frame_bytes":self.max_frame,"max_declared_2k_component_bytes":self.max_component,
                "max_declared_2k_portion_bytes":self.max_2k,"ordered_codestream_digest":self.digest.hexdigest(),
                "declared_structure_and_rate_bounds_verified":True,
                "packet_membership_verified":False,"full_dci_conformity_verified":False}
