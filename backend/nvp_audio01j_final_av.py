"""AUDIO-01J immutable final-picture / approved PCM24 audio MOV export.

The worker makes a new ProRes picture-stream-copy + PCM24 MOV. This function
does NOT grant authorization; the trusted host must verify creator consent
and contained worker admission before invoking it.
"""
from __future__ import annotations
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess

from backend.nvp_audio01j_picture_lock import validate_picture_lock
from backend.nvp_audio01i_native_host import DELIVERY as AUDIO_DELIVERY
from backend.nvp_audio01i_mastering import sha_file
from backend.nvp_audio01f_picture_sound import _decoded_sha
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_film_index import _id

FORMAT="nvp.audio01j.final_av_master.v1"
FPS=24
RATE=48000
MAX_FRAMES=480


def _run(command,timeout=600):
    p=subprocess.run(command,stdin=subprocess.DEVNULL,
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     timeout=timeout,check=False)
    if p.returncode:
        raise RuntimeError("Native AV operation failed: "+
                           p.stderr.decode("utf8","replace")[-1000:])
    return p.stdout


def _audio_decoded(movie,ffmpeg,expected_samples):
    """Hash entire decoded stereo PCM24; refuse padding, trimming, resampling."""
    raw=_run([str(ffmpeg),"-nostdin","-v","error","-xerror","-i",str(movie),
              "-map","0:a:0","-c:a","pcm_s24le","-f","s24le","pipe:1"],timeout=240)
    if len(raw)!=expected_samples*6:
        raise RuntimeError("Decoded output audio differs from picture clock")
    return hashlib.sha256(raw).hexdigest()


def verify_mux(movie,source_video,source_audio,frames,*,ffmpeg,ffprobe):
    if type(frames) is not int or not 1<=frames<=MAX_FRAMES:
        raise ValueError("Invalid native AV frame count")
    streams=json.loads(_run([str(ffprobe),"-v","error","-count_frames",
        "-show_streams","-of","json",str(movie)],timeout=180))["streams"]
    if len(streams)!=2 or [s.get("codec_type") for s in streams]!=["video","audio"]:
        raise RuntimeError("Expected exactly one video and one audio track")
    v,a=streams
    if (v.get("r_frame_rate")!="24/1" or int(v.get("nb_read_frames",0))!=frames
        or a.get("codec_name")!="pcm_s24le"
        or int(a.get("sample_rate",0))!=RATE
        or int(a.get("channels",0))!=2):
        raise RuntimeError("Picture frame clock or final PCM24 format changed")
    expected=Fraction(frames,FPS)
    for stream in (v,a):
        duration=stream.get("duration")
        if duration in (None,"N/A") or abs(Fraction(str(duration))-expected)>Fraction(1,RATE):
            raise RuntimeError("MOV audio/video streams are not sample-clock synchronized")
    first,_=_decoded_sha(source_video,"video",ffmpeg)
    last,_=_decoded_sha(movie,"video",ffmpeg)
    if first!=last:
        raise RuntimeError("Final picture pixels differ from locked B14 source")
    expected_sha=_audio_decoded(source_audio,ffmpeg,frames*2000)
    actual_sha=_audio_decoded(movie,ffmpeg,frames*2000)
    if actual_sha!=expected_sha:
        raise RuntimeError("Final mux changed approved PCM24 samples")
    return {"fps":FPS,"frames":frames,"sample_rate":RATE,
            "samples_per_channel":frames*2000,"video_decoded_sha256":last,
            "audio_pcm24_decoded_sha256":actual_sha,
            "mov_sha256":sha_file(movie)}


def approved_inputs(capture,project_id,lock_id,audio_delivery_id,movie_dir,audio_dir):
    lock,picture=validate_picture_lock(capture,project_id,lock_id)
    audio=capture.index.read_revision(project_id,audio_delivery_id,1)
    data=audio["data"]
    if (audio["kind"]!="audio" or data.get("format")!=AUDIO_DELIVERY
        or data.get("status")!="creator_approved_final_audio"
        or data.get("final_master") is not True
        or data.get("director_approved") is not True
        or data.get("dcp_delivered") is not False):
        raise PermissionError("Only approved final AUDIO-01I delivery can be muxed")
    picture_file=Path(movie_dir)/(picture["data"]["profile"]+".mov")
    audio_file=Path(audio_dir)/"master.wav"
    if any(x.is_symlink() or not x.is_file() for x in (picture_file,audio_file)):
        raise RuntimeError("Final AV sources missing or symlinked")
    if (sha_file(picture_file)!=picture["data"]["movie_sha256"] or
        sha_file(audio_file)!=data["wav_sha256"]):
        raise RuntimeError("Final AV source file bytes changed")
    capture.index.verify_media_file(
        project_id,picture["data"]["movie_sha256"],"video/quicktime")
    capture.index.verify_media_file(project_id,data["wav_sha256"],"audio/wav")
    frames=lock["data"]["frame_count"]
    if (frames<1 or frames>MAX_FRAMES or
        frames*2000!=data["analysis"]["samples_per_channel"]):
        raise RuntimeError("Approved picture and audio sample clocks disagree")
    return lock,picture,audio,picture_file,audio_file,frames


