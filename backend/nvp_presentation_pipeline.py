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
import shutil
from pathlib import Path
import struct
import subprocess

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_digital_capture import DigitalCapture, run_frozen_take_acceptance
from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_production_scene import compact
from backend.nvp_studio import Studio
from backend.nvp_color_exr import PIXEL_PNG, PIXEL_EXR, PIXEL_CONTRACTS, check_frame

ENGINE = "blender_workbench"
PBR_ENGINE = "blender_cycles"
STYLES = frozenset(("studio", "flat"))
PBR_STYLES = frozenset(("pbr_studio", "pbr_noir"))
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
contract=plan.get("pixel_contract","png_srgb8")
if contract not in ("png_srgb8","openexr_half_rgba_scene_linear"):
    raise RuntimeError("Unsupported pixel contract")
if contract=="openexr_half_rgba_scene_linear" and plan["engine"]!="blender_cycles":
    raise RuntimeError("Scene-linear OpenEXR requires Cycles")
if take["format"]!="nvp.production.timed_proxy.v1" or \
   scene.get("nvp_take_sha")!=take["sequence_sha"] or \
   scene.get("nvp_take_dependencies")!=take["dependency_sha"]:
    raise RuntimeError("Frozen approved take does not match reopened Blender scene")
if plan["engine"]=="blender_workbench" and plan["style"] in ("studio","flat"):
    scene.render.engine="BLENDER_WORKBENCH"
    scene.display.shading.color_type="OBJECT"
    scene.display.shading.light="STUDIO" if plan["style"]=="studio" else "FLAT"
elif plan["engine"]=="blender_cycles" and plan["style"] in ("pbr_studio","pbr_noir"):
    # Presentation-only conversion; never edits the frozen World/Take ledger.
    # Physically based lights, shaders and softened geometry, still proxies.
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=plan["samples"]
    scene.cycles.use_denoising=False
    scene.view_settings.view_transform="AgX"
    world=bpy.data.worlds.new("NVP_PBR_WORLD")
    scene.world=world
    world.use_nodes=True
    bg=world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value=(.25,.3,.42,1) if plan["style"]=="pbr_studio" else (.025,.04,.08,1)
    bg.inputs["Strength"].default_value=.5 if plan["style"]=="pbr_studio" else .18
    for ob in scene.objects:
        if ob.type!="MESH":
            continue
        rgba=list(ob.color)
        m=bpy.data.materials.new("NVP_PBR_"+ob.name)
        m.use_nodes=True
        bsdf=m.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value=(rgba[0],rgba[1],rgba[2],1)
        bsdf.inputs["Roughness"].default_value=.46 if ob.name.startswith("NVP_") else .74
        bsdf.inputs["Metallic"].default_value=.12 if ob.name.startswith("NVP_") else 0
        ob.data.materials.clear()
        ob.data.materials.append(m)
        if ob.name.startswith("NVP_") and all(v>.15 for v in ob.dimensions):
            bevel=ob.modifiers.new(name="NVP_PresentationOnlyBevel",type="BEVEL")
            bevel.width=min(float(v) for v in ob.dimensions)*.045
            bevel.segments=2
    for light in list(bpy.data.lights):
        light.energy=light.energy*(1.4 if plan["style"]=="pbr_studio" else .8)
    if plan["style"]=="pbr_noir":
        ld=bpy.data.lights.new("NVP_NOIR_RIM","AREA")
        lo=bpy.data.objects.new("NVP_NOIR_RIM",ld)
        scene.collection.objects.link(lo)
        room=[ob for ob in scene.objects if ob.name=="NVP_FLOOR"][0]
        lo.location=(room.dimensions.x*.7,room.dimensions.y*.7,4.0)
        ld.energy=850.0
        ld.color=(.45,.62,1)
        ld.shape="DISK"
        ld.size=3.0
else:
    raise RuntimeError("Unsupported Blender presentation backend")
if contract=="openexr_half_rgba_scene_linear":
    scene.render.image_settings.file_format="OPEN_EXR"
    scene.render.image_settings.color_mode="RGBA"
    scene.render.image_settings.color_depth="16"
    scene.render.image_settings.exr_codec="ZIP"
    scene.view_settings.view_transform="Raw"
else:
    scene.render.image_settings.file_format="PNG"
