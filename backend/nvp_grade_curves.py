"""NVP GRADE-UI-02B1: bounded scene-linear EV tone curves and reference-shot advice.

The frozen Digital Take and HALF EXR frames remain unchanged. The five curve
knots are measured in stops relative to linear 18% gray, not 8-bit screen code.
A reference comparison can suggest a starting exposure but never applies it.
"""
from __future__ import annotations

import base64
import hashlib
import math
from pathlib import Path
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
import tempfile

from backend.nvp_grade_advanced import (
    AdvancedGradeWorkspace, make_plan, validate_plan, apply_wheels,
    neutral_wheels, measure_scopes, _PREVIEW_SLOTS, MAX_PREVIEW_BYTES,
)
from backend.nvp_color_mastering import grade_pixels, mastering_policy, view_to_rgb48, _ffmpeg_bin
from backend.nvp_color_ocio import decode_scene_linear_exr
from backend.nvp_film_index import _id

CURVE_FORMAT = "nvp.color.grade.luma_ev_curve.v1"
PLAN_FORMAT = "nvp.color.grade.shot_curves.v1"
CURVE_STOPS = (-8., -4., 0., 4., 8.)
MAX_SHOTS = 24


def neutral_curve():
    return {"format":CURVE_FORMAT,"ev_offsets":[0.,0.,0.,0.,0.]}


def validate_curve(curve):
    if type(curve) is not dict or set(curve)!={"format","ev_offsets"} or curve["format"]!=CURVE_FORMAT:
        raise ValueError("Unsupported or incomplete EV tone curve")
    values=curve["ev_offsets"]
    if type(values) is not list or len(values)!=5:
        raise ValueError("EV tone curve requires five ordered stop offsets")
    if any(type(v) not in (float,int) or not math.isfinite(v) or not -1.5<=v<=1.5 for v in values):
        raise ValueError("EV tone curve offsets must be finite within ±1.5 stops")
    if float(values[0])!=0 or float(values[-1])!=0:
        raise ValueError("Boundary stops must remain unchanged")
    output=[a+float(b) for a,b in zip(CURVE_STOPS,values)]
    if any(b<=a for a,b in zip(output,output[1:])):
        raise ValueError("Tone curve would reverse source luminance")
    return {"format":CURVE_FORMAT,"ev_offsets":[float(v) for v in values]}


def apply_ev_curve(linear,curve):
    """Keep HDR values >1; apply interpolated exposure offsets before ACES."""
    import numpy as np
    curve=validate_curve(curve)
    if linear.dtype!=np.float32 or linear.ndim!=3 or linear.shape[-1]!=4 or not np.isfinite(linear).all():
        raise ValueError("Expected finite float32 scene-linear RGBA")
    out=np.array(linear,dtype=np.float32,copy=True,order="C")
    rgb=out[...,:3]
    if (rgb<0).any():
        raise RuntimeError("Negative scene-linear RGB requires explicit treatment")
    luma=(rgb*np.array([.2126,.7152,.0722],dtype=np.float32)).sum(axis=-1)
    stops=np.log2(np.maximum(luma,1e-8)/.18)
    offsets=np.interp(stops,CURVE_STOPS,curve["ev_offsets"]).astype(np.float32)
    rgb*=np.exp2(offsets)[...,None]
    if not np.isfinite(rgb).all():
        raise RuntimeError("EV tone curve overflowed HDR values")
    return out


def make_curve_plan(grade=None,wheels=None,curves=None):
    curves={} if curves is None else curves
    if type(curves) is not dict or len(curves)>MAX_SHOTS:
        raise ValueError("Too many shot curves")
    clean={}
    for shot_id,curve in curves.items():
        _id(shot_id,"source shot identity")
        clean[shot_id]=validate_curve(curve)
    return {"format":PLAN_FORMAT,"base":make_plan(grade,wheels),
            "curves":dict(sorted(clean.items()))}


