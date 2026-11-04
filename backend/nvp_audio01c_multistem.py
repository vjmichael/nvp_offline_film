"""AUDIO-01C: bounded multi-source PCM16 stem render and sample-exact replay.

Worker-side only: the trusted native host must authorize paths, resources and
execution. Produces isolated stem WAVs and an UNAPPROVED mixed preview.
"""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
import re
from pathlib import Path
import struct
import wave

from backend.nvp_audio01_picture_follow import (
    CHANNELS, RATE, SAMPLE_WIDTH, SAMPLES_PER_FRAME, _sha_file, _safe_new,
    _wav, source_mapping,
)
from backend.nvp_audio01b_dialogue_edit import _strict_int
from backend.nvp_film_index import _id

FORMAT = "nvp.audio.multistem_pcm48.v1"
KINDS = frozenset({"dialogue", "ambience", "sfx", "music"})
MAX_STEMS = 8
MAX_CLIPS = 128
MAX_OVERLAP = 8
MAX_OUTPUT_FRAMES = 480
MAX_SOURCE_SAMPLES = RATE * 60 * 30
BLOCK_SAMPLES = 1024


def validate_stem_plan(plan, sources, output_frames):
    """Reject unbounded and forged per-sample edit instructions."""
    _strict_int(output_frames, 1, MAX_OUTPUT_FRAMES, "picture frame count")
    if type(plan) is not dict or set(plan) != {"stems"} or type(plan["stems"]) is not list:
        raise ValueError("Multi-stem plan requires stems")
    if not 1 <= len(plan["stems"]) <= MAX_STEMS:
        raise ValueError("Multi-stem plan must contain 1-8 stems")
    if type(sources) is not dict or len(sources) != len(plan["stems"]):
        raise ValueError("Each stem must have one source WAV")
    total = output_frames * SAMPLES_PER_FRAME
    seen, events, normalized = set(), [], []
    clip_count = 0
    for stem in plan["stems"]:
        if type(stem) is not dict or set(stem) != {"stem_id", "kind", "clips"}:
            raise ValueError("Unexpected stem fields")
        sid = _id(stem["stem_id"], "stem identity")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", sid):
            raise ValueError("Stem identity must be portable on Windows and Linux")
        if sid in seen or stem["kind"] not in KINDS:
            raise ValueError("Duplicate stem or unsupported category")
        seen.add(sid)
        if type(stem["clips"]) is not list or not 1 <= len(stem["clips"]) <= MAX_CLIPS:
            raise ValueError("Each stem needs bounded clips")
        if sid not in sources:
            raise ValueError("Source WAV missing for stem")
        source_samples = _wav(Path(sources[sid]))
        if not 1 <= source_samples <= MAX_SOURCE_SAMPLES:
            raise ValueError("Source duration exceeds bound")
        clips = []
        for clip in stem["clips"]:
            if type(clip) is not dict or set(clip) != {
                "out_start", "out_end", "source_start", "fade_in", "fade_out", "gain_milli"
            }:
                raise ValueError("Clip requires exact sample/fade/gain fields")
            start = _strict_int(clip["out_start"], 0, total-1, "clip start")
            end = _strict_int(clip["out_end"], start+1, total, "clip end")
            duration = end-start
            _strict_int(clip["source_start"], 0, source_samples-duration, "source start")
            _strict_int(clip["fade_in"], 0, duration, "fade in")
            _strict_int(clip["fade_out"], 0, duration, "fade out")
            _strict_int(clip["gain_milli"], 0, 1000, "gain")
            events.extend(((start, 1), (end, -1)))
            clips.append(dict(clip))
            clip_count += 1
        normalized.append({"stem_id": sid, "kind": stem["kind"],
                           "clips": clips, "source_samples": source_samples})
    if set(sources) != seen or clip_count > MAX_CLIPS:
        raise ValueError("Unexpected source IDs or too many clips")
    active = 0
    for _, delta in sorted(events, key=lambda row: (row[0], row[1])):
        active += delta
        if active > MAX_OVERLAP:
            raise ValueError("More than eight simultaneous audio clips")
    return normalized


