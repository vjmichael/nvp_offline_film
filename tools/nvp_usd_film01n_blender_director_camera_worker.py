# SPDX-License-Identifier: GPL-2.0-or-later
"""USD-FILM-01N: native source-locked Blender director-camera smoke.

One selected virtual camera, one original ActorID performance moment.
Explicit primary-ray wall exceptions are applied ONLY while this one
Cycles picture renders. Every prior wall visibility setting is restored.
No generated actor mesh, camera proxy, untrusted script or audio.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import sys

import bpy

from nvp_usd_film01m_camera_ray_mask import per_camera_primary_ray_exclusions

FORMAT="nvp.usd_film01n.director_camera_native_frame_snapshot.v1"
AUDIT="nvp.usd_film01n.native_cycles_director_camera_view.v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(path):
    hasher=sha256()
    with Path(path).open("rb") as source:
        for part in iter(lambda:source.read(1024*1024),b""):
            hasher.update(part)
    return hasher.hexdigest()


def args():
    items=sys.argv[sys.argv.index("--")+1:]
    if (len(items)!=8 or len(set(items[::2]))!=4 or
        set(items[::2]) != {
            "--manifest","--output","--audit","--preview"}):
        raise PermissionError("Fixed reviewed original director camera worker flags only")
    result=dict(zip(items[::2],items[1::2]))
    root=Path.cwd().resolve(strict=True)
    found={}
    for key,raw in result.items():
        name=Path(raw)
        file=name.resolve()
        if (name.is_symlink() or file.parent!=root or
            (key=="--manifest" and not file.is_file()) or
            (key!="--manifest" and file.exists())):
            raise PermissionError("Director camera worker source/output outside reviewed job")
        found[key]=file
    return root,found


def run():
    work,files=args()
    packet=json.loads(files["--manifest"].read_text("utf8"))
    if (type(packet) is not dict or set(packet)!={
        "format","source","source_sha256"} or packet["format"]!=FORMAT or
        packet["source_sha256"]!=sha256(
            canonical(packet["source"])).hexdigest()):
        raise PermissionError("Director camera source packet not original")
    source=packet["source"]
    keys={
        "format","source_bank_id","source_bank_revision",
        "source_bank_sha256","source_world_take_sha256",
        "source_world_sha256","source_performance_sha256",
        "source_usd_file","source_usd_sha256",
        "source_usd_size_bytes","source_camera_id",
        "source_camera_prim","source_camera_position_m",
        "source_camera_focal_length_mm","source_camera_ray_exclusions",
        "source_actor_positions","original_film_tick",
        "original_actor_source_not_replaced",
        "source_world_visibility_not_modified","native_cycles_frame_rendered"}
    if (type(source) is not dict or set(source)!=keys or
        source["format"]!=FORMAT or source["source_usd_file"]!="source.usda" or
        source["native_cycles_frame_rendered"] is not False or
        source["original_actor_source_not_replaced"] is not True or
        source["source_world_visibility_not_modified"] is not True or
        type(source["original_film_tick"]) is not int or
        type(source["source_camera_ray_exclusions"]) is not list):
        raise PermissionError("Original director camera source contract invalid")
    usd=work/"source.usda"
    if (usd.is_symlink() or not usd.is_file() or
        usd.stat().st_size!=source["source_usd_size_bytes"] or
        digest(usd)!=source["source_usd_sha256"]):
        raise RuntimeError("Original camera world USD bytes changed before Blender")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    props=set(bpy.ops.wm.usd_import.get_rna_type().properties.keys())
    kwargs={"filepath":str(usd)}
    for key in ("import_cameras","import_lights","import_materials",
                "import_usd_preview","import_meshes","read_mesh_uvs",
                "apply_unit_conversion_scale"):
        if key in props:
            kwargs[key]=True
    if "merge_parent_xform" in props:
        kwargs["merge_parent_xform"]=False
    if "set_frame_range" in props:
        kwargs["set_frame_range"]=False
    bpy.ops.wm.usd_import(**kwargs)
    scene=bpy.context.scene
    scene.frame_set(1)
    bpy.context.view_layer.update()
    objects=list(bpy.data.objects)
    meshes=[o for o in objects if o.type=="MESH" and len(o.data.vertices)>=3]
    cameras=[o for o in objects if o.type=="CAMERA"]
    if len(meshes)<3 or not cameras:
        raise RuntimeError("Real original actor geometry or camera not imported")
    name=source["source_camera_id"]
    matching=[o for o in cameras if o.name==name or
              o.name.rsplit(".",1)[0]==name]
    if len(matching)!=1:
        raise RuntimeError("Director camera missing/ambiguous in genuine USD import")
    camera=matching[0]
    observed=[float(camera.matrix_world.translation[i]) for i in range(3)]
    if any(abs(x-y)>0.01 for x,y in zip(
            observed,source["source_camera_position_m"])):
        raise RuntimeError("Actual Blender camera differs from original USD position")
    if not math.isclose(
            float(camera.data.lens),source["source_camera_focal_length_mm"],
            rel_tol=0,abs_tol=0.1):
        raise RuntimeError("Native film focal length changed in Blender import")
    checked=[]
    for actor in source["source_actor_positions"]:
        original=actor["source_prim"].split("/")[-1]
        found=[o for o in objects if o.name==original or
               o.name.rsplit(".",1)[0]==original]
        if len(found)!=1:
            raise RuntimeError("Original source ActorID root did not import uniquely")
        pos=[float(found[0].matrix_world.translation[i]) for i in range(3)]
        if any(abs(x-y)>0.01 for x,y in zip(pos,actor["position_m"])):
            raise RuntimeError("Original ActorID transform changed in native render")
        checked.append(actor["actor_id"])
    # A native camera is an optical scene object, never a renderable mesh.
    # Do not let the exporter inject a visible proxy for camera placement.
    if any(o.type=="MESH" and o.name.startswith(
            "NVPDirectorCameraRig") for o in objects):
        raise RuntimeError("Camera equipment mesh was introduced into original picture")
    scene.camera=camera
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=8
    scene.render.resolution_x=320
    scene.render.resolution_y=180
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.filepath=str(files["--preview"])
    scene.render.use_file_extension=False
    scene["nvp_original_director_bank_sha256"]=source["source_bank_sha256"]
    scene["nvp_original_take_sha256"]=source["source_world_take_sha256"]
    scene["nvp_director_camera_id"]=name
    scene["nvp_source_usd_sha256"]=source["source_usd_sha256"]
    scene["nvp_original_film_tick"]=source["original_film_tick"]
    scene["nvp_original_actor_ids_json"]=json.dumps(sorted(checked))
    scene["nvp_no_finished_film_approval"]=True
    with per_camera_primary_ray_exclusions(
            objects,source["source_camera_ray_exclusions"]) as mask:
        if (source["source_camera_ray_exclusions"] and
            mask["masked_mesh_object_count"]==0):
            raise RuntimeError("Camera primary-ray mask did not affect source wall")
        if any(o.type=="MESH" and o.name in checked for o in objects):
            pass
        bpy.ops.render.render(write_still=True)
    if not files["--preview"].is_file() or files["--preview"].stat().st_size<100:
        raise RuntimeError("Native Cycles source camera did not render a real frame")
    if any(o.type=="MESH" and o.visible_camera is False
           for o in objects):
        raise RuntimeError("Per-shot camera ray exclusions leaked after render")
    bpy.ops.wm.save_as_mainfile(filepath=str(files["--output"]))
    if not files["--output"].is_file():
        raise RuntimeError("Native director camera .blend was not saved")
    output={
        "format":AUDIT,"passed":True,
        "original_camera_bank_sha256":source["source_bank_sha256"],
        "original_world_take_sha256":source["source_world_take_sha256"],
        "source_performance_sha256":source["source_performance_sha256"],
        "source_usd_sha256":source["source_usd_sha256"],
        "original_film_tick":source["original_film_tick"],
        "camera_id":name,
        "native_camera_position_m":observed,
        "camera_focal_length_mm":float(camera.data.lens),
        "original_actor_count":len(checked),
        "actual_camera_ray_excluded_prims":mask["excluded_source_prims"],
        "actual_ray_masked_meshes":mask["masked_mesh_object_count"],
        "actual_cameras_not_rendered_as_geometry":True,
        "per_camera_ray_mask_restored":True,
        "actual_native_cycles_image":True,
        "rendered_png_sha256":digest(files["--preview"]),
        "saved_blend_sha256":digest(files["--output"]),
        "blender_version":bpy.app.version_string,
        "finished_film_approved":False}
    files["--audit"].write_text(
        json.dumps(output,sort_keys=True,separators=(",",":")),"utf8")


if __name__=="__main__":
    run()