def validate_curve_plan(plan,allowed_shots):
    if type(plan) is not dict or set(plan)!={"format","base","curves"} or plan["format"]!=PLAN_FORMAT:
        raise RuntimeError("Unknown or malformed shot-curve document")
    base=validate_plan(plan["base"],allowed_shots)
    try:
        expected=make_curve_plan(base["global"],base["shots"],plan["curves"])
    except (ValueError,TypeError,KeyError,RuntimeError) as exc:
        raise RuntimeError("Invalid shot curves") from exc
    if expected!=plan:
        raise RuntimeError("Noncanonical shot curve document")
    if set(plan["curves"])-set(allowed_shots):
        raise RuntimeError("Tone curve applies to an absent source shot")
    return expected


class CurveGradeWorkspace(AdvancedGradeWorkspace):
    def render_curve_preview(self,project_id,source_id,frame,plan,*,ffmpeg=None):
        if not _PREVIEW_SLOTS.acquire(blocking=False):
            raise RuntimeError("Curve preview busy: bounded two-worker limit")
        try:
            timeline=self.timeline(project_id,source_id)
            if type(frame) is not int or not 1<=frame<=timeline["frames"]:
                raise ValueError("Frame outside frozen source")
            checked=validate_curve_plan(plan,[s["shot_id"] for s in timeline["shots"]])
            source,rows,w,h=self.master._source(project_id,source_id)
            row=rows[frame-1]
            base=checked["base"]
            ff=_ffmpeg_bin(ffmpeg)
            policy,cpu=mastering_policy()
            with tempfile.TemporaryDirectory(prefix="nvp-curve-") as temp:
                exr=Path(temp)/"source.exr"
                exr.write_bytes(self.index.get_blob(project_id,row["image_sha256"]))
                rgba=decode_scene_linear_exr(exr,ff,(w,h))
                graded=grade_pixels(rgba,base["global"])
                graded=apply_wheels(graded,base["shots"].get(row["shot_id"],neutral_wheels()))
                graded=apply_ev_curve(graded,checked["curves"].get(row["shot_id"],neutral_curve()))
                rgb48,clip=view_to_rgb48(graded,cpu)
                scope=measure_scopes(rgb48,w,h)
                cmd=[ff,"-nostdin","-v","error","-xerror","-f","rawvideo",
                     "-pixel_format","rgb48le","-video_size",f"{w}x{h}",
                     "-i","pipe:0","-frames:v","1","-pix_fmt","rgb24",
                     "-f","image2pipe","-vcodec","png","pipe:1"]
                try:
                    result=run_owned_subprocess(cmd,input=rgb48,capture_output=True,
                                          timeout=45,check=False)
                except (OSError,subprocess.TimeoutExpired) as exc:
                    raise RuntimeError("Curve preview encoder did not finish") from exc
            if result.returncode or not 64<=len(result.stdout)<=MAX_PREVIEW_BYTES or not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("Curve preview PNG failed integrity validation")
            return {
                "format":"nvp.color.curve.preview.v1",
                "frame":frame,"shot_id":row["shot_id"],
                "png_base64":base64.b64encode(result.stdout).decode("ascii"),
                "png_sha256":hashlib.sha256(result.stdout).hexdigest(),
                "scope":scope,"clip":clip,
                "source_exr_sha256":row["image_sha256"],
                "source_sha256":timeline["source_sha256"],
                "config_sha256":policy["config_sha256"],
                "calibrated":False,"director_approved":False,
            }
        finally:
            _PREVIEW_SLOTS.release()

    def save_curve(self,project_id,source_id,grade_id,plan,expected_revision):
        """Immutable FilmIndex edit; source and timeline cannot change silently."""
        _id(source_id,"source EXR ID")
        _id(grade_id,"curve edit ID")
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError("Expected curve revision must be nonnegative")
        timeline=self.timeline(project_id,source_id)
        checked=validate_curve_plan(plan,[s["shot_id"] for s in timeline["shots"]])
        if expected_revision:
            previous=self.reopen_curve(project_id,grade_id)
            data=previous["record"]["data"]
            if (previous["record"]["revision"]!=expected_revision or
                data["source_id"]!=source_id or
                data["source_sha256"]!=timeline["source_sha256"]):
                raise RuntimeError("Curve grade stale revision or changed source")
        payload={
            "format":PLAN_FORMAT,"status":"unapproved_curve_grading_draft",
            "source_id":source_id,"source_sha256":timeline["source_sha256"],
            "take_id":timeline["take_id"],"take_sha256":timeline["take_sha256"],
            "timeline_sha256":timeline["timeline_sha256"],
            "plan":checked,"approval":"not_approved",
        }
        row=self.index.register_revision(project_id,grade_id,"edit",payload,
            expected_revision=expected_revision,dependencies=[
                {"object_id":source_id,"revision":1,"role":"presentation"},
                {"object_id":timeline["take_id"],"revision":1,"role":"source_take"},
            ])
        reopened=self.reopen_curve(project_id,grade_id)
        if reopened["record"]["document_sha256"]!=row["document_sha256"]:
            raise RuntimeError("Curve grade commit failed independent reopen")
        return {"id":grade_id,"revision":row["revision"],
                "sha256":row["document_sha256"],"plan":checked,
                "status":"unapproved_curve_grading_draft"}

    def reopen_curve(self,project_id,grade_id,revision=None):
        row=self.index.read_revision(project_id,grade_id,revision)
        data=row["data"]
        if (row["kind"]!="edit" or data.get("format")!=PLAN_FORMAT or
            data.get("status")!="unapproved_curve_grading_draft" or
            data.get("approval")!="not_approved"):
            raise RuntimeError("Not a source-bound unapproved curve grade")
        timeline=self.timeline(project_id,data["source_id"])
        for a,b in (
            ("source_sha256","source_sha256"),
            ("take_id","take_id"),
            ("take_sha256","take_sha256"),
            ("timeline_sha256","timeline_sha256"),
        ):
            if data[a]!=timeline[b]:
                raise RuntimeError("Curve edit lost frozen source/take identity")
        checked=validate_curve_plan(data["plan"],[s["shot_id"] for s in timeline["shots"]])
        required=sorted([
            {"object_id":data["source_id"],"revision":1,"role":"presentation"},
            {"object_id":data["take_id"],"revision":1,"role":"source_take"},
        ],key=lambda x:(x["object_id"],x["revision"],x["role"]))
        if row["dependencies"]!=required:
            raise RuntimeError("Curve edit has changed FilmIndex source dependencies")
        return {"record":row,"plan":checked,"timeline":timeline}

    def compare_reference(self,project_id,source_id,target_frame,reference_frame,base_plan):
        """Inspectable heuristic only; never change a grade or saved record."""
        timeline=self.timeline(project_id,source_id)
        if (type(target_frame) is not int or type(reference_frame) is not int or
            not 1<=target_frame<=timeline["frames"] or
            not 1<=reference_frame<=timeline["frames"] or target_frame==reference_frame):
            raise ValueError("Reference and target require distinct valid source frames")
        base=validate_plan(base_plan,[s["shot_id"] for s in timeline["shots"]])
        target=self.render_scope_preview(project_id,source_id,target_frame,base)
        reference=self.render_scope_preview(project_id,source_id,reference_frame,base)
        t=float(target["scope"]["luma_mean"])
        r=float(reference["scope"]["luma_mean"])
        if min(t,r)<.015:
            raise RuntimeError("Image too dark for reliable exposure suggestion")
        raw=math.log2(r/t)
        bounded=max(-.75,min(.75,raw))
        return {
            "format":"nvp.color.reference_exposure_suggestion.v1",
            "status":"inspectable_heuristic_only_not_applied",
            "target_frame":target_frame,"reference_frame":reference_frame,
            "target_shot_id":target["shot_id"],
            "reference_shot_id":reference["shot_id"],
            "target_png_sha256":target["png_sha256"],
            "reference_png_sha256":reference["png_sha256"],
            "target_display_luma_mean":t,
            "reference_display_luma_mean":r,
            "raw_ev_delta":raw,"suggested_exposure_stops":bounded,
            "suggestion_clamped":abs(bounded-raw)>1e-8,
            "explanation":"Starting-point estimate from display mean luma, not a colorimetric match or automatically applied grade",
            "source_sha256":timeline["source_sha256"],
        }
