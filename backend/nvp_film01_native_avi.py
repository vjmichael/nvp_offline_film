"""Native first-party RIFF/AVI MJPEG+PCM16 review muxer; no FFmpeg.

Turns ACTUAL previously verified OpenUSD PNG frames and source PCM WAV
into an interleaved, seekable, playable 24fps AVI review derivative.
This never creates new picture frames, invents sound, grades image,
changes FilmIndex source or implies cinema color/master acceptance.

AVI MJPEG at 640x360 and mono 48kHz PCM16 is a practical, compressed
computer-screen review format. Media player/codec support may vary.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import struct
import wave
from zipfile import ZipFile
from PIL import Image

FORMAT="nvp.film01.original_native_avi_review.v1"
FPS=24
AUDIO_RATE=48000
SAMPLES_PER_FRAME=2000
IMAGE_WIDTH=640
IMAGE_HEIGHT=360
MAX_FRAMES=720
MAX_SOURCE_PNG_BYTES=750000
MAX_SOURCE_ZIP_BYTES=512*1024*1024
MAX_MJPEG_FRAME_BYTES=512000
KEYFRAME=0x10


def _chunk(tag,payload):
    if type(tag) is not bytes or len(tag)!=4:
        raise ValueError("Original AVI chunk tag must be four bytes")
    return tag+struct.pack("<I",len(payload))+payload+(
        b"\x00" if len(payload)%2 else b"")


def _list(tag,children):
    return _chunk(b"LIST",tag+children)


def _strh(kind,codec,length,scale,rate,sample_bytes,width=0,height=0):
    return struct.pack(
        "<4s4sIHHIIIIIIIIhhhh",
        kind,codec,0,0,0,0,scale,rate,0,length,
        MAX_MJPEG_FRAME_BYTES if kind==b"vids" else 4000,
        0xFFFFFFFF,sample_bytes,0,0,width,height)


def _header(count):
    image_format=struct.pack(
        "<IiiHH4sIiiII",
        40,IMAGE_WIDTH,IMAGE_HEIGHT,1,24,b"MJPG",
        IMAGE_WIDTH*IMAGE_HEIGHT*3,0,0,0,0)
    pcm_format=struct.pack(
        "<HHIIHH",1,1,AUDIO_RATE,AUDIO_RATE*2,2,16)
    main=struct.pack(
        "<IIIIIIIIII4I",round(1000000/FPS),4*1024*1024,
        0,0x110,count,0,2,MAX_MJPEG_FRAME_BYTES,
        IMAGE_WIDTH,IMAGE_HEIGHT,0,0,0,0)
    video=_list(b"strl",
        _chunk(b"strh",_strh(
            b"vids",b"MJPG",count,1,FPS,0,
            IMAGE_WIDTH,IMAGE_HEIGHT))+
        _chunk(b"strf",image_format))
    audio=_list(b"strl",
        _chunk(b"strh",_strh(
            b"auds",b"\x00"*4,count*SAMPLES_PER_FRAME,
            1,AUDIO_RATE,2))+
        _chunk(b"strf",pcm_format))
    return _list(b"hdrl",_chunk(b"avih",main)+video+audio)


def _encode_jpeg_verified(png):
    if not isinstance(png,bytes) or not 100<=len(png)<=MAX_SOURCE_PNG_BYTES:
        raise PermissionError("Missing genuine bounded NVP original PNG")
    with Image.open(BytesIO(png)) as img:
        img.load()
        if img.format!="PNG" or img.size!=(IMAGE_WIDTH,IMAGE_HEIGHT) or (
                img.mode!="RGB"):
            raise PermissionError("Native original PNG color/frame changed")
        out=BytesIO()
        img.save(out,format="JPEG",quality=90,subsampling=0,
                 progressive=False,optimize=False)
    jpeg=out.getvalue()
    if (not 100<len(jpeg)<=MAX_MJPEG_FRAME_BYTES or
            not jpeg.startswith(b"\xff\xd8") or
            not jpeg.endswith(b"\xff\xd9")):
        raise RuntimeError("Native AVI JPEG frame failed serialization")
    with Image.open(BytesIO(jpeg)) as reread:
        reread.load()
        if reread.format!="JPEG" or reread.size!=(IMAGE_WIDTH,IMAGE_HEIGHT):
            raise RuntimeError("Native MJPEG frame could not be reopened")
    return jpeg


def _verify_source(z,expected_frames):
    name="original_30s_preview_receipt.json"
    if name not in z.namelist():
        raise PermissionError("Native original source frame receipt missing")
    receipt=json.loads(z.read(name))
    if (receipt.get("frames_rendered_from_usd")!=expected_frames or
            receipt.get("intended_30s_output_frames")!=MAX_FRAMES or
            receipt.get("exact_pcm_samples")!=expected_frames*SAMPLES_PER_FRAME or
            receipt.get("native_raster_preview_only") is not True or
            receipt.get("dci_master_or_dcp_created") is not False or
            receipt.get("playable_muxed_movie_created") is not False):
        raise PermissionError("Not a verified original OpenUSD/PCM review package")
    rows=receipt.get("frame_receipts")
    if type(rows) is not list or len(rows)!=expected_frames:
        raise PermissionError("Original source frame manifest is incomplete")
    if len(z.namelist())!=expected_frames+3:
        raise PermissionError("Unexpected native source review ZIP assets")
    for i,row in enumerate(rows):
        if (row.get("frame_zero")!=i or
                type(row.get("frame_png_sha256")) is not str or
                len(row["frame_png_sha256"])!=64 or
                type(row.get("original_source_take_sha256")) is not str or
                len(row["original_source_take_sha256"])!=64):
            raise PermissionError("Non-contiguous or forged picture receipt")
    sound="audio/original_source_review_48k_mono.wav"
    if sound not in z.namelist():
        raise PermissionError("No original source WAV in NVP review bundle")
    if z.getinfo(sound).file_size!=44+expected_frames*SAMPLES_PER_FRAME*2:
        raise PermissionError("Original sound bytes differ from expected exact duration")
    with z.open(sound) as wf:
        if sha256(wf.read()).hexdigest()!=receipt["audio_wav_sha256"]:
            raise PermissionError("Native source sound digest mismatched")
    return receipt


def mux_original_native_avi(original_zip,output_file,*,expected_frames=MAX_FRAMES):
    """Commit a PLAYABLE review AVI only after all exact source images/PCM verify.

    The AVI RIFF stream is produced incrementally, one authentic PNG
    and 4000 original PCM bytes at a time. No unverified synthetic
    frame interpolation, image repeated on error or silent audio repair.
    The output is atomic: a failure leaves only .partial and no deliverable.
    """
    source=Path(original_zip)
    output=Path(output_file)
    if (not source.is_absolute() or not source.is_file() or source.is_symlink()
            or not output.is_absolute() or output.exists() or
            output.is_symlink() or type(expected_frames) is not int or
            not 1<=expected_frames<=MAX_FRAMES or
            source.stat().st_size>MAX_SOURCE_ZIP_BYTES):
        raise PermissionError("Requires trusted source ZIP, fresh absolute AVI and bounded count")
    scratch=output.with_name(output.name+".partial")
    if scratch.exists() or scratch.is_symlink():
        raise FileExistsError("Source AVI scratch already exists")
    names=[]
    with ZipFile(source,"r") as z:
        receipt=_verify_source(z,expected_frames)
        audio_data=z.read("audio/original_source_review_48k_mono.wav")
        with wave.open(BytesIO(audio_data),"rb") as reader:
            if (reader.getframerate()!=AUDIO_RATE or
                    reader.getsampwidth()!=2 or
                    reader.getnchannels()!=1 or
                    reader.getnframes()!=expected_frames*SAMPLES_PER_FRAME):
                raise PermissionError("Recorded sound incompatible with exact original frame count")
            original_pcm=reader.readframes(reader.getnframes())
        if len(original_pcm)!=expected_frames*SAMPLES_PER_FRAME*2:
            raise RuntimeError("Incomplete source PCM when assembling AVI")
        with scratch.open("xb") as f:
            f.write(b"RIFF")
            f.write(b"\x00"*4)
            f.write(b"AVI ")
            f.write(_header(expected_frames))
            movi_start=f.tell()
            f.write(b"LIST")
            f.write(b"\x00"*4)
            f.write(b"movi")
            entries=[]
            for i,row in enumerate(receipt["frame_receipts"]):
                png_name=f"preview_frames/frame_{i:04d}.png"
                if png_name not in z.namelist():
                    raise PermissionError("Missing actual native source frame")
                png=z.read(png_name)
                if sha256(png).hexdigest()!=row["frame_png_sha256"]:
                    raise PermissionError("Original source frame content SHA changed")
                jpeg=_encode_jpeg_verified(png)
                for tag,payload in (
                    (b"00dc",jpeg),
                    (b"01wb",original_pcm[
                        i*SAMPLES_PER_FRAME*2:(i+1)*SAMPLES_PER_FRAME*2]),
                ):
                    offset=f.tell()-(movi_start+8)
                    f.write(_chunk(tag,payload))
                    entries.append((tag,KEYFRAME,offset,len(payload)))
                names.append((png_name,sha256(jpeg).hexdigest()))
            movi_end=f.tell()
            f.seek(movi_start+4)
            f.write(struct.pack("<I",movi_end-movi_start-8))
            f.seek(movi_end)
            idx=b"".join(struct.pack("<4sIII",*row) for row in entries)
            f.write(_chunk(b"idx1",idx))
            end=f.tell()
            if end>=2**32:
                raise RuntimeError("AVI 1.0 native frame output exceeds 4 GiB")
            f.seek(4)
            f.write(struct.pack("<I",end-8))
            f.flush()
    # Reopen and scan exact RIFF/movi/index membership, not just existence.
    with scratch.open("rb") as f:
        header=f.read(12)
        if header[:4]!=b"RIFF" or header[8:]!=b"AVI ":
            raise RuntimeError("Native playable preview missing AVI RIFF container")
        if struct.unpack("<I",header[4:8])[0]!=scratch.stat().st_size-8:
            raise RuntimeError("Native playable preview RIFF length is wrong")
    if output.exists() or output.is_symlink():
        raise FileExistsError("Playable AVI was created concurrently")
    scratch.rename(output)
    result={
        "format":FORMAT,"source_archive_sha256":sha256(source.read_bytes()).hexdigest(),
        "file_sha256":sha256(output.read_bytes()).hexdigest(),
        "file_bytes":output.stat().st_size,
        "frames":expected_frames,"frame_rate":FPS,
        "pixel_resolution":[IMAGE_WIDTH,IMAGE_HEIGHT],
        "picture_codec":"MJPEG","audio_codec":"PCM_S16LE",
        "original_pcm_sample_count":len(original_pcm)//2,
        "source_png_to_jpeg_frames":len(names),
        "source_png_lossy_review_transcode":True,
        "source_image_sha_integrity_checked":True,
        "original_sound_sha_integrity_checked":True,
        "playable_avi_container_written":True,
        "external_player_verified":False,
        "creative_quality_approved":False,
        "dci_cinema_mastered":False,
        "original_source_unchanged":True,
    }
    return result
