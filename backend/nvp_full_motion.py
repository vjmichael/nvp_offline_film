"""NVP-PIPE-01B: complete frozen-take motion pictures, media provenance, A/V timebase.

This adapter is the *first playable image motion presentation*, not a final
dialogue-synchronized film master or a neural video generator. It compiles
a bounded full-frame immutable capture, renders every frame with an explicitly
selected Blender adapter, encodes H.264 MP4 via external FFmpeg, independently
probes/decodes the output, then stores immutable bytes with source lineage.

Cycles PBR changes LIGHTING/MATERIALS of existing authorized proxy shapes.
It does NOT magically replace those proxy assets with photorealistic actors.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_presentation_pipeline import (
    ENGINE, PBR_ENGINE, STYLES, PBR_STYLES, PresentationPipeline, selected_frames,
    PIXEL_PNG, PIXEL_EXR,
)
from backend.nvp_studio import Studio

FORMAT = "nvp.presentation.motion.v1"
MAX_VIDEO_FRAMES = 240  # 10 seconds at 24fps, until chunked media jobs land
AUDIO_SAMPLE_RATE = 48000

# Selectable, versioned delivery codecs. 10-bit ProRes encoding does not
# imply our current 8-bit PNG source is genuinely 10-bit captured content.
EXPORT_PROFILES = {
    "h264_mp4": {
        "container": "mp4", "extension": ".mp4", "mime": "video/mp4",
        "codec": "h264", "pix_fmt": "yuv420p", "bits_per_component": 8,
        "codec_tag": None,
        "ffmpeg_args": ["-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "18", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart"],
    },
    "prores_422_hq_mov": {
        "container": "mov", "extension": ".mov", "mime": "video/quicktime",
        "codec": "prores", "pix_fmt": "yuv422p10le", "bits_per_component": 10,
        "codec_tag": "apch",
        "ffmpeg_args": ["-c:v", "prores_ks", "-profile:v", "3",
                        "-pix_fmt", "yuv422p10le"],
    },
    "dnxhr_hqx_mov": {
        "container": "mov", "extension": ".mov", "mime": "video/quicktime",
        "codec": "dnxhd", "pix_fmt": "yuv422p10le", "bits_per_component": 10,
        "codec_tag": "AVdh", "profile_name": "DNXHR HQX",
        "min_width": 256, "min_height": 120,
        "ffmpeg_args": ["-c:v", "dnxhd", "-profile:v", "dnxhr_hqx",
                        "-pix_fmt", "yuv422p10le"],
    },
}


def _codec_receipt(profile, expected):
    spec=EXPORT_PROFILES[profile]
    result={"codec":spec["codec"],"pix_fmt":spec["pix_fmt"],
            "width":expected["width"],"height":expected["height"],
            "fps_num":expected["fps"],"fps_den":1,
            "decoded_frame_count":expected["frames"]}
    if spec["codec_tag"] is not None:
        result["codec_tag"]=spec["codec_tag"]
    if "profile_name" in spec:
        result["codec_profile"]=spec["profile_name"]
    return result


def _run(command, *, timeout, action):
    """No shell expansion or user-generated Python; refuse unsuccessful jobs."""
    try:
        result = subprocess.run(command,capture_output=True,text=True,
                                timeout=timeout,check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{action} timed out; no motion presentation published") from exc
    if result.returncode!=0:
        raise RuntimeError(f"{action} failed; no motion presentation published: "+
                           (result.stderr+"\n"+result.stdout)[-1400:])
    return result


def _tool(name, override=None):
    if override is not None:
        if not isinstance(override,str) or not override.strip():
            raise ValueError("Invalid encoder/decoder program")
        found=shutil.which(override)
    else:
        found=shutil.which(name)
    if not found:
        raise RuntimeError(f"{name} unavailable; no motion presentation published")
    return found


def _probe_video(video,probe,expected,*,timeout=120):
    output=_run([probe,"-v","error","-select_streams","v:0",
                 "-count_frames","-show_entries",
                 "stream=codec_name,profile,codec_tag_string,width,height,nb_read_frames,r_frame_rate,pix_fmt",
                 "-of","json",str(video)],timeout=timeout,action="Independent FFprobe")
    try:
        streams=json.loads(output.stdout)["streams"]
        if len(streams)!=1:
            raise ValueError("Exactly one video stream required")
        stream=streams[0]
        frames=int(stream["nb_read_frames"])
        width=int(stream["width"])
        height=int(stream["height"])
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        raise RuntimeError("Independently probed media has incomplete video metadata") from exc
    profile=expected.get("output_profile","h264_mp4")
    if profile not in EXPORT_PROFILES:
        raise ValueError("Unknown requested professional output profile")
    spec=EXPORT_PROFILES[profile]
    if (stream.get("codec_name")!=spec["codec"] or
        stream.get("pix_fmt")!=spec["pix_fmt"] or
        (spec["codec_tag"] is not None and
         stream.get("codec_tag_string")!=spec["codec_tag"]) or
        (spec.get("profile_name") is not None and
         stream.get("profile")!=spec["profile_name"]) or
        stream.get("r_frame_rate")!=f"{expected['fps']}/1" or
        (width,height)!=(expected["width"],expected["height"]) or
        frames!=expected["frames"]):
        raise RuntimeError("Encoded presentation frames, FPS, codec/profile or resolution mismatch")
    return _codec_receipt(profile,expected)


def _dialogue_timeline(frozen):
    """Compile *timing only* into 48kHz sample coordinates, no voice invention."""
    fps=frozen["timed_take"]["fps"]
    if AUDIO_SAMPLE_RATE%fps:
        raise ValueError("Audio sample rate cannot exactly represent frozen frame clock")
    per_frame=AUDIO_SAMPLE_RATE//fps
    end_frame=frozen["timed_take"]["shots"][-1]["stop_frame"]
    cues=[]
    for src in frozen["timed_take"]["dialogue"]:
        start=src["start_frame"]
        duration=src["duration_frames"]
        if type(start) is not int or type(duration) is not int or \
           start<1 or duration<1 or start+duration>end_frame:
            raise RuntimeError("Invalid frozen dialogue time span")
        cues.append({"line_id":src["line_id"],"speaker_id":src["speaker"],
                     "start_frame":start,"duration_frames":duration,
                     "start_sample":(start-1)*per_frame,
                     "duration_samples":duration*per_frame,
                     "status":"timing_only_no_waveform"})
    return cues


class FullMotionPipeline:
    def __init__(self,studio:Studio,index:FilmIndex|None=None):
        self.studio=studio
        self.index=index if index is not None else FilmIndex(studio)
        self.capture=DigitalCapture(studio,self.index)
        self.frames=PresentationPipeline(studio,self.index)

    @staticmethod
    def capabilities():
        return {"output":"video/mp4","codec":"h264","pix_fmt":"yuv420p",
                "export_profiles":{key:{
                    "container":spec["container"],"codec":spec["codec"],
                    "pix_fmt":spec["pix_fmt"],
                    "bits_per_component":spec["bits_per_component"]
                } for key,spec in EXPORT_PROFILES.items()},
                "motion":"full_24fps_captured_sequence",
                "renderers":[ENGINE,PBR_ENGINE],
                "styles":{ENGINE:sorted(STYLES),PBR_ENGINE:sorted(PBR_STYLES)},
                "max_frames":MAX_VIDEO_FRAMES,"max_duration_seconds":MAX_VIDEO_FRAMES/24,
                "source":"immutable_approved_digital_take",
                "audio":"timecoded_dialogue_manifest_only_no_waveform",
                "needs":["Blender","FFmpeg","FFprobe"],
                "status":"local_conventional_adapter",
                "limitations":["Cycles PBR shading on proxy assets is not photoreal actor geometry",
                               "No spoken audio, voice conversion or final soundtrack",
                               "No AI video models or style-conditioned diffusion",
                               "Only source-accurate 24fps frame ranges within current job budget"]}

    def render_video(self,project_id,take_id,motion_id,output_dir, *,
                     engine=ENGINE,style="studio",width=320,height=180,
                     samples=8,executable="blender",ffmpeg=None,ffprobe=None,
                     timeout=600,output_profile="h264_mp4",
                     source_frames_id=None,source_pixel_contract=PIXEL_PNG,
                     allow_uncalibrated_exr_preview=False):
        _id(take_id,"source take")
        _id(motion_id,"motion presentation ID")
        if output_profile not in EXPORT_PROFILES:
            raise ValueError("Unsupported professional/export video profile")
        profile=EXPORT_PROFILES[output_profile]
        if source_pixel_contract not in (PIXEL_PNG,PIXEL_EXR):
            raise ValueError("Unknown motion frame-source pixel contract")
        if source_pixel_contract==PIXEL_EXR and output_profile!="h264_mp4":
            raise RuntimeError("EXR to ProRes/DNxHR requires measured OCIO output transform; cannot claim calibrated master")
        if source_pixel_contract==PIXEL_EXR and not allow_uncalibrated_exr_preview:
            raise RuntimeError("Scene-linear EXR-to-SDR review must be explicitly labeled uncalibrated")
        if len(motion_id)>72:
            raise ValueError("Motion ID must leave room for its distinct frame-source identity")
        if type(timeout) is not int or not 10<=timeout<=7200:
            raise ValueError("Invalid presentation execution timeout")
        if type(width) is not int or type(height) is not int or \
           width%2 or height%2 or not (64<=width<=1920 and 64<=height<=1080):
            raise ValueError("4:2:0/4:2:2 video export requires bounded even dimensions")
        if width < profile.get("min_width",64) or height < profile.get("min_height",64):
            raise ValueError("DNxHR HQX encoder requires at least 256x120 input raster")
        if engine not in (ENGINE,PBR_ENGINE):
            raise ValueError("Selected video renderer is not supported")
        if (engine==ENGINE and style not in STYLES) or \
           (engine==PBR_ENGINE and style not in PBR_STYLES):
            raise ValueError("Style is not a capability of selected video renderer")
        frozen=self.capture.reopen(project_id,take_id)
        frame_list=selected_frames(frozen["timed_take"],"full")
        if len(frame_list)<2 or len(frame_list)>MAX_VIDEO_FRAMES:
            raise ValueError("Capture exceeds full-motion budget; chunked shots not yet supported")
        # Validate all expensive prerequisites before creating expensive jobs.
        encoder=_tool("ffmpeg",ffmpeg)
        probe=_tool("ffprobe",ffprobe)
        if source_frames_id is not None:
            _id(source_frames_id,"existing full-frame source presentation")
        frame_id=source_frames_id if source_frames_id is not None else motion_id+"_frames"
        # The existing verified intermediate may be reused without touching
        # Blender or the actor take, allowing different deliverable codecs
        # from the exact same frame hashes.
        for oid in ((motion_id,frame_id) if source_frames_id is None else (motion_id,)):
            try:
                self.index.read_revision(project_id,oid)
            except KeyError:
                pass
            else:
                raise RuntimeError("Presentation ID already exists; never overwrite finished outputs")
        root=Path(output_dir).resolve()
        if root.is_symlink():
            raise RuntimeError("Cannot render under a symlinked output directory")
        root.mkdir(parents=True,exist_ok=True)
        if source_frames_id is None:
            self.frames.render(project_id,take_id,frame_id,root,
                               engine=engine,style=style,frame_mode="full",
                               width=width,height=height,samples=samples,
                               executable=executable,timeout=timeout,
                               pixel_contract=source_pixel_contract,ffmpeg=ffmpeg)
        frames=self.frames.reopen(project_id,frame_id)
        source_data=frames["record"]["data"]
        if (frames["audit"]["frame_count"]!=len(frame_list) or
            source_data["source_take_id"]!=take_id or
            source_data["source_take_sha256"]!=frozen["record"]["document_sha256"] or
            source_data["engine"]!=engine or source_data["style"]!=style or
            source_data["samples"]!=samples or
            source_data["width"]!=width or source_data["height"]!=height or
            source_data["frame_mode"]!="full"):
            raise RuntimeError("Selected full-frame source cannot be reused for this render contract")
        actual_contract=source_data.get("pixel_contract",PIXEL_PNG)
        if actual_contract!=source_pixel_contract:
            raise RuntimeError("Source frame pixel contract changed on reuse")
        # Encode only the indexed SHA-verified frames; reuse this record when
        # requesting a separate professional format with no visual rerender.
        token=hashlib.sha256((project_id+"|"+motion_id).encode("utf-8")).hexdigest()[:24]
        clip_dir=root/("encoded_"+token)
        clip_dir.mkdir(exist_ok=False)
        source_ext=".exr" if source_pixel_contract==PIXEL_EXR else ".png"
        for frame in frames["record"]["data"]["rendered_frames"]:
            raw=self.index.get_blob(project_id,frame["image_sha256"])
            framepath=clip_dir/f"frame_{frame['frame']:06d}{source_ext}"
            if framepath.exists():
                raise RuntimeError("Frame encoder staging path unexpectedly exists")
            framepath.write_bytes(raw)
        movie=clip_dir/("full_motion"+profile["extension"])
        source_fps=frozen["timed_take"]["fps"]
        _run([encoder,"-hide_banner","-nostdin","-loglevel","error",
              "-framerate",str(source_fps),"-start_number","1",
              "-i",str(clip_dir/("frame_%06d"+source_ext)),
              "-frames:v",str(len(frame_list)),
              *profile["ffmpeg_args"],"-an",
              "-f",profile["container"],str(movie)],
             timeout=timeout,action="FFmpeg "+output_profile+" encode")
        if not movie.is_file() or movie.stat().st_size==0:
            raise RuntimeError("FFmpeg generated no encoded video bytes")
        expected={"fps":source_fps,"width":width,"height":height,
                  "frames":len(frame_list),"output_profile":output_profile}
        decoded=_probe_video(movie,probe,expected,timeout=timeout)
        _run([encoder,"-hide_banner","-nostdin","-v","error",
              "-i",str(movie),"-f","null","-"],
             timeout=timeout,action="Independent full video decode")
        indexed=self.index.put_media_file(project_id,movie,profile["mime"])
        cue_manifest=_dialogue_timeline(frozen)
        audio_duration_samples=len(frame_list)*(AUDIO_SAMPLE_RATE//source_fps)
        record_data={
            "format":FORMAT,"status":"rendered_unreviewed",
            "source_take_id":take_id,
            "source_take_sha256":frozen["record"]["document_sha256"],
            "source_frames_id":frame_id,
            "source_frames_sha256":frames["record"]["document_sha256"],
            "video_sha256":indexed["sha256"],
            "video_bytes":indexed["size_bytes"],
            "video_mime":profile["mime"],
            "output_profile":output_profile,
            "video_container":profile["container"],
            "video_extension":profile["extension"],
            "encoded_bit_depth":profile["bits_per_component"],
            "engine":engine,"style":style,"samples":samples,
            "source_pixel_contract":source_pixel_contract,
            "width":width,"height":height,"source_fps":source_fps,
            "frame_count":len(frame_list),
            "duration_seconds":len(frame_list)/source_fps,
            "first_frame":1,"last_frame":len(frame_list),
            "codec_receipt":decoded,
            "audio_sample_rate":AUDIO_SAMPLE_RATE,
            "audio_duration_samples":audio_duration_samples,
            "dialogue_timeline":cue_manifest,
            "audio_status":"timed_dialogue_only_no_waveform",
            "quality_contract":("scene_linear_exr_to_uncalibrated_h264_review"
                                if source_pixel_contract==PIXEL_EXR else
                                "source_camera_and_actor_proxy_with_conventional_shading"),
            "limitations":["Not a photoreal character model",
                           "No audio track, TTS, music or final mastered sound",
                           "No AI video model was used"],
        }
        receipt=self.index.register_revision(
            project_id,motion_id,"presentation",record_data,
            dependencies=[
                {"object_id":take_id,"revision":1,"role":"source_take"},
                {"object_id":frame_id,"revision":1,"role":"presentation"},
            ])
        independent=self.reopen(project_id,motion_id,ffprobe=probe,
                                ffmpeg=encoder,check_decode=True)
        return {"receipt":receipt,"media":indexed,
                "audit":independent["audit"],"work_directory":str(clip_dir)}

    def reopen(self,project_id,motion_id,*,ffprobe=None,ffmpeg=None,
               check_decode=False):
        """Provenance and stored-media SHA checks; optional independent decode."""
        record=self.index.read_revision(project_id,motion_id)
        data=record["data"]
        if record["kind"]!="presentation" or data.get("format")!=FORMAT or \
           data.get("status")!="rendered_unreviewed":
            raise RuntimeError("Not a published full-motion presentation")
        if data.get("engine") not in (ENGINE,PBR_ENGINE):
            raise RuntimeError("Unknown rendered motion engine")
        expected_edges=sorted([
            {"object_id":data["source_take_id"],"revision":1,"role":"source_take"},
            {"object_id":data["source_frames_id"],"revision":1,"role":"presentation"}],
            key=lambda x:(x["object_id"],x["revision"],x["role"]))
        if record["dependencies"]!=expected_edges:
            raise RuntimeError("Full-motion source lineage edge mismatch")
        frozen=self.capture.reopen(project_id,data["source_take_id"])
        source=self.frames.reopen(project_id,data["source_frames_id"])
        if (data["source_take_sha256"]!=frozen["record"]["document_sha256"] or
            data["source_frames_sha256"]!=source["record"]["document_sha256"] or
            source["record"]["data"]["source_take_id"]!=data["source_take_id"] or
            source["record"]["data"]["engine"]!=data["engine"] or
            source["record"]["data"]["style"]!=data["style"] or
            source["record"]["data"]["samples"]!=data["samples"] or
            source["record"]["data"].get("pixel_contract",PIXEL_PNG)!=data.get("source_pixel_contract",PIXEL_PNG)):
            raise RuntimeError("Presentation video not bound to its exact render source")
        total=len(selected_frames(frozen["timed_take"],"full"))
        if (data["frame_count"]!=total or
            source["record"]["data"]["frame_mode"]!="full" or
            source["audit"]["frame_count"]!=total or
            data["first_frame"]!=1 or data["last_frame"]!=total or
            data["source_fps"]!=frozen["timed_take"]["fps"] or
            data["duration_seconds"]!=total/data["source_fps"] or
            data["audio_sample_rate"]!=AUDIO_SAMPLE_RATE or
            data["audio_duration_samples"]!=total*AUDIO_SAMPLE_RATE//data["source_fps"] or
            data["dialogue_timeline"]!=_dialogue_timeline(frozen) or
            data["audio_status"]!="timed_dialogue_only_no_waveform"):
            raise RuntimeError("Full-motion timebase, frames or audio cues inconsistent")
        output_profile=data.get("output_profile","h264_mp4")
        if output_profile not in EXPORT_PROFILES:
            raise RuntimeError("Unsupported stored film export profile")
        profile=EXPORT_PROFILES[output_profile]
        if data.get("source_pixel_contract")==PIXEL_EXR and (
            output_profile!="h264_mp4" or
            data.get("quality_contract")!="scene_linear_exr_to_uncalibrated_h264_review"):
            raise RuntimeError("Stored EXR-derived movie falsely claims a calibrated master")
        if (data.get("video_mime")!=profile["mime"] or
            data.get("video_container",profile["container"])!=profile["container"] or
            data.get("video_extension",profile["extension"])!=profile["extension"] or
            data.get("encoded_bit_depth",profile["bits_per_component"])!=profile["bits_per_component"]):
            raise RuntimeError("Film export profile metadata does not match original codec")
        media=self.index.verify_media_file(project_id,data["video_sha256"],profile["mime"])
        if media["size_bytes"]!=data["video_bytes"]:
            raise RuntimeError("Film clip metadata size was corrupted")
        expected={"fps":data["source_fps"],"width":data["width"],"height":data["height"],
                  "frames":total,"output_profile":output_profile}
        receipt=data["codec_receipt"]
        if receipt!=_codec_receipt(output_profile,expected):
            raise RuntimeError("Film clip codec receipt does not match frozen source")
        if check_decode:
            encoder=_tool("ffmpeg",ffmpeg)
            decoder=_tool("ffprobe",ffprobe)
            measured=_probe_video(media["path"],decoder,expected)
            if measured!=receipt:
                raise RuntimeError("Stored film fails independent video probe")
            _run([encoder,"-hide_banner","-nostdin","-v","error",
                  "-i",media["path"],"-f","null","-"],
                 timeout=120,action="Full-motion reopened movie decode")
        return {"record":record,"media":media,"audit":{
            "status":"verified_full_motion_unreviewed",
            "frames":total,"fps":data["source_fps"],
            "codec":profile["codec"],"container":profile["container"],
            "profile":output_profile,"video_sha256":data["video_sha256"],
            "source_take_sha256":data["source_take_sha256"],
            "all_source_frames_verified":source["audit"]["all_images_verified"],
            "source_pixel_contract":data.get("source_pixel_contract",PIXEL_PNG),
            "media_sha_verified":True,
            "video_independently_decoded":bool(check_decode),
            "audio_status":data["audio_status"]}}
