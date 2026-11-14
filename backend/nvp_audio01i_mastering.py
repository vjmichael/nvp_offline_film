"""AUDIO-01I: bounded, immutable PCM24 mastering candidates.

No worker may approve its own final mix or delivery. This produces an
unapproved candidate from the currently ACCEPTed AUDIO-01H composite.
Actual executable scheduling/authorization belongs to the native host.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

from backend.nvp_audio01i_fault_matrix import crash_after
from backend.nvp_audio01h_mix_decision import FORMAT as DECISION_FORMAT
from backend.nvp_audio01h_stem_revision import FORMAT as AUTOMATED_FORMAT
from backend.nvp_film_index import _id

FORMAT="nvp.audio01i.master_candidate.v1"
PROFILES={
    "archive_pcm24_v1":{"normalize":False,"target_lufs":None,"ceiling_dbtp":None},
    "streaming_pcm24_v1":{"normalize":True,"target_lufs":-16.0,"ceiling_dbtp":-1.5},
}
RATE=48000
MAX_SAMPLES=960000


def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as inp:
        for part in iter(lambda:inp.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()


def _run(args,timeout=180):
    result=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,
                          check=False,timeout=timeout)
    if result.returncode:
        raise RuntimeError("Native mastering failed: "+
                           result.stderr.decode("utf8","replace")[-1000:])
    return result


def inspect_native(path,ffmpeg,ffprobe,expected_samples):
    """Use ffprobe for real PCM24 stream and loudnorm for measured BS.1770 data."""
    path=Path(path)
    result=_run([str(ffprobe),"-v","error","-show_streams","-of","json",str(path)])
    streams=json.loads(result.stdout)["streams"]
    if len(streams)!=1 or streams[0].get("codec_type")!="audio":
        raise RuntimeError("Master must have exactly one audio stream")
    info=streams[0]
    if (info.get("codec_name")!="pcm_s24le" or
        int(info.get("sample_rate",0))!=RATE or int(info.get("channels",0))!=2):
        raise RuntimeError("Master requires 48 kHz stereo PCM24")
    # Decode the full stream and count actual PCM24 samples. WAV headers may
    # use WAVE_FORMAT_EXTENSIBLE, which Python 3.11 wave cannot parse.
    raw=_run([str(ffmpeg),"-nostdin","-v","error","-xerror","-i",str(path),
              "-map","0:a:0","-ac","2","-ar","48000",
              "-c:a","pcm_s24le","-f","s24le","pipe:1"])
    if len(raw.stdout)!=expected_samples*6:
        raise RuntimeError("Decoded PCM24 sample clock mismatched picture")
    run=_run([str(ffmpeg),"-nostdin","-hide_banner","-v","info","-i",str(path),
              "-map","0:a:0","-af","loudnorm=I=-23:TP=-2:LRA=7:print_format=json",
              "-f","null","-"])
    output=run.stderr.decode("utf8","replace")
    blocks=re.findall(r'\{[^{}]*"input_i"[^{}]*"input_tp"[^{}]*\}',output,re.S)
    if len(blocks)!=1:
        raise RuntimeError("Missing unambiguous real loudness analysis")
    info=json.loads(blocks[0])
    values={}
    for k in ("input_i","input_tp","input_lra","input_thresh"):
        try: value=float(info[k])
        except (ValueError,TypeError,KeyError) as exc:
            raise RuntimeError("Malformed mastering loudness measurement") from exc
        if not math.isfinite(value):
            raise RuntimeError("Silent or invalid mastering evidence")
        values[k]=value
    return {"integrated_lufs":values["input_i"],"true_peak_dbtp":values["input_tp"],
            "loudness_range_lu":values["input_lra"],
            "samples_per_channel":expected_samples,"sample_rate":RATE,"channels":2,
            "bit_depth":24,"measurement":"ffmpeg_loudnorm_ebu_r128"}


def accepted_source(capture,project_id,decision_id,decision_revision):
    """No stale approval: decision must be CURRENT HEAD and ACCEPT."""
    if type(decision_revision) is not int or decision_revision<1:
        raise ValueError("Explicit decision revision required")
    current=capture.index.read_revision(project_id,decision_id)
    if current["revision"]!=decision_revision or current["kind"]!="audio":
        raise PermissionError("Old mix decision cannot authorize mastering")
    decision=current["data"]
    if (decision.get("format")!=DECISION_FORMAT or
        decision.get("decision")!="ACCEPT" or
        decision.get("final_mix") is not True or
        decision.get("director_approved") is not True or
        decision.get("final_master") is not False):
        raise PermissionError("Current creator mix acceptance required")
    original=capture.index.read_revision(project_id,decision["source_audio_id"],1)
    data=original["data"]
    if (original["document_sha256"]!=decision["source_audio_sha256"] or
        data.get("format")!=AUTOMATED_FORMAT or
        data.get("source_stem_id") is not None or
        data.get("automated_wav_sha256")!=decision["wav_sha256"]):
        raise RuntimeError("Decision not bound to immutable approved composite")
    indexed=capture.index.verify_media_file(project_id,decision["wav_sha256"],"audio/wav")
    return current,original,Path(indexed["path"])


def render_candidate(capture,project_id,decision_id,decision_revision,candidate_id,
                     profile,destination,*,ffmpeg="ffmpeg",ffprobe="ffprobe"):
    """Make an unapproved master candidate, never a final delivery."""
    _id(candidate_id,"master candidate ID")
    if profile not in PROFILES:
        raise ValueError("Unknown mastering target profile")
    decision,source,wav=accepted_source(capture,project_id,decision_id,decision_revision)
    samples=source["data"]["samples_per_channel"]
    if type(samples) is not int or samples<1 or samples>MAX_SAMPLES:
        raise RuntimeError("Unbounded or invalid picture/sample clock")
    target=Path(destination)
    if (target.exists() or target.is_symlink() or
        target.parent.is_symlink() or not target.parent.is_dir() or
        target.suffix.lower()!=".wav"):
        raise RuntimeError("Master candidate must be an absent WAV destination")
    try: capture.index.read_revision(project_id,candidate_id)
    except KeyError: pass
    else: raise RuntimeError("Master candidate identity already used")
    original_sha=sha_file(wav)
    setting=PROFILES[profile]
    audio_filter=[]
    if setting["normalize"]:
        # A new, independently measured candidate is required; the filter is
        # not presumed to hit an exact target on short or highly dynamic audio.
        audio_filter=["-af","loudnorm=I=-16:TP=-1.5:LRA=11:print_format=summary"]
    _run([str(ffmpeg),"-nostdin","-hide_banner","-v","error","-xerror",
          "-i",str(wav),"-map","0:a:0","-vn",*audio_filter,
          "-ar","48000","-ac","2","-c:a","pcm_s24le","-f","wav",str(target)])
    try:
        measured=inspect_native(target,ffmpeg,ffprobe,samples)
        if setting["normalize"] and measured["true_peak_dbtp"] > setting["ceiling_dbtp"]+0.1:
            raise RuntimeError("Candidate exceeds explicit true-peak ceiling")
        if sha_file(wav)!=original_sha or original_sha!=source["data"]["automated_wav_sha256"]:
            raise RuntimeError("Accepted source changed during mastering")
        stored=capture.index.put_media_file(project_id,target,"audio/wav")
        document={
            "format":FORMAT,"status":"unapproved_master_candidate",
            "profile":profile,"project_id":project_id,
            "decision_id":decision_id,"decision_revision":decision_revision,
            "decision_sha256":decision["document_sha256"],
            "mix_id":source["object_id"],"mix_sha256":source["document_sha256"],
            "source_wav_sha256":original_sha,
            "candidate_wav_sha256":stored["sha256"],
            "samples_per_channel":samples,"analysis":measured,
            "final_mix":True,"master_approved":False,
            "final_master":False,"delivered":False
        }
        result=capture.index.register_revision(
            project_id,candidate_id,"audio",document,expected_revision=0,
            dependencies=[
                {"object_id":decision_id,"revision":decision_revision,"role":"audio"},
                {"object_id":source["object_id"],"revision":1,"role":"audio"}])
        crash_after("candidate_filmindex_registered")
        return {"status":"UNAPPROVED_MASTER_CANDIDATE",
                "document_sha256":result["document_sha256"],
                "candidate_id":candidate_id,"wav_sha256":stored["sha256"],
                "analysis":measured,"final_master":False}
    except BaseException:
        # Keep interrupted artifact inspectable; no false published revision.
        raise
