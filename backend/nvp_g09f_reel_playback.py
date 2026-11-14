"""G09-F source-derived, byte-addressed playback across verified reel cuts.

The reel list is a virtual continuous 24 fps / 48 kHz presentation clock.
Each requested picture and sound window can cross a reel boundary without
inserting silence or resetting Film Time. Reels are the actual verified AVI
assets; no FFmpeg, external decoder, temporary re-encode or original USD
reconstruction. A device-clock WebAudio client presents the bounded windows.

The first request for a reel independently hashes it; the reader caches a
validated RIFF index with a fixed-size LRU. Subsequent reads require the
same file identity/size/mtime/ctime; a changed file is fully rechecked before
the index is reused. This is local-file integrity, not strong tamperproof
custody against a malicious OS actor restoring timestamps or inode contents.
"""
from __future__ import annotations
import base64
from collections import OrderedDict
from hashlib import sha256
from io import BytesIO
import math
from pathlib import Path
import struct
import threading
import wave

from PIL import Image
from backend.nvp_g09f_package import _verified_manifest,MAX_REEL_BYTES
from backend.nvp_g09e_chunk import FRAMES_PER_CHUNK

MAX_FRAMES_PER_REQUEST=12
MAX_SAMPLES_PER_REQUEST=24000
MAX_JPEG_BYTES=2*1024*1024
CACHE_REELS=8
RATE=48000
FPS=24

def _state(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file():
        raise RuntimeError("An archived film reel is not a safe original file")
    st=p.stat()
    if not 512<=st.st_size<=MAX_REEL_BYTES:
        raise RuntimeError("The original film reel exceeds the playback budget")
    return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)

def _exact_sha(path,expected):
    h=sha256()
    with open(path,"rb") as f:
        for piece in iter(lambda:f.read(1024*1024),b""):
            h.update(piece)
    if h.hexdigest()!=expected:
        raise RuntimeError("An original film reel changed after independent verification")

def _read_index(path,frames):
    """Parse actual RIFF/list + idx1, reject non-monotonic or alien chunks."""
    p=Path(path)
    with open(p,"rb") as f:
        size=p.stat().st_size
        head=f.read(12)
        if (len(head)!=12 or head[:4]!=b"RIFF" or head[8:12]!=b"AVI "
            or struct.unpack_from("<I",head,4)[0]!=size-8):
            raise RuntimeError("A distributed reel is not genuine RIFF AVI")
        cursor=12;media_begin=None;media_end=None;idx_offset=None;idx_size=None
        while cursor+8<=size:
            f.seek(cursor)
            header=f.read(8)
            tag,n=struct.unpack("<4sI",header)
            end=cursor+8+n+(n&1)
            if end>size:
                raise RuntimeError("An AVI container chunk is truncated")
            if tag==b"LIST":
                f.seek(cursor+8)
                kind=f.read(4)
                if kind==b"movi":
                    if media_begin is not None:
                        raise RuntimeError("AVI has competing media streams")
                    media_begin=cursor+12
                    media_end=cursor+8+n
            elif tag==b"idx1":
                if idx_offset is not None:
                    raise RuntimeError("AVI contains multiple conflicting indexes")
                idx_offset=cursor+8;idx_size=n
            cursor=end
        if cursor!=size or media_begin is None or idx_offset is None or (
                media_end is None or media_end>idx_offset):
            raise RuntimeError("The film reel contains no valid media index")
        if idx_size!=frames*2*16:
            raise RuntimeError("Reel AVI index does not match its picture/audio clock")
        f.seek(idx_offset)
        idx=f.read(idx_size)
        first_chunk=media_begin-4
        entries=[]
        next_at=media_begin
        for n in range(frames):
            pair=[]
            for kind in (b"00dc",b"01wb"):
                pos=(n*2+(0 if kind==b"00dc" else 1))*16
                tag,flags,rel,length=struct.unpack_from("<4sIII",idx,pos)
                absolute=first_chunk+rel
                if tag!=kind or absolute!=next_at or absolute+8+length>media_end:
                    raise RuntimeError("Reel AVI media bytes or ordering changed")
                f.seek(absolute)
                real_tag,real_size=struct.unpack("<4sI",f.read(8))
                if real_tag!=kind or real_size!=length:
                    raise RuntimeError("The AVI index points to different source bytes")
                if kind==b"00dc" and not 100<=length<=MAX_JPEG_BYTES:
                    raise RuntimeError("The displayed original picture is not bounded JPEG")
                if kind==b"01wb" and length!=8000:
                    raise RuntimeError("A reel sound block is not 2000 stereo samples")
                pair.append((absolute+8,length))
                next_at=absolute+8+length+(length&1)
            entries.append((pair[0],pair[1]))
        if next_at!=media_end:
            raise RuntimeError("An AVI contains unindexed data after the film")
        return tuple(entries)

