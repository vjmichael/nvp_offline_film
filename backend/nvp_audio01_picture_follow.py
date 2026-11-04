"""NVP AUDIO-01A: exact 24fps/48kHz source-dialogue PCM editorial conform.

This is a deterministic, *silent-until-source-provided* audio worker engine:
no speech synthesis, music generation, lip animation or professional mix claim.
It only produces a source-synchronous stereo WAV based on the actual B13 edit
frame map. Approval, resource admission, sandboxing and worker supervision must
be enforced by the trusted native host.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import wave

from backend.nvp_b12_editorial_delivery import RATE as PICTURE_RATE
from backend.nvp_b14_picture_conform import _source_rows
from backend.nvp_film_index import _id

RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2
SAMPLES_PER_FRAME = RATE // PICTURE_RATE
FORMAT = "nvp.audio.edited_pcm48_stereo.v1"
MAX_EDITS = 480

if RATE % PICTURE_RATE or PICTURE_RATE != 24:
    raise RuntimeError("AUDIO-01A must have integer 48k-to-24fps alignment")


def _sha_file(file):
    h = hashlib.sha256()
    with Path(file).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_new(path):
    if path.is_symlink() or path.exists() or not path.parent.is_dir() or path.parent.is_symlink():
        raise RuntimeError("AUDIO-01 requires an absent output under a trusted parent")


def _wav(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Audio source is absent or symlinked")
    with wave.open(str(path), "rb") as w:
        if (w.getcomptype() != "NONE" or w.getnchannels() != CHANNELS or
            w.getsampwidth() != SAMPLE_WIDTH or w.getframerate() != RATE):
            raise RuntimeError("AUDIO-01 needs actual stereo 48kHz 16-bit PCM WAV")
        return w.getnframes()


def source_mapping(edit, original):
    """One exact output-frame → original-source-frame mapping, no guesswork."""
    if edit["editorial_map"]["frame_count"] > MAX_EDITS:
        raise RuntimeError("AUDIO-01A editorial test exceeds short-fixture budget")
    return [(n, src["frame"]) for n, src in _source_rows(edit, original)]


def conform_pcm_audio(capture, project_id, edit_id, revision,
                      input_wav, output_dir, audio_id):
    """Copy exactly 2,000 source samples per edited frame in 48kHz stereo.

    Source must cover the complete original timeline; no invented voice or
    timing is allowed. Discontinuous edges are explicitly marked pending
    creative audio transitions, rather than silently called a final mix.
    """
    _id(audio_id, "audio conform identity")
    if type(revision) is not int or revision < 1:
        raise ValueError("Exact editorial revision required")
    output_dir = Path(output_dir)
    _safe_new(output_dir)
    try:
        capture.index.read_revision(project_id, audio_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Audio ID cannot overwrite an existing revision")
    edit = capture.index.read_revision(project_id, edit_id, revision)
    original_id = edit["data"]["source_delivery_id"]
    original = capture.index.read_revision(project_id, original_id, 1)
    if original["document_sha256"] != edit["data"]["source_delivery_sha256"]:
        raise RuntimeError("Edited audio source does not match frozen original delivery")
    mapping = source_mapping(edit["data"], original["data"])
    source_frames = original["data"]["frame_count"]
    if _wav(input_wav) != source_frames * SAMPLES_PER_FRAME:
        raise RuntimeError("PCM dialogue source is not aligned to original picture duration")
    source_sha = _sha_file(input_wav)
    indexed_source = capture.index.put_media_file(project_id, input_wav, "audio/wav")
    if indexed_source["sha256"] != source_sha:
        raise RuntimeError("Source WAV changed while indexing")
    output_dir.mkdir(mode=0o700)
    target = output_dir / "edited_picture_follow_pcm48.wav"
    discontinuities = []
    with wave.open(str(input_wav), "rb") as inp, target.open("xb") as exclusive:
        with wave.open(exclusive, "wb") as out:
            out.setnchannels(CHANNELS)
            out.setsampwidth(SAMPLE_WIDTH)
            out.setframerate(RATE)
            last = None
            for n, source in mapping:
                if last is not None and source != last + 1:
                    discontinuities.append({"edit_frame": n, "previous_source_frame": last,
                                            "next_source_frame": source,
                                            "needs_audio_transition_review": True})
                inp.setpos((source - 1) * SAMPLES_PER_FRAME)
                segment = inp.readframes(SAMPLES_PER_FRAME)
                if len(segment) != SAMPLES_PER_FRAME * CHANNELS * SAMPLE_WIDTH:
                    raise RuntimeError("Source PCM ended mid-frame")
                out.writeframesraw(segment)
                last = source
    if _wav(target) != len(mapping) * SAMPLES_PER_FRAME:
        raise RuntimeError("Edited PCM sample count does not match edit")
    output_sha = _sha_file(target)
    indexed = capture.index.put_media_file(project_id, target, "audio/wav")
    if indexed["sha256"] != output_sha:
        raise RuntimeError("Edited WAV changed before FilmIndex publication")
    manifest = {
        "format": FORMAT, "status": "unapproved_picture_follow_audio_conform",
        "project_id": project_id, "edit_id": edit_id, "edit_revision": revision,
        "edit_sha256": edit["document_sha256"],
        "source_delivery_id": original_id,
        "source_delivery_sha256": original["document_sha256"],
        "source_take_id": edit["data"]["source_take_id"],
        "source_take_sha256": edit["data"]["source_take_sha256"],
        "source_pcm_sha256": source_sha,
        "output_pcm_sha256": output_sha,
        "output_wav": target.name, "fps": PICTURE_RATE, "sample_rate": RATE,
        "sample_width": SAMPLE_WIDTH, "channels": CHANNELS,
        "samples_per_frame": SAMPLES_PER_FRAME,
        "source_frames": source_frames, "edit_frames": len(mapping),
        "total_audio_samples_per_channel": len(mapping) * SAMPLES_PER_FRAME,
        "frame_map": [{"edit_frame": n, "source_frame": source} for n, source in mapping],
        "discontinuities": discontinuities, "audio_transitions_approved": False,
        "dialogue_generated": False, "sound_mixed": False,
        "final_audio_master": False,
    }
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf8")
    with (output_dir / "audio_conform_manifest.json").open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    deps = [
        {"object_id": edit_id, "revision": revision, "role": "timeline"},
        {"object_id": original_id, "revision": 1, "role": "presentation"},
        {"object_id": manifest["source_take_id"], "revision": 1, "role": "source_take"},
    ]
    rec = capture.index.register_revision(project_id, audio_id, "audio",
                                          manifest, expected_revision=0,
                                          dependencies=deps)
    return {"status": "VERIFIED_AUDIO_PICTURE_FRAME_MAPPING",
            "audio_id": audio_id, "document_sha256": rec["document_sha256"],
            "frames": len(mapping), "samples": len(mapping) * SAMPLES_PER_FRAME,
            "discontinuities": len(discontinuities), "audio_mixed": False}


def verify_pcm_audio(capture, project_id, audio_id, output_dir):
    rec = capture.index.read_revision(project_id, audio_id, 1)
    data = rec["data"]
    if (rec["kind"] != "audio" or data.get("format") != FORMAT or
        data.get("status") != "unapproved_picture_follow_audio_conform" or
        data.get("sound_mixed") is not False or
        data.get("final_audio_master") is not False):
        raise RuntimeError("Audio conform cannot be treated as a final master")
    edit = capture.index.read_revision(project_id, data["edit_id"], data["edit_revision"])
    source = capture.index.read_revision(project_id, data["source_delivery_id"], 1)
    if (edit["document_sha256"] != data["edit_sha256"] or
        source["document_sha256"] != data["source_delivery_sha256"]):
        raise RuntimeError("Audio conform lost immutable source lineage")
    mapping = source_mapping(edit["data"], source["data"])
    if data["frame_map"] != [{"edit_frame": n, "source_frame": s} for n, s in mapping]:
        raise RuntimeError("Stored audio/frame mapping was forged")
    expected_edges = sorted([
        {"object_id": data["edit_id"], "revision": data["edit_revision"], "role": "timeline"},
        {"object_id": data["source_delivery_id"], "revision": 1, "role": "presentation"},
        {"object_id": data["source_take_id"], "revision": 1, "role": "source_take"}
    ], key=lambda r: (r["object_id"], r["revision"], r["role"]))
    if rec["dependencies"] != expected_edges:
        raise RuntimeError("Audio dependency edges differ from indexed originals")
    path = Path(output_dir)
    if not path.is_dir() or path.is_symlink():
        raise RuntimeError("Audio presentation directory is missing")
    manifest = path / "audio_conform_manifest.json"
    if (manifest.is_symlink() or
        json.loads(manifest.read_text("utf8")) != data):
        raise RuntimeError("Audio conform manifest no longer matches FilmIndex")
    wave_file = path / data["output_wav"]
    if (wave_file.is_symlink() or _wav(wave_file) !=
        len(mapping) * SAMPLES_PER_FRAME or
        _sha_file(wave_file) != data["output_pcm_sha256"]):
        raise RuntimeError("Audio output bytes changed")
    source_media = capture.index.verify_media_file(project_id,
                                        data["source_pcm_sha256"], "audio/wav")
    result_media = capture.index.verify_media_file(project_id,
                                        data["output_pcm_sha256"], "audio/wav")
    with wave.open(source_media["path"], "rb") as inp, wave.open(str(wave_file), "rb") as out:
        for n, frame in mapping:
            inp.setpos((frame - 1) * SAMPLES_PER_FRAME)
            if out.readframes(SAMPLES_PER_FRAME) != inp.readframes(SAMPLES_PER_FRAME):
                raise RuntimeError(f"Audio data differs from original sample range at {n}")
    return {"status": "VERIFIED_AUDIO_PICTURE_FRAME_MAPPING",
            "frames": len(mapping),
            "samples": len(mapping) * SAMPLES_PER_FRAME,
            "audio_sha256": result_media["sha256"],
            "audio_mixed": False, "final_audio_master": False}
