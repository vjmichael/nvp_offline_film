"""G09-D first-party picture/audio interchange ZIP from VERIFIED native film.

Contains the exact completed 8-bit MJPEG picture frames as separate JPEG
assets, a real 48kHz stereo signed-16 WAV made from the actual film soundtrack
and a hashed manifest. It is a USEFUL edit/exchange package, NOT a lossless
source render, 16bit/EXR picture master, 24bit microphone source, ProRes, BWF
metadata claim, MXF, SMPTE DCP, ACES/OCIO certification or theatrical film.

No FFmpeg, executable launch, source reconstruction from a pre-rendered
frame-index, arbitrary asset paths, network or untrusted ZIP extraction.
This is a derived delivery from the independently checked finished AVI.
"""
from __future__ import annotations
from hashlib import sha256
from io import BytesIO
import json
import struct
import wave
from zipfile import ZipFile,ZipInfo,ZIP_STORED

from backend.nvp_g08_native_avi import (
    verify_movie,MAX_OUTPUT_BYTES,WIDTH,HEIGHT,FPS,AUDIO_HZ)
FORMAT="nvp.g09d.picture_sound_interchange.v1"
MAX_PACKAGE_BYTES=96*1024*1024
MAX_FRAMES=720

def _json(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=False,allow_nan=False).encode("utf8")

def _member(archive,path,data):
    if type(data) is not bytes or len(data)>MAX_PACKAGE_BYTES:
        raise ValueError("This interchange member exceeds its budget")
    info=ZipInfo(path,date_time=(1980,1,1,0,0,0))
    info.compress_type=ZIP_STORED
    info.create_system=3;info.external_attr=0o100644<<16
    archive.writestr(info,data)

def _parse_verified(data):
    if type(data) is not bytes or not 0<len(data)<=MAX_OUTPUT_BYTES:
        raise ValueError("The finished film is outside interchange limits")
    if len(data)>MAX_PACKAGE_BYTES-8*1024*1024:
        raise ValueError("This first interchange package supports smaller films")
    movi=data.find(b"movi");idx=data.rfind(b"idx1")
    if movi<0 or idx<0:raise RuntimeError("Verified film media was not found")
    at=movi+4;frames=[];pcm=bytearray()
    while at<idx:
        if at+8>idx:raise RuntimeError("Movie interchange source is truncated")
        kind=data[at:at+4]
        size=struct.unpack_from("<I",data,at+4)[0]
        stop=at+8+size
        if stop>idx:raise RuntimeError("Movie interchange contains a truncated asset")
        raw=data[at+8:stop]
        if kind==b"00dc":frames.append(raw)
        elif kind==b"01wb":pcm.extend(raw)
        else:raise RuntimeError("Unknown verified movie media type")
        at=stop+(size&1)
    if at!=idx or not 1<=len(frames)<=MAX_FRAMES or len(pcm)!=len(frames)*8000:
        raise RuntimeError("Original picture/audio frame counts do not agree")
    return frames,bytes(pcm)

def make_interchange(finished_movie,*,source_sha256=None):
    if source_sha256 and sha256(finished_movie).hexdigest()!=source_sha256:
        raise RuntimeError("Finished original film digest changed")
    frames,pcm=_parse_verified(finished_movie)
    verified=verify_movie(finished_movie,len(frames),
        expected_sha=source_sha256)
    if not verified["verified"]:
        raise RuntimeError("A complete original film was not independently verified")
    wav=BytesIO()
    with wave.open(wav,"wb") as f:
        f.setnchannels(2);f.setsampwidth(2)
        f.setframerate(AUDIO_HZ);f.writeframes(pcm)
    sound=wav.getvalue()
    manifest={"format":FORMAT,
        "source_avi_sha256":sha256(finished_movie).hexdigest(),
        "source_avi_independently_verified":True,
        "output_profile":"640x360_24fps_8bit_sdr_jpeg_48000_stereo_pcm16",
        "width":WIDTH,"height":HEIGHT,"frame_rate":FPS,
        "audio_rate":AUDIO_HZ,"audio_channels":2,"audio_sample_depth":16,
        "audio_sample_count_per_channel":len(pcm)//4,
        "original_filmed_openusd_pcm_rewritten":False,
        "picture_is_already_8bit_display_referred":True,
        "frame_sequence_is_not_lossless_openusd_render":True,
        "dcp_compliant":False,"aces_ocio_certified":False,
        "assets":[]}
    dest=BytesIO()
    with ZipFile(dest,"w") as z:
        for i,frame in enumerate(frames):
            name=f"picture/frame_{i:06}.jpg"
            manifest["assets"].append({"path":name,
                "size":len(frame),"sha256":sha256(frame).hexdigest(),
                "kind":"display_referred_jpeg_frame",
                "source_frame":i})
            _member(z,name,frame)
            if dest.tell()>MAX_PACKAGE_BYTES:
                raise ValueError("Interchange package exceeds bounded size")
        name="sound/finished_stereo_48000_pcm16.wav"
        manifest["assets"].append({"path":name,
            "size":len(sound),"sha256":sha256(sound).hexdigest(),
            "kind":"derived_finished_sound"})
        _member(z,name,sound)
        _member(z,"manifest.json",_json(manifest))
    output=dest.getvalue()
    if len(output)>MAX_PACKAGE_BYTES:
        raise ValueError("Finished interchange package is too large")
    # Independent fresh ZIP instance checks manifest paths, full bytes,
    # WAV channel/sample clock and exact independent frame identity.
    with ZipFile(BytesIO(output),"r") as z:
        members=z.namelist()
        expected=[a["path"] for a in manifest["assets"]]+["manifest.json"]
        if members!=expected or z.testzip() is not None:
            raise RuntimeError("Picture/sound interchange members were altered")
        parsed=json.loads(z.read("manifest.json"))
        if parsed!=manifest:
            raise RuntimeError("Interchange manifest changed during delivery")
        for member in manifest["assets"]:
            actual=z.read(member["path"])
            if sha256(actual).hexdigest()!=member["sha256"] or (
                    len(actual)!=member["size"]):
                raise RuntimeError("A picture/sound interchange asset was changed")
        with wave.open(BytesIO(z.read(name)),"rb") as f:
            if (f.getnchannels()!=2 or f.getsampwidth()!=2 or
                f.getframerate()!=48000 or
                f.getnframes()!=len(frames)*2000):
                raise RuntimeError("Interchange sound lost its film clock")
    return output,{"format":FORMAT,
        "source_avi_sha256":manifest["source_avi_sha256"],
        "package_sha256":sha256(output).hexdigest(),
        "frames":len(frames),"audio_samples_per_channel":len(pcm)//4,
        "manifest_sha256":sha256(_json(manifest)).hexdigest(),
        "assets_verified":len(manifest["assets"]),
        "verified":True,"dcp_compliant":False,
        "original_film_untouched":True}
