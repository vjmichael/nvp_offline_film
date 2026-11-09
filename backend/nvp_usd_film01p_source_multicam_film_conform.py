"""USD-FILM-01P: edited 30-second multicamera short + ONE original 48k mix.

Conforms a director-approved EDL from fully verified 01O 720-frame camera
rolls. Each edit cut samples the same actor performance at the same film
time. The SOUND is mixed once from the verified frozen 01E original scene
Take's 48k PCM events, then independently decoded from the finished movie.
This is a technical source-authentic short, not creative/cinema approval.
"""
from __future__ import annotations

from array import array
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
import subprocess
import wave

from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import (
    TICKS_PER_SECOND as T,TemporalLedger)
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_usd_film01f_original_audio import render_original_source_stems
from backend.nvp_usd_film01o_original_camera_roll_source import (
    canonical,file_sha)
from backend.nvp_usd_film01o_recoverable_camera_roll_host import (
    ROLL_FORMAT,CHUNK,CHUNKS_PER_ROLL,
    RecoverableOriginalCameraRolls)

FORMAT="nvp.usd_film01p.one_original_30s_multicam_edited_picture_sound.v1"
FPS=24
FRAMES=720
AUDIO_RATE=48000
SAMPLES=30*AUDIO_RATE
CUT_MAX=96
AUDIO_MAX=16


def _run(command,timeout=180):
    result=subprocess.run(command,check=True,capture_output=True,
                          text=True,timeout=timeout)
    return result.stdout


def _probe(file,ffprobe):
    return json.loads(_run([ffprobe,"-v","error","-count_frames",
        "-show_streams","-show_format","-of","json",str(file)]))


def _decoded_frames(source,ffprobe):
    video=[s for s in _probe(source,ffprobe)["streams"]
           if s["codec_type"]=="video"]
    if len(video)!=1 or video[0].get("r_frame_rate")!="24/1":
        raise RuntimeError("Edited film must contain exactly one 24fps picture stream")
    return int(video[0]["nb_read_frames"])


def even_camera_coverage_edl(camera_ids):
    """Default 9-camera example: 9 cuts × 80 frames = 30sec film."""
    if (type(camera_ids) is not list or
        not 1<=len(camera_ids)<=CUT_MAX or
        any(type(x) is not str or not x for x in camera_ids) or
        len(set(camera_ids))!=len(camera_ids)):
        raise ValueError("Choose 1–96 distinct original director camera IDs")
    base,rem=divmod(FRAMES,len(camera_ids))
    index=0
    cuts=[]
    for i,camera_id in enumerate(camera_ids):
        length=base+(1 if i<rem else 0)
        cuts.append({"camera_id":camera_id,
                     "source_in_frame":index,
                     "source_out_frame":index+length,
                     "edit_in_frame":index,
                     "edit_out_frame":index+length})
        index+=length
    return cuts


def _validate_edl(edl,source_camera_ids):
    if (type(edl) is not list or not 1<=len(edl)<=CUT_MAX or
        any(type(x) is not dict or set(x)!={
            "camera_id","source_in_frame","source_out_frame",
            "edit_in_frame","edit_out_frame"} for x in edl)):
        raise ValueError("Director EDL must contain bounded typed camera cuts")
    available=set(source_camera_ids)
    current=0
    for cut in edl:
        indices=[cut[x] for x in (
            "source_in_frame","source_out_frame",
            "edit_in_frame","edit_out_frame")]
        if (cut["camera_id"] not in available or
            any(type(x) is not int for x in indices) or
            not 0<=indices[0]<indices[1]<=FRAMES or
            indices[0]!=indices[2] or indices[1]!=indices[3] or
            indices[2]!=current):
            raise PermissionError(
                "Camera cuts must cover one unchanged original actor timeline")
        current=indices[3]
    if current!=FRAMES:
        raise RuntimeError("Exactly 720 continuous original film frames required")
    return edl


