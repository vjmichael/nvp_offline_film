"""USD-FILM-01F — real original 48 kHz PCM stems for world-rendered shots.

Non-mastered source review only. Every source WAV is derived by bounded reads
of existing FilmIndex PCM chunks from the same verified 01E world Take. This
DOES NOT do gain/mix, soundtrack cue alignment, editing or picture mux; NVP's
existing AUDIO01 editor/mastering pipeline owns those later work orders.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import wave

from backend.nvp_data_av_source import RecordedSoundSources,SAMPLE_RATE
from backend.nvp_film_index import FilmIndex,_require_pid,_id
from backend.nvp_usd_film01e_world_take import OpenUSDWorldTakeCapture

MAX_STEMS=16
MAX_SOURCE_PCM_BYTES=32*1024*1024
READ_SAMPLES=8192


def render_original_source_stems(index, pid, world_take_id, directory):
    """Save original mono PCM source signals as inspectable native WAVs."""
    if not isinstance(index,FilmIndex):
        raise TypeError("Use original FilmIndex audio source authority")
    _require_pid(pid)
    _id(world_take_id,"world source Take")
    target=Path(directory)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Only a fresh private original source stem folder")
    take=OpenUSDWorldTakeCapture(
        index,verify_creator_action=lambda *_:False)
    report=take.verify_take(pid,world_take_id)
    if report["status"]!="VERIFIED_ORIGINAL_WORLD_SOURCE_DATA_TAKE":
        raise RuntimeError("Original world Take audio cannot be verified")
    source=index.read_revision(pid,world_take_id,1)
    audio=source["data"]["original_timeline_audio_sources"]
    if type(audio) is not list or not 1<=len(audio)<=MAX_STEMS:
        raise ValueError("Only 1–16 exact original audio source events in this probe")
    reader=RecordedSoundSources(index)
    target.mkdir(mode=0o700)
    proof=[]
    try:
        for i,item in enumerate(audio):
            if item["sample_rate_hz"]!=SAMPLE_RATE or (
                item["ticks_per_original_pcm_sample"]!=147000):
                raise PermissionError("Audio source Film Time/PCM contract changed")
            original=reader.describe(
                pid,item["original_source_id"],
                item["original_source_revision"])
            data=original["data"]
            if (original["document_sha256"]!=
                    item["original_source_document_sha256"] or
                data["sample_count"]!=item["sample_count"] or
                data["sample_count"]*2>MAX_SOURCE_PCM_BYTES):
                raise RuntimeError("Wrong original source PCM or oversize stem")
            label="source_event_"+str(i).zfill(2)+".wav"
            path=target/label
            if path.exists() or path.is_symlink():
                raise PermissionError("Original PCM output stem was replaced")
            ess=sha256()
            # wave preserves every original signed 16-bit LE sample intact;
            # it does not invoke TTS, resampling, effects, audio conversion,
            # gain scaling or another sound engine.
            flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_BINARY",0)
            handle=os.open(path,flags,0o600)
            with os.fdopen(handle,"wb") as out:
                with wave.open(out,"wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(SAMPLE_RATE)
                    first=0
                    while first<data["sample_count"]:
                        take_samples=min(READ_SAMPLES,data["sample_count"]-first)
                        chunk=reader.read(
                            pid,item["original_source_id"],
                            item["original_source_revision"],
                            first,take_samples)
                        ess.update(chunk)
                        wav.writeframesraw(chunk)
                        first+=take_samples
            with wave.open(str(path),"rb") as wav:
                if (wav.getnchannels()!=1 or wav.getframerate()!=SAMPLE_RATE or
                    wav.getsampwidth()!=2 or
                    wav.getnframes()!=data["sample_count"]):
                    raise RuntimeError("Exported original PCM WAV source parameters wrong")
                actual=sha256()
                while True:
                    chunk=wav.readframes(READ_SAMPLES)
                    if not chunk:
                        break
                    actual.update(chunk)
            if actual.hexdigest()!=ess.hexdigest():
                raise RuntimeError("Independent source WAV readback changed PCM essence")
            proof.append({
                "event_id":item["event_id"],
                "original_world_take_sha256":source["document_sha256"],
                "source_audio_id":item["original_source_id"],
                "source_audio_revision":item["original_source_revision"],
                "source_audio_document_sha256":original["document_sha256"],
                "original_event_start_tick":item["event_start_tick"],
                "original_event_end_tick":item["event_end_tick"],
                "wave_file":label,
                "original_pcm_essence_sha256":ess.hexdigest(),
                "real_wav_sha256":sha256(path.read_bytes()).hexdigest(),
                "sample_count":data["sample_count"],
                "sample_rate":SAMPLE_RATE,
                "gain_processing_applied":False,
                "real_original_sound_not_final_mix":True,
            })
        return {
            "format":"nvp.usd_film01f.original_pcm_source_stems.v1",
            "world_take_id":world_take_id,
            "world_take_sha256":source["document_sha256"],
            "original_source_stems":proof,
            "actual_original_pcm_readback_verified":True,
            "source_gain_or_mastering_applied":False,
            "final_picture_sound_mux_verified":False,
            "real_film_auditory_performance_approved":False,
        }
    except Exception:
        # Technical PCM stage was not accepted. Remove its partial files;
        # source stored in FilmIndex was never changed.
        import shutil
        shutil.rmtree(target)
        raise
