"""AUDIO-01F: exact-clock multitrack sound attached to a verified B14 picture.

Worker-side technical review only. Trusted native host MUST authorize paths,
resources and subprocess. Sources remain immutable and unapproved. The silent
B14 picture is stream-copied; verified 48 kHz 16-bit stereo composite is muxed.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
import wave

from backend.nvp_b14_edited_movie import verify_edited_technical_mov
from backend.nvp_audio01e_wav_publication import (
    FORMAT as AUDIO_FORMAT, verify_published_wavs,
)
from backend.nvp_film_index import _id
from backend.nvp_audio01g_fault_matrix import crash_after

FORMAT="nvp.audio01f.picture_sound_technical_preview.v1"
FPS=24
RATE=48000
SAMPLES_PER_FRAME=RATE//FPS
MAX_FRAMES=480


def _sha_file(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      allow_nan=False,ensure_ascii=True).encode("ascii")


def _run(command, *, stdout=None, timeout=600):
    done=run_owned_subprocess(command,stdout=stdout or subprocess.PIPE,
                        stderr=subprocess.PIPE,stdin=subprocess.DEVNULL,
                        timeout=timeout,check=False)
    if done.returncode!=0:
        raise RuntimeError("Native media operation failed: "+
                           done.stderr.decode("utf8","replace")[-1200:])
    return done.stdout


def _probe(movie,ffprobe):
    raw=_run([ffprobe,"-v","error","-count_frames","-show_streams",
              "-of","json",str(movie)],timeout=180)
    return json.loads(raw.decode("utf8"))["streams"]


def _duration(stream):
    value=stream.get("duration")
    if value in (None,"N/A"):
        raise RuntimeError("Media stream has no independently measurable duration")
    return Fraction(str(value))


def _verify_streams(movie, frames, ffprobe):
    streams=_probe(movie,ffprobe)
    if len(streams)!=2 or [x.get("codec_type") for x in streams]!=["video","audio"]:
        raise RuntimeError("Review movie requires exactly one picture and one audio stream")
    vid,aud=streams
    if (vid.get("r_frame_rate")!="24/1" or
        int(vid.get("nb_read_frames",0))!=frames or
        aud.get("codec_name")!="pcm_s16le" or
        int(aud.get("sample_rate",0))!=RATE or
        int(aud.get("channels",0))!=2):
        raise RuntimeError("Picture/audio stream format or frame count changed")
    expected=Fraction(frames,FPS)
    # MOV timescales can be rounded by a single 48 kHz tick, not one frame.
    if abs(_duration(vid)-expected)>Fraction(1,RATE):
        raise RuntimeError("Picture duration drifted")
    if abs(_duration(aud)-expected)>Fraction(1,RATE):
        raise RuntimeError("Sound duration drifted")
    return {"frames":frames,"fps":FPS,"samples_per_channel":frames*SAMPLES_PER_FRAME,
            "audio_rate":RATE,"audio_channels":2}


def _decoded_sha(movie, stream, ffmpeg):
    """Bounded-memory full decode; hash decoded pixel/PCM bytes, never the MOV container."""
    if stream=="video":
        args=["-map","0:v:0","-pix_fmt","yuv422p10le","-f","rawvideo"]
        unit=1
    elif stream=="audio":
        args=["-map","0:a:0","-ar","48000","-ac","2",
              "-acodec","pcm_s16le","-f","s16le"]
        unit=4
    else:
        raise ValueError("Unrecognized stream")
    if os.name == "nt":
        raise RuntimeError("Legacy direct-pipe FFmpeg decode cannot run outside the release-owned native decoder")
    proc=subprocess.Popen([ffmpeg,"-nostdin","-hide_banner","-v","error",
                           "-xerror","-i",str(movie),*args,"pipe:1"],
                          stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    sha=hashlib.sha256()
    count=0
    try:
        for chunk in iter(lambda:proc.stdout.read(1024*1024),b""):
            count+=len(chunk)
            if count>2*1024*1024*1024:
                proc.kill()
                raise RuntimeError("Technical preview decode exceeds 2GiB bound")
            sha.update(chunk)
        code=proc.wait(timeout=180)
        if code:
            raise RuntimeError("Decoded technical movie stream failed: "+
                               proc.stderr.read().decode("utf8","replace")[-800:])
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=15)
        proc.stdout.close()
        proc.stderr.close()
    if count%unit:
        raise RuntimeError("Decoded PCM bytes have incomplete samples")
    return sha.hexdigest(),count


def _wav_pcm_proof(path):
    sha=hashlib.sha256()
    count=0
    with wave.open(str(path),"rb") as wav:
        if wav.getnchannels()!=2 or wav.getsampwidth()!=2 or wav.getframerate()!=RATE or wav.getcomptype()!="NONE":
            raise RuntimeError("Only uncompressed source stereo PCM16 at 48kHz accepted")
        frames=wav.getnframes()
        while True:
            part=wav.readframes(1024*64)
            if not part:
                break
            sha.update(part)
            count+=len(part)
    if count!=frames*4:
        raise RuntimeError("Indexed WAV frame length changed")
    return sha.hexdigest(),frames,count


def mux_picture_sound_review(picture_mov, mix_wav, output_mov, *,
                             frames, ffmpeg="ffmpeg", ffprobe="ffprobe"):
    """Mux and independently verify the exact 24:48k picture/sound clock."""
    if type(frames) is not int or not 1<=frames<=MAX_FRAMES:
        raise ValueError("Initial picture conform limited to 480 frames")
    movie=Path(picture_mov)
    wav=Path(mix_wav)
    out=Path(output_mov)
    if any(p.is_symlink() or not p.is_file() for p in (movie,wav)):
        raise RuntimeError("Missing or symlinked immutable media source")
    if (out.is_symlink() or out.exists() or
        out.parent.is_symlink() or not out.parent.is_dir()):
        raise RuntimeError("Technical review destination must be absent")
    if not shutil.which(ffmpeg) or not shutil.which(ffprobe):
        raise RuntimeError("Real FFmpeg and FFprobe executables required")
    pcmsha,n,pcmbytes=_wav_pcm_proof(wav)
    if n!=frames*SAMPLES_PER_FRAME:
        raise RuntimeError("Sound samples do not match exact picture frame duration")
    before,_=_decoded_sha(movie,"video",ffmpeg)
    # Never trim/truncate mismatched media using -shortest or audio padding.
    _run([ffmpeg,"-nostdin","-hide_banner","-v","error","-xerror",
          "-i",str(movie),"-i",str(wav),
          "-map","0:v:0","-map","1:a:0","-c:v","copy",
          "-c:a","pcm_s16le","-ar","48000","-ac","2",
          "-movflags","+faststart","-f","mov",str(out)],timeout=600)
    timing=_verify_streams(out,frames,ffprobe)
    after,_=_decoded_sha(out,"video",ffmpeg)
    output_audio,read_bytes=_decoded_sha(out,"audio",ffmpeg)
    if before!=after or output_audio!=pcmsha or read_bytes!=pcmbytes:
        raise RuntimeError("Mux changed frozen picture pixels or exact soundtrack PCM")
    return {**timing,"picture_decoded_sha256":after,
            "audio_decoded_pcm_sha256":output_audio,
            "mov_sha256":_sha_file(out)}


def build_picture_sound_preview(capture,project_id,candidate_id,audio_id,
                                package,conform_dir,movie_dir,audio_dir,
                                audio_plan,audio_sources,audio_chunks,
                                destination,presentation_id,*,
                                ffmpeg="ffmpeg",ffprobe="ffprobe"):
    """Bind immutable B14 picture and AUDIO-01E stems into unapproved review MOV."""
    _id(presentation_id,"picture-sound presentation ID")
    try:
        capture.index.read_revision(project_id,presentation_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Picture-sound presentation already registered")
    candidate=capture.index.read_revision(project_id,candidate_id,1)
    audio=capture.index.read_revision(project_id,audio_id,1)
    picdata=candidate["data"]
    auddata=audio["data"]
    if (candidate["kind"]!="presentation" or audio["kind"]!="audio" or
        auddata.get("format")!=AUDIO_FORMAT or
        auddata.get("picture_bound") is not False or
        auddata.get("final_mix") is not False or
        picdata.get("audio_included") is not False or
        picdata.get("approved_final_master") is not False):
        raise RuntimeError("Only unapproved independently indexed source media supported")
    picproof=verify_edited_technical_mov(capture,project_id,candidate_id,
                                         package,conform_dir,movie_dir,
                                         ffmpeg=ffmpeg,ffprobe=ffprobe)
    samples=picdata["frame_count"]*SAMPLES_PER_FRAME
    if samples!=auddata["total_samples_per_channel"]:
        raise RuntimeError("Sound and original picture clocks differ")
    audproof=verify_published_wavs(capture,project_id,audio_id,audio_plan,
                                   audio_sources,samples,audio_chunks,audio_dir)
    if audproof["status"]!="VERIFIED_UNAPPROVED_INDEXED_WAV_PREVIEW":
        raise RuntimeError("Audio source failed independent replay")
    mix=next((x for x in auddata["wav_outputs"] if x["stem_id"] is None),None)
    if mix is None or mix["filename"]!="mix_preview.wav":
        raise RuntimeError("AUDIO-01E has no verified composite")
    source=Path(movie_dir)/picdata["movie_path"]
    wav=Path(audio_dir)/mix["filename"]
    if _sha_file(wav)!=mix["sha256"] or _sha_file(source)!=picdata["movie_sha256"]:
        raise RuntimeError("Published frozen inputs changed")
    output=Path(destination)
    if output.exists() or output.is_symlink() or not output.parent.is_dir() or output.parent.is_symlink():
        raise RuntimeError("Picture-sound output must be absent")
    # Keep partial FFmpeg output invisible at the final presentation path.
    # The staging directory and destination must share a filesystem.
    staging=output.with_name(".nvp-audio01g-"+output.name+".stage")
    if staging.exists() or staging.is_symlink():
        raise RuntimeError("Previous interrupted mux staging requires native audit")
    staging.mkdir(mode=0o700)
    crash_after("stage_directory_created")
    mux=staging/"picture_sound_review.mov"
    timing=mux_picture_sound_review(source,wav,mux,
                                    frames=picdata["frame_count"],
                                    ffmpeg=ffmpeg,ffprobe=ffprobe)
    crash_after("mov_bytes_written")
    crash_after("mov_independently_verified")
    indexed=capture.index.put_media_file(project_id,mux,"video/quicktime")
    if indexed["sha256"]!=timing["mov_sha256"]:
        raise RuntimeError("FilmIndex ingest changed review movie")
    crash_after("filmindex_media_ingested")
    document={
        "format":FORMAT,"status":"unapproved_synchronized_picture_sound_review",
        "project_id":project_id,"picture_id":candidate_id,
        "picture_revision":1,"picture_document_sha256":candidate["document_sha256"],
        "original_video_sha256":picdata["movie_sha256"],
        "audio_id":audio_id,"audio_revision":1,
        "audio_document_sha256":audio["document_sha256"],
        "source_mix_sha256":mix["sha256"],
        "rendered_mov_sha256":indexed["sha256"],"rendered_mov_bytes":indexed["size_bytes"],
        "movie_filename":"picture_sound_review.mov",
        **timing,"sample_clock_ratio":"2000_samples_per_24fps_frame",
        "picture_locked":False,"director_approved":False,
        "final_mix":False,"final_master":False,"dcp_delivered":False,
    }
    raw=_canonical(document)
    with (staging/"picture_sound_manifest.json").open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    crash_after("manifest_file_fsynced")
    # A completed, independently decoded MOV and canonical manifest are
    # atomically promoted together. FilmIndex presentation follows promotion,
    # never preceding a partial file. Crash windows retain inspectable orphans.
    with mux.open("r+b") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    crash_after("movie_file_fsynced")
    os.replace(staging,output)
    crash_after("staging_directory_promoted")
    if os.name=="posix":
        fd=os.open(str(output.parent),os.O_RDONLY | getattr(os,"O_DIRECTORY",0))
        try:os.fsync(fd)
        finally:os.close(fd)
    crash_after("destination_parent_fsynced")
    deps=[
        {"object_id":candidate_id,"revision":1,"role":"presentation"},
        {"object_id":audio_id,"revision":1,"role":"audio"},
        {"object_id":picdata["source_edit_id"],
         "revision":picdata["source_edit_revision"],"role":"timeline"},
    ]
    published=capture.index.register_revision(project_id,presentation_id,
        "presentation",document,expected_revision=0,dependencies=deps)
    crash_after("filmindex_presentation_registered")
    return {"status":"VERIFIED_UNAPPROVED_PICTURE_SOUND_REVIEW",
            "document_sha256":published["document_sha256"],
            "presentation_id":presentation_id,**timing,
            "final_master":False}


def verify_picture_sound_preview(capture,project_id,presentation_id,
                                 candidate_id,audio_id,package,conform_dir,
                                 movie_dir,audio_dir,audio_plan,audio_sources,
                                 audio_chunks,destination,*,
                                 ffmpeg="ffmpeg",ffprobe="ffprobe"):
    rec=capture.index.read_revision(project_id,presentation_id,1)
    data=rec["data"]
    if (rec["kind"]!="presentation" or data.get("format")!=FORMAT or
        data.get("status")!="unapproved_synchronized_picture_sound_review" or
        data.get("picture_id")!=candidate_id or data.get("audio_id")!=audio_id or
        any(data.get(k) is not False for k in (
            "picture_locked","director_approved","final_mix","final_master","dcp_delivered"))):
        raise RuntimeError("Review presentation provenance or approval flags changed")
    picture=capture.index.read_revision(project_id,candidate_id,1)
    audio=capture.index.read_revision(project_id,audio_id,1)
    if (picture["document_sha256"]!=data["picture_document_sha256"] or
        audio["document_sha256"]!=data["audio_document_sha256"]):
        raise RuntimeError("Picture or audio revision changed")
    expected=sorted([
        {"object_id":candidate_id,"revision":1,"role":"presentation"},
        {"object_id":audio_id,"revision":1,"role":"audio"},
        {"object_id":picture["data"]["source_edit_id"],
         "revision":picture["data"]["source_edit_revision"],"role":"timeline"}
    ],key=lambda x:(x["object_id"],x["revision"],x["role"]))
    if rec["dependencies"]!=expected:
        raise RuntimeError("Picture-sound FilmIndex dependencies changed")
    verify_edited_technical_mov(capture,project_id,candidate_id,
                                package,conform_dir,movie_dir,
                                ffmpeg=ffmpeg,ffprobe=ffprobe)
    samples=picture["data"]["frame_count"]*SAMPLES_PER_FRAME
    verify_published_wavs(capture,project_id,audio_id,audio_plan,audio_sources,
                          samples,audio_chunks,audio_dir)
    folder=Path(destination)
    manifest=folder/"picture_sound_manifest.json"
    movie=folder/"picture_sound_review.mov"
    if (folder.is_symlink() or not folder.is_dir() or
        manifest.is_symlink() or manifest.read_bytes()!=_canonical(data) or
        movie.is_symlink() or not movie.is_file() or
        _sha_file(movie)!=data["rendered_mov_sha256"] or
        movie.stat().st_size!=data["rendered_mov_bytes"]):
        raise RuntimeError("Review media or FilmIndex manifest changed")
    indexed=capture.index.verify_media_file(project_id,data["rendered_mov_sha256"],
                                            "video/quicktime")
    if indexed["sha256"]!=data["rendered_mov_sha256"]:
        raise RuntimeError("Indexed picture-sound review unavailable")
    timing=_verify_streams(movie,picture["data"]["frame_count"],ffprobe)
    if timing["samples_per_channel"]!=data["samples_per_channel"]:
        raise RuntimeError("Review sample clock changed")
    vsha,_=_decoded_sha(movie,"video",ffmpeg)
    asha,n=_decoded_sha(movie,"audio",ffmpeg)
    srcsha,_=_decoded_sha(Path(movie_dir)/picture["data"]["movie_path"],"video",ffmpeg)
    wavsha,_,bytes_= _wav_pcm_proof(Path(audio_dir)/"mix_preview.wav")
    if (vsha!=srcsha or vsha!=data["picture_decoded_sha256"] or
        asha!=wavsha or asha!=data["audio_decoded_pcm_sha256"] or n!=bytes_):
        raise RuntimeError("Review MOV no longer decodes to identical frozen picture/sound")
    return {"status":"VERIFIED_UNAPPROVED_PICTURE_SOUND_REVIEW",
            "presentation_id":presentation_id,**timing,"final_master":False}
