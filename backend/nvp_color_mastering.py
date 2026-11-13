"""COLOR-01B2 — scene-linear EXR to Rec.1886/Rec.709 grade, then 10-bit MOV.

This is an immutable, unapproved technical mastering candidate, NOT a
calibrated, creative-approved, sound-mixed or theatrical final film master.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
import tempfile

from backend.nvp_color_ocio import SOURCE_COLOR_SPACE, OCIO_VERSION, CONFIG_NAME, OUTPUT_VIEW, _config, _deps, _ffmpeg_bin, decode_scene_linear_exr
from backend.nvp_color_exr import exr_info, PIXEL_EXR
from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_presentation_pipeline import PresentationPipeline
from backend.nvp_studio import Studio

FORMAT="nvp.presentation.color.video_master_candidate.v1"
GRADE_FORMAT="nvp.color.grade.global.v1"
DISPLAY="Rec.1886 Rec.709 - Display"
VIEW=OUTPUT_VIEW
FPS=24
MAX_FRAMES=48
MAX_RASTER_PIXELS=1024*576
MAX_INTERMEDIATE_BYTES=192*1024*1024
PROFILES={
    "prores_422_hq_mov":{"codec":"prores","profile":"HQ","tag":"apch","command":["-c:v","prores_ks","-profile:v","3"]},
    "dnxhr_hqx_mov":{"codec":"dnxhd","profile":"DNXHR HQX","tag":"AVdh","command":["-c:v","dnxhd","-profile:v","dnxhr_hqx"]},
}
GRADE_FIELDS={
    "exposure_stops":(-4.,4.),"contrast":(0.5,2.),"saturation":(0.,2.),
    "red_gain":(0.7,1.3),"green_gain":(0.7,1.3),"blue_gain":(0.7,1.3),
}


def grade_recipe(**overrides):
    """First versioned non-destructive global grading recipe, not the full GUI."""
    if any(key not in GRADE_FIELDS for key in overrides):
        raise ValueError("Unknown COLOR-01B2 global grading control")
    values={"exposure_stops":0.,"contrast":1.,"saturation":1.,
            "red_gain":1.,"green_gain":1.,"blue_gain":1.}
    values.update(overrides)
    for key,(lo,hi) in GRADE_FIELDS.items():
        v=values[key]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:
            raise ValueError("Grading control outside bounded allowed range: "+key)
        values[key]=float(v)
    return {"format":GRADE_FORMAT,"scope":"global_all_frames",**values}


def validate_grade(grade):
    if type(grade) is not dict or grade.get("format")!=GRADE_FORMAT or grade.get("scope")!="global_all_frames":
        raise RuntimeError("Missing or invalid grading recipe")
    try:
        expected=grade_recipe(**{k:grade[k] for k in GRADE_FIELDS})
    except (KeyError,ValueError,TypeError) as exc:
        raise RuntimeError("Forged or invalid grading recipe") from exc
    if grade!=expected:
        raise RuntimeError("Grading recipe contains forged or unknown entries")
    return grade


def mastering_policy():
    ocio,cfg=_config()
    if DISPLAY not in list(cfg.getDisplays()) or VIEW not in list(cfg.getViews(DISPLAY)):
        raise RuntimeError("Pinned OCIO lacks required Rec.1886/Rec.709 SDR display view")
    transform=ocio.DisplayViewTransform(src=SOURCE_COLOR_SPACE,display=DISPLAY,view=VIEW,
                                        looksBypass=False,dataBypass=False)
    processor=cfg.getProcessor(transform)
    policy={
        "format":"nvp.color.video.mastering_policy.v1",
        "ocio_version":OCIO_VERSION,"config":CONFIG_NAME,
        "config_sha256":hashlib.sha256(cfg.serialize().encode("utf8")).hexdigest(),
        "source_color_space":SOURCE_COLOR_SPACE,
        "source_primaries_status":"creator_declared_not_colorimeter_verified",
        "display":DISPLAY,"view":VIEW,
        "processor_cache_id":processor.getCacheID(),
        "grading_stage":"global_linear_before_ACES2_display_view",
        "transfer_intent":"Rec1886_D65_SDR100_display_view_BT709_compatible_video_tags",
        "signal_matrix":"bt709","signal_range":"tv_legal_10bit_yuv422",
        "color_primaries":"bt709","color_transfer_tag":"bt709",
        "pixel_format":"yuv422p10le",
        "quality_status":"unapproved_mastering_candidate_not_calibrated",
    }
    return policy,processor.getDefaultCPUProcessor()


def grade_pixels(pixels,grade):
    _,np=_deps()
    validate_grade(grade)
    if pixels.dtype!=np.float32 or pixels.ndim!=3 or pixels.shape[-1]!=4:
        raise ValueError("Expected float32 linear RGBA frame")
    if not np.isfinite(pixels).all() or not np.allclose(pixels[...,3],1,atol=1e-6,rtol=0):
        raise RuntimeError("Input EXR has nonfinite or transparent linear pixels")
    out=np.array(pixels,dtype=np.float32,order="C",copy=True)
    rgb=out[...,:3]
    rgb*=np.array([grade["red_gain"],grade["green_gain"],grade["blue_gain"]],dtype=np.float32)
    rgb*=2.**grade["exposure_stops"]
    rgb[:]=(rgb-.18)*grade["contrast"]+.18
    luma=(rgb*np.array([.2126,.7152,.0722],dtype=np.float32)).sum(axis=-1,keepdims=True)
    rgb[:]=luma+(rgb-luma)*grade["saturation"]
    if not np.isfinite(out).all():
        raise RuntimeError("Grading caused nonfinite values")
    return out


def view_to_rgb48(graded_linear,cpu,*,max_clip_fraction=.02):
    _,np=_deps()
    if not 0<=max_clip_fraction<=.02:
        raise ValueError("Invalid clipping threshold")
    if not np.isfinite(graded_linear).all():
        raise RuntimeError("Mastering rejects nonfinite scene-linear RGBA input")
    if not np.allclose(graded_linear[...,3],1,atol=1e-6,rtol=0):
        raise RuntimeError("Mastering requires opaque scene-linear RGBA before view")
    # Apply the OCIO display/view to RGB only: Rec.1886's applyRGBA can
    # numerically alter alpha (~1e-5) although the original EXR is opaque.
    # Always copy: tiny arrays could otherwise alias the source input.
    vals=np.array(graded_linear[...,:3],dtype=np.float32,order="C",copy=True)
    cpu.applyRGB(vals)
    if not np.isfinite(vals).all():
        raise RuntimeError("OCIO produced nonfinite display RGB values")
    outside=(vals<0)|(vals>1)
    n=int(np.count_nonzero(outside));fraction=n/vals.size
    if fraction>max_clip_fraction:
        raise RuntimeError("Proposed SDR master would clip too many display channels")
    q=np.rint(np.clip(vals,0,1)*65535).astype("<u2")
    return np.ascontiguousarray(q).tobytes(),{
        "clipped_channels":n,"clip_fraction":float(fraction),
        "display_min_before_quant":float(vals.min()),
        "display_max_before_quant":float(vals.max()),
        "output_bits":16,"quantization":"nearest_even",
    }


def _execute(command,*,output=None,timeout=240):
    try:
        with (Path(output).open("wb") if output else open(os.devnull,"wb")) as target:
            p=run_owned_subprocess(command,stdout=target,stderr=subprocess.PIPE,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Mastering encoder/decoder failed or timed out") from exc
    if p.returncode:
        raise RuntimeError("Mastering tool failed: "+p.stderr[-900:].decode("utf8","replace"))


def _ffprobe(path,ffprobe):
    command=[ffprobe,"-v","error","-select_streams","v:0","-count_frames",
             "-show_entries","stream=codec_name,profile,codec_tag_string,pix_fmt,width,height,r_frame_rate,nb_read_frames,color_range,color_space,color_transfer,color_primaries",
             "-of","json",str(path)]
    try:
        p=run_owned_subprocess(command,capture_output=True,timeout=90,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Independent metadata probe failed") from exc
    if p.returncode:
        raise RuntimeError("Independent FFprobe failed: "+p.stderr[-300:].decode("utf8","replace"))
    try:
        streams=json.loads(p.stdout)["streams"]
        if len(streams)!=1:
            raise ValueError("Multiple or missing video streams")
        return streams[0]
    except (KeyError,ValueError,TypeError,IndexError) as exc:
        raise RuntimeError("Incomplete independent MOV stream metadata") from exc


def _frame_yuv_bytes(width,height):
    return width*height*4  # YUV 10-bit 4:2:2, 16bit planar storage.


def _color_filter():
    # ACES view already baked. FFmpeg only performs declared YCbCr matrix/range.
    return ("scale=out_color_matrix=bt709:out_range=tv,"
            "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
            "format=yuv422p10le")


def encode_mov(rgb_raw,output,profile,*,width,height,frames,ffmpeg):
    if profile not in PROFILES:
        raise ValueError("Unsupported NVP-COLOR-01B2 mastering profile")
    spec=PROFILES[profile]
    _execute([ffmpeg,"-nostdin","-hide_banner","-v","error",
        "-f","rawvideo","-pixel_format","rgb48le","-video_size",f"{width}x{height}",
        "-framerate",str(FPS),"-i",str(rgb_raw),"-vf",_color_filter(),
        *spec["command"],"-pix_fmt","yuv422p10le","-color_range","tv",
        "-color_primaries","bt709","-color_trc","bt709","-colorspace","bt709",
        "-movflags","+write_colr","-frames:v",str(frames),"-an","-y",str(output)],timeout=450)
    if not output.is_file() or not output.stat().st_size:
        raise RuntimeError("No real mastered MOV was encoded")


def _yuv_reference(rgb_raw,output,*,width,height,frames,ffmpeg):
    _execute([ffmpeg,"-nostdin","-hide_banner","-v","error",
        "-f","rawvideo","-pixel_format","rgb48le","-video_size",f"{width}x{height}",
        "-framerate",str(FPS),"-i",str(rgb_raw),"-vf",_color_filter(),
        "-frames:v",str(frames),"-pix_fmt","yuv422p10le","-f","rawvideo",str(output)],
        timeout=180)


def video_audit(movie,*,profile,width,height,frames,ffmpeg,ffprobe,reference_yuv=None):
    """Full independent decode; code-range scan and bounded lossy reference delta."""
    _,np=_deps()
    spec=PROFILES[profile]
    meta=_ffprobe(movie,ffprobe)
    wanted={"codec_name":spec["codec"],"profile":spec["profile"],
            "codec_tag_string":spec["tag"],"pix_fmt":"yuv422p10le",
            "width":width,"height":height,"r_frame_rate":f"{FPS}/1",
            "color_space":"bt709","color_transfer":"bt709","color_primaries":"bt709"}
    for key,val in wanted.items():
        if meta.get(key)!=val:
            raise RuntimeError(f"Mastered MOV {key} mismatch: {meta.get(key)!r} != {val!r}")
    if int(meta.get("nb_read_frames",0))!=frames:
        raise RuntimeError("Mastered MOV has missing or extra picture frames")
    if profile=="dnxhr_hqx_mov" and meta.get("color_range")!="tv":
        raise RuntimeError("DNxHR output does not advertise limited/TV sample range")
    with tempfile.TemporaryDirectory(prefix="nvp-master-audit-") as temp:
        decoded=Path(temp)/"decoded.yuv"
        _execute([ffmpeg,"-nostdin","-hide_banner","-v","error","-xerror",
            "-i",str(movie),"-map","0:v:0","-pix_fmt","yuv422p10le",
            "-f","rawvideo",str(decoded)],timeout=240)
        expected=frames*_frame_yuv_bytes(width,height)
        if decoded.stat().st_size!=expected:
            raise RuntimeError("Decoded MOV contains wrong 10bit 4:2:2 sample count")
        arr=np.fromfile(decoded,dtype="<u2")
        n=width*height
        parts=arr.reshape((frames,n*2))
        y,u,v=parts[:,:n],parts[:,n:n+n//2],parts[:,n+n//2:]
        illegal=int(np.count_nonzero((y<64)|(y>940)))+sum(
            int(np.count_nonzero((c<64)|(c>960))) for c in (u,v))
        if illegal:
            raise RuntimeError(f"Mastered YUV has {illegal} out-of-legal-range samples")
        metrics={"decoded_samples":int(arr.size),"illegal_samples":illegal,
            "decoded_yuv10_sha256":hashlib.sha256(decoded.read_bytes()).hexdigest(),
            "y_min":int(y.min()),"y_max":int(y.max()),
            "u_min":int(u.min()),"u_max":int(u.max()),
            "v_min":int(v.min()),"v_max":int(v.max()),
            "reference_comparison":"not_requested"}
        if reference_yuv is not None:
            ref=Path(reference_yuv)
            if ref.stat().st_size!=expected:
                raise RuntimeError("OCIO RGB reference-to-YUV sample count mismatch")
            original=np.fromfile(ref,dtype="<u2")
            error=np.abs(arr.astype(np.int32)-original.astype(np.int32))
            mean=float(error.mean());p99=float(np.percentile(error,99));maxerr=int(error.max())
            if mean>12 or p99>32 or maxerr>160:
                raise RuntimeError(f"Video materially differs from grade/color reference: {mean}, {p99}, {maxerr}")
            metrics.update({"reference_comparison":"passed_bounded_lossy_10bit_yuv",
                "mean_absolute_error_codes":mean,"p99_error_codes":p99,
                "max_error_codes":maxerr,
                "reference_yuv10_sha256":hashlib.sha256(ref.read_bytes()).hexdigest()})
    return {"metadata":meta,"decoded":metrics,
            "prores_range_metadata_note":(
                "range_field_unspecified_but_all_samples_legal"
                if profile=="prores_422_hq_mov" and not meta.get("color_range")
                else "explicit_range_present")}


class ColorMasteringPipeline:
    def __init__(self,studio:Studio,index:FilmIndex|None=None):
        self.studio=studio
        self.index=index if index is not None else FilmIndex(studio)
        self.frames=PresentationPipeline(studio,self.index)

    def _source(self,project_id,source_exr_id):
        source=self.frames.reopen(project_id,source_exr_id)
        data=source["record"]["data"];rows=data["rendered_frames"]
        if data.get("pixel_contract")!=PIXEL_EXR or data.get("frame_mode")!="full":
            raise RuntimeError("Mastering requires contiguous full-frame HALF EXR, not sampled keyframes or PNG")
        if not 2<=len(rows)<=MAX_FRAMES or data.get("frame_rate")!=FPS:
            raise RuntimeError("Mastering requires a bounded 24fps full-motion sequence")
        if [r["frame"] for r in rows]!=list(range(1,len(rows)+1)):
            raise RuntimeError("Mastering refuses missing, reordered or duplicate frames")
        width,height=data["width"],data["height"]
        if width<256 or height<120 or width%2 or height%2 or width*height>MAX_RASTER_PIXELS:
            raise RuntimeError("Mastering raster unsupported by the validated codec gateway")
        if width*height*len(rows)*6>MAX_INTERMEDIATE_BYTES:
            raise RuntimeError("Mastering RGB48 staging exceeds bounded budget")
        return source,rows,width,height

    def _reference(self,project_id,source,rows,width,height,recipe,workspace,ffmpeg):
        policy,cpu=mastering_policy()
        source_rgb=Path(workspace)/"ocio_grade_rec1886_rgb48le.raw"
        perframe=[]
        with source_rgb.open("wb") as out:
            for row in rows:
                raw=self.index.get_blob(project_id,row["image_sha256"])
                info=exr_info(raw)
                if (info["width"],info["height"])!=(width,height):
                    raise RuntimeError("Frame content violates EXR geometry")
                exr=Path(workspace)/f"source_{row['frame']:06d}.exr"
                exr.write_bytes(raw)
                linear=decode_scene_linear_exr(exr,ffmpeg,(width,height))
                graded=grade_pixels(linear,recipe)
                rgb48,stats=view_to_rgb48(graded,cpu)
                out.write(rgb48)
                perframe.append({"frame":row["frame"],"shot_id":row["shot_id"],
                    "source_exr_sha256":row["image_sha256"],
                    "graded_rgb48_sha256":hashlib.sha256(rgb48).hexdigest(),
                    "clipping":stats})
        return source_rgb,policy,perframe

    def encode(self,project_id,source_exr_id,movie_id,output_dir,*,
               output_profile="prores_422_hq_mov",recipe=None,
               source_primaries_declared=False,ffmpeg=None,ffprobe=None):
        _id(source_exr_id,"master source EXR presentation")
        _id(movie_id,"mastering candidate ID")
        if output_profile not in PROFILES:
            raise ValueError("Unsupported ProRes/DNxHR mastering format")
        if source_primaries_declared is not True:
            raise RuntimeError("Creator must explicitly declare the source EXR linear Rec.709 primaries")
        recipe=grade_recipe() if recipe is None else validate_grade(recipe)
        try:
            self.index.read_revision(project_id,movie_id)
        except KeyError:
            pass
        else:
            raise RuntimeError("Mastering ID exists; no destructive overwrite")
        source,rows,width,height=self._source(project_id,source_exr_id)
        binary=_ffmpeg_bin(ffmpeg)
        probe=shutil.which(ffprobe or "ffprobe")
        if not probe:
            raise RuntimeError("Independent FFprobe unavailable; master publication refused")
        root=Path(output_dir)
        if root.is_symlink():
            raise RuntimeError("Mastering output directory cannot be symlinked")
        root=root.resolve();root.mkdir(parents=True,exist_ok=True)
        workspace=root/("color01b2_"+hashlib.sha256((project_id+"|"+movie_id).encode()).hexdigest()[:24])
        workspace.mkdir(exist_ok=False)
        rgb,policy,perframe=self._reference(project_id,source,rows,width,height,recipe,workspace,binary)
        reference=workspace/"reference_yuv422p10le.raw"
        _yuv_reference(rgb,reference,width=width,height=height,frames=len(rows),ffmpeg=binary)
        mov=workspace/("color_managed_"+output_profile+".mov")
        encode_mov(rgb,mov,output_profile,width=width,height=height,frames=len(rows),ffmpeg=binary)
        audit=video_audit(mov,profile=output_profile,width=width,height=height,
            frames=len(rows),ffmpeg=binary,ffprobe=probe,reference_yuv=reference)
        after=self.frames.reopen(project_id,source_exr_id)
        if after["record"]["document_sha256"]!=source["record"]["document_sha256"]:
            raise RuntimeError("FilmIndex EXR source changed during mastering")
        media=self.index.put_media_file(project_id,mov,"video/quicktime")
        data=source["record"]["data"]
        ledger={
            "format":FORMAT,"status":"unapproved_color_managed_sdr_master_candidate",
            "source_exr_id":source_exr_id,"source_exr_sha256":source["record"]["document_sha256"],
            "source_take_id":data["source_take_id"],"source_take_sha256":data["source_take_sha256"],
            "source_primaries_declaration":SOURCE_COLOR_SPACE,
            "creator_declared_source_primaries":True,
            "grade":recipe,"color_policy":policy,
            "video_sha256":media["sha256"],"video_bytes":media["size_bytes"],
            "output_profile":output_profile,"width":width,"height":height,
            "fps":FPS,"frame_count":len(rows),"frame_evidence":perframe,
            "video_audit":audit,
            "limitations":[
                "Not director-approved, calibrated, picture-locked or broadcast-certified",
                "Creator-declared EXR primaries, not independently measured calibration",
                "No dialogue/soundtrack, EDL, 4K, DCI/XYZ or cinema-server ingest",
                "Lossy 10bit YUV422; 16bit RGB intermediate is not lossless 16bit MOV"],
        }
        receipt=self.index.register_revision(project_id,movie_id,"presentation",ledger,
            dependencies=[{"object_id":source_exr_id,"revision":1,"role":"presentation"},
                          {"object_id":data["source_take_id"],"revision":1,"role":"source_take"}])
        self.reopen(project_id,movie_id,check_decode=True,ffmpeg=binary,ffprobe=probe)
        return {"receipt":receipt,"media":media,"audit":audit,
                "workspace":str(workspace),"screening_ready":False}

    def reopen(self,project_id,movie_id,*,check_decode=False,ffmpeg=None,ffprobe=None):
        record=self.index.read_revision(project_id,movie_id);data=record["data"]
        if record["kind"]!="presentation" or data.get("format")!=FORMAT or data.get("status")!="unapproved_color_managed_sdr_master_candidate":
            raise RuntimeError("Not an indexed COLOR-01B2 technical film candidate")
        if data.get("creator_declared_source_primaries") is not True or data.get("source_primaries_declaration")!=SOURCE_COLOR_SPACE:
            raise RuntimeError("Candidate lost explicit source color primaries declaration")
        recipe=validate_grade(data["grade"])
        source,rows,width,height=self._source(project_id,data["source_exr_id"])
        src=source["record"]["data"]
        if (source["record"]["document_sha256"]!=data["source_exr_sha256"] or
            (src["source_take_id"],src["source_take_sha256"])!=(data["source_take_id"],data["source_take_sha256"])):
            raise RuntimeError("Mastering candidate lost authoritative EXR or frozen take lineage")
        expected=sorted([
            {"object_id":data["source_exr_id"],"revision":1,"role":"presentation"},
            {"object_id":data["source_take_id"],"revision":1,"role":"source_take"}],
            key=lambda x:(x["object_id"],x["revision"],x["role"]))
        if record["dependencies"]!=expected:
            raise RuntimeError("Mastering FilmIndex direct lineage edges changed")
        policy,_=mastering_policy()
        if data["color_policy"]!=policy:
            raise RuntimeError("Mastering OCIO processor/display policy differs from receipt")
        if (data["width"],data["height"],data["fps"],data["frame_count"])!=(width,height,FPS,len(rows)):
            raise RuntimeError("Video raster or timing differs from frozen EXR")
        if data["output_profile"] not in PROFILES:
            raise RuntimeError("Unsupported stored mastering profile")
        if len(data["frame_evidence"])!=len(rows):
            raise RuntimeError("Mastering dropped indexed source frames")
        for srcrow,measured in zip(rows,data["frame_evidence"]):
            if (measured["frame"],measured["shot_id"],measured["source_exr_sha256"])!=(
                srcrow["frame"],srcrow["shot_id"],srcrow["image_sha256"]):
                raise RuntimeError("Master frame timeline or source SHA differs from take")
        media=self.index.verify_media_file(project_id,data["video_sha256"],"video/quicktime")
        if media["size_bytes"]!=data["video_bytes"]:
            raise RuntimeError("Mastered MOV size differs from FilmIndex")
        if check_decode:
            binary=_ffmpeg_bin(ffmpeg);probe=shutil.which(ffprobe or "ffprobe")
            if not probe:
                raise RuntimeError("Independent FFprobe unavailable")
            with tempfile.TemporaryDirectory(prefix="nvp-master-reopen-") as temp:
                rgb,reference_policy,perframe=self._reference(
                    project_id,source,rows,width,height,recipe,temp,binary)
                if reference_policy!=data["color_policy"] or perframe!=data["frame_evidence"]:
                    raise RuntimeError("Independent grade replay differs from stored pixels or OCIO policy")
                ref=Path(temp)/"reference_yuv.raw"
                _yuv_reference(rgb,ref,width=width,height=height,frames=len(rows),ffmpeg=binary)
                measured=video_audit(media["path"],profile=data["output_profile"],
                    width=width,height=height,frames=len(rows),ffmpeg=binary,ffprobe=probe,
                    reference_yuv=ref)
                if measured!=data["video_audit"]:
                    raise RuntimeError("Reopened video differs from independently measured receipt")
        return {"record":record,"media":media,"check_decode":bool(check_decode),
                "frame_count":len(rows),"screening_ready":False}
