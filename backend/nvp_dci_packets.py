"""Independent Tier-2 packet accounting for the canonical NVP cinema subset.

One layer, CPRL, one origin-zero tile, no coding overrides, no SOP/EPH,
no packed headers and code-block style zero. Does not decode Tier-1 MQ data.
Packet identities are implicit in JPEG 2000; the independent geometry and
header parser proves positional coverage, not semantic pixel provenance.
"""
from __future__ import annotations
import hashlib
import struct
from backend.nvp_dci_codestream import inspect_cinema_codestream, _segment
from backend.nvp_wo3_j2k_audit import PROFILES


def _ceil(n, d):
    return -(-n // d)


class _Bits:
    def __init__(self, raw, start, end):
        self.raw, self.pos, self.end = raw, start, end
        self.rem = self.byte = 0

    def read(self, n=1):
        value = 0
        for _ in range(n):
            if not self.rem:
                if self.pos >= self.end:
                    raise ValueError('Truncated packet header')
                stuffed = self.byte == 255
                self.byte = self.raw[self.pos]; self.pos += 1
                if stuffed and self.byte & 128:
                    raise ValueError('Invalid packet header stuffing')
                self.rem = 7 if stuffed else 8
            self.rem -= 1
            value = (value << 1) | ((self.byte >> self.rem) & 1)
        return value

    def align(self):
        if self.byte & ((1 << self.rem) - 1):
            raise ValueError('Nonzero packet header padding')
        if self.byte == 255:
            if self.pos >= self.end or self.raw[self.pos] != 0:
                raise ValueError('Missing terminal packet header stuffing')
            self.pos += 1
        return self.pos


class _Tree:
    def __init__(self, w, h):
        self.levels = []
        while True:
            self.levels.append((w, h, [[0, None] for _ in range(w*h)]))
            if w == h == 1:
                break
            w, h = _ceil(w, 2), _ceil(h, 2)

    def below(self, x, y, threshold, bits):
        lower = 0
        for level in range(len(self.levels)-1, -1, -1):
            w, _, nodes = self.levels[level]
            node = nodes[(y >> level)*w + (x >> level)]
            low, known = node
            low = max(low, lower)
            while known is None and low < threshold:
                if bits.read():
                    known = low
                else:
                    low += 1
            node[:] = [low, known]
            lower = low if known is None else known
        return known is not None and known < threshold


def _passes(bits):
    if not bits.read(): return 1
    if not bits.read(): return 2
    v = bits.read(2)
    if v != 3: return v+3
    v = bits.read(5)
    if v != 31: return v+6
    return bits.read(7)+37


def _geometry(width, height, d, r0, r1):
    events = []
    for r in range(r0, r1):
        scale = 1 << (d-r)
        p = 128 if not r else 256
        rw, rh = _ceil(width,scale), _ceil(height,scale)
        for y in range(_ceil(rh,p)):
            for x in range(_ceil(rw,p)):
                bands = []
                for band_index, (ox, oy) in enumerate(((0,0),) if not r else ((1,0),(0,1),(1,1))):
                    if not r:
                        bw,bh,step = rw,rh,p
                    else:
                        bw,bh = _ceil(width-ox*scale,2*scale),_ceil(height-oy*scale,2*scale)
                        step = p//2
                    x0,y0=x*step,y*step
                    x1,y1=min(x0+step,bw),min(y0+step,bh)
                    if x0 < x1 and y0 < y1:
                        bands.append((_ceil(x1,32)-x0//32,_ceil(y1,32)-y0//32, 0 if not r else 1+3*(r-1)+band_index))
                events.append((y*p*scale,x*p*scale,r,tuple(bands)))
    return sorted(events)


def _packet(raw, pos, end, bands, bitplanes):
    bits = _Bits(raw,pos,end)
    body=blocks=0
    if bits.read():
        for w,h,band in bands:
            inclusion, zero = _Tree(w,h), _Tree(w,h)
            for y in range(h):
                for x in range(w):
                    if not inclusion.below(x,y,1,bits):
                        continue
                    # Check against the specified subband QCD capacity,
                    # not a substitute for Tier-1 entropy decoding.
                    z=1
                    while not zero.below(x,y,z,bits):
                        z+=1
                        if z>bitplanes[band]: raise ValueError('Excessive zero bitplanes for QCD subband')
                    passes=_passes(bits)
                    if passes > 3*(bitplanes[band]-z+1)-2:
                        raise ValueError('Coding passes exceed QCD bit-plane capacity')
                    lblock=3
                    while bits.read():
                        lblock+=1
                        if lblock>21: raise ValueError('Excessive codeblock length signalling')
                    length=bits.read(lblock+passes.bit_length()-1)
                    if length==0: raise ValueError('Empty included codeblock contribution')
                    body+=length; blocks+=1
                    if body>end-pos: raise ValueError('Packet body exceeds tile-part')
    stop=bits.align()
    if body>end-stop: raise ValueError('Truncated packet body')
    return stop+body,stop-pos,body,blocks


def inspect_cinema_packets(raw, profile):
    report=inspect_cinema_codestream(raw,profile)
    w,h,_=PROFILES[profile]; d=report['wavelet_levels']; four=profile.startswith('4K_')
    groups=(_geometry(w,h,d,0,d),_geometry(w,h,d,d,d+1)) if four else (_geometry(w,h,d,0,d+1),)
    # QCD scalar-expounded exponents plus guard bits define magnitude bitplanes.
    marker_cursor=4+int.from_bytes(raw[4:6],'big')
    bitplanes=None
    while marker_cursor<report['main_header_bytes']:
        marker,payload,marker_cursor=_segment(raw,marker_cursor,report['main_header_bytes'])
        if marker==0x5c:
            guard=payload[0]>>5
            bitplanes=tuple((payload[i]>>3)+guard-1 for i in range(1,len(payload),2))
    if bitplanes is None or any(n<0 for n in bitplanes):
        raise ValueError('Invalid QCD magnitude bit-plane capacity')
    digest=hashlib.sha256(b'NVP-DCI-P4B-packet-map-v1\0'+profile.encode('ascii')+bytes.fromhex(report['raw_codestream_sha256']))
    pos=report['main_header_bytes']; parts=[]
    for index,size in enumerate(report['tile_part_bytes']):
        end=pos+size; cursor=pos+12
        while raw[cursor:cursor+2]!=b'\xff\x93':
            _,_,cursor=_segment(raw,cursor,end)
        cursor+=2
        component=index%3; group=index//3
        headers=bodies=blocks=0
        for y,x,r,bands in groups[group]:
            start=cursor
            cursor,head,body,n=_packet(raw,cursor,end,bands,bitplanes)
            headers+=head;bodies+=body;blocks+=n
            digest.update(struct.pack('>8I',component,r,x,y,start,head,body,n))
        if cursor!=end:
            raise ValueError('Extra bytes after expected CPRL packet coverage')
        parts.append({'component':component,'resolution_group':group,'packets':len(groups[group]),'packet_header_bytes':headers,'packet_body_bytes':bodies,'included_codeblocks':blocks,'tile_part_bytes':size})
        pos=end
    return {**report,'format':'nvp.dci.tier2_packet_accounting.v1','status':'CANONICAL_TIER2_PACKET_COVERAGE_VERIFIED','packet_membership_verified':True,'packet_coverage_verified':True,'packet_map_sha256':digest.hexdigest(),'packets_audited':sum(p['packets'] for p in parts),'packet_parts':parts,'entropy_decoded':False,'full_dci_codestream_conformity_verified':False,'dci_compliant':False}


class ReelPacketAudit:
    """Ordered constant-memory receipt; strict audit on every exact frame."""
    def __init__(self, profile):
        if profile not in PROFILES: raise ValueError('Unsupported cinema profile')
        self.profile=profile
        self.count=self.packets=self.max_frame=self.max_component=self.max_2k=0
        self.levels=None
        self.raw_digest=hashlib.sha256(b'NVP-DCI-P4A-v1\0'+profile.encode('ascii'))
        self.packet_digest=hashlib.sha256(b'NVP-DCI-P4B-reel-v1\0'+profile.encode('ascii'))

    def add(self, raw):
        r=inspect_cinema_packets(raw,self.profile)
        if self.levels is not None and self.levels!=r['wavelet_levels']:
            raise ValueError('Wavelet levels changed within cinema reel')
        self.levels=r['wavelet_levels']
        self.raw_digest.update(bytes.fromhex(r['raw_codestream_sha256']))
        self.packet_digest.update(bytes.fromhex(r['packet_map_sha256']))
        self.count+=1; self.packets+=r['packets_audited']
        self.max_frame=max(self.max_frame,r['bytes'])
        self.max_component=max(self.max_component,*r['declared_2k_component_bytes'])
        self.max_2k=max(self.max_2k,r['declared_2k_portion_bytes'])
        return r

    def finish(self, expected_frames):
        if type(expected_frames) is not int or expected_frames<1 or self.count!=expected_frames:
            raise ValueError('Incomplete packet audit coverage')
        return {'format':'nvp.dci.reel_tier2_constraints.v1','profile':self.profile,
                'frames_audited':self.count,'packets_audited':self.packets,'wavelet_levels':self.levels,
                'max_frame_bytes':self.max_frame,'max_declared_2k_component_bytes':self.max_component,
                'max_declared_2k_portion_bytes':self.max_2k,'ordered_codestream_digest':self.raw_digest.hexdigest(),
                'ordered_packet_map_digest':self.packet_digest.hexdigest(),
                'declared_structure_and_rate_bounds_verified':True,'packet_membership_verified':True,
                'packet_coverage_verified':True,'entropy_decoded':False,'full_dci_conformity_verified':False}
