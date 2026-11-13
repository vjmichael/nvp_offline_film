"""NVP GRADE-UI-02A: real per-shot scene-linear lift/gamma/gain and pixel scopes.

This is an unapproved, non-destructive grade plan applied to genuine, SHA-
verified full-frame Cycles HALF EXR imagery. No edit rewrites a take or EXR.
Scopes are measured from *the same post-ACES RGB48 display pixels* as preview.
The browser remains uncalibrated and cannot certify a mastering result.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
import tempfile

from backend.nvp_color_mastering import (
    grade_recipe, validate_grade, grade_pixels, mastering_policy,
    view_to_rgb48, _ffmpeg_bin,
)
from backend.nvp_color_ocio import decode_scene_linear_exr
from backend.nvp_grade_workspace import GradeWorkspace, _PREVIEW_SLOTS, MAX_PREVIEW_BYTES
from backend.nvp_film_index import _id

FORMAT = "nvp.color.grade.shot_wheels.v1"
WHEEL_FORMAT = "nvp.color.wheels.linear_lift_gamma_gain.v1"
MAX_SHOTS = 24
MAX_SCOPE_BYTES = 1024*576*6


def neutral_wheels():
    return {"format":WHEEL_FORMAT, "lift":[0.,0.,0.],
            "gamma":[1.,1.,1.], "gain":[1.,1.,1.]}


def validate_wheels(value):
    if type(value) is not dict or set(value)!={"format","lift","gamma","gain"} or value["format"]!=WHEEL_FORMAT:
        raise ValueError("Unknown or malformed scene-linear color wheel format")
    import math
    for field,lo,hi in (("lift",-.05,.05),("gamma",.7,1.4),("gain",.75,1.3)):
        vals=value[field]
        if type(vals) is not list or len(vals)!=3:
            raise ValueError("Color wheels require exactly three RGB coordinates")
        for v in vals:
            if type(v) not in (float,int) or not math.isfinite(v) or not lo<=v<=hi:
                raise ValueError("Color wheel coordinate is outside bounded range")
    return {"format":WHEEL_FORMAT,
            "lift":[float(v) for v in value["lift"]],
            "gamma":[float(v) for v in value["gamma"]],
            "gain":[float(v) for v in value["gain"]]}


def make_plan(global_grade=None, shots=None):
    """Canonical editable grade plan with strict shot IDs and bounded controls."""
    g=grade_recipe() if global_grade is None else validate_grade(global_grade)
    if shots is None:
        shots={}
    if type(shots) is not dict or len(shots)>MAX_SHOTS:
        raise ValueError("Color grading requires at most 24 shot-specific wheel sets")
    validated={}
    for shot_id,wheels in shots.items():
        _id(shot_id,"shot identity")
        if shot_id in validated:
            raise ValueError("Repeated shot")
        validated[shot_id]=validate_wheels(wheels)
    return {"format":FORMAT,"global":g,"shots":dict(sorted(validated.items()))}


def validate_plan(plan,allowed_shots):
    if type(plan) is not dict or set(plan)!={"format","global","shots"} or plan["format"]!=FORMAT:
        raise RuntimeError("Unsupported or forged shot grading document")
    try:
        expected=make_plan(plan["global"],plan["shots"])
    except (ValueError,TypeError,KeyError,RuntimeError) as exc:
        raise RuntimeError("Invalid bounded shot grading controls") from exc
    if plan!=expected:
        raise RuntimeError("Shot grading plan is not canonical")
    if set(plan["shots"])-set(allowed_shots):
        raise RuntimeError("Shot grade refers to an absent/foreign source shot")
    return expected


def shot_manifest(rows):
    """Map actual frozen frame IDs to contiguous authored shot spans."""
    if not 2<=len(rows)<=48 or [r["frame"] for r in rows]!=list(range(1,len(rows)+1)):
        raise RuntimeError("Shot grading requires an exact bounded full-frame source timeline")
    shots=[]
    seen=set()
    for row in rows:
        shot=_id(row["shot_id"],"source shot ID")
        if shots and shots[-1]["shot_id"]==shot:
            shots[-1]["end_frame"]=row["frame"]
            shots[-1]["frames"]+=1
        else:
            if shot in seen:
                raise RuntimeError("Noncontiguous repeated shot ID; ambiguous grading timeline")
            seen.add(shot)
            shots.append({"shot_id":shot,"start_frame":row["frame"],"end_frame":row["frame"],"frames":1})
        if len(shots)>MAX_SHOTS:
            raise RuntimeError("Too many shots for current bounded grading interface")
    return shots


def apply_wheels(linear_rgba,wheels):
    """Apply editable lift / pivoted gamma / gain *before* the ACES display view.

    This is an explicit three-channel artistic approximation, not ASC-CDL or
    camera white balance. The .18 middle-gray pivot is stable for gamma=1.
    """
    import numpy as np
    w=validate_wheels(wheels)
    if linear_rgba.dtype!=np.float32 or linear_rgba.ndim!=3 or linear_rgba.shape[-1]!=4:
        raise ValueError("Color wheels require float32 linear RGBA")
    if not np.isfinite(linear_rgba).all():
        raise RuntimeError("Color wheels cannot operate on nonfinite pixels")
    out=np.array(linear_rgba,dtype=np.float32,copy=True,order="C")
    rgb=out[...,:3]
    lift=np.array(w["lift"],dtype=np.float32)
    gamma=np.array(w["gamma"],dtype=np.float32)
    gain=np.array(w["gain"],dtype=np.float32)
    # An additive lift may yield negative scene-linear values. Clamp at 0
    # explicitly, before power, rather than yielding NaN or undefined output.
    rgb[:]=np.maximum(rgb+lift,0)
    rgb[:]=np.power(rgb/np.float32(.18),1/gamma)*np.float32(.18)*gain
    if not np.isfinite(out).all():
        raise RuntimeError("Color wheels overflowed the scene-linear image")
    return out


def measure_scopes(rgb48,width,height):
    """64-bin RGB/luma histogram, waveform and vectorscope from real SDR RGB48.

    These are software analysis signals, *not* calibrated scopes from an SDI
    device. No browser/CSS values enter the calculation.
    """
    import numpy as np
    if type(width) is not int or type(height) is not int or width<1 or height<1:
        raise ValueError("Invalid display raster")
    if len(rgb48)!=width*height*6 or len(rgb48)>MAX_SCOPE_BYTES:
        raise RuntimeError("Scope analysis has an inconsistent source pixel buffer")
    arr=np.frombuffer(rgb48,dtype="<u2").reshape(height,width,3)
    rgb=arr.astype(np.float32)/65535.
    luma=.2126*rgb[:,:,0]+.7152*rgb[:,:,1]+.0722*rgb[:,:,2]
    histogram={}
    for i,key in enumerate(("red","green","blue")):
        histogram[key]=np.histogram(arr[:,:,i],bins=64,range=(0,65536))[0].astype(int).tolist()
    histogram["luma"]=np.histogram(luma,bins=64,range=(0,1.0000001))[0].astype(int).tolist()
    # Spatial waveform: 64 horizontal positions, 64 luma levels.
    xbins=np.minimum((np.arange(width)*64//width),63)
    ybins=np.minimum((luma*64).astype(np.int32),63)
    waveform=np.zeros((64,64),dtype=np.int32)
    np.add.at(waveform,(np.broadcast_to(xbins,(height,width)),ybins),1)
    # BT.709 display-referred Cb/Cr analysis, centered at half-range.
    cb=(rgb[:,:,2]-luma)/1.8556+.5
    cr=(rgb[:,:,0]-luma)/1.5748+.5
    u=np.clip((cb*64).astype(np.int32),0,63)
    v=np.clip((cr*64).astype(np.int32),0,63)
    vectorscope=np.zeros((64,64),dtype=np.int32)
    np.add.at(vectorscope,(v,u),1)
    return {
        "format":"nvp.scope.display_rgb48.v1",
        "status":"software_measurements_not_calibrated_monitor",
        "width":width,"height":height,"pixels":width*height,
        "rgb48_sha256":hashlib.sha256(rgb48).hexdigest(),
        "histogram":histogram,
        "waveform":waveform.tolist(),
        "vectorscope":vectorscope.tolist(),
        "luma_min":float(luma.min()),
        "luma_max":float(luma.max()),
        "luma_mean":float(luma.mean()),
        "display_referred":True,
    }


class AdvancedGradeWorkspace(GradeWorkspace):
    def timeline(self,project_id,source_id):
        source,rows,w,h=self.master._source(project_id,source_id)
        spans=shot_manifest(rows)
        return {
            "source_id":source_id,
            "source_sha256":source["record"]["document_sha256"],
            "take_id":source["record"]["data"]["source_take_id"],
            "take_sha256":source["record"]["data"]["source_take_sha256"],
            "width":w,"height":h,"fps":24,
            "frames":len(rows),"shots":spans,
            "timeline_sha256":hashlib.sha256(json.dumps(spans,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
            "status":"frozen_source_shot_boundaries_not_editable",
        }

    def save_advanced(self,project_id,source_id,grade_id,plan,expected_revision):
        _id(grade_id,"advanced grade ID")
        _id(source_id,"EXR source ID")
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError("Expected edit revision must be nonnegative")
        timeline=self.timeline(project_id,source_id)
        normalized=validate_plan(plan,[shot["shot_id"] for shot in timeline["shots"]])
        if expected_revision:
            previous=self.reopen_advanced(project_id,grade_id)
            if (previous["record"]["revision"]!=expected_revision or
                previous["record"]["data"]["source_id"]!=source_id or
                previous["record"]["data"]["source_sha256"]!=timeline["source_sha256"]):
                raise RuntimeError("Advanced grading revision conflict")
        record={
            "format":FORMAT,"status":"unapproved_shot_grading_draft",
            "source_id":source_id,"source_sha256":timeline["source_sha256"],
            "take_id":timeline["take_id"],"take_sha256":timeline["take_sha256"],
            "timeline_sha256":timeline["timeline_sha256"],
            "timeline":timeline["shots"],
            "plan":normalized,"approval":"not_approved",
        }
        created=self.index.register_revision(
            project_id,grade_id,"edit",record,expected_revision=expected_revision,
            dependencies=[
                {"object_id":source_id,"revision":1,"role":"presentation"},
                {"object_id":timeline["take_id"],"revision":1,"role":"source_take"},
            ])
        self.reopen_advanced(project_id,grade_id)
        return {"id":grade_id,"revision":created["revision"],
                "sha256":created["document_sha256"],"plan":normalized,
                "status":"unapproved_shot_grading_draft"}

    def reopen_advanced(self,project_id,grade_id,revision=None):
        row=self.index.read_revision(project_id,grade_id,revision)
        d=row["data"]
        if (row["kind"]!="edit" or d.get("format")!=FORMAT or
            d.get("status")!="unapproved_shot_grading_draft" or d.get("approval")!="not_approved"):
            raise RuntimeError("Not a valid unapproved shot grade")
        tl=self.timeline(project_id,d["source_id"])
        if (d["source_sha256"]!=tl["source_sha256"] or
            d["take_id"]!=tl["take_id"] or
            d["take_sha256"]!=tl["take_sha256"] or
            d["timeline_sha256"]!=tl["timeline_sha256"] or
            d["timeline"]!=tl["shots"]):
            raise RuntimeError("Shot grade altered frozen source/take or shot timeline")
        plan=validate_plan(d["plan"],[s["shot_id"] for s in tl["shots"]])
        expected=sorted([
            {"object_id":d["source_id"],"revision":1,"role":"presentation"},
            {"object_id":d["take_id"],"revision":1,"role":"source_take"},
        ],key=lambda x:(x["object_id"],x["revision"],x["role"]))
        if row["dependencies"]!=expected:
            raise RuntimeError("Shot grade FilmIndex source dependencies disagree")
        return {"record":row,"plan":plan,"timeline":tl}

    def render_scope_preview(self,project_id,source_id,frame,plan,*,ffmpeg=None):
        if not _PREVIEW_SLOTS.acquire(blocking=False):
            raise RuntimeError("Advanced grading preview busy: bounded two-worker limit")
        try:
            tl=self.timeline(project_id,source_id)
            if type(frame) is not int or frame<1 or frame>tl["frames"]:
                raise ValueError("Requested frame outside frozen shot timeline")
            normalized=validate_plan(plan,[s["shot_id"] for s in tl["shots"]])
            source,rows,w,h=self.master._source(project_id,source_id)
            row=rows[frame-1]
            wheels=normalized["shots"].get(row["shot_id"],neutral_wheels())
            ff=_ffmpeg_bin(ffmpeg)
            policy,cpu=mastering_policy()
            with tempfile.TemporaryDirectory(prefix="nvp-advanced-grade-") as tmp:
                path=Path(tmp)/"source.exr"
                path.write_bytes(self.index.get_blob(project_id,row["image_sha256"]))
                rgba=decode_scene_linear_exr(path,ff,(w,h))
                linear=grade_pixels(rgba,normalized["global"])
                adjusted=apply_wheels(linear,wheels)
                rgb48,clip=view_to_rgb48(adjusted,cpu)
                scopes=measure_scopes(rgb48,w,h)
                args=[
                    ff,"-nostdin","-v","error","-xerror","-f","rawvideo",
                    "-pixel_format","rgb48le","-video_size",f"{w}x{h}",
                    "-i","pipe:0","-frames:v","1","-pix_fmt","rgb24",
                    "-f","image2pipe","-vcodec","png","pipe:1",
                ]
                try:
                    result=run_owned_subprocess(args,input=rgb48,capture_output=True,timeout=45,check=False)
                except (OSError,subprocess.TimeoutExpired) as exc:
                    raise RuntimeError("Advanced source-derived preview could not finish") from exc
            if (result.returncode or
                not 64<=len(result.stdout)<=MAX_PREVIEW_BYTES or
                not result.stdout.startswith(b"\x89PNG\r\n\x1a\n")):
                raise RuntimeError("Advanced graded PNG is invalid")
            return {
                "png_base64":base64.b64encode(result.stdout).decode("ascii"),
                "png_sha256":hashlib.sha256(result.stdout).hexdigest(),
                "scope":scopes,"frame":frame,"shot_id":row["shot_id"],
                "source_exr_sha256":row["image_sha256"],
                "source_presentation_sha256":tl["source_sha256"],
                "color_config_sha256":policy["config_sha256"],
                "clip":clip,"approved":False,"calibrated":False,
            }
        finally:
            _PREVIEW_SLOTS.release()
