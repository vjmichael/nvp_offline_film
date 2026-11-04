"""AUDIO-01B: deterministic, sample-addressed dialogue editorial preview.

An approved native host must authorize paths and execution. This worker-side
primitive does not create dialogue, approve editorial decisions, or master audio.
Audio clips may lead/lag B13 picture cuts and overlap for J/L edits or fades.
"""
from __future__ import annotations

from array import array
import hashlib
import json
import os
from pathlib import Path
import struct
import wave

from backend.nvp_audio01_picture_follow import (
    CHANNELS, RATE, SAMPLE_WIDTH, SAMPLES_PER_FRAME, _sha_file, _safe_new,
    _wav, source_mapping,
)
from backend.nvp_film_index import _id

FORMAT = "nvp.audio.dialogue_edit_pcm48.v1"
MAX_FRAMES = 480
MAX_CLIPS = 128
MAX_OVERLAP = 8


def _strict_int(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Invalid " + name)
    return value


def validate_audio_plan(plan, source_frames, output_frames):
    """Exact integer-sample plan. No floating-point timing or unbounded work."""
    _strict_int(source_frames, 1, MAX_FRAMES, "source frames")
    _strict_int(output_frames, 1, MAX_FRAMES, "output frames")
    if type(plan) is not dict or set(plan) != {"clips"} or type(plan["clips"]) is not list:
        raise ValueError("Expected a bounded audio plan with clips")
    if not 1 <= len(plan["clips"]) <= MAX_CLIPS:
        raise ValueError("Audio plan requires 1–128 clips")
    output_samples = output_frames * SAMPLES_PER_FRAME
    source_samples = source_frames * SAMPLES_PER_FRAME
    normalized = []
    events = []
    for clip in plan["clips"]:
        required = {"out_start", "out_end", "source_start", "fade_in", "fade_out", "gain_milli"}
        if type(clip) is not dict or set(clip) != required:
            raise ValueError("Audio clips require exact sample addressing and fade fields")
        start = _strict_int(clip["out_start"], 0, output_samples - 1, "clip start")
        end = _strict_int(clip["out_end"], start + 1, output_samples, "clip end")
        length = end - start
        source_start = _strict_int(clip["source_start"], 0, source_samples - length,
                                   "source sample range")
        fade_in = _strict_int(clip["fade_in"], 0, length, "fade in")
        fade_out = _strict_int(clip["fade_out"], 0, length, "fade out")
        gain = _strict_int(clip["gain_milli"], 0, 1000, "gain")
        normalized.append(dict(clip))
        events.extend([(start, 1), (end, -1)])
    active = 0
    for _, delta in sorted(events, key=lambda x: (x[0], x[1])):
        active += delta
        if active > MAX_OVERLAP:
            raise ValueError("Audio plan has too many simultaneous clips")
    return normalized


def _s16(value):
    return max(-32768, min(32767, value))


def _samples(path):
    count = _wav(path)
    with wave.open(str(path), "rb") as src:
        raw = src.readframes(count)
    if len(raw) != count * CHANNELS * SAMPLE_WIDTH:
        raise RuntimeError("Incomplete source audio")
    return count, array("h", struct.unpack("<" + "h" * (count * CHANNELS), raw))


def render_audio_samples(source_path, plan, source_frames, output_frames):
    """Returns deterministic 16-bit PCM bytes at exactly 48kHz stereo.

    Two fade envelopes multiply for short overlapping fades. Integer rounding,
    saturation, and mixing policy are stable across CPU architectures.
    """
    clips = validate_audio_plan(plan, source_frames, output_frames)
    count, src = _samples(source_path)
    if count != source_frames * SAMPLES_PER_FRAME:
        raise RuntimeError("Original dialogue WAV does not match source picture")
    total = output_frames * SAMPLES_PER_FRAME
    left = [0] * total
    right = [0] * total
    for clip in clips:
        start, end, source_start = (clip["out_start"], clip["out_end"],
                                    clip["source_start"])
        duration = end - start
        for offset in range(duration):
            # 0 at the first sample of a fade-in, 1000 after it;
            # 0 at the last sample of a fade-out, 1000 before it.
            fade = 1000
            fi, fo = clip["fade_in"], clip["fade_out"]
            if fi:
                fade = min(fade, min(1000, offset * 1000 // fi))
            if fo:
                fade = min(fade, min(1000, (duration - 1 - offset) * 1000 // fo))
            weight = clip["gain_milli"] * fade  # millionth-scale
            pos = start + offset
            srcpos = (source_start + offset) * 2
            left[pos] += int(src[srcpos]) * weight
            right[pos] += int(src[srcpos + 1]) * weight
    out = bytearray(total * CHANNELS * SAMPLE_WIDTH)
    for n in range(total):
        # Explicit symmetric nearest-integer rounding before saturation.
        def round_div(v):
            return (v + 500000) // 1000000 if v >= 0 else -((-v + 500000) // 1000000)
        struct.pack_into("<hh", out, n * 4,
                         _s16(round_div(left[n])), _s16(round_div(right[n])))
    return bytes(out)


def _manifest(capture, project_id, edit_id, revision, plan, source_sha, output_sha,
              source_frames, output_frames):
    edit = capture.index.read_revision(project_id, edit_id, revision)
    if edit["kind"] != "edit":
        raise RuntimeError("Audio timing must bind an actual FilmIndex edit")
    delivery_id = edit["data"]["source_delivery_id"]
    delivery = capture.index.read_revision(project_id, delivery_id, 1)
    if edit["data"]["source_delivery_sha256"] != delivery["document_sha256"]:
        raise RuntimeError("Audio edit lost original picture lineage")
    mapping = source_mapping(edit["data"], delivery["data"])
    if len(mapping) != output_frames or delivery["data"]["frame_count"] != source_frames:
        raise RuntimeError("Audio edit duration differs from frozen picture edit")
    return {
        "format": FORMAT,
        "status": "unapproved_dialogue_edit_preview",
        "project_id": project_id,
        "edit_id": edit_id, "edit_revision": revision,
        "edit_sha256": edit["document_sha256"],
        "source_delivery_id": delivery_id,
        "source_delivery_sha256": delivery["document_sha256"],
        "source_take_id": edit["data"]["source_take_id"],
        "source_take_sha256": edit["data"]["source_take_sha256"],
        "source_wav_sha256": source_sha, "output_wav_sha256": output_sha,
        "output_wav": "dialogue_edit_preview.wav",
        "source_frames": source_frames, "output_frames": output_frames,
        "sample_rate": RATE, "channels": CHANNELS, "sample_width": SAMPLE_WIDTH,
        "total_samples_per_channel": output_frames * SAMPLES_PER_FRAME,
        "clips": plan["clips"], "frame_map": [
            {"edit_frame": n, "source_frame": s} for n, s in mapping
        ],
        "picture_locked": False, "director_approved": False,
        "final_mix": False, "final_master": False,
    }


def _edges(data):
    return [{"object_id": data["edit_id"], "revision": data["edit_revision"], "role": "timeline"},
            {"object_id": data["source_delivery_id"], "revision": 1, "role": "presentation"},
            {"object_id": data["source_take_id"], "revision": 1, "role": "source_take"}]


def create_dialogue_preview(capture, project_id, edit_id, revision, input_wav,
                            output_dir, audio_id, plan):
    """Produce real sample-edited WAV and immutable FilmIndex revision."""
    _id(audio_id, "dialogue preview identity")
    if type(revision) is not int or revision < 1:
        raise ValueError("Exact editorial revision required")
    destination = Path(output_dir)
    _safe_new(destination)
    try:
        capture.index.read_revision(project_id, audio_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Existing audio identity cannot be overwritten")
    edit = capture.index.read_revision(project_id, edit_id, revision)
    delivery = capture.index.read_revision(project_id, edit["data"]["source_delivery_id"], 1)
    source_frames = delivery["data"]["frame_count"]
    output_frames = edit["data"]["editorial_map"]["frame_count"]
    pcm = render_audio_samples(input_wav, plan, source_frames, output_frames)
    source_sha = _sha_file(input_wav)
    if capture.index.put_media_file(project_id, input_wav, "audio/wav")["sha256"] != source_sha:
        raise RuntimeError("Original WAV changed while indexing")
    destination.mkdir(mode=0o700)
    wave_path = destination / "dialogue_edit_preview.wav"
    with wave_path.open("xb") as stream:
        with wave.open(stream, "wb") as out:
            out.setnchannels(CHANNELS)
            out.setsampwidth(SAMPLE_WIDTH)
            out.setframerate(RATE)
            out.writeframes(pcm)
    output_sha = _sha_file(wave_path)
    if capture.index.put_media_file(project_id, wave_path, "audio/wav")["sha256"] != output_sha:
        raise RuntimeError("Edited WAV changed while indexing")
    data = _manifest(capture, project_id, edit_id, revision, plan, source_sha,
                     output_sha, source_frames, output_frames)
    path = destination / "dialogue_edit_manifest.json"
    with path.open("xb") as output:
        output.write(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf8"))
        output.flush()
        os.fsync(output.fileno())
    rec = capture.index.register_revision(project_id, audio_id, "audio", data,
                                          expected_revision=0, dependencies=_edges(data))
    return {"status": "UNAPPROVED_AUDIO_EDITORIAL_PREVIEW", "audio_id": audio_id,
            "revision_sha256": rec["document_sha256"],
            "samples_per_channel": data["total_samples_per_channel"],
            "source_unchanged": True, "final_mix": False}


def verify_dialogue_preview(capture, project_id, audio_id, output_dir):
    rec = capture.index.read_revision(project_id, audio_id, 1)
    data = rec["data"]
    if (rec["kind"] != "audio" or data.get("format") != FORMAT or
        data.get("status") != "unapproved_dialogue_edit_preview" or
        data.get("final_mix") is not False or
        data.get("final_master") is not False or
        data.get("director_approved") is not False or
        data.get("picture_locked") is not False or
        data.get("project_id") != project_id):
        raise RuntimeError("Dialogue preview claimed final or mismatched provenance")
    if rec["dependencies"] != sorted(_edges(data), key=lambda r: (r["object_id"], r["revision"], r["role"])):
        raise RuntimeError("Audio timeline dependency mismatch")
    manifest = _manifest(capture, project_id, data["edit_id"], data["edit_revision"],
                         {"clips": data["clips"]}, data["source_wav_sha256"],
                         data["output_wav_sha256"], data["source_frames"], data["output_frames"])
    if manifest != data:
        raise RuntimeError("Dialogue edit no longer agrees with frozen picture")
    parent = Path(output_dir)
    if parent.is_symlink() or not parent.is_dir():
        raise RuntimeError("Dialogue preview destination is unsafe")
    manifest_path = parent / "dialogue_edit_manifest.json"
    if manifest_path.is_symlink() or json.loads(manifest_path.read_text("utf8")) != data:
        raise RuntimeError("Dialogue edit manifest was modified")
    wav_path = parent / data["output_wav"]
    if wav_path.is_symlink() or _sha_file(wav_path) != data["output_wav_sha256"]:
        raise RuntimeError("Dialogue preview WAV changed")
    if _wav(wav_path) != data["total_samples_per_channel"]:
        raise RuntimeError("Dialogue preview length changed")
    source = capture.index.verify_media_file(project_id, data["source_wav_sha256"], "audio/wav")
    indexed = capture.index.verify_media_file(project_id, data["output_wav_sha256"], "audio/wav")
    expected = render_audio_samples(source["path"], {"clips": data["clips"]},
                                    data["source_frames"], data["output_frames"])
    with wave.open(str(wav_path), "rb") as output:
        if output.readframes(data["total_samples_per_channel"]) != expected:
            raise RuntimeError("Dialogue samples differ from source/plan deterministic replay")
    if indexed["sha256"] != data["output_wav_sha256"]:
        raise RuntimeError("Indexed dialogue differs")
    return {"status": "VERIFIED_UNAPPROVED_AUDIO_EDITORIAL_PREVIEW",
            "samples_per_channel": data["total_samples_per_channel"],
            "source_unchanged": True, "final_mix": False}
