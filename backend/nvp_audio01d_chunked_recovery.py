"""AUDIO-01D: bounded-memory, durable, resumable PCM-stem chunk worker.

Long-duration *audio-only technical preview*. Not an approved mix, final master,
OS sandbox, or B13 picture conform. The caller must authorize all paths and
control cancellation; a later integration must bind a full-length picture ID.

Chunk bodies are immutable. A recovered job rehashes all receipt-bound chunks
before advancing; changed source, plan or prior chunk aborts. There is no
append-in-place WAV and no publishing a half-rendered output as complete.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import wave

from backend.nvp_audio01c_multistem import (
    CHANNELS, RATE, SAMPLE_WIDTH, BLOCK_SAMPLES, KINDS, MAX_OVERLAP,
    _render_blocks, _round_million,
)
from backend.nvp_audio01_picture_follow import _sha_file, _wav
from backend.nvp_film_index import _id

FORMAT = "nvp.audio.chunked_preview.v1"
MAX_DURATION_SAMPLES = RATE * 60 * 120  # 2-hour bounded audio worker
MAX_CLIPS = 50000
MAX_STEMS = 8
CHUNK_SAMPLES = RATE  # durable one-second chunks; 384kB per eight stereo stems
MAX_SOURCE_SAMPLES = RATE * 60 * 120


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _write_new(path, raw):
    with Path(path).open("xb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def _atomic_replace(path, raw):
    target = Path(path)
    stage = target.with_name(target.name + ".new")
    if stage.exists() or stage.is_symlink():
        raise RuntimeError("Unresolved checkpoint stage; operator cleanup required")
    _write_new(stage, raw)
    os.replace(stage, target)
    # Persistent file sync; caller/host must handle filesystem/parent durability.


def _validate(plan, sources, total_samples):
    if (type(total_samples) is not int or not 1 <= total_samples <= MAX_DURATION_SAMPLES or
        type(plan) is not dict or set(plan) != {"stems"} or
        type(plan["stems"]) is not list or not 1 <= len(plan["stems"]) <= MAX_STEMS or
        type(sources) is not dict or len(sources) != len(plan["stems"])):
        raise ValueError("Invalid bounded multi-stem job")
    seen, events, total_clips = set(), [], 0
    validated = []
    for stem in plan["stems"]:
        if type(stem) is not dict or set(stem) != {"stem_id", "kind", "clips"}:
            raise ValueError("Invalid stem")
        sid = _id(stem["stem_id"], "stem identity")
        if not sid.replace("_", "").isalnum() or not sid[0].isalpha() or len(sid)>64:
            raise ValueError("Unsafe stem file identity")
        if sid in seen or stem["kind"] not in KINDS or sid not in sources:
            raise ValueError("Repeated stem, missing source, or unsupported type")
        seen.add(sid)
        n = _wav(sources[sid])
        if not 1 <= n <= MAX_SOURCE_SAMPLES or not isinstance(stem["clips"], list):
            raise ValueError("Source duration/clip list invalid")
        clips = []
        for c in stem["clips"]:
            if type(c) is not dict or set(c) != {
                "out_start", "out_end", "source_start", "fade_in", "fade_out", "gain_milli"
            } or any(type(v) is not int for v in c.values()):
                raise ValueError("Invalid exact-sample clip")
            start,end,src = c["out_start"],c["out_end"],c["source_start"]
            duration = end-start
            if not (0<=start<end<=total_samples and 0<=src<=n-duration and
                    0<=c["fade_in"]<=duration and 0<=c["fade_out"]<=duration and
                    0<=c["gain_milli"]<=1000):
                raise ValueError("Clip outside source or destination range")
            events.extend(((start,1),(end,-1)))
            total_clips += 1
            clips.append(dict(c))
        validated.append({"stem_id":sid,"kind":stem["kind"],"clips":clips,
                          "source_samples":n})
    if set(sources) != seen or total_clips < 1 or total_clips > MAX_CLIPS:
        raise ValueError("Invalid source mapping/clip count")
    active = 0
    for _,delta in sorted(events,key=lambda x:(x[0],x[1])):
        active += delta
        if active > MAX_OVERLAP:
            raise ValueError("Too many simultaneous clips")
    return validated


def _source_receipts(stems, sources):
    return [{"stem_id":s["stem_id"],"kind":s["kind"],
             "source_sha256":_sha_file(sources[s["stem_id"]]),
             "source_samples":s["source_samples"],"clips":s["clips"]}
            for s in stems]


def _chunk_name(index):
    return f"chunk_{index:07d}.pcm"


def _receipt_path(directory):
    return directory/"checkpoint.json"


def _read_state(directory):
    path = _receipt_path(directory)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Checkpoint absent or symlinked")
    state = json.loads(path.read_text("utf8"))
    if type(state) is not dict or state.get("format") != FORMAT:
        raise RuntimeError("Checkpoint schema changed")
    return state


def _check_inputs(stems, sources, stored):
    if len(stored) != len(stems):
        raise RuntimeError("Source count differs from checkpoint")
    for s,row in zip(stems,stored):
        if (s["stem_id"]!=row["stem_id"] or s["kind"]!=row["kind"] or
            s["source_samples"]!=row["source_samples"] or
            s["clips"]!=row["clips"] or
            _sha_file(sources[s["stem_id"]])!=row["source_sha256"]):
            raise RuntimeError("Input audio or plan changed since checkpoint")


def _audit_chunks(directory, state):
    receipts = state["chunks"]
    expected_start = 0
    for i,r in enumerate(receipts):
        if r["index"] != i or r["start_sample"] != expected_start:
            raise RuntimeError("Missing or reordered chunk receipt")
        count = r["samples"]
        if not 1 <= count <= CHUNK_SAMPLES:
            raise RuntimeError("Invalid chunk sample count")
        for file,sha in zip(r["files"],r["sha256"]):
            p=directory/file
            if p.is_symlink() or not p.is_file() or p.stat().st_size != count*4 or _sha_file(p)!=sha:
                raise RuntimeError("Checkpoint chunk was lost or modified")
        expected_start += count
    if expected_start != state["next_sample"] or expected_start>state["total_samples"]:
        raise RuntimeError("Checkpoint offset inconsistent")
    return expected_start


def _render_chunk(stems, sources, first, stop):
    """Seek-and-render only bounded material overlapping one durable chunk."""
    from contextlib import ExitStack
    count = stop-first
    results = [[0]*(2*count) for _ in range(len(stems)+1)]
    with ExitStack() as stack:
        readers = {
            s["stem_id"]:stack.enter_context(wave.open(str(sources[s["stem_id"]]),"rb"))
            for s in stems
        }
        for i,stem in enumerate(stems):
            reader=readers[stem["stem_id"]]
            for clip in stem["clips"]:
                lo=max(first,clip["out_start"])
                hi=min(stop,clip["out_end"])
                if hi<=lo:
                    continue
                relative=lo-clip["out_start"]
                reader.setpos(clip["source_start"]+relative)
                pcm=reader.readframes(hi-lo)
                if len(pcm)!=(hi-lo)*4:
                    raise RuntimeError("Stem truncated while rendering")
                samples=struct.unpack("<"+"h"*(2*(hi-lo)),pcm)
                duration=clip["out_end"]-clip["out_start"]
                for n in range(hi-lo):
                    t=relative+n
                    fade=1000
                    if clip["fade_in"]:
                        fade=min(fade,t*1000//clip["fade_in"])
                    if clip["fade_out"]:
                        fade=min(fade,(duration-1-t)*1000//clip["fade_out"])
                    gain=clip["gain_milli"]*fade
                    offset=2*(lo-first+n)
                    results[i][offset]+=samples[2*n]*gain
                    results[i][offset+1]+=samples[2*n+1]*gain
            for n,v in enumerate(results[i]):
                results[-1][n]+=v
    output=[]
    for values in results:
        rounded=[_round_million(v) for v in values]
        if any(v < -32768 or v > 32767 for v in rounded):
            raise RuntimeError("Audio would clip; reduce source gains")
        output.append(struct.pack("<"+"h"*len(rounded),*rounded))
    return output


def run_chunked_preview(plan, sources, total_samples, directory, *,
                        cancel=None, max_new_chunks=None):
    """Start or resume a specific immutable, checkpointed audio-only job.

    cancel is a trusted host callback checked before each new chunk.
    max_new_chunks supports controlled pause and restart testing.
    """
    directory=Path(directory)
    if directory.is_symlink() or directory.parent.is_symlink() or not directory.parent.is_dir():
        raise RuntimeError("Unsafe worker output parent")
    stems=_validate(plan,sources,total_samples)
    if directory.exists():
        if not directory.is_dir():
            raise RuntimeError("Output destination is not a directory")
        state=_read_state(directory)
        if state["total_samples"]!=total_samples:
            raise RuntimeError("Duration changed after job creation")
        _check_inputs(stems,sources,state["sources"])
        start=_audit_chunks(directory,state)
    else:
        directory.mkdir(mode=0o700)
        state={"format":FORMAT,"status":"in_progress","total_samples":total_samples,
               "sample_rate":RATE,"channels":CHANNELS,
               "sources":_source_receipts(stems,sources),
               "chunks":[],"next_sample":0,
               "final_mix":False,"final_master":False}
        _write_new(_receipt_path(directory),_json_bytes(state))
        start=0
    if state["status"] == "complete":
        if start != total_samples:
            raise RuntimeError("Completed checkpoint is missing samples")
        return {"status":"COMPLETE_AUDIO_CHUNK_PREVIEW","chunks":len(state["chunks"]),
                "samples_per_channel":total_samples,"final_mix":False}
    if state["status"] != "in_progress":
        raise RuntimeError("Unknown resumable state")
    produced=0
    while start<total_samples:
        if cancel is not None and cancel():
            return {"status":"CANCELLED_RESUMABLE","next_sample":start,
                    "chunks":len(state["chunks"])}
        if max_new_chunks is not None and produced>=max_new_chunks:
            return {"status":"PAUSED_RESUMABLE","next_sample":start,
                    "chunks":len(state["chunks"])}
        stop=min(start+CHUNK_SAMPLES,total_samples)
        frames=_render_chunk(stems,sources,start,stop)
        index=len(state["chunks"])
        files=[f"stem_{s['stem_id']}_{_chunk_name(index)}" for s in stems]
        files.append("mix_"+_chunk_name(index))
        shas=[_hash(raw) for raw in frames]
        for file,raw in zip(files,frames):
            p=directory/file
            if p.exists() or p.is_symlink():
                # Crash between output chunk and receipt: require trusted recovery.
                raise RuntimeError("Orphan chunk exists without committed receipt")
            _write_new(p,raw)
        receipt={"index":index,"start_sample":start,"samples":stop-start,
                 "files":files,"sha256":shas}
        state["chunks"].append(receipt)
        state["next_sample"]=stop
        _atomic_replace(_receipt_path(directory),_json_bytes(state))
        produced += 1
        start=stop
    # Full receipt chain revalidated before transitioning to complete.
    _audit_chunks(directory,state)
    state["status"]="complete"
    _atomic_replace(_receipt_path(directory),_json_bytes(state))
    return {"status":"COMPLETE_AUDIO_CHUNK_PREVIEW","chunks":len(state["chunks"]),
            "samples_per_channel":total_samples,"final_mix":False}


def verify_chunked_preview(plan,sources,total_samples,directory,*,replay=True):
    """Verify checkpoint, source hashes and optionally every decoded PCM chunk."""
    folder=Path(directory)
    state=_read_state(folder)
    stems=_validate(plan,sources,total_samples)
    if (state["status"]!="complete" or state["total_samples"]!=total_samples or
        state["final_mix"] is not False or state["final_master"] is not False or
        state["sample_rate"]!=RATE or state["channels"]!=CHANNELS):
        raise RuntimeError("Not a completed unapproved technical preview")
    _check_inputs(stems,sources,state["sources"])
    _audit_chunks(folder,state)
    if replay:
        for receipt in state["chunks"]:
            first=receipt["start_sample"]
            expected=_render_chunk(stems,sources,first,first+receipt["samples"])
            for f,raw in zip(receipt["files"],expected):
                if (folder/f).read_bytes()!=raw:
                    raise RuntimeError("PCM chunk disagrees with deterministic replay")
    return {"status":"VERIFIED_CHUNKED_AUDIO_PREVIEW",
            "chunks":len(state["chunks"]),"samples_per_channel":total_samples,
            "full_replay":bool(replay),"final_master":False}
