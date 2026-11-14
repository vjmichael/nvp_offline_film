"""NVP B11: bridge immutable Float32 FilmIndex takes into existing ACES2 SDR review.

REUSE the already-tested COLOR-01B OCIO DisplayViewTransform, Float32 FFmpeg
decode and round-trip verified 16-bit PNG encoder. Unlike the legacy
half-precision COLOR-01B presentation, B9 stores genuine Float32 frames as
content-addressed media. This adapter accepts only those original verified
files and never re-quantizes, edits, or overwrites a Digital Take.

This module is host-only: the production entrypoint must run inside the
creator-approved resource-admitted NVP native review worker (B11 host).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.nvp_color_ocio import (
    color_policy,decode_scene_linear_exr,apply_view,_encode_png16,_ffmpeg_bin,
    SOURCE_COLOR_SPACE,OUTPUT_PROFILE)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_exr_fidelity import inspect_exr_header
from backend.nvp_exr_publish import verify_indexed_exr_sequence
from backend.nvp_film_index import _id
from backend.nvp_frozen_take_stage import _source,TIMED
from backend.nvp_presentation_pipeline import _png_info
from backend.nvp_production_scene import digest

FORMAT="nvp.presentation.b11.frozen_float32_sdr_png16.v1"
MAX_FRAMES=120
NEAR_OPAQUE_ALPHA_POLICY="nvp.display_review.near_opaque_aa_alpha_v1"
MAX_ALPHA_SHORTFALL=.003


def normalize_near_opaque_preview_alpha(pixels):
    """Normalize only sub-0.3% AA alpha shortfall in derived SDR review.

    B9 Blender Workbench has been observed writing alpha 0.99853515625
    on every pixel of an otherwise opaque frame. That is not the same as
    transparently compositing a performer or set. We refuse truly
    transparent inputs rather than invent an unknown matte/premultiplication
    convention. Only the derived display-review copy gets alpha=1; the
    authoritative original Float32 EXR is never changed.
    """
    import numpy as np
    if (not isinstance(pixels,np.ndarray) or pixels.dtype!=np.float32 or
        pixels.ndim!=3 or pixels.shape[-1]!=4 or
        not np.isfinite(pixels).all()):
        raise RuntimeError("Review needs finite Float32 RGBA native pixels")
    alpha=pixels[...,3]
    low=float(alpha.min())
    high=float(alpha.max())
    if low<1-MAX_ALPHA_SHORTFALL or high>1+1e-6:
        raise RuntimeError(
            "Genuine transparency or invalid alpha requires explicit "
            "creator-approved linear compositing, not near-opaque normalization")
    changed=np.ascontiguousarray(pixels,dtype=np.float32).copy()
    changed[...,3]=1.0
    return changed,{
        "format":NEAR_OPAQUE_ALPHA_POLICY,
        "source_alpha_min":low,
        "source_alpha_max":high,
        "max_allowed_alpha_shortfall":MAX_ALPHA_SHORTFALL,
        "normalized_preview_pixels":int(np.count_nonzero(alpha!=1.0)),
        "source_float32_exr_alpha_modified":False,
        "premultiplication_assumed":False,
        "actual_transparency_composited":False,
    }


def frozen_review_source(capture:DigitalCapture,project_id:str,exr_presentation_id:str):
    """Independently prove complete original B9 Float32 capture and shot cuts."""
    if not isinstance(capture,DigitalCapture):
        raise TypeError("Only native FilmIndex-backed DigitalCapture is supported")
    _id(exr_presentation_id,"source EXR presentation")
    accepted=verify_indexed_exr_sequence(capture,project_id,exr_presentation_id)
    source=capture.index.read_revision(project_id,exr_presentation_id)
    data=source["data"]
    frozen=_source(capture,project_id,accepted["source_take_id"])
    shots=json.loads(frozen["bytes"][TIMED])["shots"]
    if (source["kind"]!="presentation" or source["revision"]!=1 or
        data["format"]!="nvp.presentation.scene_linear_float32_exr_sequence.v1" or
        accepted["frames"]!=len(data["frames"]) or
        not 1<=accepted["frames"]<=MAX_FRAMES or
        accepted["fps"]!=24 or
        accepted["width"]>1920 or accepted["height"]>1080 or
        len(shots)<1 or shots[0]["start_frame"]!=1 or
        shots[-1]["stop_frame"]!=accepted["frames"]+1):
        raise RuntimeError("Only complete bounded original frozen 24fps Float32 take is editorial eligible")
    cutlist=[{"shot_id":row["id"],"start_frame":row["start_frame"],
              "stop_frame_exclusive":row["stop_frame"]} for row in shots]
    if any(cutlist[i]["stop_frame_exclusive"]!=cutlist[i+1]["start_frame"]
           for i in range(len(cutlist)-1)):
        raise RuntimeError("Frozen source has a missing or overlapping camera cut")
    for frame in range(1,accepted["frames"]+1):
        if sum(a["start_frame"]<=frame<a["stop_frame_exclusive"]
               for a in cutlist)!=1:
            raise RuntimeError("Frozen source frame did not map to exactly one camera shot")
    return {"format":"nvp.b11.frozen_source.v1","project_id":project_id,
            "source_presentation_id":exr_presentation_id,
            "source_presentation_sha256":source["document_sha256"],
            "source_take_id":accepted["source_take_id"],
            "source_take_sha256":accepted["source_take_sha256"],
            "fps":accepted["fps"],"frame_count":accepted["frames"],
            "resolution":[accepted["width"],accepted["height"]],
            "cutlist":cutlist,"frames":data["frames"]}


def _frame_row(source,frame):
    for shot in source["cutlist"]:
        if shot["start_frame"]<=frame<shot["stop_frame_exclusive"]:
            return shot["shot_id"]
    raise RuntimeError("Frame has no original camera cut")


def render_aces2_sdr_review(capture:DigitalCapture,project_id,source_exr_id,
                            review_id,output_dir,*,source_primaries_declared=False,
                            ffmpeg=None):
    """Create full Float32-source ACES2 SDR16 review; no unapproved job dispatch.

    This is the worker-side function. A *trusted native host* must verify
    the creator action and resource-admit an OS-contained process before
    invoking it; never expose this as a browser/model API.
    """
    _id(review_id,"new derived SDR review")
    if source_primaries_declared is not True:
        raise PermissionError("Creator must explicitly declare original linear Rec.709 input primaries")
    source=frozen_review_source(capture,project_id,source_exr_id)
    try:
        capture.index.read_revision(project_id,review_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Immutable film review ID already exists")
    w,h=source["resolution"]
    policy,cpu=color_policy()
    if policy["source_space"]!=SOURCE_COLOR_SPACE or policy["output_profile"]!=OUTPUT_PROFILE:
        raise RuntimeError("Pinned established ACES 2 SDR view policy unexpectedly changed")
    binary=_ffmpeg_bin(ffmpeg)
    root=Path(output_dir)
    if root.is_symlink():
        raise RuntimeError("Native SDR review workspace is a symlink")
    root=root.resolve()
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    stage=root/("b11_"+hashlib.sha256((project_id+"|"+review_id).encode()).hexdigest()[:24])
    stage.mkdir(mode=0o700,exist_ok=False)
    rows=[]
    for entry in source["frames"]:
        frame=entry["frame"]
        stored=capture.index.verify_media_file(project_id,entry["sha256"],"image/x-exr")
        path=Path(stored["path"])
        if path.is_symlink():
            raise RuntimeError("Indexed original EXR source is symlinked")
        inspect_exr_header(path,width=w,height=h)
        # Reuse COLOR-01B's true float32 HDR decoder, ACES2 display-view
        # processor, nearest-even RGB48 quantizer and full FFmpeg readback.
        pixels=decode_scene_linear_exr(path,binary,(w,h))
        # The verified native Workbench EXR can have 0.998535 AA alpha,
        # despite its opaque scene. The pre-existing generic mastering
        # function correctly refuses nonopaque RGBA. Normalize only this
        # narrowly bounded preview copy, with evidence; never silently
        # composite genuinely transparent source frames.
        review_pixels,alpha_audit=normalize_near_opaque_preview_alpha(pixels)
        quant,statistics=apply_view(review_pixels,cpu)
        output=stage/("review_%06d.png"%frame)
        measured=_encode_png16(quant,output,binary)
        sha=capture.index.put_blob(project_id,output.read_bytes(),"image/png")
        if sha!=measured["sha256"]:
            raise RuntimeError("Published 16-bit SDR PNG changed after independent decode")
        rows.append({
            "frame":frame,"shot_id":_frame_row(source,frame),
            "source_exr_sha256":entry["sha256"],
            "png16_sha256":sha,"size_bytes":measured["size_bytes"],
            "decoded_rgb48le_sha256":measured["raw_rgb48le_sha256"],
            "clip_audit":statistics,
            "alpha_audit":alpha_audit,
        })
    if [row["frame"] for row in rows]!=list(range(1,source["frame_count"]+1)):
        raise RuntimeError("Incomplete/discontinuous SDR review not publishable")
    # Reopen authoritative B9 source after entire work, not the live scene.
    after=frozen_review_source(capture,project_id,source_exr_id)
    if after!=source:
        raise RuntimeError("Original frozen Digital Take/Float32 frame source changed mid-review")
    document={
        "format":FORMAT,"status":"unapproved_display_referred_sdr_review_candidate",
        "project_id":project_id,"source_presentation_id":source_exr_id,
        "source_presentation_sha256":source["source_presentation_sha256"],
        "source_take_id":source["source_take_id"],
        "source_take_sha256":source["source_take_sha256"],
        "source_primaries_declaration":SOURCE_COLOR_SPACE,
        "creator_source_primaries_approved":True,
        "display_review_alpha_policy":NEAR_OPAQUE_ALPHA_POLICY,
        "max_alpha_shortfall":MAX_ALPHA_SHORTFALL,
        "color_policy":policy,"fps":24,
        "width":w,"height":h,"frame_count":source["frame_count"],
        "cutlist":source["cutlist"],"review_frames":rows,
        "16bit_display_referred":True,
        "all_original_float32_frames_preserved":True,
        "editorial_cut_timing_from_frozen_take":True,
        "fully_rendered_video_file":False,
        "calibrated_display_or_final_grade":False,
        "approved_soundtrack_present":False,
    }
    deps=[{"object_id":source_exr_id,"revision":1,"role":"presentation"},
          {"object_id":source["source_take_id"],"revision":1,"role":"source_take"}]
    recorded=capture.index.register_revision(
        project_id,review_id,"presentation",document,dependencies=deps)
    verified=verify_sdr_review(capture,project_id,review_id,decode_png=True,ffmpeg=binary)
    return {**verified,"presentation_sha256":recorded["document_sha256"],
            "generated_review_directory":str(stage),
            "original_frozen_take_modified":False}


def verify_sdr_review(capture:DigitalCapture,project_id,review_id,*,
                      decode_png=False,ffmpeg=None):
    """Restart-safe verifier: rehash *every* RGB48 PNG and frozen source frame."""
    record=capture.index.read_revision(project_id,review_id)
    data=record["data"]
    if (record["kind"]!="presentation" or record["revision"]!=1 or
        data.get("format")!=FORMAT or data.get("project_id")!=project_id or
        data.get("status")!="unapproved_display_referred_sdr_review_candidate" or
        data.get("source_primaries_declaration")!=SOURCE_COLOR_SPACE or
        data.get("creator_source_primaries_approved") is not True or
        data.get("display_review_alpha_policy")!=NEAR_OPAQUE_ALPHA_POLICY or
        data.get("max_alpha_shortfall")!=MAX_ALPHA_SHORTFALL or
        data.get("16bit_display_referred") is not True or
        data.get("all_original_float32_frames_preserved") is not True or
        data.get("editorial_cut_timing_from_frozen_take") is not True or
        data.get("fully_rendered_video_file") is not False):
        raise RuntimeError("SDR editorial review is misrepresented or untrusted")
    source=frozen_review_source(capture,project_id,data["source_presentation_id"])
    if (source["source_presentation_sha256"]!=data["source_presentation_sha256"] or
        source["source_take_id"]!=data["source_take_id"] or
        source["source_take_sha256"]!=data["source_take_sha256"] or
        source["cutlist"]!=data["cutlist"] or
        source["frame_count"]!=data["frame_count"] or
        source["fps"]!=data["fps"] or
        source["resolution"]!=[data["width"],data["height"]]):
        raise RuntimeError("Review timing or original Digital Take lineage differs")
    edges=sorted([
        {"object_id":source["source_presentation_id"],"revision":1,"role":"presentation"},
        {"object_id":source["source_take_id"],"revision":1,"role":"source_take"},
    ],key=lambda x:(x["object_id"],x["revision"],x["role"]))
    if record["dependencies"]!=edges:
        raise RuntimeError("SDR review FilmIndex dependencies differ from source revisions")
    expected_policy,_=color_policy()
    if data["color_policy"]!=expected_policy:
        raise RuntimeError("Official ACES2 view/config/processor identity changed")
    rows=data["review_frames"]
    if (len(rows)!=source["frame_count"] or
        [x["frame"] for x in rows]!=list(range(1,source["frame_count"]+1))):
        raise RuntimeError("SDR review has missing/duplicate timeline frames")
    native=_ffmpeg_bin(ffmpeg) if decode_png else None
    for src,out in zip(source["frames"],rows):
        if (out["source_exr_sha256"]!=src["sha256"] or
            out["shot_id"]!=_frame_row(source,src["frame"])):
            raise RuntimeError("SDR review lost original frame or camera cut identity")
        alpha=out.get("alpha_audit",{})
        if (alpha.get("format")!=NEAR_OPAQUE_ALPHA_POLICY or
            alpha.get("max_allowed_alpha_shortfall")!=MAX_ALPHA_SHORTFALL or
            alpha.get("source_float32_exr_alpha_modified") is not False or
            alpha.get("actual_transparency_composited") is not False or
            alpha.get("premultiplication_assumed") is not False or
            not 1-MAX_ALPHA_SHORTFALL<=alpha.get("source_alpha_min",-1)<=1+1e-6 or
            not 1-MAX_ALPHA_SHORTFALL<=alpha.get("source_alpha_max",-1)<=1+1e-6 or
            alpha["source_alpha_min"]>alpha["source_alpha_max"]):
            raise RuntimeError("SDR review alpha disclosure is inconsistent")
        png=capture.index.get_blob(project_id,out["png16_sha256"])
        if (_png_info(png)!=(data["width"],data["height"]) or
            png[24]!=16 or png[25]!=2 or len(png)!=out["size_bytes"]):
            raise RuntimeError("Stored SDR review is not valid 16-bit RGB")
        if native:
            import tempfile
            with tempfile.TemporaryDirectory(prefix="nvp-b11-sdr-read-") as temp:
                image=Path(temp)/"verified.png"
                image.write_bytes(png)
                from backend.nvp_color_ocio import _run
                raw=_run([native,"-nostdin","-v","error","-xerror",
                         "-i",str(image),"-frames:v","1","-pix_fmt","rgb48le",
                         "-f","rawvideo","-"],
                         label="B11 independent indexed SDR 16-bit pixel readback")
                if hashlib.sha256(raw).hexdigest()!=out["decoded_rgb48le_sha256"]:
                    raise RuntimeError("Stored indexed SDR pixels differ from original ACES output")
    return {
        "format":FORMAT,"status":"VERIFIED_16BIT_SDR_EDITORIAL_REVIEW",
        "project_id":project_id,"presentation_id":review_id,
        "source_take_id":source["source_take_id"],
        "source_exr_presentation_id":source["source_presentation_id"],
        "fps":source["fps"],"review_frame_count":len(rows),
        "cut_count":len(source["cutlist"]),
        "cutlist":source["cutlist"],"color_policy":expected_policy,
        "all_frames_decoded":bool(decode_png),
        "full_video_master":False,
        "physical_display_calibrated":False,
    }
