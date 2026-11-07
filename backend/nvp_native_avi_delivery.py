"""DA-05C: FFmpeg-free, bounded single-file AVI picture + PCM delivery.

A deliberately modest independently encoded *derivative* from a separately
creator-approved SHA-verified PNG+WAV package. Uncompressed BGR24/PCM16 AVI
is interoperable but large and NOT ProRes, DCP or a cinema mastering claim.
This muxer cannot open a Digital Take or authorize a source change.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import struct
import tempfile
import wave

from PIL import Image

from backend.nvp_final_2d_native import FORMAT as PACKAGE_FORMAT, _png_header

FORMAT="nvp.final_2d.avi_rgb_pcm.v1"
MAX_AVI_BYTES=1024*1024*1024
MAX_FRAMES=7200
MAX_PIXELS=4096*2160
SAMPLE_RATE=48000


def _sha(path):
    h=sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def _start(out,kind,subtype=None):
    p=out.tell()
    out.write(kind+b"\0\0\0\0")
    if subtype is not None:out.write(subtype)
    return p


def _finish(out,start):
    end=out.tell()
    size=end-start-8
    if size>0xffffffff:raise ValueError("RIFF chunk exceeds 32-bit size")
    out.seek(start+4)
    out.write(struct.pack("<I",size))
    out.seek(end)
    if size%2:out.write(b"\0")


def _chunk(out,tag,data):
    pos=out.tell()
    out.write(tag+struct.pack("<I",len(data)))
    out.write(data)
    if len(data)%2:out.write(b"\0")
    return pos


def _avi_stream_header(kind,handler,scale,rate,length,buffer_size,
                       *,sample_size=0,width=0,height=0):
    return struct.pack("<4s4sIHHIIIIIIIIhhhh",
        kind,handler,0,0,0,0,scale,rate,0,length,
        buffer_size,0xffffffff,sample_size,0,0,width,height)


def _frame_bgr(png_path,width,height):
    data=png_path.read_bytes()
    if _png_header(data)!=(width,height):
        raise RuntimeError("Approved picture raster dimensions changed")
    with Image.open(BytesIO(data)) as image:
        if image.mode=="RGBA":
            # A derived master cannot silently invent an alpha compositor.
            raise RuntimeError("AVI RGB24 export requires opaque approved pictures")
        image.load()
        rgb=image.convert("RGB")
        raw=rgb.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes("raw","BGR")
    pitch=(width*3+3)&~3
    if pitch==width*3:return raw
    return b"".join(raw[y*width*3:(y+1)*width*3]+b"\0"*(pitch-width*3)
                    for y in range(height))


def deliver_avi(package_dir,output_file,*,expected_take_sha256,
                approve_delivery):
    """Publish no-replace AVI with bounded memory and independent approval.

    output_file must be selected by a trusted native host, never from an
    arbitrary web API or model tool. No FFmpeg executable is discovered.
    """
    if not callable(approve_delivery):raise TypeError("Native approval required")
    parent=Path(package_dir)
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("Expected existing trusted package directory")
    target=Path(output_file)
    if (target.suffix.lower()!=".avi" or target.is_symlink() or
            not target.parent.is_dir() or target.exists()):
        raise FileExistsError("A new trusted AVI destination is required")
    manifest_path=parent/"manifest.json"
    doc=json.loads(manifest_path.read_text("utf8"))
    if (doc.get("format")!=PACKAGE_FORMAT or
            doc.get("original_take_sha256")!=expected_take_sha256 or
            doc.get("ffmpeg_used") is not False or
            doc.get("conventional_single_file_master") is not False or
            doc.get("original_data_modified") is not False):
        raise RuntimeError("Only creator-approved source-pinned derived packages are accepted")
    if type(expected_take_sha256) is not str or len(expected_take_sha256)!=64:
        raise ValueError("Exact original Digital Take digest required")
    frames=doc.get("pictures")
    if not isinstance(frames,list) or not 1<=len(frames)<=MAX_FRAMES:
        raise ValueError("Bounded picture manifest required")
    width,height=doc["picture_dimensions"]
    if (not isinstance(width,int) or not isinstance(height,int) or
            width<=0 or height<=0 or width*height>MAX_PIXELS):
        raise ValueError("Invalid original renderer dimensions")
    fps_num,fps_den=doc["fps_num"],doc["fps_den"]
    if (type(fps_num) is not int or type(fps_den) is not int or
            fps_num<=0 or fps_den<=0 or fps_num>120000):
        raise RuntimeError("Untrusted presentation cadence")
    if (len(frames)!=doc["output_picture_count"] or
            any(type(f) is not dict or
                f.get("png_file")!=f"{i+1:07d}.png" or
                f.get("sample_index")!=i or
                type(f.get("sha256")) is not str
                for i,f in enumerate(frames))):
        raise RuntimeError("Noncanonical image sequence manifest")
    wav=parent/"soundtrack.wav"
    if (wav.is_symlink() or _sha(wav)!=doc.get("audio_sha256") or
            any((parent/"pictures"/f["png_file"]).is_symlink() for f in frames)):
        raise RuntimeError("Derived picture/audio source tampered")
    with wave.open(str(wav),"rb") as track:
        if (track.getnchannels()!=2 or track.getsampwidth()!=2 or
                track.getframerate()!=SAMPLE_RATE or
                track.getcomptype()!="NONE" or
                track.getnframes()!=doc["audio_samples"]):
            raise RuntimeError("Derived audio clock does not match approved source")
    # Deterministic upper bound before creating any output.
    pitch=(width*3+3)&~3
    approximate=(len(frames)*pitch*height + doc["audio_samples"]*4+
                 len(frames)*80+8192)
    if approximate>MAX_AVI_BYTES:
        raise ValueError("Uncompressed native AVI exceeds bounded one-file delivery size")
    grant={"operation":FORMAT,
           "original_take_sha256":expected_take_sha256,
           "manifest_sha256":_sha(manifest_path),
           "picture_count":len(frames),"audio_samples":doc["audio_samples"],
           "fps_num":fps_num,"fps_den":fps_den,
           "width":width,"height":height,
           "output_name":target.name,"source_mutated":False}
    if approve_delivery(dict(grant)) is not True:
        raise PermissionError("Creator denied derived AVI publication")
    # Recheck the exact approved manifest and audio after the native prompt.
    if (_sha(manifest_path)!=grant["manifest_sha256"] or
            _sha(wav)!=doc["audio_sha256"]):
        raise RuntimeError("Approved package changed while granting delivery")
    fd,tmp=tempfile.mkstemp(prefix=".nvp-avi-",suffix=".staged",dir=target.parent)
    os.close(fd)
    staged=Path(tmp)
    try:
        with staged.open("wb") as out, wave.open(str(wav),"rb") as audio:
            riff=_start(out,b"RIFF",b"AVI ")
            hdrl=_start(out,b"LIST",b"hdrl")
            frame_bytes=pitch*height
            microsec=round(1000000*fps_den/fps_num)
            avih=struct.pack("<IIIIIIIIII4I",
                microsec,round(frame_bytes*fps_num/fps_den)+SAMPLE_RATE*4,
                0,0x10,len(frames),0,2,frame_bytes,width,height,0,0,0,0)
            _chunk(out,b"avih",avih)
            video=_start(out,b"LIST",b"strl")
            _chunk(out,b"strh",_avi_stream_header(
                b"vids",b"DIB ",fps_den,fps_num,len(frames),frame_bytes,
                width=width,height=height))
            _chunk(out,b"strf",struct.pack("<IiiHHIIiiII",
                40,width,height,1,24,0,frame_bytes,0,0,0,0))
            _finish(out,video)
            sound=_start(out,b"LIST",b"strl")
            _chunk(out,b"strh",_avi_stream_header(
                b"auds",b"\0\0\0\0",4,SAMPLE_RATE*4,
                doc["audio_samples"],MAX_AVI_BYTES//1000,sample_size=4))
            _chunk(out,b"strf",struct.pack("<HHIIHH",1,2,SAMPLE_RATE,
                SAMPLE_RATE*4,4,16))
            _finish(out,sound)
            _finish(out,hdrl)
            movi=_start(out,b"LIST",b"movi")
            index=[]
            previous_sample=0
            for i,frame in enumerate(frames):
                path=parent/"pictures"/frame["png_file"]
                if _sha(path)!=frame["sha256"]:
                    raise RuntimeError("Approved frame SHA changed before encode")
                raw=_frame_bgr(path,width,height)
                if len(raw)!=frame_bytes:raise RuntimeError("Noncanonical BGR24 buffer")
                pos=_chunk(out,b"00db",raw)
                index.append((b"00db",0x10,pos-(movi+8),len(raw)))
                upto=min(doc["audio_samples"],(
                    (i+1)*SAMPLE_RATE*fps_den//fps_num))
                n=upto-previous_sample
                if n<0:raise RuntimeError("Nonmonotonic native audio cadence")
                if n:
                    pcm=audio.readframes(n)
                    if len(pcm)!=n*4:raise RuntimeError("Truncated native PCM stream")
                    pos=_chunk(out,b"01wb",pcm)
                    index.append((b"01wb",0,pos-(movi+8),len(pcm)))
                previous_sample=upto
                if out.tell()>MAX_AVI_BYTES:
                    raise ValueError("Single-file native movie exceeded size limit")
            if previous_sample<doc["audio_samples"]:
                n=doc["audio_samples"]-previous_sample
                pcm=audio.readframes(n)
                if len(pcm)!=n*4:raise RuntimeError("Truncated soundtrack tail")
                pos=_chunk(out,b"01wb",pcm)
                index.append((b"01wb",0,pos-(movi+8),len(pcm)))
            _finish(out,movi)
            _chunk(out,b"idx1",b"".join(
                struct.pack("<4sIII",*item) for item in index))
            _finish(out,riff)
            if out.tell()>MAX_AVI_BYTES:
                raise ValueError("Native AVI RIFF exceeded bounded output limit")
            out.flush();os.fsync(out.fileno())
        if target.exists():raise FileExistsError("Do not overwrite prior movie")
        # Atomic no-clobber publication for a local, same-directory file.
        os.link(staged,target,follow_symlinks=False)
        return {"format":FORMAT,"status":"DERIVED_SINGLE_FILE_AVI",
                "output_file":str(target),"output_sha256":_sha(target),
                "take_sha256":expected_take_sha256,
                "source_modified":False,"ffmpeg_used":False,
                "cinema_master_accepted":False}
    finally:
        staged.unlink(missing_ok=True)
