"""INT-02D: creator-approved 24fps playable AVI from source-verified edited PNG/PCM.

This is a final presentation DERIVATIVE, never a source, new frame clock,
cinema master, grade or DCP. It encodes MJPEG and original stereo PCM16 into
one seek-indexed RIFF AVI, without FFmpeg, network, codec subprocesses or
modification of FilmIndex. A second, one-use native creator approval is required.
"""
from __future__ import annotations
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import wave

from PIL import Image
from backend.nvp_int02_edited_film import (
    OUTPUT_FRAMES, AUDIO_SAMPLES, verify_edited_film,
)
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_film_index import _require_pid, _id

FORMAT = "nvp.int02.playable_avi_preview.v1"
RATE = 48000
FPS = 24
SAMPLES_PER_FRAME = 2000
MAX_JPEG_BYTES = 12 * 1024 * 1024
MAX_RIFF_BYTES = 0xFFFFFFFF - 4096


def _sha_file(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _u32(value):
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise RuntimeError("Native AVI chunk exceeds bounded 32-bit RIFF size")
    return struct.pack("<I", value)


def _chunk(tag, data):
    return tag + _u32(len(data)) + data + (b"\0" if len(data) & 1 else b"")


def _avi_list(kind, contents):
    return _chunk(b"LIST", kind + contents)


def _headers(width, height, frames):
    if (type(width) is not int or type(height) is not int or
        not 16 <= width <= 3840 or not 16 <= height <= 2160 or
        width * height > 8294400 or type(frames) is not int or
        not 1 <= frames <= OUTPUT_FRAMES):
        raise ValueError("Unbounded native AVI picture geometry or duration")
    avih = struct.pack("<IIIIIIIIII4I", 1000000 // FPS, 0, 0, 0x110,
                       frames, 0, 2, MAX_JPEG_BYTES, width, height, 0, 0, 0, 0)
    video_strh = struct.pack("<4s4sIHHIIIIIIIIhhhh", b"vids", b"MJPG",
        0, 0, 0, 0, 1, FPS, 0, frames, MAX_JPEG_BYTES,
        0xFFFFFFFF, 0, 0, 0, width, height)
    video_strf = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24,
                             int.from_bytes(b"MJPG", "little"),
                             width * height * 3, 0, 0, 0, 0)
    audio_strh = struct.pack("<4s4sIHHIIIIIIIIhhhh", b"auds", b"\0" * 4,
        0, 0, 0, 0, 4, RATE * 4, 0, frames * SAMPLES_PER_FRAME,
        SAMPLES_PER_FRAME * 4, 0xFFFFFFFF, 4, 0, 0, 0, 0)
    audio_strf = struct.pack("<HHIIHH", 1, 2, RATE, RATE * 4, 4, 16)
    return _avi_list(b"hdrl", _chunk(b"avih", avih) +
        _avi_list(b"strl", _chunk(b"strh", video_strh) +
                  _chunk(b"strf", video_strf)) +
        _avi_list(b"strl", _chunk(b"strh", audio_strh) +
                  _chunk(b"strf", audio_strf)))


def _mjpeg(png, dimensions):
    source = Path(png)
    if (source.is_symlink() or not source.is_file() or
        not 0 < source.stat().st_size <= 24 * 1024 * 1024):
        raise RuntimeError("Native source picture missing or linked")
    with Image.open(source) as decoded:
        if decoded.format != "PNG" or list(decoded.size) != list(dimensions):
            raise RuntimeError("Native picture format or dimensions changed")
        decoded.load()
        stream = BytesIO()
        decoded.convert("RGB").save(
            stream, format="JPEG", quality=90, subsampling=0,
            optimize=False, progressive=False)
        result = stream.getvalue()
    if not (4 <= len(result) <= MAX_JPEG_BYTES and
            result.startswith(b"\xff\xd8") and result.endswith(b"\xff\xd9")):
        raise RuntimeError("Bounded MJPEG frame encoding failed")
    return result


