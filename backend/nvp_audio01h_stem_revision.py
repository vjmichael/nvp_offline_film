"""AUDIO-01H.2: immutable stem automation authoring, pending native-host gate.

This is a trusted-library transaction and does NOT launch an uncontained
subprocess. Caller must obtain per-turn native authorization before calling.
No output may be called an approved mix or master.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import wave

from backend.nvp_audio01h_automation import apply_pcm16_stereo, validate_automation
from backend.nvp_audio01h_fault_matrix import crash_after
from backend.nvp_audio01e_wav_publication import FORMAT as STEM_FORMAT
from backend.nvp_film_index import _id

FORMAT = "nvp.audio01h.automated_stem_revision.v1"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def automate_stem(capture, project_id, source_audio_id, stem_id, points,
                  source_dir, destination, output_id, *, authorize):
    """Create separately indexed immutable automation; never mutate source WAV.

    authorize receives exact source SHA, output ID, destination and control
    points. Production callers must use NVP's native authorization/resource
    broker before entering this function.
    """
    _id(output_id, "automated stem ID")
    if stem_id is not None:
        _id(stem_id, "original stem ID")
    source_record = capture.index.read_revision(project_id, source_audio_id, 1)
    source_data = source_record["data"]
    if (source_record["kind"] != "audio" or
        source_data.get("format") != STEM_FORMAT or
        source_data.get("final_mix") is not False):
        raise RuntimeError("Automation requires immutable unapproved AUDIO-01E stems")
    items = [x for x in source_data["wav_outputs"] if x["stem_id"] == stem_id]
    if len(items) != 1 or (stem_id is None and items[0]["filename"] != "mix_preview.wav"):
        raise RuntimeError("Exactly one indexed source stem/composite required")
    item = items[0]
    source = Path(source_dir) / item["filename"]
    target = Path(destination)
    if (source.is_symlink() or not source.is_file() or
        target.exists() or target.is_symlink() or target.parent.is_symlink()
        or not target.parent.is_dir() or target.suffix.lower() != ".wav"):
        raise RuntimeError("Source or output path is unsafe")
    samples = source_data["total_samples_per_channel"]
    envelope = validate_automation(points, samples)
    with wave.open(str(source), "rb") as reader:
        if (reader.getnchannels(), reader.getsampwidth(),
            reader.getframerate(), reader.getcomptype(), reader.getnframes()
            ) != (2, 2, 48000, "NONE", samples):
            raise RuntimeError("Source PCM does not match exact picture clock")
        pcm = reader.readframes(samples)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_sha != item["sha256"]:
        raise RuntimeError("Immutable published source WAV changed")
    capture.index.verify_media_file(project_id, source_sha, "audio/wav")
    scope = {
        "operation": "nvp.audio01h.automate_stem",
        "project_id": project_id, "audio_id": source_audio_id,
        "audio_document_sha": source_record["document_sha256"],
        "stem_id": stem_id, "source_sha256": source_sha,
        "output_id": output_id, "destination": str(target.absolute()),
        "envelope": [list(x) for x in envelope],
        "final_mix": False, "final_master": False
    }
    if not callable(authorize) or authorize(scope) is not True:
        raise PermissionError("Exact automated stem change not authorized")
    try:
        capture.index.read_revision(project_id, output_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Automation output identity already exists")
    output_pcm = apply_pcm16_stereo(pcm, envelope, total_samples=samples)
    # Exclusive creation, not an in-place edit. Uncommitted output remains
    # an inspectable orphan; it is never accepted as a FilmIndex revision.
    with target.open("xb") as raw:
        with wave.open(raw, "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            wav.writeframes(output_pcm)
        raw.flush()
        os.fsync(raw.fileno())
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_sha:
        raise RuntimeError("Source changed during authorized automation")
    stored = capture.index.put_media_file(project_id, target, "audio/wav")
    doc = {
        "format": FORMAT, "status": "unapproved_automated_stem",
        "source_audio_id": source_audio_id,
        "source_audio_sha256": source_record["document_sha256"],
        "source_stem_id": stem_id, "source_wav_sha256": source_sha,
        "automated_wav_sha256": stored["sha256"],
        "samples_per_channel": samples, "sample_rate": 48000,
        "automation": [list(x) for x in envelope],
        "picture_locked": False, "final_mix": False,
        "director_approved": False, "final_master": False
    }
    revision = capture.index.register_revision(
        project_id, output_id, "audio", doc, expected_revision=0,
        dependencies=[{"object_id": source_audio_id, "revision": 1, "role": "audio"}])
    crash_after("worker_output_registered")
    return {"status": "UNAPPROVED_AUTOMATED_STEM", "output_id": output_id,
            "document_sha256": revision["document_sha256"],
            "wav_sha256": stored["sha256"], "samples_per_channel": samples}
