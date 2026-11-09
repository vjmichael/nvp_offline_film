# SPDX-License-Identifier: GPL-2.0-or-later
"""01O: pinned Blender 5.2 worker for EIGHT contiguous original film frames.

One original source animated USD and one director camera are reused for an
8-frame Cycles chunk. Other camera rays/shadows recover before the next
frame. Outputs are PNGs + one source-linked audit, not self-certified media.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Euler,Vector
from nvp_usd_film01m_camera_ray_mask import per_camera_primary_ray_exclusions

SOURCE_FORMAT="nvp.usd_film01o.original_720frame_director_rig_source.v1"
CHUNK_FORMAT="nvp.usd_film01o.reviewed_native_cycles_chunk.v1"
AUDIT_FORMAT="nvp.usd_film01o.native_cycles_chunk_audit.v1"

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")

def digest(path):
    h=sha256()
    with Path(path).open("rb") as source:
        for part in iter(lambda:source.read(1<<20),b""):
            h.update(part)
    return h.hexdigest()

def main():
    args=sys.argv[sys.argv.index("--")+1:]
    if len(args)!=4 or set(args[::2])!={"--manifest","--audit"}:
        raise PermissionError("Only reviewed source chunk and audit options allowed")
    params=dict(zip(args[::2],args[1::2]))
    root=Path.cwd().resolve(strict=True)
    paths={}
    for option,name in params.items():
        supplied=Path(name)
        dest=supplied.resolve()
        if supplied.is_symlink() or dest.parent!=root or (
            option=="--manifest" and not dest.is_file()) or (
            option=="--audit" and dest.exists()):
            raise PermissionError("Original Cycles render chunk path outside job")
        paths[option]=dest
    chunk=json.loads(paths["--manifest"].read_text("utf8"))
    source=json.loads((root/"source.json").read_text("utf8"))
    if (type(source) is not dict or source.get("format")!=SOURCE_FORMAT or
        source.get("frame_count")!=720 or source.get("fps")!=24 or
        source.get("native_cycles_pixels_rendered") is not False or
        type(chunk) is not dict or set(chunk)!={
            "format","source_manifest_sha256","source_usd_sha256",
            "camera_bank_sha256","camera_id","start_frame",
            "frame_count","attempt"} or
        chunk["format"]!=CHUNK_FORMAT or
        chunk["source_manifest_sha256"]!=digest(root/"source.json") or
        chunk["source_usd_sha256"]!=source["source_usd_sha256"] or
        chunk["camera_bank_sha256"]!=source["source_camera_bank_sha256"]):
        raise PermissionError("Unverified original film roll chunk source")
    start=chunk["start_frame"]
    count=chunk["frame_count"]
    if (type(start) is not int or type(count) is not int or
        start not in range(0,720,8) or count!=min(8,720-start) or
        type(chunk["attempt"]) is not int or not 1<=chunk["attempt"]<=99):
        raise ValueError("Only exact contiguous eight-frame original chunks")
    cameras=[c for c in source["cameras"] if c["camera_id"]==chunk["camera_id"]]
    if len(cameras)!=1:
        raise PermissionError("Requested camera not in original film source bank")
    choice=cameras[0]
    original_world=root/"source.usda"
    if (original_world.is_symlink() or not original_world.is_file() or
        original_world.stat().st_size!=source["source_usd_size_bytes"] or
        digest(original_world)!=source["source_usd_sha256"]):
        raise PermissionError("Original animated USD changed before native render")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    supported=set(bpy.ops.wm.usd_import.get_rna_type().properties.keys())
    opts={"filepath":str(original_world)}
    for option in ("import_cameras","import_lights","import_materials",
                   "import_usd_preview","import_meshes","read_mesh_uvs",
                   "apply_unit_conversion_scale","set_frame_range"):
        if option in supported:opts[option]=True
    if "merge_parent_xform" in supported:opts["merge_parent_xform"]=False
    bpy.ops.wm.usd_import(**opts)
    scene=bpy.context.scene
    scene.frame_start=1
    scene.frame_end=720
    scene.render.fps=24
    objects=list(bpy.data.objects)
    camera_leaf=choice["source_camera_prim"].split("/")[-1]
    found=[o for o in objects if o.type=="CAMERA" and (
        o.name==camera_leaf or o.name.rsplit(".",1)[0]==camera_leaf)]
    if len(found)!=1 or len([o for o in objects
            if o.type=="MESH" and len(o.data.vertices)>=3])<3:
        raise RuntimeError("Missing original imported actor meshes or native film camera")
    camera=found[0]
    if not math.isclose(float(camera.data.lens),
        choice["source_focal_length_mm"],rel_tol=0,abs_tol=.1):
        raise RuntimeError("Camera source focal length changed in Blender importer")
    scene.camera=camera
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=8
    scene.render.resolution_x=320
    scene.render.resolution_y=180
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.use_file_extension=False
    scene["nvp_original_camera_bank_sha256"]=source["source_camera_bank_sha256"]
    scene["nvp_original_take_sha256"]=source["original_world_take_sha256"]
    scene["nvp_original_performance_sha256"]=source["original_performance_sha256"]
    original_actor_ids={a["actor_id"] for a in
        source["original_frame_evidence"][0]["original_actor_positions"]}
    rows=[]
    for i in range(start,start+count):
        frame=source["original_frame_evidence"][i]
        if frame["frame"]!=i:
            raise RuntimeError("Missing or reordered original film actor-state frame")
        scene.frame_set(i+1)
        bpy.context.view_layer.update()
        actual_camera=[float(camera.matrix_world.translation[j]) for j in range(3)]
        expected_camera=next((x["position_m"]
            for x in frame["original_camera_positions"]
            if x["camera_id"]==chunk["camera_id"]),None)
        if (expected_camera is None or any(
                abs(a-b)>.01 for a,b in zip(actual_camera,expected_camera))):
            raise RuntimeError("Animated original native camera moved in Blender")
        actual_ids=set()
        for actor in frame["original_actor_positions"]:
            if actor["actor_id"] in actual_ids:
                raise RuntimeError("Repeated actor identity")
            actual_ids.add(actor["actor_id"])
            leaf=actor["source_prim"].split("/")[-1]
            matching=[o for o in objects if o.name==leaf or
                      o.name.rsplit(".",1)[0]==leaf]
            if len(matching)!=1:
                raise RuntimeError("Original ActorID root missing from Blender animation")
            location=[float(matching[0].matrix_world.translation[j])
                      for j in range(3)]
            if any(abs(a-b)>.01 for a,b in zip(location,actor["position_m"])):
                raise RuntimeError("Actual Blender actor motion differs from original source USD")
        if actual_ids!=original_actor_ids:
            raise PermissionError("Original performing ActorIDs changed within a film roll")
        frame_name=f"frame_{i:04d}.png"
        picture=root/frame_name
        if picture.exists() or picture.is_symlink():
            raise FileExistsError("Blender worker cannot overwrite an earlier source frame")
        scene.render.filepath=str(picture)
        with per_camera_primary_ray_exclusions(
                objects,choice["camera_ray_exclusions"]) as masking:
            if choice["camera_ray_exclusions"] and not masking[
                    "masked_mesh_object_count"]:
                raise RuntimeError("Source wall ray mask was not imported/applied")
            bpy.ops.render.render(write_still=True)
        if not picture.is_file() or picture.stat().st_size<100:
            raise RuntimeError("Actual original-frame Cycles output is missing")
        rows.append({
            "frame":i,
            "original_film_tick":frame["original_film_tick"],
            "original_actor_state_sha256":frame[
                "original_actor_state_sha256"],
            "rendered_png_file":frame_name,
            "rendered_png_sha256":digest(picture),
            "original_actor_positions_independently_checked":True,
            "original_camera_position_independently_checked":True,
            "primary_ray_excluded_prims":choice["camera_ray_exclusions"],
            "ray_visibility_restored_for_next_frame":True,
            "actual_native_cycles_image":True})
    report={
        "format":AUDIT_FORMAT,"passed":True,
        "source_manifest_sha256":chunk["source_manifest_sha256"],
        "source_usd_sha256":chunk["source_usd_sha256"],
        "original_camera_bank_sha256":source["source_camera_bank_sha256"],
        "original_world_take_sha256":source["original_world_take_sha256"],
        "original_performance_sha256":source["original_performance_sha256"],
        "camera_id":chunk["camera_id"],"start_frame":start,
        "frame_count":count,"attempt":chunk["attempt"],
        "original_frame_receipts":rows,
        "actual_native_cycles_frames":len(rows),
        "blender_version":bpy.app.version_string,
        "finished_film_approved":False}
    paths["--audit"].write_bytes(canonical(report))

if __name__=="__main__":
    main()