def _write_interleaved_avi(destination, frames, audio_path, dimensions, *,
                           expected_sha=None, cancelled=lambda: False,
                           progress=lambda stage, value: None):
    """Real 24-fps MJPEG/PCM mux. Caller alone owns unpublished staging."""
    count = len(frames)
    if (not 1 <= count <= OUTPUT_FRAMES or
        expected_sha is not None and len(expected_sha) != count):
        raise ValueError("Incomplete or unbounded native picture sequence")
    headers = _headers(*dimensions, count)
    sound_digest = sha256()
    entries = []
    with wave.open(str(audio_path), "rb") as sound:
        if (sound.getnchannels(), sound.getsampwidth(), sound.getframerate(),
            sound.getnframes(), sound.getcomptype()) != (
                2, 2, RATE, count * SAMPLES_PER_FRAME, "NONE"):
            raise RuntimeError("Original-derived audio duration/format differs from picture")
        with Path(destination).open("xb") as out:
            out.write(b"RIFF" + b"\0" * 4 + b"AVI " + headers)
            movi = out.tell()
            out.write(b"LIST" + b"\0" * 4 + b"movi")
            movi_base = movi + 8
            for i, frame in enumerate(frames):
                if cancelled():
                    raise InterruptedError("Director cancelled native AVI flattening")
                if expected_sha is not None and _sha_file(frame) != expected_sha[i]:
                    raise RuntimeError("Original derived picture SHA changed during export")
                jpg = _mjpeg(frame, dimensions)
                pcm = sound.readframes(SAMPLES_PER_FRAME)
                if len(pcm) != SAMPLES_PER_FRAME * 4:
                    raise RuntimeError("Original PCM omitted at picture boundary")
                sound_digest.update(pcm)
                for tag, payload, flags in (
                    (b"00dc", jpg, 0x10), (b"01wb", pcm, 0)):
                    entries.append((tag, flags, out.tell() - movi_base,
                                    len(payload)))
                    out.write(_chunk(tag, payload))
                if out.tell() > MAX_RIFF_BYTES - 24000:
                    raise RuntimeError("Original film cannot fit in bounded RIFF")
                progress("playable_avi", i + 1)
            if sound.readframes(1):
                raise RuntimeError("Extra original PCM beyond final frame")
            end_movi = out.tell()
            out.seek(movi + 4)
            out.write(_u32(end_movi - (movi + 8)))
            out.seek(end_movi)
            out.write(_chunk(b"idx1", b"".join(
                struct.pack("<4sIII", *entry) for entry in entries)))
            size = out.tell()
            if size > MAX_RIFF_BYTES:
                raise RuntimeError("Native playable film too large")
            out.seek(4)
            out.write(_u32(size - 8))
            out.flush()
            os.fsync(out.fileno())
    return {"avi_sha256": _sha_file(destination),
            "avi_bytes": Path(destination).stat().st_size,
            "video_frames": count,
            "pcm_sample_frames": count * SAMPLES_PER_FRAME,
            "pcm_sha256": sound_digest.hexdigest()}


def _verify_avi_structure(path, frames, expected_audio_sha, dimensions):
    """Read back RIFF/idx1 and interleaved picture/PCM, independently of mux."""
    source = Path(path)
    with source.open("rb") as stream:
        if stream.read(4) != b"RIFF":
            raise RuntimeError("Playable AVI RIFF header absent")
        declared = struct.unpack("<I", stream.read(4))[0]
        if stream.read(4) != b"AVI " or declared != source.stat().st_size - 8:
            raise RuntimeError("Playable AVI root length changed")
        if stream.read(4) != b"LIST":
            raise RuntimeError("Playable AVI stream headers absent")
        header_len = struct.unpack("<I", stream.read(4))[0]
        if stream.read(4) != b"hdrl":
            raise RuntimeError("Playable AVI hdrl identity changed")
        stream.seek(12 + 8 + header_len)
        movi = stream.tell()
        if stream.read(4) != b"LIST":
            raise RuntimeError("Playable AVI movi list absent")
        movi_len = struct.unpack("<I", stream.read(4))[0]
        if stream.read(4) != b"movi":
            raise RuntimeError("Playable AVI movi identity changed")
        movi_base = movi + 8
        movi_end = movi + 8 + movi_len
        check = []
        digest = sha256()
        for i in range(frames * 2):
            off = stream.tell() - movi_base
            tag = stream.read(4)
            length = struct.unpack("<I", stream.read(4))[0]
            if i % 2 == 0:
                if tag != b"00dc" or not 4 <= length <= MAX_JPEG_BYTES:
                    raise RuntimeError("Playable picture packet missing")
                encoded = stream.read(length)
                if (not encoded.startswith(b"\xff\xd8") or
                    not encoded.endswith(b"\xff\xd9")):
                    raise RuntimeError("Playable MJPEG packet incomplete")
                with Image.open(BytesIO(encoded)) as picture:
                    if list(picture.size) != list(dimensions):
                        raise RuntimeError("Playable picture dimensions differ")
            else:
                if tag != b"01wb" or length != SAMPLES_PER_FRAME * 4:
                    raise RuntimeError("Playable PCM interleave truncated")
                digest.update(stream.read(length))
            check.append((tag, 0x10 if i % 2 == 0 else 0, off, length))
            if length & 1:
                stream.read(1)
        if stream.tell() != movi_end:
            raise RuntimeError("Playable film sample list has extra/missing data")
        if stream.read(4) != b"idx1" or struct.unpack(
                "<I", stream.read(4))[0] != len(check) * 16:
            raise RuntimeError("Playable movie seek index missing")
        for row in check:
            if struct.unpack("<4sIII", stream.read(16)) != row:
                raise RuntimeError("Playable movie seek index points to wrong bytes")
        if stream.read(1):
            raise RuntimeError("Playable AVI has unverified trailing bytes")
    if digest.hexdigest() != expected_audio_sha:
        raise RuntimeError("Playable movie PCM differs from native source")
    return {"readback_verified": True, "complete_interleave": True,
            "indexed_frames": frames, "audio_sha256": digest.hexdigest()}