scene.render.resolution_x=plan["width"]
scene.render.resolution_y=plan["height"]
scene.render.resolution_percentage=100
scene.render.film_transparent=False
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
    if Path(basename).name!=basename or not basename.endswith(".exr" if contract=="openexr_half_rgba_scene_linear" else ".png"):
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
    "engine":plan["engine"],"style":plan["style"],"samples":plan["samples"],
    "pixel_contract":contract,
    "pixel_storage":({"file_format":"OPEN_EXR","color_depth":"16","color_mode":"RGBA",
                      "view_transform":scene.view_settings.view_transform}
                     if contract=="openexr_half_rgba_scene_linear" else {"file_format":"PNG"}),
    "frames":observed,
    "take_sequence_sha":take["sequence_sha"],
    "take_dependency_sha":take["dependency_sha"],
    "blender_version":bpy.app.version_string
},sort_keys=True,indent=2),"utf-8")
'''


def selected_frames(timed_take: dict, mode="keyframes", extension="png"):
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
                           "filename":f"frame_{frame:06d}."+extension})
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

    Blender Workbench and CPU Cycles PBR are supported now. Detailed
    character geometry and neural video/voice adapters remain separate work.
    """

    def __init__(self,studio:Studio,index:FilmIndex|None=None):
        self.studio=studio
        self.index=index if index is not None else FilmIndex(studio)
        self.capture=DigitalCapture(studio,self.index)

    @staticmethod
    def available_engines():
        common=["frozen_take","camera_cuts","actor_paths","world_proxy_geometry"]
        return [{
            "engine":ENGINE,
            "styles":sorted(STYLES),
            "frame_modes":sorted(FRAME_MODES),
            "inputs":common,
            "outputs":["image/png"],
            "pixel_contracts":[PIXEL_PNG],
            "limitations":["Fast proxy rendering; not photorealistic",
                           "No generated video/voice/audio or lip synchronization",
                           "Keyframes mode yields sampled stills, not full motion"],
        },{
            "engine":PBR_ENGINE,
            "styles":sorted(PBR_STYLES),
            "frame_modes":sorted(FRAME_MODES),
            "inputs":common,
            "outputs":["image/png","image/x-exr"],
            "pixel_contracts":[PIXEL_PNG,PIXEL_EXR],
            "limitations":["Physically based Cycles CPU lighting and materials only",
                           "Characters and set remain proxy meshes until licensed detailed assets are integrated",
                           "Slower than Workbench and not photorealistic by itself",
                           "No generative voice/video, no audio rendering"],
        }]

    def render(self,project_id,take_id,presentation_id,output_dir, *,
               engine=ENGINE,style="studio",frame_mode="keyframes",
               width=320,height=180,executable="blender",timeout=180,
               samples=8,pixel_contract=PIXEL_PNG,ffmpeg=None):
        _id(take_id,"digital take ID")
        _id(presentation_id,"presentation ID")
        if engine not in (ENGINE,PBR_ENGINE):
            raise ValueError("Selected video/renderer backend is not installed or unsupported")
        if (engine==ENGINE and style not in STYLES) or \
           (engine==PBR_ENGINE and style not in PBR_STYLES) or frame_mode not in FRAME_MODES:
            raise ValueError("Unsupported presentation style or frame mode")
        if pixel_contract not in PIXEL_CONTRACTS:
            raise ValueError("Unsupported pixel contract")
        if pixel_contract==PIXEL_EXR and engine!=PBR_ENGINE:
            raise ValueError("Scene-linear EXR requires Blender Cycles")
        decoder=shutil.which(ffmpeg or "ffmpeg") if pixel_contract==PIXEL_EXR else None
        if pixel_contract==PIXEL_EXR and not decoder:
            raise RuntimeError("Independent FFmpeg EXR decoder required before film registration")
        if type(samples) is not int or not 1<=samples<=128:
            raise ValueError("Samples must be between 1 and 128")
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
        frames=selected_frames(frozen["timed_take"],frame_mode,"exr" if pixel_contract==PIXEL_EXR else "png")
        state=blender_available(executable)
        if not state["available"]:
            raise RuntimeError("Blender unavailable; no presentation was published: "+state["reason"])
        root=Path(output_dir).resolve()
        # Do not clobber approved or staged presentations on retries.
        # Film IDs may legally contain ':' or other characters unsuitable for
        # Windows paths. The workspace path is a SHA-derived safe basename,
        # never a user-supplied filesystem path segment.
        folder_key=hashlib.sha256((project_id+"\\0"+presentation_id).encode("utf-8")).hexdigest()[:32]
        working=root/("presentation_"+folder_key)
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
                                "width":width,"height":height,"samples":samples,
                                "pixel_contract":pixel_contract}),"utf-8")
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
            receipt.get("pixel_contract")!=pixel_contract or
            (pixel_contract==PIXEL_EXR and receipt.get("pixel_storage")!={
                "file_format":"OPEN_EXR","color_depth":"16","color_mode":"RGBA",
                "view_transform":"Raw"}) or
            receipt.get("take_sequence_sha")!=frozen["timed_take"]["sequence_sha"] or
            receipt.get("take_dependency_sha")!=frozen["timed_take"]["dependency_sha"] or
            [(f["shot_id"],f["frame"],f["filename"]) for f in receipt.get("frames",[])]!=
            [(f["shot_id"],f["frame"],f["filename"]) for f in frames]):
            raise RuntimeError("Blender render receipt does not match approved take/plan")
        stored=[]
        for frame in frames:
            raw=(rendered/frame["filename"]).read_bytes()
            info=check_frame(raw,pixel_contract,_png_info)
            if pixel_contract==PIXEL_EXR:
                try:
                    result=subprocess.run([
                        decoder,"-nostdin","-v","error","-xerror",
                        "-i",str(rendered/frame["filename"]),"-frames:v","1",
                        "-f","null","-"],capture_output=True,text=True,
                        timeout=timeout,check=False)
                except (OSError,subprocess.TimeoutExpired) as exc:
                    raise RuntimeError("Independent EXR decode unavailable; no frame published") from exc
                if result.returncode:
                    raise RuntimeError("Independent EXR decode failed; no frame published: "+
                                       result.stderr[-500:])
            if (info["width"],info["height"])!=(width,height):
                raise RuntimeError("Rendered output dimensions differ from requested presentation")
            sha=self.index.put_blob(project_id,raw,info["media_type"])
            stored.append({"shot_id":frame["shot_id"],"frame":frame["frame"],
                           "image_sha256":sha,"size_bytes":len(raw),
                           "width":info["width"],"height":info["height"],
                           "pixel_info":info})
        take_sha=frozen["record"]["document_sha256"]
        data={"format":"nvp.presentation.blender.v1",
              "status":"rendered_unreviewed",
              "engine":engine,"engine_version":receipt.get("blender_version"),
              "style":style,"samples":samples,"pixel_contract":pixel_contract,
              "frame_mode":frame_mode,"frame_rate":frozen["timed_take"]["fps"],
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
           data.get("engine") not in (ENGINE,PBR_ENGINE) or \
           (data["engine"]==ENGINE and data.get("style") not in STYLES) or \
           (data["engine"]==PBR_ENGINE and data.get("style") not in PBR_STYLES):
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
        pixel_contract=data.get("pixel_contract",PIXEL_PNG)
        if pixel_contract not in PIXEL_CONTRACTS or (pixel_contract==PIXEL_EXR and data["engine"]!=PBR_ENGINE):
            raise RuntimeError("Unsupported stored frame pixel contract")
        expected_frames=selected_frames(frozen["timed_take"],data["frame_mode"],
                                        "exr" if pixel_contract==PIXEL_EXR else "png")
        rows=data["rendered_frames"]
        receipt=data.get("render_receipt")
        if not isinstance(receipt,dict) or \
           receipt.get("format")!="nvp.blender.presentation.render_receipt.v1" or \
           receipt.get("engine")!=data["engine"] or \
           receipt.get("style")!=data["style"] or \
           receipt.get("samples")!=data.get("samples") or \
           receipt.get("pixel_contract",PIXEL_PNG)!=pixel_contract or \
           (pixel_contract==PIXEL_EXR and receipt.get("pixel_storage")!={"file_format":"OPEN_EXR",
               "color_depth":"16","color_mode":"RGBA","view_transform":"Raw"}) or \
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
            info=check_frame(raw,pixel_contract,_png_info)
            if len(raw)!=row["size_bytes"] or \
               (info["width"],info["height"])!=(row["width"],row["height"]) or \
               (row["width"],row["height"])!=(data["width"],data["height"]) or \
               row.get("pixel_info",info)!=info:
                raise RuntimeError("Presentation image bytes or pixel contract differ from receipt")
        return {"record":record,"audit":{
            "status":"verified_rendered_unreviewed",
            "frame_mode":data["frame_mode"],"pixel_contract":pixel_contract,
            "frame_count":len(rows),"shot_count":len(frozen["timed_take"]["shots"]),
            "source_take_sha256":data["source_take_sha256"],
            "stored_image_hashes":[r["image_sha256"] for r in rows],
            "all_images_verified":True}}