def _read_pcm_mix_from_original(index,pid,source_take_id,*,folder):
    """True source audio essence with original authored event gain/timing."""
    original=index.read_revision(pid,source_take_id,1)
    report=render_original_source_stems(index,pid,source_take_id,folder)
    stems=report["original_source_stems"]
    if not 1<=len(stems)<=AUDIO_MAX:
        raise RuntimeError("The original 30s film needs source-owned PCM sound")
    take=original["data"]
    scene_takes=take["original_scene_takes"]
    if len(scene_takes)!=1:
        raise PermissionError("Cannot mix nine independent actor sound Takes")
    original_scene=scene_takes[0]
    timeline=TemporalLedger(index).events_in(
        pid,original_scene["timeline_id"],
        original_scene["timeline_revision"],
        start_tick=0,end_tick=30*T,limit=500)["events"]
    events={x["event_id"]:x for x in timeline}
    mixed=array("f",[0.0])*SAMPLES
    proof=[]
    for stem in stems:
        event=events.get(stem["event_id"])
        if (event is None or event["event_kind"]!="sound" or
            event["source_id"]!=stem["source_audio_id"] or
            event["source_revision"]!=stem["source_audio_revision"] or
            event["source_document_sha256"]!=
                stem["source_audio_document_sha256"] or
            event["start_tick"]!=stem["original_event_start_tick"] or
            event["end_tick"]!=stem["original_event_end_tick"] or
            event["start_tick"]%147000!=0):
            raise RuntimeError("Original PCM source event changed after freezing")
        gain=event["payload"].get("gain",1.0)
        if type(gain) not in (int,float) or not 0<=gain<=2:
            raise RuntimeError("Unbounded original source sound event gain")
        input_wav=Path(folder)/stem["wave_file"]
        if input_wav.is_symlink() or file_sha(input_wav)!=stem["real_wav_sha256"]:
            raise RuntimeError("Original source WAV essence substituted")
        start=event["start_tick"]//147000
        end=min(event["end_tick"]//147000,SAMPLES)
        if start<0 or start>=SAMPLES or end<start:
            raise RuntimeError("Original recorded source outside film timeline")
        with wave.open(str(input_wav),"rb") as wav:
            if (wav.getnchannels()!=1 or wav.getframerate()!=AUDIO_RATE or
                wav.getsampwidth()!=2 or
                wav.getnframes()!=stem["sample_count"]):
                raise RuntimeError("Non-original mono 48k PCM sample format")
            count=min(wav.getnframes(),end-start)
            at=0
            while at<count:
                take_count=min(8192,count-at)
                samples=wav.readframes(take_count)
                if len(samples)!=take_count*2:
                    raise RuntimeError("Source audio event lost original PCM frames")
                for j,value in enumerate(
                        struct.unpack("<"+"h"*take_count,samples)):
                    mixed[start+at+j]+=gain*value
                at+=take_count
        proof.append({"event_id":stem["event_id"],
            "source_audio_document_sha256":stem["source_audio_document_sha256"],
            "original_source_pcm_sha256":stem["original_pcm_essence_sha256"],
            "start_sample":start,"sample_count_mixed":count,
            "original_event_gain":float(gain)})
    target=Path(folder).parent/"original_30s_48k_mix.wav"
    if target.exists() or target.is_symlink():
        raise FileExistsError("Do not overwrite previous source mix")
    with wave.open(str(target),"wb") as out:
        out.setnchannels(1)
        out.setframerate(AUDIO_RATE)
        out.setsampwidth(2)
        # Mix the original sources at authored gain; saturation is
        # deliberate clipping and separately reported, never hidden.
        clipped=0
        for start in range(0,SAMPLES,8192):
            block=mixed[start:start+8192]
            values=[]
            for value in block:
                quantized=round(value)
                if quantized>32767 or quantized< -32768:
                    clipped+=1
                values.append(max(-32768,min(32767,quantized)))
            out.writeframesraw(struct.pack("<"+"h"*len(values),*values))
    with wave.open(str(target),"rb") as check:
        if (check.getnchannels()!=1 or check.getframerate()!=AUDIO_RATE or
            check.getsampwidth()!=2 or check.getnframes()!=SAMPLES):
            raise RuntimeError("Finished original PCM technical mix is not 30 seconds")
        sha=sha256(check.readframes(SAMPLES)).hexdigest()
    return {"mix_file":str(target),"mix_file_sha256":file_sha(target),
        "mix_original_pcm_essence_sha256":sha,
        "sample_count":SAMPLES,"rate_hz":AUDIO_RATE,
        "mixed_original_events":proof,"clipped_pcm_samples":clipped,
        "source_sound_not_synthesized":True}


def verify_source_camera_rolls(index,pid,bank_id,revision,rolls,supervisor,
                               *,approved_attempts=None):
    """Reread every source PNG and all 90 genuine supervisor jobs per roll."""
    bank=DirectorCameraBank(
        index,verify_director_action=lambda *_:False).verify(
            pid,bank_id,revision)
    source_host=RecoverableOriginalCameraRolls(index,supervisor,
        verify_director_action=lambda *_:False,
        prove_process_custody=lambda *_:False)
    folder,source=source_host.source(pid,bank_id,revision)
    expected={c["camera_id"]:c for c in source["cameras"]}
    if (type(rolls) is not dict or
        not rolls or set(rolls)!=set(expected)):
        raise PermissionError("Original camera bank needs all selected complete rolls")
    verified={}
    for camera_id,location in rolls.items():
        root=Path(location)
        if root.is_symlink() or not root.is_dir():
            raise PermissionError("Unreviewed original camera roll path")
        receipt=root/"roll_receipt.json"
        frame_receipt=root/"frame_receipts.json"
        if (receipt.is_symlink() or frame_receipt.is_symlink() or
            not receipt.is_file() or not frame_receipt.is_file()):
            raise PermissionError("Missing original camera roll evidence")
        data=json.loads(receipt.read_text("utf8"))
        rows=json.loads(frame_receipt.read_text("utf8"))
        if (data.get("format")!=ROLL_FORMAT or
            data.get("camera_bank_sha256")!=source[
                "source_camera_bank_sha256"] or
            data.get("original_performance_sha256")!=
                source["original_performance_sha256"] or
            data.get("original_world_take_sha256")!=
                source["original_world_take_sha256"] or
            data.get("source_usd_sha256")!=source["source_usd_sha256"] or
            data.get("verified_chunk_count")!=CHUNKS_PER_ROLL or
            data.get("frame_count")!=FRAMES or
            data.get("frame_receipts_sha256")!=file_sha(frame_receipt) or
            type(rows) is not list or len(rows)!=FRAMES):
            raise RuntimeError("Original source camera roll provenance mismatch")
        other=list(root.iterdir())
        if (len(other)!=FRAMES+2 or
            any(p.is_symlink() for p in other)):
            raise PermissionError("Unexpected or symlinked source camera footage")
        for start in range(0,FRAMES,CHUNK):
            attempt=(approved_attempts or {}).get(camera_id,{}).get(start,1)
            job_id=__import__(
                "backend.nvp_usd_film01o_recoverable_camera_roll_host",
                fromlist=["chunk_id"]).chunk_id(
                    source["source_camera_bank_sha256"],
                    camera_id,start,attempt)
            source_host._validate_job(
                job_id,source,folder,camera_id,start,attempt)
        from PIL import Image
        for i,row in enumerate(rows):
            source_frame=source["original_frame_evidence"][i]
            image_file=root/f"frame_{i:04d}.png"
            if (row.get("original_film_tick")!=source_frame["original_film_tick"] or
                row.get("original_actor_state_sha256")!=source_frame[
                    "original_actor_state_sha256"] or
                row.get("original_camera_id")!=camera_id or
                row.get("original_camera_path")!=expected[
                    camera_id]["source_camera_prim"] or
                row.get("rendered_png_sha256")!=file_sha(image_file)):
                raise RuntimeError("Camera roll frame does not match verified worker")
            with Image.open(image_file) as image:
                if image.format!="PNG" or image.size!=(320,180):
                    raise RuntimeError("Original footage failed native PNG decode")
                image.verify()
        verified[camera_id]={"roll_path":root,
            "original_native_frames":FRAMES,
            "supervisor_verified_chunks":CHUNKS_PER_ROLL,
            "roll_source_sha256":file_sha(receipt)}
    return verified,source


def conform_original_30s_multicam_short(index:FilmIndex,pid,bank_id,revision,
                                      rolls,edl,supervisor,*,out_dir,
                                      ffmpeg,ffprobe,approved_attempts=None):
    """Conform the original 30s actor short; no media is claimed without pixels."""
    if not shutil.which(ffmpeg) or not shutil.which(ffprobe):
        raise RuntimeError("Real FFmpeg and FFprobe executables are required")
    verified,source=verify_source_camera_rolls(
        index,pid,bank_id,revision,rolls,supervisor,
        approved_attempts=approved_attempts)
    cuts=_validate_edl(edl,list(verified))
    output=Path(out_dir)
    if output.exists() or output.is_symlink():
        raise FileExistsError("Never overwrite an original film render acceptance")
    output.mkdir(parents=True,mode=0o700)
    try:
        picture_dir=output/"picture"
        picture_dir.mkdir()
        clips=[]
        for i,cut in enumerate(cuts):
            folder=picture_dir/f"cut_{i:02d}"
            folder.mkdir()
            for local,index in enumerate(range(
                    cut["source_in_frame"],cut["source_out_frame"])):
                sourcefile=verified[cut["camera_id"]][
                    "roll_path"]/f"frame_{index:04d}.png"
                target=folder/f"frame_{local:04d}.png"
                shutil.copyfile(sourcefile,target)
                if file_sha(target)!=file_sha(sourcefile):
                    raise RuntimeError("Source picture changed while editing")
            length=cut["source_out_frame"]-cut["source_in_frame"]
            movie=picture_dir/f"shot_{i:02d}.mkv"
            _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
                "-framerate","24","-start_number","0",
                "-i",str(folder/"frame_%04d.png"),
                "-frames:v",str(length),"-an","-c:v","ffv1",str(movie)])
            if _decoded_frames(movie,ffprobe)!=length:
                raise RuntimeError("Selected original camera cut does not decode")
            clips.append(movie)
        (picture_dir/"edl_concat.txt").write_text(
            "".join(f"file '{x.name}'\n" for x in clips),"utf8")
        picture=output/"original_30s_picture.mkv"
        _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
            "-f","concat","-safe","1",
            "-i",str(picture_dir/"edl_concat.txt"),
            "-c","copy",str(picture)])
        if _decoded_frames(picture,ffprobe)!=FRAMES:
            raise RuntimeError("Edited source film is not exactly 720 decoded pictures")
        mix=_read_pcm_mix_from_original(
            index,pid,index.read_revision(
                pid,bank_id,revision)["data"]["world_take_id"],
            folder=output/"original_48k_stems")
        film=output/"original_30s_multicam_with_48k_audio.mkv"
        _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
            "-i",str(picture),"-i",mix["mix_file"],
            "-map","0:v:0","-map","1:a:0",
            "-c:v","copy","-c:a","pcm_s16le",
            "-shortest",str(film)])
        streams=_probe(film,ffprobe)["streams"]
        videos=[s for s in streams if s["codec_type"]=="video"]
        audio=[s for s in streams if s["codec_type"]=="audio"]
        if (len(videos)!=1 or len(audio)!=1 or
            audio[0].get("sample_rate")!="48000" or
            audio[0].get("codec_name")!="pcm_s16le" or
            _decoded_frames(film,ffprobe)!=FRAMES):
            raise RuntimeError("Original movie contains incomplete picture or PCM")
        raw=output/"verified_mux_audio.raw"
        _run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error",
            "-i",str(film),"-map","0:a:0",
            "-ar","48000","-ac","1","-f","s16le",str(raw)])
        if (raw.stat().st_size!=SAMPLES*2 or
            file_sha(raw)!=mix["mix_original_pcm_essence_sha256"]):
            raise RuntimeError("Actual muxed original PCM differs from source mix")
        raw.unlink()
        result={
            "format":FORMAT,
            "source_camera_bank_sha256":source["source_camera_bank_sha256"],
            "original_world_take_sha256":source["original_world_take_sha256"],
            "original_performance_sha256":source["original_performance_sha256"],
            "source_native_camera_roll_count":len(verified),
            "all_original_camera_rolls_supervisor_verified":True,
            "original_rolls":[{"camera_id":key,
                "source_roll_receipt_sha256":value["roll_source_sha256"]}
                for key,value in verified.items()],
            "original_edited_cut_decisions":cuts,
            "picture_frames":FRAMES,"fps":FPS,
            "duration_seconds":30,
            "original_48khz_audio":mix,
            "film_file":film.name,"film_sha256":file_sha(film),
            "independent_ffprobe_picture_frames_verified":True,
            "independent_final_pcm_essence_verified":True,
            "native_original_film_technical_conform":True,
            "director_visual_and_audio_approval":False,
            "full_cinema_master_acceptance":False}
        (output/"film_receipt.json").write_bytes(canonical(result))
        return result
    except Exception:
        shutil.rmtree(output)
        raise