class VerifiedReelReader:
    def __init__(self):
        self._guard=threading.RLock()
        self._cache=OrderedDict()

    def _reel(self,folder,manifest,index):
        refs=_verified_manifest(manifest)
        if type(index) is not int or not 0<=index<len(refs):
            raise ValueError("Choose a verified original-film reel")
        item=refs[index]
        path=Path(folder)/item["path"]
        before=_state(path)
        key=(str(path),item["sha256"])
        with self._guard:
            cached=self._cache.get(key)
            if cached and cached["stat"]==before:
                self._cache.move_to_end(key)
                return path,cached["entries"]
        _exact_sha(path,item["sha256"])
        index_entries=_read_index(path,item["end_frame"]-item["start_frame"])
        after=_state(path)
        if after!=before:
            raise RuntimeError("The film reel changed while its frame index was read")
        with self._guard:
            self._cache[key]={"stat":after,"entries":index_entries}
            self._cache.move_to_end(key)
            while len(self._cache)>CACHE_REELS:
                self._cache.popitem(last=False)
        return path,index_entries

    def timeline(self,folder,manifest):
        _verified_manifest(manifest)
        return {"format":"nvp.g09f.continuous_reel_playback.v1",
            "source_sha256":manifest["source_sha256"],
            "duration_seconds":manifest["total_frames"]/FPS,
            "picture_frames":manifest["total_frames"],
            "audio_samples":manifest["total_frames"]*2000,
            "reels":manifest["reel_count"],
            "fps":FPS,"sample_rate":RATE,"channels":2,
            "original_output_reels_preserved":True,
            "playback_uses_one_global_sample_clock":True,
            "physical_gapless_device_acceptance_passed":False}

    def pictures(self,folder,manifest,start,count):
        if (type(start) is not int or type(count) is not int or
                not 0<=start<manifest["total_frames"] or
                not 1<=count<=MAX_FRAMES_PER_REQUEST):
            raise ValueError("Choose a bounded original film picture window")
        frames=[]
        for global_i in range(start,min(start+count,manifest["total_frames"])):
            index,local=divmod(global_i,FRAMES_PER_CHUNK)
            path,entries=self._reel(folder,manifest,index)
            (offset,size),_=entries[local]
            with open(path,"rb") as source:
                source.seek(offset);raw=source.read(size)
            if (len(raw)!=size or not raw.startswith(b"\xff\xd8") or
                not raw.endswith(b"\xff\xd9")):
                raise RuntimeError("A distributed source picture was altered")
            with Image.open(BytesIO(raw)) as decoded:
                decoded.load()
                if decoded.size!=(640,360):
                    raise RuntimeError("A film picture lost its delivery profile")
            frames.append({"frame":global_i,
                "picture_base64":base64.b64encode(raw).decode("ascii"),
                "at_tick":global_i*294000000})
        return {"format":"nvp.g09f.checked_pictures.v1",
            "source_sha256":manifest["source_sha256"],
            "start_frame":start,"frames":frames,
            "original_reels_untouched":True}

    def sound(self,folder,manifest,start,count):
        total=manifest["total_frames"]*2000
        if (type(start) is not int or type(count) is not int or
                not 0<=start<total or
                not 1<=count<=MAX_SAMPLES_PER_REQUEST):
            raise ValueError("Choose an exact original-film sound window")
        end=min(start+count,total)
        raw=bytearray()
        current=start
        while current<end:
            frame,offset_in_frame=divmod(current,2000)
            index,local=divmod(frame,FRAMES_PER_CHUNK)
            path,entries=self._reel(folder,manifest,index)
            (_, _),(pcm_at,pcm_bytes)=entries[local]
            if pcm_bytes!=8000:
                raise RuntimeError("An original sound packet lost its sample clock")
            n=min(end-current,2000-offset_in_frame)
            with open(path,"rb") as f:
                f.seek(pcm_at+offset_in_frame*4)
                piece=f.read(n*4)
            if len(piece)!=n*4:
                raise RuntimeError("A film's original-derived PCM is truncated")
            raw.extend(piece)
            current+=n
        with BytesIO() as buffer:
            with wave.open(buffer,"wb") as wav:
                wav.setnchannels(2);wav.setsampwidth(2)
                wav.setframerate(RATE);wav.writeframes(bytes(raw))
            packaged=buffer.getvalue()
        return packaged,{"format":"nvp.g09f.checked_sound.v1",
            "source_sha256":manifest["source_sha256"],
            "start_sample":start,"sample_count":end-start,
            "sample_rate":RATE,"channels":2,
            "spans_reel_boundary":start//480000!=(end-1)//480000,
            "source_pcm_replaced":False}