def export_final_av(capture,project_id,lock_id,audio_delivery_id,
                    movie_dir,audio_dir,output_dir,export_id,*,ffmpeg,ffprobe):
    """Atomic directory publication; never reuse interrupted stage or ID."""
    _id(export_id,"final audiovisual export ID")
    try:capture.index.read_revision(project_id,export_id)
    except KeyError:pass
    else:raise RuntimeError("Final AV identity already exists")
    lock,picture,audio,video,wav,frames=approved_inputs(
        capture,project_id,lock_id,audio_delivery_id,movie_dir,audio_dir)
    dest=Path(output_dir)
    stage=dest.with_name("."+dest.name+".audio01j.stage")
    if (dest.exists() or dest.is_symlink() or stage.exists() or stage.is_symlink()
        or dest.parent.is_symlink() or not dest.parent.is_dir()):
        raise RuntimeError("AV export destination must be absent, without stale staging")
    stage.mkdir(mode=0o700)
    mov=stage/"final_picture_sound.mov"
    _run([str(ffmpeg),"-nostdin","-hide_banner","-v","error","-xerror",
        "-i",str(video),"-i",str(wav),"-map","0:v:0","-map","1:a:0",
        "-c:v","copy","-c:a","pcm_s24le","-ar","48000","-ac","2",
        "-f","mov",str(mov)],timeout=600)
    proof=verify_mux(mov,video,wav,frames,ffmpeg=ffmpeg,ffprobe=ffprobe)
    if (sha_file(video)!=picture["data"]["movie_sha256"] or
        sha_file(wav)!=audio["data"]["wav_sha256"]):
        raise RuntimeError("Approved AV source was replaced during mux")
    indexed=capture.index.put_media_file(project_id,mov,"video/quicktime")
    if indexed["sha256"]!=proof["mov_sha256"]:
        raise RuntimeError("Indexed AV output changed on publication")
    doc={"format":FORMAT,"status":"approved_final_audiovisual_master",
         "project_id":project_id,"picture_lock_id":lock_id,
         "picture_lock_sha256":lock["document_sha256"],
         "picture_source_sha256":picture["document_sha256"],
         "audio_delivery_id":audio_delivery_id,
         "audio_delivery_sha256":audio["document_sha256"],
         "original_video_sha256":picture["data"]["movie_sha256"],
         "original_audio_sha256":audio["data"]["wav_sha256"],
         "rendered_mov_sha256":indexed["sha256"],
         "rendered_mov_bytes":indexed["size_bytes"],
         "movie_filename":"final_picture_sound.mov",
         **proof,"picture_locked":True,"final_mix":True,
         "director_approved":True,"final_master":True,
         "dcp_delivered":False}
    manifest=stage/"final_av_manifest.json"
    with manifest.open("xb") as f:
        f.write(canonical_bytes(doc));f.flush();os.fsync(f.fileno())
    with mov.open("r+b") as f:
        f.flush();os.fsync(f.fileno())
    os.replace(stage,dest)
    if os.name=="posix":
        fd=os.open(str(dest.parent),os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
        try:os.fsync(fd)
        finally:os.close(fd)
    record=capture.index.register_revision(
        project_id,export_id,"master",doc,expected_revision=0,
        dependencies=[
            {"object_id":lock_id,"revision":1,"role":"presentation"},
            {"object_id":audio_delivery_id,"revision":1,"role":"audio"}])
    return {"status":"FINAL_AV_MASTER_PUBLISHED","export_id":export_id,
            "document_sha256":record["document_sha256"],
            "mov_sha256":indexed["sha256"],"frames":frames,
            "final_master":True,"dcp_delivered":False}


def verify_final_av(capture,project_id,export_id,output_dir,movie_dir,audio_dir,*,
                    ffmpeg,ffprobe):
    row=capture.index.read_revision(project_id,export_id,1)
    doc=row["data"];root=Path(output_dir)
    if row["kind"]!="master" or doc.get("format")!=FORMAT:
        raise RuntimeError("Not an indexed final audiovisual master")
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Missing final AV publication")
    manifest=root/"final_av_manifest.json";mov=root/"final_picture_sound.mov"
    if (manifest.is_symlink() or mov.is_symlink()
        or manifest.read_bytes()!=canonical_bytes(doc)
        or sha_file(mov)!=doc["rendered_mov_sha256"]
        or mov.stat().st_size!=doc["rendered_mov_bytes"]):
        raise RuntimeError("Final AV manifest or native movie bytes changed")
    lock,picture,audio,video,wav,frames=approved_inputs(
        capture,project_id,doc["picture_lock_id"],
        doc["audio_delivery_id"],movie_dir,audio_dir)
    if (lock["document_sha256"]!=doc["picture_lock_sha256"]
        or audio["document_sha256"]!=doc["audio_delivery_sha256"]
        or picture["document_sha256"]!=doc["picture_source_sha256"]):
        raise RuntimeError("Immutable source approvals changed")
    capture.index.verify_media_file(
        project_id,doc["rendered_mov_sha256"],"video/quicktime")
    proof=verify_mux(mov,video,wav,frames,ffmpeg=ffmpeg,ffprobe=ffprobe)
    if any(proof[k]!=doc[k] for k in proof):
        raise RuntimeError("Published movie no longer decodes to approved AV")
    return {"status":"VERIFIED_FINAL_AV_MASTER","frames":frames,
            "final_master":True,"dcp_delivered":False}
