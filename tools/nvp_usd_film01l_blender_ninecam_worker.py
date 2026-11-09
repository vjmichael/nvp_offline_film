# SPDX-License-Identifier: GPL-2.0-or-later
"""01L reviewed first-party Blender worker: 9 real cameras / one source frame.

Fixed Cycles worker with source camera/actor position parity. No model script,
new proxy actor, replacement camera, invented animation or external asset URL.
This is a 9-camera smoke at selected source frames, NOT 6480 film frames.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import math
import sys

import bpy

FORMAT="nvp.usd_film01l.native_cycles_nine_camera_smoke_packet.v1"
AUDIT="nvp.usd_film01l.native_cycles_nine_camera_smoke_receipt.v1"
ANGLES=("A","B","C")
FRAMINGS=("wide","medium","close")

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode("ascii")

def digest(path):
    h=sha256()
    with Path(path).open("rb") as file:
        for part in iter(lambda:file.read(1048576),b""):
            h.update(part)
    return h.hexdigest()

def run():
    arguments=sys.argv[sys.argv.index("--")+1:]
    if len(arguments)!=6 or set(arguments[::2])!={
        "--manifest","--output","--audit"}:
        raise PermissionError("Only reviewed nine-camera worker options are allowed")
    args=dict(zip(arguments[::2],arguments[1::2]))
    work=Path.cwd().resolve(strict=True)
    paths={}
    for flag,name in args.items():
        p=Path(name)
        f=p.resolve()
        if p.is_symlink() or f.parent!=work or (
            flag=="--manifest" and not f.is_file()) or (
            flag!="--manifest" and f.exists()):
            raise PermissionError("Nine-camera worker files must stay private")
        paths[flag]=f
    packet=json.loads(paths["--manifest"].read_text("utf8"))
    if (type(packet) is not dict or set(packet)!={
        "format","source","source_sha256"} or packet["format"]!=FORMAT or
        packet["source_sha256"]!=sha256(
            canonical(packet["source"])).hexdigest()):
        raise PermissionError("Unverified original world/rig packet")
    source=packet["source"]
    fields={"source_usd_file","source_usd_sha256",
        "original_world_sha256","original_world_take_sha256",
        "original_performance_sha256","original_rig_sha256",
        "original_film_tick","original_render_frame",
        "original_actor_state_sha256","original_actor_positions",
        "original_camera_rig"}
    if type(source) is not dict or set(source)!=fields:
        raise PermissionError("Original nine-camera source packet altered")
    if (source["source_usd_file"]!="source.usda" or
        type(source["original_render_frame"]) is not int or
        source["original_render_frame"] not in (0,360,719) or
        type(source["original_actor_positions"]) is not list or
        len(source["original_actor_positions"])<3 or
        len(source["original_camera_rig"])!=9):
        raise PermissionError("Source frame/actor/camera scope incorrect")
    usd=work/source["source_usd_file"]
    if usd.is_symlink() or not usd.is_file() or digest(usd)!=source["source_usd_sha256"]:
        raise PermissionError("Immutable source USD SHA differs from packet")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    supported=set(bpy.ops.wm.usd_import.get_rna_type().properties.keys())
    kw={"filepath":str(usd)}
    for key in ("import_cameras","import_lights","import_materials",
                "import_meshes","import_usd_preview","read_mesh_uvs",
                "apply_unit_conversion_scale","set_frame_range"):
        if key in supported:kw[key]=True
    if "merge_parent_xform" in supported:kw["merge_parent_xform"]=False
    bpy.ops.wm.usd_import(**kw)
    scene=bpy.context.scene
    scene.frame_start=1
    scene.frame_end=720
    scene.render.fps=24
    scene.frame_set(source["original_render_frame"]+1)
    bpy.context.view_layer.update()
    imported=list(bpy.data.objects)
    cameras=[x for x in imported if x.type=="CAMERA"]
    meshes=[x for x in imported if x.type=="MESH" and
            len(x.data.vertices)>=3]
    if len(cameras)!=9 or len(meshes)<3:
        raise RuntimeError("Blender USD import dropped original source cameras/actors")
    object_names={o.name:o for o in imported}
    actor_samples=[]
    for item in source["original_actor_positions"]:
        name=item["source_prim"].split("/")[-1]
        matches=[o for o in imported if o.name==name or
                 o.name.rsplit(".",1)[0]==name]
        if len(matches)!=1:
            raise RuntimeError("Original ActorID root missing in Blender")
        ob=matches[0]
        pos=[float(ob.matrix_world.translation[i]) for i in range(3)]
        if any(abs(x-y)>0.01 for x,y in zip(pos,item["position_m"])):
            raise RuntimeError("Actual Blender actor animation differs from original USD")
        actor_samples.append({"actor_id":item["actor_id"],
                              "blender_actor_position_m":pos})
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=4
    scene.render.resolution_x=320
    scene.render.resolution_y=180
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.use_file_extension=False
    scene["nvp_original_rig_sha256"]=source["original_rig_sha256"]
    scene["nvp_original_performance_sha256"]=source["original_performance_sha256"]
    scene["nvp_original_world_take_sha256"]=source["original_world_take_sha256"]
    scene["nvp_original_film_tick"]=source["original_film_tick"]
    scene["nvp_camera_count"]=9
    rows=[]
    for angle in ANGLES:
        for framing in FRAMINGS:
            expected=next((c for c in source["original_camera_rig"]
                if c["angle"]==angle and c["framing"]==framing),None)
            if expected is None:
                raise RuntimeError("Original nine-camera bank incomplete")
            name=expected["native_composed_camera_path"].split("/")[-1]
            matching=[c for c in cameras if c.name==name or
                      c.name.rsplit(".",1)[0]==name]
            if len(matching)!=1:
                raise RuntimeError("Blender imported missing/ambiguous original camera")
            camera=matching[0]
            observed=[float(camera.matrix_world.translation[i]) for i in range(3)]
            if any(abs(a-b)>0.01 for a,b in zip(
                    observed,expected["source_world_positions_m"][0])):
                raise RuntimeError("Blender camera source position parity failed")
            lens=float(camera.data.lens)
            if not math.isclose(lens,expected["focal_length_mm"],
                                rel_tol=0,abs_tol=0.1):
                raise RuntimeError("Original wide/medium/close USD lens changed in Blender")
            scene.camera=camera
            filename=f"{angle}_{framing}.png"
            frame=work/filename
            if frame.exists() or frame.is_symlink():
                raise FileExistsError("Never overwrite native camera frame output")
            scene.render.filepath=str(frame)
            bpy.ops.render.render(write_still=True)
            if not frame.is_file() or frame.stat().st_size<100:
                raise RuntimeError("One original camera did not render a native Cycles picture")
            rows.append({
                "angle":angle,"framing":framing,
                "camera_prim":expected["native_composed_camera_path"],
                "camera_shot_sha256":expected["camera_shot_sha256"],
                "rendered_png_file":filename,"rendered_png_sha256":digest(frame),
                "original_world_sha256":source["original_world_sha256"],
                "original_performance_sha256":source["original_performance_sha256"],
                "original_actor_state_sha256":source["original_actor_state_sha256"],
                "original_film_tick":source["original_film_tick"],
                "actual_native_cycles_image":True,
                "actual_blender_camera_and_actor_source_position_parity":True})
    bpy.ops.wm.save_as_mainfile(filepath=str(paths["--output"]))
    if not paths["--output"].is_file():
        raise RuntimeError("Original nine-camera Blender scene failed save")
    audit={"format":AUDIT,"passed":True,
        "original_rig_sha256":source["original_rig_sha256"],
        "original_world_take_sha256":source["original_world_take_sha256"],
        "source_usd_sha256":source["source_usd_sha256"],
        "original_film_tick":source["original_film_tick"],
        "original_actor_state_sha256":source["original_actor_state_sha256"],
        "actual_blender_version":bpy.app.version_string,
        "actual_native_cycles_image_count":len(rows),
        "actual_original_actor_motion_at_frame_verified":True,
        "camera_views":rows,
        "original_actor_samples":actor_samples,
        "saved_blend_sha256":digest(paths["--output"]),
        "complete_6480_frame_coverage_rendered":False,
        "director_visual_approval":False}
    paths["--audit"].write_text(
        json.dumps(audit,sort_keys=True,separators=(",",":")),"utf8")

if __name__=="__main__":
    run()
