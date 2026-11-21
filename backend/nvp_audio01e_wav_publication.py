"""NVP AUDIO-01E: materialize verified AUDIO-01D chunks as immutable WAV media.

One audio-only technical preview plus isolated PCM16 stems. This is *not* final
mixing, filmmaker approval or sound/picture lock. The native host remains
responsible for path authorization, exclusive worker supervision and cleanup.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import wave

from backend.nvp_audio01d_chunked_recovery import (
    FORMAT as CHUNK_FORMAT, CHUNK_SAMPLES, _audit_chunks, _check_inputs,
    _read_state, _validate, verify_chunked_preview,
)
from backend.nvp_audio01_picture_follow import (
    CHANNELS, RATE, SAMPLE_WIDTH, SAMPLES_PER_FRAME, _sha_file, _wav, _safe_new,
)
from backend.nvp_film_index import _id

FORMAT = "nvp.audio.materialized_multistem_preview.v1"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sources_checked(plan, sources, samples, chunks_dir):
    root = Path(chunks_dir)
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("Unsafe chunk source directory")
    state = _read_state(root)
    if (state.get("format") != CHUNK_FORMAT or state.get("status") != "complete" or
        state.get("total_samples") != samples or
        state.get("final_mix") is not False or
        state.get("final_master") is not False):
        raise RuntimeError("Only completed technical audio chunks may be materialized")
    stems = _validate(plan, sources, samples)
    _check_inputs(stems, sources, state["sources"])
    _audit_chunks(root, state)
    return root, stems, state


def _materialize_wavs(root, state, outdir, stems):
    names = ["stem_" + row["stem_id"] + ".wav" for row in stems] + ["mix_preview.wav"]
    files = [outdir/name for name in names]
    with ExitStack() as stack:
        writers = []
        for path in files:
            raw = stack.enter_context(path.open("xb"))
            writer = stack.enter_context(wave.open(raw, "wb"))
            writer.setnchannels(CHANNELS)
            writer.setsampwidth(SAMPLE_WIDTH)
            writer.setframerate(RATE)
            writers.append(writer)
        for receipt in state["chunks"]:
            if len(receipt["files"]) != len(files):
                raise RuntimeError("Chunk channel count changed")
            for i, file in enumerate(receipt["files"]):
                chunk = root/file
                if chunk.is_symlink() or not chunk.is_file():
                    raise RuntimeError("Missing or symlinked chunk")
                # Bound each read to one second of PCM and verify bytes again
                # against the durable receipt before WAV publication.
                raw = chunk.read_bytes()
                if len(raw) != receipt["samples"]*CHANNELS*SAMPLE_WIDTH or (
                    hashlib.sha256(raw).hexdigest() != receipt["sha256"][i]):
                    raise RuntimeError("Chunk changed during materialization")
                writers[i].writeframesraw(raw)
    total = state["total_samples"]
    for path in files:
        if _wav(path) != total:
            raise RuntimeError("Materialized WAV duration differs from checkpoint")
    return files


def publish_chunked_wavs(capture, project_id, audio_id, plan, sources,
                         total_samples, chunks_dir, output_dir):
    """Publish stem/mix WAV and FilmIndex record after complete chunk proof.

    No picture/audio synchronization is claimed: an exact picture index of this
    duration must be attached by a later approved editorial conform.
    """
    _id(audio_id, "materialized audio identity")
    output = Path(output_dir)
    _safe_new(output)
    try:
        capture.index.read_revision(project_id, audio_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Audio identity exists; never overwrite")
    root, stems, state = _sources_checked(plan, sources, total_samples, chunks_dir)
    # Check deterministic PCM replay (stronger than merely trusting SHA receipts).
    verify_chunked_preview(plan, sources, total_samples, root, replay=True)
    output.mkdir(mode=0o700)
    files = _materialize_wavs(root, state, output, stems)
    outputs = []
    for i, path in enumerate(files):
        sha = _sha_file(path)
        stored = capture.index.put_media_file(project_id, path, "audio/wav")
        if stored["sha256"] != sha:
            raise RuntimeError("WAV changed while indexing")
        outputs.append({"filename": path.name, "sha256": sha,
                        "samples_per_channel": total_samples,
                        "stem_id": stems[i]["stem_id"] if i<len(stems) else None,
                        "kind": stems[i]["kind"] if i<len(stems) else "composite"})
    source_records=[]
    for row in state["sources"]:
        original = Path(sources[row["stem_id"]])
        proof = _sha_file(original)
        if proof != row["source_sha256"]:
            raise RuntimeError("Original media changed before publication")
        indexed = capture.index.put_media_file(project_id, original, "audio/wav")
        if indexed["sha256"] != proof:
            raise RuntimeError("Original stem changed during indexing")
        source_records.append(dict(row))
    receipt_sha = hashlib.sha256(_canonical(state)).hexdigest()
    document = {
        "format": FORMAT, "status": "unapproved_audio_only_pcm16_stems",
        "project_id": project_id, "chunk_receipt_sha256": receipt_sha,
        "source_stems": source_records, "wav_outputs": outputs,
        "total_samples_per_channel": total_samples,
        "sample_rate": RATE, "channels": CHANNELS, "sample_width": SAMPLE_WIDTH,
        "picture_bound": False, "picture_locked": False, "director_approved": False,
        "final_mix": False, "final_master": False,
    }
    with (output/"audio01e_manifest.json").open("xb") as f:
        f.write(_canonical(document))
        f.flush()
        os.fsync(f.fileno())
    record = capture.index.register_revision(project_id, audio_id, "audio", document,
                                              expected_revision=0, dependencies=[])
    return {"status": "UNAPPROVED_INDEXED_MULTISTEM_WAV_PREVIEW",
            "audio_id": audio_id, "document_sha256": record["document_sha256"],
            "wav_count": len(files), "samples_per_channel": total_samples,
            "picture_bound": False, "final_mix": False}


def verify_published_wavs(capture, project_id, audio_id, plan, sources,
                          total_samples, chunks_dir, output_dir):
    """Independent after-restart verification: source chunks and published WAV."""
    record = capture.index.read_revision(project_id, audio_id, 1)
    data = record["data"]
    if (record["kind"]!="audio" or record["dependencies"] != [] or
        data.get("format") != FORMAT or data.get("project_id") != project_id or
        data.get("status") != "unapproved_audio_only_pcm16_stems" or
        data.get("total_samples_per_channel") != total_samples or
        data.get("sample_rate") != RATE or data.get("channels") != CHANNELS or
        data.get("sample_width") != SAMPLE_WIDTH or
        data.get("picture_bound") is not False or
        data.get("picture_locked") is not False or
        data.get("director_approved") is not False or
        data.get("final_mix") is not False or data.get("final_master") is not False):
        raise RuntimeError("Audio publication is not an unapproved source-only preview")
    root, stems, state = _sources_checked(plan, sources, total_samples, chunks_dir)
    verify_chunked_preview(plan,sources,total_samples,root,replay=True)
    if hashlib.sha256(_canonical(state)).hexdigest()!=data["chunk_receipt_sha256"]:
        raise RuntimeError("Published chunk checkpoint was replaced")
    if state["sources"] != data["source_stems"]:
        raise RuntimeError("Published source provenance was replaced")
    folder=Path(output_dir)
    if folder.is_symlink() or not folder.is_dir():
        raise RuntimeError("Output folder missing or unsafe")
    manifest=folder/"audio01e_manifest.json"
    if (manifest.is_symlink() or not manifest.is_file() or
        manifest.read_bytes()!=_canonical(data)):
        raise RuntimeError("Audio publication manifest changed")
    if len(data["wav_outputs"])!=len(stems)+1:
        raise RuntimeError("Published WAV count changed")
    for i, item in enumerate(data["wav_outputs"]):
        expected = "stem_"+stems[i]["stem_id"]+".wav" if i<len(stems) else "mix_preview.wav"
        if item["filename"] != expected or (
            item["stem_id"] != (stems[i]["stem_id"] if i<len(stems) else None)):
            raise RuntimeError("Published stem identity changed")
        path=folder/expected
        if (path.is_symlink() or not path.is_file() or
            _wav(path)!=total_samples or _sha_file(path)!=item["sha256"]):
            raise RuntimeError("Published WAV bytes changed")
        capture.index.verify_media_file(project_id,item["sha256"],"audio/wav")
    # Independently compare all WAV audio samples with the immutable chunk bodies.
    with ExitStack() as stack:
        readers=[stack.enter_context(wave.open(str(folder/item["filename"]),"rb"))
                 for item in data["wav_outputs"]]
        for receipt in state["chunks"]:
            for i,file in enumerate(receipt["files"]):
                if readers[i].readframes(receipt["samples"])!=(root/file).read_bytes():
                    raise RuntimeError("WAV PCM no longer matches signed-off chunk")
    for src in data["source_stems"]:
        capture.index.verify_media_file(project_id,src["source_sha256"],"audio/wav")
    return {"status":"VERIFIED_UNAPPROVED_INDEXED_WAV_PREVIEW",
            "wav_count":len(data["wav_outputs"]),
            "samples_per_channel":total_samples,
            "picture_bound":False,"final_mix":False}
