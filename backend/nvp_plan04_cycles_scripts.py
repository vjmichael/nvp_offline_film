"""NVP-owned, immutable trusted Blender/Cycles source + independent reopen scripts.

These strings are CONSTANT first-party code. The model and browser may pass
neither script content nor binary path to a Blender process. Executed in
Blender's own isolated Python interpreter after source and script SHA pinning.
"""
TRUSTED_CYCLES_SCRIPT=r'''
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

parser=argparse.ArgumentParser()
parser.add_argument("--manifest",required=True)
parser.add_argument("--output",required=True)
parser.add_argument("--render",required=True)
parser.add_argument("--audit",required=True)
args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
source=json.loads(Path(args.manifest).read_text(encoding="utf8"))
if (type(source) is not dict or set(source)!={"format","take_sha256",
        "scene_sha256","selection_sha256","source_tick","camera_path",
        "camera_translation","geometry","engine","resolution"} or
        source["format"]!="nvp.plan04.openusd_cycles_source.v1" or
        source["engine"]!="CYCLES_CPU" or
        source["resolution"]!=[400,240] or
        not 1<=len(source["geometry"])<=32):
    raise RuntimeError("Untrusted Blender scene manifest")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.render.engine="CYCLES"
scene.cycles.device="CPU"
scene.cycles.samples=8
# Optional denoisers differ across Cycles builds. Never require OIDN/OptiX
# for the CPU witness; retain mandatory native render and independent reopen.
def disable_optional_denoising(view_layer):
    settings=getattr(view_layer, "cycles", None)
    if settings is None or not hasattr(settings, "use_denoising"):
        return "CAPABILITY_UNAVAILABLE"
    settings.use_denoising=False
    if settings.use_denoising is not False:
        raise RuntimeError("Cycles denoising could not be disabled")
    return "DISABLED"

denoising_capability=disable_optional_denoising(bpy.context.view_layer)
scene.render.resolution_x=400
scene.render.resolution_y=240
scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG"
scene.render.film_transparent=False
scene.render.threads_mode="FIXED"
scene.render.threads=2
scene["nvp_original_take_sha256"]=source["take_sha256"]
scene["nvp_original_scene_sha256"]=source["scene_sha256"]
scene["nvp_source_selection_sha256"]=source["selection_sha256"]
# Blender ID properties can narrow Python integers to signed 32-bit.
# Store authoritative 64-bit Film Time as exact decimal text; do not
# round or truncate original USD ticks in renderer metadata.
scene["nvp_exact_film_tick"]=str(source["source_tick"])
scene["nvp_original_camera_path"]=source["camera_path"]
focus=Vector((0.0,0.0,0.0))
for number,object_spec in enumerate(source["geometry"]):
    if set(object_spec)!={"path","shape","size_m","position","asset_sha256"}:
        raise RuntimeError("Missing verified USD geometry fields")
    point=object_spec["position"]
    size=object_spec["size_m"]
    if (object_spec["shape"] not in ("cube","sphere") or
            type(point) is not list or len(point)!=3 or
            any(type(x) not in (float,int) or not math.isfinite(x) or
                abs(x)>100000 for x in point) or
            type(size) not in (float,int) or not 0<float(size)<=1000):
        raise RuntimeError("Malformed NVP USD primitive")
    if object_spec["shape"]=="sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=20,
                                            radius=float(size)/2,location=point)
    else:
        bpy.ops.mesh.primitive_cube_add(size=float(size),location=point)
    obj=bpy.context.object
    obj.name="nvp_source_"+str(number).zfill(2)
    obj["nvp_usd_prim_path"]=object_spec["path"]
    obj["nvp_asset_sha256"]=object_spec["asset_sha256"]
    mat=bpy.data.materials.new(name="NVP approved procedural neutral "+str(number))
    mat.diffuse_color=(0.68,0.69,0.72,1) if number%2==0 else (0.30,0.52,0.68,1)
    mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value=mat.diffuse_color
        bsdf.inputs["Roughness"].default_value=0.36
    obj.data.materials.append(mat)
    focus+=Vector(point)
focus/=len(source["geometry"])
campos=Vector(source["camera_translation"])
if (campos-focus).length<0.5:
    campos=focus+Vector((4,-6,3))
bpy.ops.object.camera_add(location=campos)
camera=bpy.context.object
camera.name="NVP_Approved_OpenUSD_Camera"
direction=focus-campos
camera.rotation_euler=direction.to_track_quat("-Z","Y").to_euler()
camera.data.type="PERSP"
camera.data.lens=40.0
scene.camera=camera
bpy.ops.object.light_add(type="AREA",location=focus+Vector((3,-4,5)))
light=bpy.context.object
light.name="NVP_Source_Fill_Light"
light.data.energy=850.0
light.data.shape="DISK"
light.data.size=5
scene.world.color=(0.05,0.05,0.05)
bpy.ops.wm.save_as_mainfile(filepath=args.output,check_existing=False)
scene.render.filepath=args.render
bpy.ops.render.render(write_still=True)
if not Path(args.output).is_file() or not Path(args.render).is_file():
    raise RuntimeError("Blender did not produce native scene and Cycles frame")
audit={
    "passed":True,
    "format":"nvp.plan04.cycles_source_build.v1",
    "engine":scene.render.engine,
    "cycles_cpu_denoising_capability":denoising_capability,
    "take_sha256":source["take_sha256"],
    "scene_sha256":source["scene_sha256"],
    "selection_sha256":source["selection_sha256"],
    "source_tick":source["source_tick"],
    "camera_path":source["camera_path"],
    "geometry_count":len(source["geometry"]),
    "original_source_modified":False,
    "ffmpeg_used":False,
    "cinema_master_published":False
}
Path(args.audit).write_text(json.dumps(audit,sort_keys=True),encoding="utf8")
'''
TRUSTED_REOPEN_SCRIPT=r'''
import argparse
import json
import sys
from pathlib import Path

import bpy

p=argparse.ArgumentParser()
p.add_argument("--manifest",required=True)
p.add_argument("--audit",required=True)
p.add_argument("--preview",required=True)
args=p.parse_args(sys.argv[sys.argv.index("--")+1:])
expected=json.loads(Path(args.manifest).read_text(encoding="utf8"))
scene=bpy.context.scene
if (set(expected)!={"take_sha256","scene_sha256","selection_sha256",
        "source_tick","geometry_count"} or
        scene.render.engine!="CYCLES" or scene.camera is None or
        scene["nvp_original_take_sha256"]!=expected["take_sha256"] or
        scene["nvp_original_scene_sha256"]!=expected["scene_sha256"] or
        scene["nvp_source_selection_sha256"]!=expected["selection_sha256"] or
        scene["nvp_exact_film_tick"]!=str(expected["source_tick"])):
    raise RuntimeError("Independently reopened Blender differs from immutable source")
objects=[o for o in scene.objects if o.name.startswith("nvp_source_")]
if len(objects)!=expected["geometry_count"]:
    raise RuntimeError("Reopened scene geometry count changed")
scene.render.filepath=args.preview
scene.cycles.device="CPU"
scene.cycles.samples=8
# Repeat the capability check in the independent native Blender process.
reopen_settings=getattr(bpy.context.view_layer,"cycles",None)
if reopen_settings is not None and hasattr(reopen_settings,"use_denoising"):
    reopen_settings.use_denoising=False
    if reopen_settings.use_denoising is not False:
        raise RuntimeError("Independent Blender cannot disable denoising")
bpy.ops.render.render(write_still=True)
if not Path(args.preview).is_file():
    raise RuntimeError("Independent Blender reopening produced no Cycles preview")
Path(args.audit).write_text(json.dumps({
    "passed":True,
    "format":"nvp.plan04.cycles_independent_reopen.v1",
    "engine":"CYCLES","source_take_sha256":expected["take_sha256"],
    "source_scene_sha256":expected["scene_sha256"],
    "source_tick":expected["source_tick"],
    "geometry_count":len(objects),
    "reopened_in_separate_native_blender_worker":True,
    "ffmpeg_used":False,"original_source_modified":False,
    "master_published":False,
},sort_keys=True),encoding="utf8")
'''
