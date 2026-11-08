"""FILM02-03B: independently decode the REAL exported 30s MJPEG/PCM review.

This source/picture-bound verifier checks every AVI RIFF/index offset, JPEG
decoder output, original native Cycles PNG -> exact JPEG conversion, and each
interleaved 2,000-sample original PCM frame. It reports measurements for
later human director screening; it cannot approve lighting or acting.

The test-only lower-level scan can accept short synthetic fixture AVI files;
the FILM02 production entrypoint ALWAYS requires all 720 genuine Cycles PNGs,
their six independent Blender readbacks and 1,440,000 original PCM samples.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import struct
import wave

from PIL import Image, ImageChops, ImageDraw, ImageStat

from backend.nvp_film01_native_avi import _encode_jpeg_verified
from tools.nvp_film02_blender_handoff import FRAMES, FPS, validate_handoff
from tools.nvp_film02_blender_cycles_acceptance import sha_file
from tools.nvp_film02_cycles_collect import verify_three_shots
from tools.nvp_film02_original_av_review import (
    FORMAT as SOURCE_AV_FORMAT, VIDEO_NAME, WAV_NAME, PCM_PROOF, REVIEW_PROOF,
    validate_audio_proof,
)

FORMAT = "nvp.film02.independent_real_30s_avi_decoded_screen_review.v1"
MAX_RIFF_BYTES = 1024 * 1024 * 1024
WIDTH, HEIGHT = 640, 360
SAMPLES_PER_FRAME = 2000
SAMPLE_BYTES = SAMPLES_PER_FRAME * 2
DIRECTOR_FRAMES = (0, 120, 239, 240, 360, 479, 480, 600, 623, 624, 635, 636, 719)


def _safe_file(path):
    file = Path(path)
    if not file.is_absolute() or file.is_symlink() or not file.is_file():
        raise PermissionError("An existing absolute non-symlink native review file is required")
    return file


def _children(reader, first, last):
    """Bounded RIFF child offsets without trusting nested LIST lengths."""
    result = []
    cursor = first
    while cursor < last:
        reader.seek(cursor)
        header = reader.read(8)
        if len(header) != 8:
            raise RuntimeError("Truncated AVI stream header")
        tag, count = struct.unpack("<4sI", header)
        next_position = cursor + 8 + count + (count & 1)
        if count < 1 or next_position > last:
            raise RuntimeError("AVI stream header exceeds its parent LIST")
        result.append((tag, cursor, count))
        cursor = next_position
    if cursor != last:
        raise RuntimeError("AVI stream LIST contains unindexed bytes")
    return result


def _validate_native_stream_headers(reader, first, last, expected_frames):
    """Verify real 24fps / 640x360 MJPEG and 48kHz PCM playback metadata."""
    chunks = _children(reader, first, last)
    avih = [(position, size) for tag, position, size in chunks if tag == b"avih"]
    streams = [(position, size) for tag, position, size in chunks if tag == b"LIST"]
    if len(avih) != 1 or avih[0][1] != 56 or len(streams) != 2:
        raise RuntimeError("Expected one native AVI playback clock and two streams")
    reader.seek(avih[0][0] + 8)
    main = struct.unpack("<IIIIIIIIII4I", reader.read(56))
    if (main[0] != round(1000000/FPS) or
            main[4] != expected_frames or main[6] != 2 or
            main[8] != WIDTH or main[9] != HEIGHT):
        raise RuntimeError("AVI header declares wrong film rate/size/length")
    seen = set()
    for position, size in streams:
        reader.seek(position + 8)
        if size < 4 or reader.read(4) != b"strl":
            raise RuntimeError("Unexpected AVI stream list type")
        entries = _children(reader, position+12, position+8+size+(size&1))
        strh = [(at, n) for tag, at, n in entries if tag == b"strh"]
        strf = [(at, n) for tag, at, n in entries if tag == b"strf"]
        if len(strh) != 1 or len(strf) != 1 or strh[0][1] != 56:
            raise RuntimeError("Incomplete AVI native video/audio stream")
        reader.seek(strh[0][0]+8)
        h = struct.unpack("<4s4sIHHIIIIIIIIhhhh", reader.read(56))
        reader.seek(strf[0][0]+8)
        if h[0] == b"vids":
            if (h[1] != b"MJPG" or h[6:10] != (1,FPS,0,expected_frames)
                    or strf[0][1] != 40):
                raise RuntimeError("AVI original MJPEG stream has wrong playback metadata")
            img = struct.unpack("<IiiHH4sIiiII", reader.read(40))
            if img[:6] != (40,WIDTH,HEIGHT,1,24,b"MJPG"):
                raise RuntimeError("AVI actual MJPEG image format mismatches source")
        elif h[0] == b"auds":
            if (h[6:10] != (1,48000,0,expected_frames*SAMPLES_PER_FRAME)
                    or h[12] != 2 or strf[0][1] != 16):
                raise RuntimeError("AVI original audio timing changed")
            audio = struct.unpack("<HHIIHH", reader.read(16))
            if audio != (1,1,48000,96000,2,16):
                raise RuntimeError("AVI PCM stream format changed")
        else:
            raise RuntimeError("Unrecognized review stream in original film")
        if h[0] in seen:
            raise RuntimeError("Duplicate video/audio stream")
        seen.add(h[0])
    if seen != {b"vids", b"auds"}:
        raise RuntimeError("Original playable AVI must contain picture and sound")


def _parse_riff(avi, expected_frames):
    """Parse top-level RIFF/LIST/movi and full idx1 independently of muxer."""
    size = avi.stat().st_size
    if not 200 < size < MAX_RIFF_BYTES:
        raise RuntimeError("Native review AVI size is unreasonable")
    with avi.open("rb") as inp:
        header = inp.read(12)
        if (header[:4] != b"RIFF" or header[8:] != b"AVI " or
                len(header) != 12 or struct.unpack("<I", header[4:8])[0] != size-8):
            raise RuntimeError("Native AVI RIFF length/container inconsistent")
        movi = None
        index = None
        playback_header = False
        position = 12
        while position < size:
            inp.seek(position)
            head = inp.read(8)
            if len(head) != 8:
                raise RuntimeError("Truncated top-level AVI chunk")
            tag, length = struct.unpack("<4sI", head)
            end = position + 8 + length + (length & 1)
            if end > size or length < 1:
                raise RuntimeError("Corrupt bounded AVI chunk length")
            if tag == b"LIST":
                inp.seek(position+8)
                list_kind = inp.read(4)
                if list_kind == b"hdrl":
                    if playback_header:
                        raise RuntimeError("Repeated native AVI playback header")
                    _validate_native_stream_headers(inp, position+12, end, expected_frames)
                    playback_header = True
                if list_kind == b"movi":
                    if movi is not None:
                        raise RuntimeError("More than one original picture/audio stream")
                    movi = (position, end)
            elif tag == b"idx1":
                if index is not None or length != expected_frames * 2 * 16:
                    raise RuntimeError("Incomplete or duplicated original AVI index")
                inp.seek(position+8)
                index = inp.read(length)
            position = end
        if movi is None or index is None or not playback_header:
            raise RuntimeError("Missing original AVI playback header, media or index")
        return movi, [
            struct.unpack_from("<4sIII", index, i * 16)
            for i in range(expected_frames * 2)]


def scan_actual_movie(avi_path, wav_path, *, expected_frames=FRAMES,
                      source_pictures=None, source_rows=None,
                      director_frames=DIRECTOR_FRAMES):
    """Independent RIFF/decoder/audio scan, with optional exact Cycles binding.

    For production, caller must pass all 720 trusted source_rows and picture
    paths from verify_three_shots; no optional shortcut in the public CLI.
    """
    if (type(expected_frames) is not int or not 1 <= expected_frames <= FRAMES or
            type(director_frames) not in (tuple, list) or
            any(type(n) is not int or not 0 <= n < expected_frames
                for n in director_frames)):
        raise ValueError("Invalid bounded AVI readback scope")
    avi = _safe_file(avi_path)
    wav = _safe_file(wav_path)
    if source_rows is not None and (
            type(source_rows) is not list or len(source_rows) != expected_frames or
            source_pictures is None):
        raise PermissionError("Picture source proof must be complete")
    movi, entries = _parse_riff(avi, expected_frames)
    start, end = movi
    cursor = start + 12  # the 'movi' list type precedes its first child
    rows = []
    decoded_contact = {}
    previous_small = None
    with avi.open("rb") as video, wave.open(str(wav), "rb") as sound:
        if (sound.getnchannels() != 1 or sound.getsampwidth() != 2 or
                sound.getframerate() != 48000 or
                sound.getnframes() != expected_frames * SAMPLES_PER_FRAME):
            raise RuntimeError("Original WAV does not match AVI Film Time")
        for n in range(expected_frames):
            out = {"frame_zero": n, "film_time_seconds": round(n / FPS, 6)}
            for part in range(2):
                tag, flags, offset, length = entries[n*2+part]
                expected_tag = b"00dc" if part == 0 else b"01wb"
                if (tag != expected_tag or
                        start + 8 + offset != cursor or
                        not 0 < length < 1024*1024 or
                        cursor + 8 + length + (length&1) > end):
                    raise RuntimeError("AVI picture/PCM index lost source frame order")
                video.seek(cursor)
                header = video.read(8)
                if len(header) != 8 or header[:4] != tag or (
                        struct.unpack("<I", header[4:])[0] != length):
                    raise RuntimeError("AVI indexed chunk was modified or truncated")
                payload = video.read(length)
                if len(payload) != length:
                    raise RuntimeError("Truncated original frame inside AVI")
                cursor += 8 + length + (length & 1)
                if part == 0:
                    if not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
                        raise RuntimeError("Native MJPEG picture frame is not JPEG")
                    with Image.open(BytesIO(payload)) as decoder:
                        decoder.load()
                        if decoder.format != "JPEG" or decoder.size != (WIDTH, HEIGHT):
                            raise RuntimeError("Real MJPEG picture not independently decodable")
                        image = decoder.convert("RGB")
                    if source_rows is not None:
                        original = source_rows[n]
                        pic = Path(source_pictures) / f"shot_{n//240}"/"frames"/f"frame_{n:04d}.png"
                        if (pic.is_symlink() or not pic.is_file() or
                                original.get("frame_zero") != n or
                                original.get("png_sha256") != sha_file(pic) or
                                _encode_jpeg_verified(pic.read_bytes()) != payload):
                            raise PermissionError("Review movie pixel differs from real Cycles PNG")
                        out["original_Cycles_PNG_sha256"] = original["png_sha256"]
                    small = image.convert("L").resize((160, 90))
                    hist = small.histogram()
                    out["mean_luma_8bit"] = round(ImageStat.Stat(small).mean[0], 3)
                    out["black_pixel_fraction"] = round(sum(hist[:8])/14400, 5)
                    out["highlight_pixel_fraction"] = round(sum(hist[247:])/14400, 5)
                    out["difference_from_previous_mean_8bit"] = (
                        None if previous_small is None else
                        round(ImageStat.Stat(ImageChops.difference(
                            previous_small, small)).mean[0], 3))
                    previous_small = small
                    out["actual_MJPEG_sha256"] = sha256(payload).hexdigest()
                    if n in director_frames:
                        decoded_contact[n] = image
                else:
                    if length != SAMPLE_BYTES or payload != sound.readframes(SAMPLES_PER_FRAME):
                        raise PermissionError("AVI sound differs from original 48kHz PCM")
                    samples = struct.iter_unpack("<h", payload)
                    sq = 0
                    peak = 0
                    for (value,) in samples:
                        sq += value*value
                        peak = max(peak, abs(value))
                    out["audio_rms_dbfs"] = (
                        None if sq == 0 else round(
                            20*math.log10(math.sqrt(sq/SAMPLES_PER_FRAME)/32768), 3))
                    out["audio_peak_dbfs"] = (
                        None if peak == 0 else round(20*math.log10(peak/32768), 3))
                    out["original_PCM16_sha256"] = sha256(payload).hexdigest()
            rows.append(out)
        if cursor != end:
            raise RuntimeError("Unindexed picture/audio bytes remain in original AVI")
        if sound.readframes(1):
            raise RuntimeError("Original source WAV exceeds picture duration")
    return {"frames": rows, "decoded_contact_frames": decoded_contact,
            "movie_sha256": sha_file(avi),
            "wav_sha256": sha_file(wav),
            "frame_count": len(rows)}


def audit_original_film(shot_root, source_root, handoff_path, review_dir,
                        out_dir):
    """Production-only: refuses any missing native original film evidence."""
    shots = Path(shot_root).resolve(strict=True)
    root = Path(source_root).resolve(strict=True)
    handoff = _safe_file(handoff_path)
    review = Path(review_dir).resolve(strict=True)
    out = Path(out_dir)
    if not out.is_absolute() or out.exists() or out.is_symlink():
        raise PermissionError("Independent director audit requires a fresh path")
    plan = json.loads(handoff.read_text("utf8"))
    source_report = json.loads((root/"original-source-report.json").read_text("utf8"))
    validate_handoff(plan, source_report)
    expected_rows, native_shots = verify_three_shots(plan, source_report, shots)
    original_sound = json.loads(_safe_file(review/PCM_PROOF).read_text("utf8"))
    validate_audio_proof(plan, review/WAV_NAME, original_sound)
    movie_receipt = json.loads(_safe_file(review/REVIEW_PROOF).read_text("utf8"))
    if (movie_receipt.get("format") != SOURCE_AV_FORMAT or
            movie_receipt.get("passed") is not True or
            movie_receipt.get("source_manifest_sha256") != plan["manifest_sha256"] or
            movie_receipt.get("source_edit_sha256") != plan["source_edit_sha256"] or
            movie_receipt.get("source_cut_frames") != [240,480] or
            movie_receipt.get("beacon_cue_frames") != [624,636] or
            movie_receipt.get("real_original_Cycles_frames") != FRAMES or
            movie_receipt.get("human_audio_visual_approval") is not False or
            movie_receipt.get("installed_Windows_playback_accepted") is not False or
            movie_receipt.get("theatrical_DCP_accepted") is not False):
        raise PermissionError("Not a verified unapproved original Cycles AVI review")
    scanned = scan_actual_movie(
        review/VIDEO_NAME, review/WAV_NAME,
        source_pictures=shots, source_rows=expected_rows)
    if (scanned["frame_count"] != FRAMES or
            scanned["movie_sha256"] != movie_receipt["movie_sha256"] or
            scanned["wav_sha256"] != movie_receipt["source_original_WAV_sha256"] or
            scanned["wav_sha256"] != original_sound["pcm_wav_sha256"]):
        raise RuntimeError("Independent decoded movie changed since source approval")
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    contact = Image.new("RGB", (3*WIDTH+4*12, 5*390+6*12), (18,20,25))
    pen = ImageDraw.Draw(contact)
    for idx, n in enumerate(DIRECTOR_FRAMES):
        image = scanned["decoded_contact_frames"][n]
        x = 12 + (idx % 3) * (WIDTH+12)
        y = 12 + (idx // 3) * 390
        contact.paste(image, (x,y))
        pen.text((x,y+365), f"AVI DECODED {n/FPS:.2f}s | frame {n} | shot {n//240}",
                 fill=(236,237,239))
    image_path = out/"FILM02_REAL_CYCLES_actual_AVI_decoded_director_contact.png"
    contact.save(image_path,"PNG")
    full = scanned["frames"]
    receipt = {
        "format": FORMAT, "passed": True,
        "film_duration_seconds": 30, "fps": FPS,
        "real_source_project_id": plan["source_project_id"],
        "source_manifest_sha256": plan["manifest_sha256"],
        "source_edit_sha256": plan["source_edit_sha256"],
        "verified_real_blender_Cycles_shots": len(native_shots),
        "verified_actual_native_Cycles_frames": scanned["frame_count"],
        "source_hard_cut_frames": [240,480],
        "beacon_source_audio_frames": [624,636],
        "actual_decoded_movie_sha256": scanned["movie_sha256"],
        "actual_original_PCM_WAV_sha256": scanned["wav_sha256"],
        "avi_picture_codec": "MJPEG", "avi_audio_codec": "PCM_S16LE",
        "sample_rate_hz": 48000, "original_pcm_samples": 1440000,
        "fully_decoded_all_MJPEG_and_original_PCM_frames": True,
        "all_720_decoded_frames_equal_individual_native_Cycles_PNG_transcodes": True,
        "director_contact_png_sha256": sha_file(image_path),
        "observed_frame_metrics": full,
        "no_fake_or_missing_frames_allowed": True,
        "human_director_viewed_or_approved": False,
        "installed_player_real_time_24fps_acceptance": False,
        "calibrated_color_master_or_DCP": False,
    }
    (out/"FILM02_REAL_CYCLES_independent_AVI_audio_picture_audit.json").write_text(
        json.dumps(receipt,sort_keys=True,indent=2)+"\n",encoding="utf8")
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--handoff",type=Path,required=True)
    parser.add_argument("--shots",type=Path,required=True)
    parser.add_argument("--review",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    opt=parser.parse_args()
    result=audit_original_film(
        opt.shots,opt.source,opt.handoff,opt.review,opt.out.resolve())
    print(json.dumps({
        "full_native_Cycles_movie_picture_and_sound_decode":"PASS",
        "frames":result["verified_actual_native_Cycles_frames"],
        "original_source_sha256":result["source_manifest_sha256"],
        "human_visual_approval":"OPEN",
        "installed_real_time_playback":"OPEN",
    },sort_keys=True))


if __name__=="__main__":
    main()
