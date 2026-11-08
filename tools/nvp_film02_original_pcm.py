"""FILM02-03: original, frame-exact 48 kHz PCM from immutable FilmIndex Takes.

This file creates no new synthetic sound. It uses the source-time event/mixer
contract already used by NVP's first-party editorial audio preview, without
re-rendering or replacing original Blender/Cycles picture. Each 24-fps frame
is 2,000 ORIGINAL PCM16 mono samples. Silent frames are never fabricated
to conceal a failed source lookup. No FFmpeg, DCP or master claimed.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import wave

from backend.nvp_data_av_source import SAMPLE_RATE, RecordedSoundSources
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_wo6_07e_source_review import _window_pcm
from tools.nvp_film02_blender_handoff import (
    FRAMES, FPS, SHOT_FRAMES, CHIRP, validate_handoff, build_handoff,
)

FORMAT = "nvp.film02.original_pcm16_source_review.v1"
SAMPLES_PER_FRAME = SAMPLE_RATE // FPS
TOTAL_SAMPLES = FRAMES * SAMPLES_PER_FRAME
FRAME_TICKS = TICKS_PER_SECOND // FPS
MAX_EVENTS = 32


def _hash(path):
    h = sha256()
    with path.open("rb") as reader:
        for block in iter(lambda: reader.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_original_pcm_frame(index, plan, frame_zero, *, verify_timeline=False):
    """One original editor-selected 2,000-sample frame, no invented sound."""
    if not isinstance(index, FilmIndex):
        raise TypeError("Original audio requires a genuine FilmIndex")
    if type(frame_zero) is not int or not 0 <= frame_zero < FRAMES:
        raise ValueError("Film Time must be an original frame in 0..719")
    shot_no = frame_zero // SHOT_FRAMES
    shot = plan["shots"][shot_no]
    frame = plan["frames"][frame_zero]
    if (frame["output_frame_zero"] != frame_zero or
            frame["source_take_sha256"] != shot["take_sha256"] or
            frame["source_film_tick"] != str((frame_zero % SHOT_FRAMES) * FRAME_TICKS)):
        raise PermissionError("Original picture and source PCM editorial time disagree")
    pid = plan["source_project_id"]
    take = index.read_revision(pid, shot["take_id"], 1)
    if (take["document_sha256"] != shot["take_sha256"] or
            take["data"]["scene_document_sha256"] != shot["scene_sha256"] or
            take["data"]["timeline_document_sha256"] != shot["timeline_sha256"]):
        raise PermissionError("Original frozen soundtrack Take revision changed")
    timeline = TemporalLedger(index)
    timeline_id = take["data"]["timeline_id"]
    timeline_rev = take["data"]["timeline_revision"]
    if verify_timeline:
        proof = timeline.verify(pid, timeline_id, timeline_rev)
        if proof is None:
            raise RuntimeError("Cannot verify original audio ledger")
    source_tick = int(frame["source_film_tick"])
    events = timeline.events_in(
        pid, timeline_id, timeline_rev,
        start_tick=source_tick, end_tick=source_tick + FRAME_TICKS,
        limit=MAX_EVENTS + 1)["events"]
    if len(events) > MAX_EVENTS:
        raise RuntimeError("Source event window exceeds bounded PCM mixer")
    sound_ids = sorted(e["event_id"] for e in events
                       if e["event_kind"] in ("sound", "dialogue", "music"))
    if sound_ids != frame["source_sound_event_ids"]:
        raise PermissionError("Original source event identities differ at Film Time")
    original_wav, tracks, omissions = _window_pcm(
        index, pid, events, source_tick, SAMPLES_PER_FRAME)
    if original_wav is None or omissions:
        raise RuntimeError("Original recorded source audio missing or exhausted")
    accepted = sorted(row["event_id"] for row in tracks)
    if accepted != sound_ids or not accepted:
        raise RuntimeError("Some original recorded source audio could not be mixed")
    # Every original event's source SHA is verified by _window_pcm, and
    # 07E's original audio reader never writes a changed source signal.
    with wave.open(BytesIO(original_wav), "rb") as audio:
        if (audio.getnchannels() != 1 or audio.getsampwidth() != 2 or
                audio.getframerate() != SAMPLE_RATE or
                audio.getnframes() != SAMPLES_PER_FRAME):
            raise RuntimeError("An original 24fps audio frame is not exact PCM16")
        samples = audio.readframes(SAMPLES_PER_FRAME)
    if len(samples) != SAMPLES_PER_FRAME * 2:
        raise RuntimeError("Truncated source PCM at editorial frame")
    return {"frame_zero": frame_zero, "shot_number": shot_no,
            "original_take_sha256": shot["take_sha256"],
            "source_film_tick": frame["source_film_tick"],
            "source_audio_event_ids": sound_ids,
            "original_pcm16_sha256": sha256(samples).hexdigest(),
            "sample_first": frame_zero * SAMPLES_PER_FRAME,
            "sample_count": SAMPLES_PER_FRAME,
            "pcm": samples}


def _destination(source_root, output):
    source = Path(source_root).resolve(strict=True)
    target = Path(output)
    if (not target.is_absolute() or target.exists() or target.is_symlink() or
            not target.parent.is_dir() or
            target.resolve().is_relative_to(source) or
            source.is_relative_to(target.resolve()) or
            target.with_name(target.name + ".partial").exists()):
        raise PermissionError("Fresh separate output cannot overwrite original source")
    return target


def write_original_pcm(source_root, plan, report, wav_path, receipt_path):
    """Commit a SHA-verified full original 30s WAV after exact 720-frame readback."""
    if not isinstance(plan, dict) or not isinstance(report, dict):
        raise TypeError("A frozen original FilmIndex source and handoff are required")
    validate_handoff(plan, report)
    if build_handoff(source_root) != plan:
        raise PermissionError("Original FilmIndex source no longer matches handoff")
    output = _destination(source_root, wav_path)
    receipt_file = _destination(source_root, receipt_path)
    if receipt_file == output:
        raise PermissionError("Sound data and receipt cannot share one file")
    studio = Studio(Path(source_root) / "short.sqlite3")
    index = FilmIndex(studio)
    tmp = output.with_name(output.name + ".partial")
    rows = []
    chirp_frames = []
    with tmp.open("xb") as output_file:
        with wave.open(output_file, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(SAMPLE_RATE)
            for n in range(FRAMES):
                sample = read_original_pcm_frame(
                    index, plan, n, verify_timeline=(n % SHOT_FRAMES == 0))
                audio.writeframesraw(sample["pcm"])
                rows.append({
                    key: value for key, value in sample.items() if key != "pcm"})
                if CHIRP in sample["source_audio_event_ids"]:
                    chirp_frames.append(n)
    if chirp_frames != list(range(624, 636)):
        raise RuntimeError("Original 26-second beacon cue is missing from PCM")
    with wave.open(str(tmp), "rb") as reader:
        if (reader.getnchannels() != 1 or reader.getsampwidth() != 2 or
                reader.getframerate() != SAMPLE_RATE or
                reader.getnframes() != TOTAL_SAMPLES):
            raise RuntimeError("Original 30-second WAV does not match exact 24fps")
    if len(rows) != FRAMES or rows[-1]["sample_first"] != (FRAMES-1)*SAMPLES_PER_FRAME:
        raise RuntimeError("Original source sound did not cover all 720 pictures")
    # No file is accepted without its accompanying SHA-bound source proof.
    proof = {
        "format": FORMAT, "passed": True,
        "source_project_id": plan["source_project_id"],
        "source_manifest_sha256": plan["manifest_sha256"],
        "source_edit_sha256": plan["source_edit_sha256"],
        "original_source_take_sha256": [s["take_sha256"] for s in plan["shots"]],
        "source_audio_sha256": [s["sound_sha256"] for s in plan["shots"]],
        "source_cut_frames": [240, 480],
        "beacon_cue_frames": [624, 636],
        "sample_rate_hz": SAMPLE_RATE, "channels": 1,
        "sample_format": "PCM_S16LE",
        "fps": FPS, "samples_per_picture_frame": SAMPLES_PER_FRAME,
        "picture_frame_count": FRAMES, "total_original_samples": TOTAL_SAMPLES,
        "pcm_wav_sha256": _hash(tmp),
        "original_frame_pcm_receipts": rows,
        "source_original_takes_unchanged": True,
        "original_sound_source_used": True,
        "new_audio_composed_or_synthesized": False,
        "soundtrack_mastered": False,
        "real_creator_approval": False,
        "cinema_release_accepted": False,
    }
    # The receipt must exist before the WAV is made visible as a final file.
    partial_receipt = receipt_file.with_name(receipt_file.name + ".partial")
    with partial_receipt.open("x", encoding="utf8") as writer:
        json.dump(proof, writer, sort_keys=True, indent=2, allow_nan=False)
        writer.write("\n")
    if output.exists() or receipt_file.exists():
        raise FileExistsError("Original review targets changed during source read")
    tmp.rename(output)
    partial_receipt.rename(receipt_file)
    return proof
