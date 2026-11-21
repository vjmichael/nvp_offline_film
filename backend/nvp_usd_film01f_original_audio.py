"""USD-FILM-01F original 48 kHz recorded-PCM stem reconciliation.

Reopens original world Take and every FilmIndex audio source by exact immutable
SHA. Persists finite, separately labeled mono WAV stems for independent listening
and source-integrity review. No soundtrack summation, generated voice, mastering,
FFmpeg, renderer execution, user path selection, or film-release approval.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import wave

from backend.nvp_data_av_source import (
    RecordedSoundSources, SAMPLE_RATE, MAX_READ_SAMPLES)
from backend.nvp_film_index import FilmIndex, _require_pid, _sha
from backend.nvp_usd_film01e_world_take import (
    OpenUSDWorldTakeCapture, FORMAT as WORLD_TAKE_FORMAT)

FORMAT = "nvp.usd_film01f.original_pcm_stems_verified.v1"
MAX_STEMS = 64
MAX_TOTAL_PCM_BYTES = 512 * 1024 * 1024


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _file_sha(path):
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reopen_wav(path, expected_samples, expected_pcm_sha):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Original PCM derivative stem is missing or linked")
    digest=sha256()
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels()!=1 or wav.getsampwidth()!=2 or
                wav.getframerate()!=SAMPLE_RATE or
                wav.getnframes()!=expected_samples):
            raise RuntimeError("Original 48 kHz PCM stem clock/format changed")
        count=0
        while count<expected_samples:
            data=wav.readframes(min(MAX_READ_SAMPLES,expected_samples-count))
            count+=len(data)//2
            digest.update(data)
        if count!=expected_samples or wav.readframes(1):
            raise RuntimeError("Original PCM stem was truncated or appended")
    if digest.hexdigest()!=expected_pcm_sha:
        raise RuntimeError("Original PCM stem bytes changed after write")
    return _file_sha(path)


def render_original_source_stems(index: FilmIndex, project_id, world_take_id,
                                 output_parent):
    """Persist only genuine recorded source stems from a verified original Take.

    The trusted 01F protected host owns the output path and has already
    completed native Cycles + independent Blender reopen before calling this.
    The original 48k mono tracks remain separate: mixing needs independent
    creator audio policy and is NOT implied by a successful stem receipt.
    """
    if not isinstance(index,FilmIndex):
        raise TypeError("Original FilmIndex and preserved project identity required")
    _require_pid(project_id)
    from backend.nvp_film_index import _id
    _id(world_take_id, "original Film01E world Take")
    parent=Path(output_parent)
    if (parent.exists() or parent.is_symlink() or
            not parent.parent.is_dir() or parent.parent.is_symlink()):
        raise PermissionError("Only a fresh host-owned original stem output directory")
    captured=OpenUSDWorldTakeCapture(
        index, verify_creator_action=lambda *_: False)
    witness=captured.verify_take(project_id,world_take_id)
    if witness.get("status")!="VERIFIED_ORIGINAL_WORLD_SOURCE_DATA_TAKE":
        raise PermissionError("Original world Take source verification was not successful")
    world=index.read_revision(project_id,world_take_id,1)
    data=world["data"]
    if (world["kind"]!="take" or data.get("format")!=WORLD_TAKE_FORMAT or
            witness.get("world_take_sha256",world["document_sha256"])!=
                world["document_sha256"]):
        raise RuntimeError("Original world Take identity changed before PCM reopening")
    sources=data.get("original_timeline_audio_sources")
    if type(sources) is not list or not 1<=len(sources)<=MAX_STEMS:
        raise PermissionError("Source film needs a finite nonempty original PCM stem list")
    audio=RecordedSoundSources(index)
    prepared=[]
    total_bytes=0
    unique=set()
    for n,src in enumerate(sources):
        if type(src) is not dict or not all(k in src for k in (
            "set","source_take_id","event_id","original_source_id",
            "original_source_revision","original_source_document_sha256",
            "sample_rate_hz","sample_count","original_PCM_not_remixed")):
            raise RuntimeError("Original world source PCM descriptor malformed")
        key=(src["set"],src["source_take_id"],src["event_id"],
             src["original_source_id"],src["original_source_revision"])
        if key in unique:
            raise RuntimeError("Original world contains duplicated same audio event")
        unique.add(key)
        if (src["sample_rate_hz"]!=SAMPLE_RATE or
                src["original_PCM_not_remixed"] is not True or
                type(src["sample_count"]) is not int or
                src["sample_count"]<1):
            raise RuntimeError("Original mono recorded PCM event was altered")
        _sha(src["original_source_document_sha256"])
        record=audio.describe(project_id,src["original_source_id"],
                              src["original_source_revision"])
        if (record["document_sha256"]!=src["original_source_document_sha256"] or
                record["data"]["sample_count"]!=src["sample_count"]):
            raise RuntimeError("Original PCM source bytes/revision changed")
        total_bytes+=src["sample_count"]*2
        if total_bytes>MAX_TOTAL_PCM_BYTES:
            raise PermissionError("Finite source stem audit exceeds worker memory/disk budget")
        prepared.append((n,src,record))
    # The original world Take has been verified; all sources are reobserved
    # before any output is created, and no original FilmIndex blob is edited.
    parent.mkdir(mode=0o700)
    rows=[]
    for n,src,record in prepared:
        label=("stem_%03d_"%n)+sha256(_canon([
            src["set"],src["source_take_id"],src["event_id"],
            src["original_source_id"],src["original_source_revision"]
        ])).hexdigest()[:16]+".wav"
        target=parent/label
        pcm_sha=sha256()
        with target.open("xb") as stream:
            with wave.open(stream,"wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(SAMPLE_RATE)
                for first in range(0,src["sample_count"],MAX_READ_SAMPLES):
                    block=audio.read(
                        project_id,src["original_source_id"],
                        src["original_source_revision"],first,
                        min(MAX_READ_SAMPLES,src["sample_count"]-first))
                    pcm_sha.update(block)
                    wav.writeframesraw(block)
            stream.flush()
            os.fsync(stream.fileno())
        reopened=_reopen_wav(target,src["sample_count"],pcm_sha.hexdigest())
        rows.append({
            "set":src["set"],"source_take_id":src["source_take_id"],
            "event_id":src["event_id"],
            "source_id":src["original_source_id"],
            "source_revision":src["original_source_revision"],
            "source_document_sha256":record["document_sha256"],
            "source_samples":src["sample_count"],
            "sample_rate":SAMPLE_RATE,"channels":1,"sample_encoding":"pcm16le",
            "file":label,"file_sha256":reopened,
            "original_pcm_sha256":pcm_sha.hexdigest(),
            "original_pcm_unmixed":True,
        })
    if index.read_revision(project_id,world_take_id,1)["document_sha256"]!=world["document_sha256"]:
        raise RuntimeError("Original world source changed while its stems were derived")
    result={
        "format":FORMAT,"project_id":project_id,
        "world_take_id":world_take_id,
        "world_take_sha256":world["document_sha256"],
        "stem_count":len(rows),"pcm_source_bytes_reopened":total_bytes,
        "original_stems":rows,
        "actual_original_pcm_readback_verified":True,
        "original_audio_not_mixed_or_mastered":True,
        "final_picture_sound_mux_verified":False,
        "film_master_approved":False,
    }
    with (parent/"source_stems_manifest.json").open("xb") as stream:
        stream.write(_canon(result))
        stream.flush()
        os.fsync(stream.fileno())
    return result
