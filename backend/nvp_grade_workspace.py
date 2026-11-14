"""NVP-GRADE-UI-01: project-scoped, non-destructive grading recipes and true previews.

The Film World and frozen Digital Take are never edited by grade operations.
Preview is a bounded unapproved browser PNG decoded from real FilmIndex EXR and
processed with the same pinned OCIO/ACES chain as color-managed mastering.
Browser preview is NOT a calibrated grading monitor or final master.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import subprocess
import tempfile
import threading

from backend.nvp_color_mastering import (
    ColorMasteringPipeline, grade_recipe, validate_grade, grade_pixels,
    view_to_rgb48, mastering_policy, _ffmpeg_bin,
)
from backend.nvp_color_ocio import decode_scene_linear_exr
from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_studio import Studio

FORMAT="nvp.color.grade.workspace.v1"
MAX_PREVIEW_BYTES=4*1024*1024
# Two OCIO/FFmpeg previews at most, even if a browser sends many requests
# while a user scrubs the image. Disallow unbounded tool/process fanout.
_PREVIEW_SLOTS=threading.BoundedSemaphore(value=2)


class GradeWorkspace:
    def __init__(self, studio: Studio, index: FilmIndex | None = None):
        self.studio=studio
        self.index=index if index is not None else FilmIndex(studio)
        self.master=ColorMasteringPipeline(studio,self.index)

    def sources(self, project_id):
        """List only independently verifiable, full-sequence, mastering-grade EXRs."""
        choices=[]
        for row in self.index.list_objects(project_id,kind="presentation"):
            doc=self.index.read_revision(project_id,row["object_id"])
            if doc["data"].get("format")!="nvp.presentation.blender.v1":
                continue
            if doc["data"].get("pixel_contract")!="openexr_half_rgba_scene_linear":
                continue
            if doc["data"].get("frame_mode")!="full":
                continue
            try:
                source,frames,w,h=self.master._source(project_id,row["object_id"])
            except RuntimeError:
                # Source may be a legitimate short keyframe preview not eligible
                # for the current native ProRes/DNxHR mastering gateway.
                continue
            choices.append({
                "id":row["object_id"],"frames":len(frames),"fps":24,
                "width":w,"height":h,"source_sha256":source["record"]["document_sha256"],
                "take_id":source["record"]["data"]["source_take_id"],
                "status":"verified_full_frame_half_exr",
            })
        return choices

    def save(self, project_id, source_exr_id, grade_id, recipe, expected_revision=0):
        """Commit an *unapproved* edit document with optimistic concurrency.

        The same grade ID can acquire historical revisions; FilmIndex retains
        every one. A recipe cannot silently switch to another take or source.
        """
        _id(grade_id,"grading recipe ID")
        _id(source_exr_id,"EXR presentation ID")
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError("Expected grading version must be a nonnegative integer")
        recipe=validate_grade(recipe)
        source,rows,_,_=self.master._source(project_id,source_exr_id)
        take_id=source["record"]["data"]["source_take_id"]
        take_sha=source["record"]["data"]["source_take_sha256"]
        if expected_revision:
            previous=self.reopen(project_id,grade_id)
            data=previous["record"]["data"]
            if (previous["record"]["revision"]!=expected_revision or
                data["source_exr_id"]!=source_exr_id or
                data["source_exr_sha256"]!=source["record"]["document_sha256"] or
                data["source_take_sha256"]!=take_sha):
                raise RuntimeError("Grading edit conflicts with another version or source")
        data={
            "format":FORMAT,"status":"draft_not_director_approved",
            "source_exr_id":source_exr_id,
            "source_exr_sha256":source["record"]["document_sha256"],
            "source_take_id":take_id,"source_take_sha256":take_sha,
            "source_frame_count":len(rows),"fps":24,
            "recipe":recipe,"source_primaries":"creator_declared_linear_rec709",
            "approval":"not_approved",
            "notes":"Edit recipe only; no export or source mutation",
        }
        committed=self.index.register_revision(
            project_id,grade_id,"edit",data,expected_revision=expected_revision,
            dependencies=[
                {"object_id":source_exr_id,"revision":1,"role":"presentation"},
                {"object_id":take_id,"revision":1,"role":"source_take"},
            ],
        )
        checked=self.reopen(project_id,grade_id)
        if checked["record"]["document_sha256"]!=committed["document_sha256"]:
            raise RuntimeError("Committed edit failed independent FilmIndex reopen")
        return {
            "id":grade_id,"revision":committed["revision"],
            "document_sha256":committed["document_sha256"],
            "source_exr_id":source_exr_id,"recipe":recipe,
            "status":"draft_not_director_approved",
        }

    def reopen(self,project_id,grade_id,revision=None):
        doc=self.index.read_revision(project_id,grade_id,revision)
        data=doc["data"]
        if (doc["kind"]!="edit" or data.get("format")!=FORMAT or
            data.get("status")!="draft_not_director_approved" or
            data.get("approval")!="not_approved"):
            raise RuntimeError("Film object is not an unapproved NVP grading edit")
        recipe=validate_grade(data.get("recipe"))
        source,frames,_,_=self.master._source(project_id,data["source_exr_id"])
        original=source["record"]["data"]
        if (source["record"]["document_sha256"]!=data["source_exr_sha256"] or
            data["source_take_id"]!=original["source_take_id"] or
            data["source_take_sha256"]!=original["source_take_sha256"] or
            data["source_frame_count"]!=len(frames) or data["fps"]!=24 or
            data.get("source_primaries")!="creator_declared_linear_rec709"):
            raise RuntimeError("Grade revision lost source/take/frame identity")
        expected=sorted([
            {"object_id":data["source_exr_id"],"revision":1,"role":"presentation"},
            {"object_id":data["source_take_id"],"revision":1,"role":"source_take"},
        ],key=lambda x:(x["object_id"],x["revision"],x["role"]))
        if doc["dependencies"]!=expected:
            raise RuntimeError("Grade receipt dependencies changed")
        return {"record":doc,"recipe":recipe}

    def list_grades(self, project_id, source_id=None):
        items=[]
        for item in self.index.list_objects(project_id,kind="edit"):
            doc=self.index.read_revision(project_id,item["object_id"])
            if doc["data"].get("format")!=FORMAT:
                continue
            if source_id is not None and doc["data"].get("source_exr_id")!=source_id:
                continue
            verified=self.reopen(project_id,item["object_id"])
            items.append({
                "id":doc["object_id"],"revision":doc["revision"],
                "source_exr_id":doc["data"]["source_exr_id"],
                "document_sha256":doc["document_sha256"],
                "recipe":verified["recipe"],
                "status":doc["data"]["status"],
            })
        return items

    def history(self,project_id,grade_id):
        self.reopen(project_id,grade_id)
        records=[]
        for row in self.index.history(project_id,grade_id):
            verified=self.reopen(project_id,grade_id,row["revision"])
            records.append({
                "revision":row["revision"],"sha256":row["document_sha"],
                "recipe":verified["recipe"],"committed_at":row["committed_at"],
            })
        return records

    def preview(self,project_id,source_exr_id,frame,recipe=None,*,ffmpeg=None):
        """Bound live previews; one API request never queues worker processes."""
        if not _PREVIEW_SLOTS.acquire(blocking=False):
            raise RuntimeError("Color preview is busy (two-worker limit); retry when the current preview completes")
        try:
            return self._preview_actual(project_id,source_exr_id,frame,recipe,ffmpeg=ffmpeg)
        finally:
            _PREVIEW_SLOTS.release()

    def _preview_actual(self,project_id,source_exr_id,frame,recipe=None,*,ffmpeg=None):
        """Actual EXR + OCIO preview; source and FilmIndex remain unchanged."""
        source,rows,width,height=self.master._source(project_id,source_exr_id)
        if type(frame) is not int or not 1<=frame<=len(rows):
            raise ValueError("Preview frame outside the actual frozen take")
        if recipe is None:
            recipe=grade_recipe()
        else:
            recipe=validate_grade(recipe)
        raw=self.index.get_blob(project_id,rows[frame-1]["image_sha256"])
        ff=_ffmpeg_bin(ffmpeg)
        policy,cpu=mastering_policy()
        with tempfile.TemporaryDirectory(prefix="nvp-grade-preview-") as temp:
            file=Path(temp)/"source.exr"
            file.write_bytes(raw)
            rgba=decode_scene_linear_exr(file,ff,(width,height))
            grading=grade_pixels(rgba,recipe)
            rgb48,stats=view_to_rgb48(grading,cpu)
            args=[
                ff,"-nostdin","-v","error","-xerror",
                "-f","rawvideo","-pixel_format","rgb48le",
                "-video_size",f"{width}x{height}",
                "-i","pipe:0","-frames:v","1",
                "-pix_fmt","rgb24","-f","image2pipe","-vcodec","png","pipe:1",
            ]
            try:
                proc=subprocess.run(args,input=rgb48,capture_output=True,
                                    timeout=45,check=False)
            except (OSError,subprocess.TimeoutExpired) as exc:
                raise RuntimeError("Real grading preview encoder failed") from exc
        if proc.returncode or not 64<=len(proc.stdout)<=MAX_PREVIEW_BYTES or not proc.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("Grading preview PNG was not generated or decoded safely")
        return {
            "bytes":proc.stdout,
            "source_frame":frame,
            "recipe":recipe,
            "source_exr_sha256":rows[frame-1]["image_sha256"],
            "color_policy_sha256":policy["config_sha256"],
            "clip":stats,
            "calibrated":False,
        }
