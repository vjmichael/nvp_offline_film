"""FILM02-03: verify genuine 720-frame Cycles images and native original PCM,
then write a synchronized 30s MJPEG+48k PCM director-review AVI (no FFmpeg).

Cannot be called with abstract placeholder images, missing native Blender
reopen evidence, a different FilmIndex project/edit or a fake soundtrack.
This is a screen review derivative, NOT a DCP, cinema master, real-time
installed playback acceptance or human approval.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct
import wave

from backend.nvp_film01_native_avi import (
    _chunk, _header, _encode_jpeg_verified, KEYFRAME,
    SAMPLES_PER_FRAME, IMAGE_WIDTH, IMAGE_HEIGHT,
)
from tools.nvp_film02_blender_handoff import FRAMES, FPS, validate_handoff
from tools.nvp_film02_blender_cycles_acceptance import sha_file
from tools.nvp_film02_cycles_collect import verify_three_shots
from tools.nvp_film02_original_pcm import (
    FORMAT as ORIGINAL_PCM_FORMAT, TOTAL_SAMPLES, write_original_pcm,
)

FORMAT = "nvp.film02.original_cycles_mjpeg_pcm30_screen_review.v1"
VIDEO_NAME = "FILM02_REAL_CYCLES_original_30sec_picture_and_sound.avi"
WAV_NAME = "FILM02_source_original_48k_mono_pcm16.wav"
PCM_PROOF = "FILM02_original_pcm_source_receipt.json"
REVIEW_PROOF = "FILM02_Cycles_original_AV_review_receipt.json"


def validate_audio_proof(plan, audio_path, audio_proof):
    """Read back all PCM samples, source time and original source proof."""
    if (audio_proof.get("format") != ORIGINAL_PCM_FORMAT or
            audio_proof.get("passed") is not True or
            audio_proof.get("source_project_id") != plan["source_project_id"] or
            audio_proof.get("source_manifest_sha256") != plan["manifest_sha256"] or
            audio_proof.get("source_edit_sha256") != plan["source_edit_sha256"] or
            audio_proof.get("source_cut_frames") != [240, 480] or
            audio_proof.get("beacon_cue_frames") != [624, 636] or
            audio_proof.get("sample_rate_hz") != 48000 or
            audio_proof.get("channels") != 1 or
            audio_proof.get("fps") != FPS or
            audio_proof.get("samples_per_picture_frame") != SAMPLES_PER_FRAME or
            audio_proof.get("picture_frame_count") != FRAMES or
            audio_proof.get("total_original_samples") != TOTAL_SAMPLES or
            audio_proof.get("original_source_take_sha256") !=
            [s["take_sha256"] for s in plan["shots"]] or
            audio_proof.get("source_audio_sha256") !=
            [s["sound_sha256"] for s in plan["shots"]] or
            audio_proof.get("source_original_takes_unchanged") is not True or
            audio_proof.get("original_sound_source_used") is not True or
            audio_proof.get("new_audio_composed_or_synthesized") is not False or
            audio_proof.get("soundtrack_mastered") is not False):
        raise PermissionError("Audio proof is not pinned to the real original film")
    wav = Path(audio_path)
    if wav.is_symlink() or not wav.is_file() or sha_file(wav) != audio_proof["pcm_wav_sha256"]:
        raise PermissionError("Original PCM source WAV was replaced")
    rows = audio_proof.get("original_frame_pcm_receipts")
    if type(rows) is not list or len(rows) != FRAMES:
        raise RuntimeError("Original WAV lacks all 720 frame-time proofs")
    chirp = []
    with wave.open(str(wav), "rb") as source:
        if (source.getnchannels() != 1 or source.getsampwidth() != 2 or
                source.getframerate() != 48000 or
                source.getnframes() != TOTAL_SAMPLES):
            raise RuntimeError("Original PCM not exactly 30s at 48kHz")
        for frame, proof in enumerate(rows):
            chunk = source.readframes(SAMPLES_PER_FRAME)
            original = plan["frames"][frame]
            if (proof.get("frame_zero") != frame or
                    proof.get("shot_number") != frame//240 or
                    proof.get("original_take_sha256") != original["source_take_sha256"] or
                    proof.get("source_film_tick") != original["source_film_tick"] or
                    proof.get("source_audio_event_ids") != original["source_sound_event_ids"] or
                    proof.get("sample_first") != frame*SAMPLES_PER_FRAME or
                    proof.get("sample_count") != SAMPLES_PER_FRAME or
                    proof.get("original_pcm16_sha256") != sha256(chunk).hexdigest()):
                raise PermissionError("Original source PCM changed at frame " + str(frame))
            if "BeaconSignalRestored" in proof["source_audio_event_ids"]:
                chirp.append(frame)
        if source.readframes(1):
            raise RuntimeError("Unexpected original PCM beyond the final picture")
    if chirp != list(range(624, 636)):
        raise RuntimeError("Original beacon cue changed relative to frozen Film Time")
    return {"original_samples": TOTAL_SAMPLES, "frame_count": FRAMES,
            "source_PCM_verified": True, "beacon_start_frame": 624}


def mux_verified_av(plan, images, shots, wav, wav_proof, output):
    """Write only real, independently accepted Cycles pixels plus exact PCM."""
    validate_audio_proof(plan, wav, wav_proof)
    if (type(images) is not list or len(images) != FRAMES or
            len({row.get("take_sha256") for row in images}) != 3 or
            [r.get("frame_zero") for r in images] != list(range(FRAMES)) or
            any(item.get("take_sha256") != plan["frames"][i]["source_take_sha256"]
                for i, item in enumerate(images))):
        raise PermissionError("Not exactly the original three verified Cycles shots")
    final = Path(output)
    if not final.is_absolute() or final.is_symlink() or final.exists():
        raise PermissionError("Screen review movie requires a fresh absolute output")
    if not final.parent.is_dir():
        raise ValueError("Trusted finished review output folder must already exist")
    staged = final.with_name(final.name + ".partial")
    if staged.exists() or staged.is_symlink():
        raise FileExistsError("Incomplete AVI scratch already exists")
    shots_root = Path(shots).resolve(strict=True)
    entries = []
    with wave.open(str(wav), "rb") as sound, staged.open("xb") as dest:
        dest.write(b"RIFF" + b"\0\0\0\0" + b"AVI ")
        dest.write(_header(FRAMES))
        movi_start = dest.tell()
        dest.write(b"LIST" + b"\0\0\0\0" + b"movi")
        for n, orig in enumerate(images):
            frame_path = shots_root/f"shot_{n//240}"/"frames"/f"frame_{n:04d}.png"
            if (frame_path.is_symlink() or not frame_path.is_file() or
                    sha_file(frame_path) != orig["png_sha256"]):
                raise PermissionError("Genuine Cycles frame changed during AV export")
            jpeg = _encode_jpeg_verified(frame_path.read_bytes())
            samples = sound.readframes(SAMPLES_PER_FRAME)
            if len(samples) != SAMPLES_PER_FRAME*2:
                raise RuntimeError("Original source PCM did not span each picture")
            for tag, payload in ((b"00dc", jpeg), (b"01wb", samples)):
                offset = dest.tell() - (movi_start + 8)
                dest.write(_chunk(tag, payload))
                entries.append((tag, KEYFRAME, offset, len(payload)))
        if sound.readframes(1):
            raise RuntimeError("Original PCM contains trailing source samples")
        movi_end = dest.tell()
        dest.seek(movi_start + 4)
        dest.write(struct.pack("<I", movi_end-movi_start-8))
        dest.seek(movi_end)
        dest.write(_chunk(b"idx1", b"".join(
            struct.pack("<4sIII", *entry) for entry in entries)))
        total = dest.tell()
        if total >= (1 << 32):
            raise RuntimeError("Review AVI exceeds bounded AVI1 RIFF limit")
        dest.seek(4)
        dest.write(struct.pack("<I", total-8))
        dest.flush()
    # Independently reread the actual RIFF header, index and all original
    # interleaved PCM; don't accept a merely existent file or asset receipt.
    with staged.open("rb") as reader, wave.open(str(wav), "rb") as audio:
        if reader.read(4) != b"RIFF":
            raise RuntimeError("Native review is not RIFF")
        data_size = struct.unpack("<I", reader.read(4))[0]
        if data_size != staged.stat().st_size - 8 or reader.read(4) != b"AVI ":
            raise RuntimeError("Malformed native movie length or AVI header")
        for n in range(FRAMES):
            for row_index, tag in ((n*2, b"00dc"), (n*2+1, b"01wb")):
                itag, _, offset, expected_size = entries[row_index]
                if itag != tag:
                    raise RuntimeError("Audio and picture interleaving lost")
                reader.seek(movi_start+8+offset)
                if reader.read(4) != tag:
                    raise RuntimeError("Review AVI index no longer addresses real media")
                length = struct.unpack("<I", reader.read(4))[0]
                if length != expected_size:
                    raise RuntimeError("AVI indexed sample size changed")
                payload = reader.read(length)
                if tag == b"01wb" and payload != audio.readframes(SAMPLES_PER_FRAME):
                    raise PermissionError("Screen review AVI PCM differs from original Take")
                if tag == b"00dc" and (
                        not payload.startswith(b"\xff\xd8") or
                        not payload.endswith(b"\xff\xd9")):
                    raise RuntimeError("Native review MJPEG frame invalid")
        reader.seek(movi_end)
        if reader.read(4) != b"idx1":
            raise RuntimeError("Review AVI original frame index missing")
        if struct.unpack("<I", reader.read(4))[0] != len(entries)*16:
            raise RuntimeError("Review AVI frame/audio index count incorrect")
        index_bytes = reader.read(len(entries)*16)
        if index_bytes != b"".join(struct.pack("<4sIII", *entry) for entry in entries):
            raise RuntimeError("Native review AVI index changed")
    if final.exists() or final.is_symlink():
        raise PermissionError("Film review output appeared during final verification")
    staged.rename(final)
    return {
        "format": FORMAT,
        "passed": True, "real_original_Cycles_frames": FRAMES,
        "duration_seconds": 30, "fps": FPS,
        "pixel_resolution": [IMAGE_WIDTH, IMAGE_HEIGHT],
        "picture_codec": "MJPEG", "source_audio_codec": "PCM_S16LE",
        "audio_rate_hz": 48000, "audio_channels": 1,
        "original_audio_sample_count": TOTAL_SAMPLES,
        "source_project_id": plan["source_project_id"],
        "source_manifest_sha256": plan["manifest_sha256"],
        "source_edit_sha256": plan["source_edit_sha256"],
        "source_cut_frames": [240, 480],
        "beacon_cue_frames": [624, 636],
        "source_original_WAV_sha256": wav_proof["pcm_wav_sha256"],
        "movie_sha256": sha_file(final), "movie_bytes": final.stat().st_size,
        "film_original_source_unchanged": True,
        "frames_derived_from_real_Blender_Cycles": True,
        "audio_derived_from_real_FilmIndex_pcm": True,
        "human_audio_visual_approval": False,
        "installed_Windows_playback_accepted": False,
        "color_managed_cinema_master": False,
        "theatrical_DCP_accepted": False,
    }


def create_original_av_review(source_root, handoff_path, shot_root, output_dir):
    root = Path(source_root).resolve(strict=True)
    handoff = Path(handoff_path).resolve(strict=True)
    dest = Path(output_dir)
    if (not dest.is_absolute() or dest.exists() or dest.is_symlink() or
            dest.resolve().is_relative_to(root) or
            root.is_relative_to(dest.resolve())):
        raise PermissionError("Screen review must use a separate fresh output folder")
    plan = json.loads(handoff.read_text("utf8"))
    report = json.loads((root/"original-source-report.json").read_text("utf8"))
    validate_handoff(plan, report)
    # Crucial: validate all actual Cycles native shot receipts FIRST.
    # Missing or counterfeit shots never result in a claimed 30-second movie.
    frames, shots = verify_three_shots(plan, report, shot_root)
    dest.mkdir(parents=True, exist_ok=False)
    audio_receipt = write_original_pcm(
        root, plan, report, dest/WAV_NAME, dest/PCM_PROOF)
    result = mux_verified_av(
        plan, frames, shot_root, dest/WAV_NAME,
        audio_receipt, dest/VIDEO_NAME)
    (dest/REVIEW_PROOF).write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", "utf8")
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", type=Path, required=True)
    cli.add_argument("--handoff", type=Path, required=True)
    cli.add_argument("--shots", type=Path, required=True)
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    result = create_original_av_review(
        args.source, args.handoff, args.shots, args.out.resolve())
    print(json.dumps({
        "real_playable_source_Cycles_AV": True,
        "movie_SHA256": result["movie_sha256"],
        "original_film_sha256": result["source_manifest_sha256"],
        "original_duration_seconds": 30,
        "director_creative_approval": False
    }, sort_keys=True))


if __name__ == "__main__":
    main()