def _round_million(v):
    return (v+500000)//1000000 if v >= 0 else -((-v+500000)//1000000)


def _wav_writer(stack, path):
    raw = stack.enter_context(path.open("xb"))
    writer = stack.enter_context(wave.open(raw, "wb"))
    writer.setnchannels(CHANNELS)
    writer.setsampwidth(SAMPLE_WIDTH)
    writer.setframerate(RATE)
    return writer


def _render_blocks(stems, sources, output_frames):
    """Bounded memory: max 1024 stereo frames per active source/output block."""
    total = output_frames*SAMPLES_PER_FRAME
    with ExitStack() as stack:
        readers = {s["stem_id"]: stack.enter_context(
            wave.open(str(sources[s["stem_id"]]), "rb")) for s in stems}
        for first_block in range(0, total, BLOCK_SAMPLES):
            last_block = min(first_block+BLOCK_SAMPLES, total)
            count = last_block-first_block
            mixed = [0]*(2*count)
            individual = []
            for stem in stems:
                summed = [0]*(2*count)
                reader = readers[stem["stem_id"]]
                for clip in stem["clips"]:
                    start = max(first_block, clip["out_start"])
                    stop = min(last_block, clip["out_end"])
                    if stop <= start:
                        continue
                    offset = start-clip["out_start"]
                    reader.setpos(clip["source_start"]+offset)
                    raw = reader.readframes(stop-start)
                    if len(raw) != (stop-start)*CHANNELS*SAMPLE_WIDTH:
                        raise RuntimeError("Original stem source truncated")
                    samples = struct.unpack("<"+"h"*(2*(stop-start)), raw)
                    duration = clip["out_end"]-clip["out_start"]
                    for j in range(stop-start):
                        t = offset+j
                        fade = 1000
                        if clip["fade_in"]:
                            fade = min(fade, t*1000//clip["fade_in"])
                        if clip["fade_out"]:
                            fade = min(fade, (duration-1-t)*1000//clip["fade_out"])
                        weight = clip["gain_milli"]*fade
                        idx = 2*(start-first_block+j)
                        summed[idx] += samples[2*j]*weight
                        summed[idx+1] += samples[2*j+1]*weight
                individual.append(summed)
                for i, value in enumerate(summed):
                    mixed[i] += value
            blocks = []
            for values in [*individual, mixed]:
                rounded = [_round_million(v) for v in values]
                if any(v < -32768 or v > 32767 for v in rounded):
                    raise RuntimeError("Audio preview would clip: reduce gains")
                blocks.append(struct.pack("<"+"h"*len(rounded), *rounded))
            yield blocks


def _lineage(capture, project_id, edit_id, revision, frames):
    if type(revision) is not int or revision < 1:
        raise ValueError("Exact B13 edit revision required")
    edit = capture.index.read_revision(project_id, edit_id, revision)
    if edit["kind"] != "edit":
        raise RuntimeError("Source must be an indexed editorial revision")
    delivery_id = edit["data"]["source_delivery_id"]
    delivery = capture.index.read_revision(project_id, delivery_id, 1)
    if delivery["document_sha256"] != edit["data"]["source_delivery_sha256"]:
        raise RuntimeError("Source delivery SHA changed")
    mapping = source_mapping(edit["data"], delivery["data"])
    if len(mapping) != frames:
        raise RuntimeError("Audio duration differs from picture edit")
    take_id = edit["data"]["source_take_id"]
    take = capture.index.read_revision(project_id, take_id, 1)
    if take["document_sha256"] != edit["data"]["source_take_sha256"]:
        raise RuntimeError("Source take SHA changed")
    return {"edit_id": edit_id, "edit_revision": revision,
            "edit_sha256": edit["document_sha256"],
            "source_delivery_id": delivery_id,
            "source_delivery_sha256": delivery["document_sha256"],
            "source_take_id": take_id,
            "source_take_sha256": take["document_sha256"],
            "picture_frame_map": [{"edit_frame": n, "source_frame": s} for n,s in mapping]}


def _dependencies(data):
    return [{"object_id": data["edit_id"], "revision": data["edit_revision"], "role": "timeline"},
            {"object_id": data["source_delivery_id"], "revision": 1, "role": "presentation"},
            {"object_id": data["source_take_id"], "revision": 1, "role": "source_take"}]


def create_multistem_preview(capture, project_id, edit_id, revision,
                             sources, plan, destination, audio_id):
    """Generate isolated source-backed stems and immutable unapproved preview."""
    _id(audio_id, "multistem preview identity")
    destination = Path(destination)
    _safe_new(destination)
    try:
        capture.index.read_revision(project_id, audio_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Audio identity must never be overwritten")
    edit = capture.index.read_revision(project_id, edit_id, revision)
    frames = edit["data"]["editorial_map"]["frame_count"]
    lineage = _lineage(capture, project_id, edit_id, revision, frames)
    stems = validate_stem_plan(plan, sources, frames)
    input_hashes = {}
    for stem in stems:
        sid = stem["stem_id"]
        sha = _sha_file(sources[sid])
        indexed = capture.index.put_media_file(project_id, sources[sid], "audio/wav")
        if indexed["sha256"] != sha:
            raise RuntimeError("Source changed while indexing")
        input_hashes[sid] = sha
    destination.mkdir(mode=0o700)
    output_paths = {s["stem_id"]: destination/("stem_"+s["stem_id"]+".wav")
                    for s in stems}
    output_paths["__mix__"] = destination/"multistem_preview.wav"
    with ExitStack() as stack:
        writers = [_wav_writer(stack, output_paths[s["stem_id"]]) for s in stems]
        writers.append(_wav_writer(stack, output_paths["__mix__"]))
        for chunks in _render_blocks(stems, sources, frames):
            for writer, chunk in zip(writers, chunks):
                writer.writeframesraw(chunk)
    for sid, sha in input_hashes.items():
        if _sha_file(sources[sid]) != sha:
            raise RuntimeError("Source changed during rendering")
    tracks = []
    for stem in stems:
        sid = stem["stem_id"]
        output = output_paths[sid]
        sha = _sha_file(output)
        if (_wav(output) != frames*SAMPLES_PER_FRAME or
            capture.index.put_media_file(project_id, output, "audio/wav")["sha256"] != sha):
            raise RuntimeError("Isolated stem publication changed")
        tracks.append({"stem_id": sid, "kind": stem["kind"],
                       "source_sha256": input_hashes[sid],
                       "source_samples": stem["source_samples"],
                       "output_file": output.name, "output_sha256": sha,
                       "clips": stem["clips"]})
    preview = output_paths["__mix__"]
    preview_sha = _sha_file(preview)
    if (_wav(preview) != frames*SAMPLES_PER_FRAME or
        capture.index.put_media_file(project_id, preview, "audio/wav")["sha256"] != preview_sha):
        raise RuntimeError("Composite preview publication changed")
    data = {"format": FORMAT, "status": "unapproved_multistem_audio_preview",
            "project_id": project_id, **lineage, "stems": tracks,
            "preview_file": preview.name, "preview_sha256": preview_sha,
            "output_frames": frames, "sample_rate": RATE, "channels": CHANNELS,
            "sample_width": SAMPLE_WIDTH, "samples_per_frame": SAMPLES_PER_FRAME,
            "total_samples_per_channel": frames*SAMPLES_PER_FRAME,
            "director_approved": False, "picture_locked": False,
            "final_mix": False, "final_master": False}
    with (destination/"multistem_manifest.json").open("xb") as out:
        out.write(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf8"))
        out.flush()
        os.fsync(out.fileno())
    record = capture.index.register_revision(project_id, audio_id, "audio", data,
                            expected_revision=0, dependencies=_dependencies(data))
    return {"status": "UNAPPROVED_MULTISTEM_AUDIO_PREVIEW",
            "audio_id": audio_id, "document_sha256": record["document_sha256"],
            "stems": len(stems), "samples_per_channel": frames*SAMPLES_PER_FRAME,
            "final_mix": False}


def verify_multistem_preview(capture, project_id, audio_id, destination):
    """Verify all indexed media and replay the exact sample mix in blocks."""
    record = capture.index.read_revision(project_id, audio_id, 1)
    data = record["data"]
    if (record["kind"] != "audio" or data.get("format") != FORMAT or
        data.get("status") != "unapproved_multistem_audio_preview" or
        data.get("project_id") != project_id or
        data.get("director_approved") is not False or
        data.get("picture_locked") is not False or
        data.get("final_mix") is not False or data.get("final_master") is not False or
        data.get("sample_rate") != RATE or data.get("channels") != CHANNELS or
        data.get("sample_width") != SAMPLE_WIDTH or
        data.get("samples_per_frame") != SAMPLES_PER_FRAME or
        data.get("total_samples_per_channel") != data.get("output_frames",0)*SAMPLES_PER_FRAME):
        raise RuntimeError("Invalid multistem preview identity or status")
    if record["dependencies"] != sorted(_dependencies(data),
                                       key=lambda r: (r["object_id"],r["revision"],r["role"])):
        raise RuntimeError("Multistem dependency graph differs")
    source = _lineage(capture, project_id, data["edit_id"],
                      data["edit_revision"], data["output_frames"])
    if any(data.get(k) != v for k,v in source.items()):
        raise RuntimeError("Picture/scene lineage changed")
    parent = Path(destination)
    if parent.is_symlink() or not parent.is_dir():
        raise RuntimeError("Missing or unsafe multistem directory")
    manifest = parent/"multistem_manifest.json"
    if manifest.is_symlink() or json.loads(manifest.read_text("utf8")) != data:
        raise RuntimeError("Multistem preview manifest changed")
    sources = {}
    for stem in data["stems"]:
        sid = stem["stem_id"]
        stored = capture.index.verify_media_file(project_id, stem["source_sha256"], "audio/wav")
        if _wav(stored["path"]) != stem["source_samples"]:
            raise RuntimeError("Original stem sample count changed")
        sources[sid] = stored["path"]
    stems = validate_stem_plan({"stems": [
        {"stem_id": row["stem_id"], "kind": row["kind"], "clips": row["clips"]}
        for row in data["stems"]]}, sources, data["output_frames"])
    if any(a["source_samples"] != b["source_samples"]
           for a,b in zip(stems,data["stems"])):
        raise RuntimeError("Original stem sample count mismatch")
    with ExitStack() as stack:
        streams = []
        for stem in data["stems"]:
            output = parent/stem["output_file"]
            if (output.name != "stem_"+stem["stem_id"]+".wav" or
                output.is_symlink() or _sha_file(output) != stem["output_sha256"] or
                _wav(output) != data["total_samples_per_channel"]):
                raise RuntimeError("Isolated stem WAV changed")
            capture.index.verify_media_file(project_id, stem["output_sha256"], "audio/wav")
            streams.append(stack.enter_context(wave.open(str(output), "rb")))
        preview = parent/data["preview_file"]
        if (preview.name != "multistem_preview.wav" or
            preview.is_symlink() or _sha_file(preview) != data["preview_sha256"] or
            _wav(preview) != data["total_samples_per_channel"]):
            raise RuntimeError("Composite preview WAV changed")
        capture.index.verify_media_file(project_id, data["preview_sha256"], "audio/wav")
        streams.append(stack.enter_context(wave.open(str(preview), "rb")))
        for blocks in _render_blocks(stems,sources,data["output_frames"]):
            for stream,block in zip(streams,blocks):
                if stream.readframes(len(block)//4) != block:
                    raise RuntimeError("Indexed stem/mix differs from source replay")
    return {"status": "VERIFIED_UNAPPROVED_MULTISTEM_AUDIO_PREVIEW",
            "stems": len(stems), "samples_per_channel": data["total_samples_per_channel"],
            "source_unchanged": True, "final_mix": False}
