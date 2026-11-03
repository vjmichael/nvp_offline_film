"""NVP-PIPE-01A: immutable, rendered Blender presentation from frozen Digital Take.

This first adapter is deliberately conventional Blender Workbench, NOT a video
AI or voice engine. The same take may yield multiple style variants. Rendering
never updates the Film World or original capture, and only verified PNG frames
are indexed. A presentation is 'rendered_unreviewed', not director approved.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_digital_capture import DigitalCapture, run_frozen_take_acceptance
from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_production_scene import compact
from backend.nvp_studio import Studio

ENGINE = "blender_workbench"
STYLES = frozenset(("studio", "flat"))
FRAME_MODES = frozenset(("keyframes", "full"))
MAX_FULL_FRAMES = 2400
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# This is trusted, static source, NOT a model prompt or arbitrary user script.
# Camera/cut/frame values come exclusively from the independently reopened take.
RENDER_SCRIPT = r'''import bpy, json, sys
from pathlib import Path

args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
if len(args)!=6 or args[0]!="--take" or args[2]!="--plan" or args[4]!="--out":
    raise ValueError("Expected exact --take PATH --plan PATH --out DIRECTORY")
take=json.loads(Path(args[1]).read_text("utf-8"))
plan=json.loads(Path(args[3]).read_text("utf-8"))
root=Path(args[5]).resolve()
root.mkdir(parents=True,exist_ok=True)
scene=bpy.context.scene
if take["format"]!="nvp.production.timed_proxy.v1" or \
   scene.get("nvp_take_sha")!=take["sequence_sha"] or \
   scene.get("nvp_take_dependencies")!=take["dependency_sha"]:
    raise RuntimeError("Frozen approved take does not match reopened Blender scene")
if plan["style"] not in ("studio","flat") or plan["engine"]!="blender_workbench":
    raise RuntimeError("Unsupported Blender presentation backend")
scene.render.engine="BLENDER_WORKBENCH"
scene.render.image_settings.file_format="PNG"
scene.render.resolution_x=plan["width"]
scene.render.resolution_y=plan["height"]
scene.render.resolution_percentage=100
scene.render.film_transparent=False
scene.display.shading.color_type="OBJECT"
scene.display.shading.light="STUDIO" if plan["style"]=="studio" else "FLAT"
scene.render.fps=take["fps"]
shots={x["id"]:x for x in take["shots"]}
observed=[]
for job in plan["frames"]:
    shot=shots[job["shot_id"]]
    frame=job["frame"]
    if not shot["start_frame"]<=frame<shot["stop_frame"]:
        raise RuntimeError("Requested frame outside original captured camera shot")
    cam=bpy.data.objects.get("NVP_CAMERA_"+shot["id"])
    if cam is None or cam.type!="CAMERA":
        raise RuntimeError("Saved scene has no approved camera for shot")
    scene.camera=cam
    scene.frame_set(frame)
    basename=job["filename"]
    if Path(basename).name!=basename or not basename.endswith(".png"):
        raise RuntimeError("Presentation filename was not a safe basename")
    file_path=root/basename
    scene.render.filepath=str(file_path)
    bpy.ops.render.render(write_still=True)
    if not file_path.is_file() or file_path.stat().st_size<64:
        raise RuntimeError("Blender did not write the requested frame")
    observed.append({"shot_id":shot["id"],"frame":frame,"filename":basename,
                     "camera_name":cam.name,"camera_lens_mm":cam.data.lens,
                     "source_sha":scene["nvp_take_sha"]})
Path(args[3]+".receipt.json").write_text(json.dumps({
    "format":"nvp.blender.presentation.render_receipt.v1",
    "engine":"blender_workbench","style":plan["style"],"frames":observed,
    "take_sequence_sha":take["sequence_sha"],
    "take_dependency_sha":take["dependency_sha"],
    "blender_version":bpy.app.version_string
},sort_keys=True,indent=2),"utf-8")
'''


def selected_frames(timed_take: dict, mode="keyframes"):
    """Frame-accurate shot selection, with full-range mode for actual sequences.

    A keyframe preview contains only selected stills. It MUST NOT be labeled
    a complete motion picture or a full-shot video export.
    """
    if mode not in FRAME_MODES:
        raise ValueError("Unknown presentation frame policy")
    shots=timed_take.get("shots")
    if not isinstance(shots,list) or not shots:
        raise ValueError("Frozen capture has no shots")
    next_frame=1
    frames=[]
    for shot in shots:
        if not isinstance(shot,dict) or type(shot.get("start_frame")) is not int or \
           type(shot.get("stop_frame")) is not int or \
           shot["start_frame"]!=next_frame or shot["stop_frame"]<=next_frame:
            raise ValueError("Invalid shot frame boundaries")
        _id(shot.get("id"),"captured shot ID")
        lo=shot["start_frame"]
        hi=shot["stop_frame"]
        sample=([lo, lo+(hi-lo-1)//2] if mode=="keyframes" else range(lo,hi))
        for frame in sorted(set(sample)):
            frames.append({"shot_id":shot["id"],"frame":frame,
                           "filename":f"frame_{frame:06d}.png"})
        next_frame=hi
    if mode=="full" and len(frames)>MAX_FULL_FRAMES:
        raise ValueError("Full sequence exceeds current 2400-frame job budget")
    return frames


def _png_info(raw: bytes):
    if len(raw)<64 or raw[:8]!=PNG_MAGIC or raw[12:16]!=b"IHDR":
        raise RuntimeError("Rendered output is not a valid PNG header")
    width,height=struct.unpack(">II",raw[16:24])
    if not (1<=width<=16384 and 1<=height<=16384 and
            b"IEND" in raw[-32:]):
        raise RuntimeError("Rendered PNG structure or dimensions invalid")
    return width,height


class PresentationPipeline:
    """User-selected presentation adapter with strict capability reporting.

    Blender Workbench is supported now. External video/voice AI adapters will
    be separately registered when their capabilities and rights are verified.
    """

    def __init__(self,studio:Studio,index:FilmIndex|None=None):
        self.studio=studio
        self.index=index if index is not None else FilmIndex(studio)
        self.capture=DigitalCapture(studio,self.index)

    @staticmethod
    def available_engines():
        return [{
            "engine":ENGINE,
            "styles":sorted(STYLES),
            "frame_modes":sorted(FRAME_MODES),
            "inputs":["frozen_take","camera_cuts","actor_paths","world_proxy_geometry"],
            "outputs":["image/png"],
            "limitations":["3D Workbench proxy rasterization; NOT photorealistic",
                           "No generative video, audio, voice, dialogue playback or lip sync",
                           "Keyframes mode yields selected stills, NOT full movie",
                           "Full mode renders a bounded 24-fps PNG sequence, no encoder yet"],
        }]

    def render(self,project_id,take_id,presentation_id,output_dir, *,
               engine=ENGINE,style="studio",frame_mode="keyframes",
               width=320,height=180,executable="blender",timeout=180):
        _id(take_id,"digital take ID")
        _id(presentation_id,"presentation ID")
        if engine!=ENGINE:
            raise ValueError("Selected video/renderer backend is not installed or unsupported")
        if style not in STYLES or frame_mode not in FRAME_MODES:
            raise ValueError("Unsupported presentation style or frame mode")
        if type(width) is not int or type(height) is not int or \
           not (64<=width<=1920 and 64<=height<=1080):
            raise ValueError("Presentation dimensions exceed allowed bounded output")
        if type(timeout) is not int or not (5<=timeout<=3600):
            raise ValueError("Invalid Blender execution timeout")
        try:
            self.index.read_revision(project_id,presentation_id)
        except KeyError:
            pass
        else:
            raise RuntimeError("Presentation already exists; use a new ID for a revision")
        frozen=self.capture.reopen(project_id,take_id)
        frames=selected_frames(frozen["timed_take"],frame_mode)
        state=blender_available(executable)
        if not state["available"]:
            raise RuntimeError("Blender unavailable; no presentation was published: "+state["reason"])
        root=Path(output_dir).resolve()
        # Do not clobber approved or staged presentations on retries.
        working=root/presentation_id
        working.mkdir(parents=True,exist_ok=False)
        native=run_frozen_take_acceptance(
            self.capture,project_id,take_id,working/"source_blend",
            executable=executable,render_preview=False,timeout=timeout)
        if native["status"]!="passed_blender_audit_only":
            raise RuntimeError("Frozen source native Blender audit failed; no presentation published")
        take=working/"take.json"
        take.write_text(compact(frozen["timed_take"]),"utf-8")
        plan=working/"plan.json"
        plan.write_text(compact({"engine":engine,"style":style,"frames":frames,
                                "width":width,"height":height}),"utf-8")
        render_py=working/"render.py"
        render_py.write_text(RENDER_SCRIPT,"utf-8")
        rendered=working/"frames"
        rendered.mkdir()
        cmd=[state["path"],"-b",native["blend"],"-t","2","--python",
             str(render_py),"--","--take",str(take),"--plan",str(plan),
             "--out",str(rendered)]
        try:
            process=subprocess.run(cmd,cwd=working,capture_output=True,
                                   text=True,timeout=timeout,check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Blender presentation timed out; no output published") from exc
        if process.returncode!=0:
            raise RuntimeError("Blender presentation failed; no output published: "+
                               (process.stderr+"\n"+process.stdout)[-1200:])
        receipt_file=Path(str(plan)+".receipt.json")
        if not receipt_file.is_file():
            raise RuntimeError("Blender produced no independent render receipt")
        receipt=json.loads(receipt_file.read_text("utf-8"))
        if (receipt.get("format")!="nvp.blender.presentation.render_receipt.v1" or
            receipt.get("engine")!=engine or receipt.get("style")!=style or
            receipt.get("take_sequence_sha")!=frozen["timed_take"]["sequence_sha"] or
            receipt.get("take_dependency_sha")!=frozen["timed_take"]["dependency_sha"] or
            [(f["shot_id"],f["frame"],f["filename"]) for f in receipt.get("frames",[])]!=
            [(f["shot_id"],f["frame"],f["filename"]) for f in frames]):
            raise RuntimeError("Blender render receipt does not match approved take/plan")
        stored=[]
        for frame in frames:
            raw=(rendered/frame["filename"]).read_bytes()
            w,h=_png_info(raw)
            if (w,h)!=(width,height):
                raise RuntimeError("Rendered output dimensions differ from requested presentation")
            sha=self.index.put_blob(project_id,raw,"image/png")
            stored.append({"shot_id":frame["shot_id"],"frame":frame["frame"],
                           "image_sha256":sha,"size_bytes":len(raw),
                           "width":w,"height":h})
        take_sha=frozen["record"]["document_sha256"]
        data={"format":"nvp.presentation.blender.v1",
              "status":"rendered_unreviewed",
              "engine":engine,"engine_version":receipt.get("blender_version"),
              "style":style,"frame_mode":frame_mode,"frame_rate":frozen["timed_take"]["fps"],
              "width":width,"height":height,"rendered_frames":stored,
              "source_take_id":take_id,"source_take_revision":1,
              "source_take_sha256":take_sha,
              "native_geometry_checks":native["checks"],
              "render_receipt":receipt,
              "limitations":["Unreviewed Blender Workbench proxy presentation",
                             "No audio/voice mix and no final encoded movie",
                             "Sampled keyframes mode is not full temporal coverage"
                             if frame_mode=="keyframes" else
                             "Full PNG sequence only; encoding is a future stage"]}
        record=self.index.register_revision(
            project_id,presentation_id,"presentation",data,
            dependencies=[{"object_id":take_id,"revision":1,"role":"source_take"}])
        confirmed=self.reopen(project_id,presentation_id)
        return {"receipt":record,"audit":confirmed["audit"],"folder":str(working)}

    def reopen(self,project_id,presentation_id):
        _id(presentation_id,"presentation ID")
        record=self.index.read_revision(project_id,presentation_id)
        if record["kind"]!="presentation":
            raise RuntimeError("Indexed object is not a presentation")
        data=record["data"]
        if data.get("format")!="nvp.presentation.blender.v1" or \
           data.get("status")!="rendered_unreviewed" or \
           data.get("engine")!=ENGINE or data.get("style") not in STYLES:
            raise RuntimeError("Unsupported or untrusted presentation record")
        expected=[{"object_id":data["source_take_id"],"revision":1,"role":"source_take"}]
        if record["dependencies"]!=expected:
            raise RuntimeError("Presentation-to-take lineage mismatch")
        frozen=self.capture.reopen(project_id,data["source_take_id"])
        if data["source_take_sha256"]!=frozen["record"]["document_sha256"]:
            raise RuntimeError("Presentation source take digest mismatch")
        if data.get("source_take_revision")!=1 or \
           data.get("frame_rate")!=frozen["timed_take"]["fps"] or \
           type(data.get("native_geometry_checks")) is not int or \
           data["native_geometry_checks"]<=0:
            raise RuntimeError("Presentation source timing or geometry audit missing")
        expected_frames=selected_frames(frozen["timed_take"],data["frame_mode"])
        rows=data["rendered_frames"]
        receipt=data.get("render_receipt")
        if not isinstance(receipt,dict) or \
           receipt.get("format")!="nvp.blender.presentation.render_receipt.v1" or \
           receipt.get("engine")!=ENGINE or \
           receipt.get("style")!=data["style"] or \
           receipt.get("blender_version")!=data.get("engine_version") or \
           receipt.get("take_sequence_sha")!=frozen["timed_take"]["sequence_sha"] or \
           receipt.get("take_dependency_sha")!=frozen["timed_take"]["dependency_sha"] or \
           not isinstance(receipt.get("frames"),list) or \
           len(receipt["frames"])!=len(expected_frames):
            raise RuntimeError("Presentation native render receipt does not match frozen source")
        shots={s["id"]:s for s in frozen["timed_take"]["shots"]}
        for planned,rendered in zip(expected_frames,receipt["frames"]):
            original=shots[planned["shot_id"]]
            if (rendered.get("shot_id"),rendered.get("frame"),
                rendered.get("filename")) != (
                    planned["shot_id"],planned["frame"],planned["filename"]) or \
               rendered.get("camera_name")!="NVP_CAMERA_"+original["id"] or \
               rendered.get("source_sha")!=frozen["timed_take"]["sequence_sha"] or \
               type(rendered.get("camera_lens_mm")) not in (int,float) or \
               not math.isfinite(rendered["camera_lens_mm"]) or \
               abs(rendered["camera_lens_mm"]-original["solution"]["lens_mm"])>0.01:
                raise RuntimeError("Presentation receipt camera, frame or source proof mismatch")
        if len(rows)!=len(expected_frames) or not rows:
            raise RuntimeError("Presentation frame coverage mismatch")
        for expected_frame,row in zip(expected_frames,rows):
            if row["shot_id"]!=expected_frame["shot_id"] or \
               row["frame"]!=expected_frame["frame"]:
                raise RuntimeError("Presentation frame/camera order mismatch")
            raw=self.index.get_blob(project_id,row["image_sha256"])
            if len(raw)!=row["size_bytes"] or _png_info(raw)!=(row["width"],row["height"]) or \
               (row["width"],row["height"])!=(data["width"],data["height"]):
                raise RuntimeError("Presentation image bytes or dimensions differ from receipt")
        return {"record":record,"audit":{
            "status":"verified_rendered_unreviewed",
            "frame_mode":data["frame_mode"],
            "frame_count":len(rows),"shot_count":len(frozen["timed_take"]["shots"]),
            "source_take_sha256":data["source_take_sha256"],
            "stored_image_hashes":[r["image_sha256"] for r in rows],
            "all_images_verified":True}}