def export_playable_edited_avi(assembly: SlateSequenceAssembly, project_id,
                               edit_id, edit_revision, derivative_dir, *,
                               approve, cancelled=lambda: False,
                               progress=lambda stage, value: None):
    """Separate native approval; atomic publication after exact source reopens."""
    if type(assembly) is not SlateSequenceAssembly or not callable(approve):
        raise TypeError("Trusted native editorial and one-use approval required")
    _require_pid(project_id)
    _id(edit_id, "committed source editor")
    source = Path(derivative_dir)
    if source.is_symlink() or not source.is_dir():
        raise RuntimeError("Verified original derivative directory missing")
    prior = verify_edited_film(assembly, project_id, edit_id,
                               edit_revision, source)
    manifest = json.loads((source / "manifest.json").read_bytes())
    name = manifest.get("presentation_id")
    _id(name, "source-bound film presentation")
    target = source.parent / ("NVPPreview30_" + name)
    if target.exists() or target.is_symlink():
        raise FileExistsError("This playable film has already been published")
    scope = {
        "operation": FORMAT, "project_id": project_id, "edit_id": edit_id,
        "edit_revision": edit_revision, "edit_sha256": prior["edit_sha256"],
        "derivative_manifest_sha256": prior["manifest_sha256"],
        "source_directory": str(source), "output_directory": str(target),
        "video": "MJPEG AVI 24fps", "audio": "PCM16 stereo 48000Hz",
        "ffmpeg_used": False, "plaintext": True,
        "production_master_accepted": False,
    }
    if approve(dict(scope)) is not True:
        raise PermissionError("Director declined separate playable export approval")
    if cancelled():
        raise InterruptedError("Director cancelled playable preview")
    if verify_edited_film(assembly, project_id, edit_id,
                          edit_revision, source) != prior:
        raise RuntimeError("Committed source changed during author approval")
    paths = [source / "pictures" / frame["png_file"]
             for frame in manifest["pictures"]]
    staging = Path(tempfile.mkdtemp(prefix=".nvp-playable-", dir=source.parent))
    try:
        coded = _write_interleaved_avi(
            staging / "movie.avi", paths, source / "soundtrack.wav",
            manifest["picture_dimensions"],
            expected_sha=[frame["sha256"] for frame in manifest["pictures"]],
            cancelled=cancelled, progress=progress)
        with wave.open(str(source / "soundtrack.wav"), "rb") as wav:
            pcm = sha256()
            for i in range(0, AUDIO_SAMPLES, 4096):
                pcm.update(wav.readframes(min(4096, AUDIO_SAMPLES - i)))
        if pcm.hexdigest() != coded["pcm_sha256"]:
            raise RuntimeError("Playable audio differs from original edited PCM")
        checked = _verify_avi_structure(
            staging / "movie.avi", OUTPUT_FRAMES, coded["pcm_sha256"],
            manifest["picture_dimensions"])
        report = {"format": FORMAT, "status": "PLAYABLE_PREVIEW_VERIFIED",
                  "source_edit_sha256": prior["edit_sha256"],
                  "source_manifest_sha256": prior["manifest_sha256"],
                  "original_modified": False, "ffmpeg_used": False,
                  "production_master_accepted": False,
                  "lossy_picture": True, "audio_pcm_exact": True,
                  **coded, **checked}
        with (staging / "preview.json").open("x", encoding="utf8") as out:
            json.dump(report, out, sort_keys=True, separators=(",", ":"))
            out.flush()
            os.fsync(out.fileno())
        if cancelled():
            raise InterruptedError("Director cancelled before native film publish")
        if verify_edited_film(assembly, project_id, edit_id,
                              edit_revision, source) != prior:
            raise RuntimeError("Immutable original changed before publication")
        if target.exists() or target.is_symlink():
            raise FileExistsError("Playable film identity was claimed concurrently")
        os.rename(staging, target)
        return {**report, "directory": str(target),
                "movie_path": str(target / "movie.avi")}
    finally:
        if staging.exists():
            shutil.rmtree(staging)
