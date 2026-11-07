"""WO3-05: full source-frame MXF/JPEG2000 decoder roundtrip gate.

The trusted host supplies exact SHA-reviewed native asdcplib unwrap and
OpenJPEG decode binaries. All source codestream SHA identities are checked
against the MXF essence extracted into private staging. Every extracted
picture frame must really decode to an XYZ12 PPM with matching source
dimensions, and the extracted 24bit PCM is checked sample-for-sample against
the approved original sound track.

These roundtrips use different executables but share the producer libraries;
they do NOT substitute for independent DCP Doctor, formal SMPTE schema/DCI
compliance, color calibration, or actual projector ingest.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import shutil
import tempfile
import wave

from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo3_j2k_audit import inspect_j2k_header,PROFILES
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary

FORMAT="nvp.wo3.native_full_essence_roundtrip.v1"
MAX_REEL_FRAMES=7200

def _sha(blob):return hashlib.sha256(blob).hexdigest()

def _ppm_header(file,*,width,height):
    with file.open("rb") as handle:
        line1=handle.readline(20)
        line2=handle.readline(100)
        # Official OpenJPEG PPM exporter inserts a bounded version line.
        # It is not part of the image data or a color transform.
        if line2.startswith(b"# OpenJPEG-"):
            line2=handle.readline(40)
        line3=handle.readline(20)
        rest=handle.read()
    if (line1!=b"P6\n" or
        line2.strip()!=f"{width} {height}".encode("ascii") or
        line3.strip()!=b"4095" or
        len(rest)!=width*height*6 or
        any(rest[i]&0xf0 for i in range(0,len(rest),2))):
        raise RuntimeError("Actual native decoder produced invalid XYZ12 raster")
    return rest

def decode_full_dcp_candidate(folder,*,unwrap:ApprovedCodecBinary,
                              decoder:ApprovedCodecBinary,
                              expected_picture_codestream_sha256,
                              expected_sound_pcm_sha256,
                              profile="2K_FLAT_24",
                              expected_frames):
    if unwrap.product!="ASDCP-asdcp_unwrap" or (
        decoder.product!="OpenJPEG-opj_decompress"):
        raise PermissionError("Exact native MXF/JPEG2000 decoding capabilities required")
    if profile not in PROFILES or type(expected_frames) is not int or (
        not 1<=expected_frames<=MAX_REEL_FRAMES):
        raise ValueError("Bounded original cinema frame count/profile required")
    if (type(expected_picture_codestream_sha256) is not list or
        len(expected_picture_codestream_sha256)!=expected_frames or
        any(type(x) is not str or len(x)!=64 or
            any(c not in "0123456789abcdef" for c in x)
            for x in expected_picture_codestream_sha256) or
        type(expected_sound_pcm_sha256) is not str or
        len(expected_sound_pcm_sha256)!=64):
        raise PermissionError("Expected original frame and sound SHA ledger required")
    audit=inspect_dcp_structure(folder)
    if audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or (
        audit["reel_count"]!=1):
        raise RuntimeError("Only independently hashed single-reel DCP accepted")
    assets={x["kind"]:x for x in audit["tracks"]}
    if set(assets)!={"picture","sound"}:
        raise RuntimeError("One real picture and sound MXF track required")
    source=Path(folder).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="nvp-wo3-roundtrip-") as tmp:
        root=Path(tmp)
        for kind in ("picture","sound"):
            original=source/assets[kind]["filename"]
            if original.is_symlink():
                raise PermissionError("Linked source MXF cannot be decoded")
            shutil.copyfile(original,root/(kind+".mxf"))
        unwrap.run(["-d",str(expected_frames),"picture.mxf","p_"],
                   cwd=root,timeout=3600)
        decoded_hashes=[]
        width,height,_=PROFILES[profile]
        for i,expected in enumerate(expected_picture_codestream_sha256):
            name="p_"+str(i).zfill(6)+".j2c"
            j2k=root/name
            if not j2k.is_file() or j2k.is_symlink():
                raise RuntimeError("Real MXF unwrap omitted an original picture")
            raw=j2k.read_bytes()
            if _sha(raw)!=expected:
                raise RuntimeError("Decoded MXF source frame differs from approved J2K")
            inspect_j2k_header(raw,profile)
            out="xyz_"+str(i).zfill(6)+".ppm"
            decoder.run(["-i",name,"-o",out],cwd=root,timeout=240)
            pixels=_ppm_header(root/out,width=width,height=height)
            decoded_hashes.append(_sha(pixels))
            j2k.unlink();(root/out).unlink()
        unwrap.run(["-d",str(expected_frames),"sound.mxf","audio"],
                   cwd=root,timeout=3600)
        audio=root/"audio.wav"
        if not audio.is_file() or audio.is_symlink():
            raise RuntimeError("Real MXF sound unwrap did not create PCM WAV")
        with wave.open(str(audio),"rb") as w:
            if (w.getsampwidth()!=3 or w.getframerate()!=48000 or
                w.getnframes()!=expected_frames*2000 or
                w.getnchannels() not in (2,6,8) or
                w.getcomptype()!="NONE"):
                raise RuntimeError("MXF does not preserve source DCI PCM24 timing")
            source_pcm=w.readframes(w.getnframes())
        if _sha(source_pcm)!=expected_sound_pcm_sha256:
            raise RuntimeError("Real sound MXF altered source-approved PCM")
        return {
            "format":FORMAT,"status":"ALL_NATIVE_ESSENCE_ROUNDTRIPPED",
            "frames_decoded":expected_frames,
            "decoded_frame_sha256":decoded_hashes,
            "picture_exact_codestream_sha_verified":True,
            "pcm24_48000_sample_exact":True,
            "verified_source_sound_pcm_sha256":_sha(source_pcm),
            "asdcplib_unwrap_sha256":unwrap.sha256,
            "openjpeg_decoder_sha256":decoder.sha256,
            "reopened_package_integrity_verified":True,
            "formal_independent_dci_validator_passed":False,
            "physical_projection_accepted":False,
            "production_dcp_accepted":False,
            "original_source_modified":False,
            "ffmpeg_used":False,
        }
