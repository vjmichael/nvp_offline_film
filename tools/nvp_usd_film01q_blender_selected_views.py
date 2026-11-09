# SPDX-License-Identifier: GPL-2.0-or-later
"""USD-FILM-01Q: actual 8 selected viewpoint frames, not full-camera rolls.

Single original USD performance. Camera may CHANGE at any original frame.
An actual Blender/Cycles worker renders only the EDL-chosen view for each
source tick, with per-shot ray-exclusion restored before the next view.
No new ActorID, synthetic frames, alternate animation or camera proxy.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import sys

import bpy
from nvp_usd_film01r_quality import verify_quality,quality_hash
from nvp_usd_film01m_camera_ray_mask import per_camera_primary_ray_exclusions

SOURCE_FORMAT="nvp.usd_film01o.original_720frame_director_rig_source.v1"
PLAN_FORMAT="nvp.usd_film01q.source_selected_view_render_plan.v1"
CHUNK_FORMAT="nvp.usd_film01q.selected_view_native_chunk.v1"
AUDIT_FORMAT="nvp.usd_film01q.native_selected_view_cycles_chunk_audit.v1"


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def digest(path):
    h=sha256()
    with Path(path).open("rb") as reader:
        for piece in iter(lambda:reader.read(1048576),b""):
            h.update(piece)
    return h.hexdigest()


def run():
    argv=sys.argv[sys.argv.index("--")+1:]
    if len(argv)!=4 or set(argv[::2])!={"--manifest","--audit"}:
        raise PermissionError("Reviewed original-shot renderer flags only")
    args=dict(zip(argv[::2],argv[1::2]))
    root=Path.cwd().resolve(strict=True)
    files={}
    for key,value in args.items():
        requested=Path(value)
        path=requested.resolve()
        if (requested.is_symlink() or path.parent!=root or
            (key=="--manifest" and not path.is_file()) or
            (key=="--audit" and path.exists())):
            raise PermissionError("Camera source shot path escaped fixed job dir")
        files[key]=path
    chunk=json.loads(files["--manifest"].read_text("utf8"))
    manifest=root/"source.json"
    plan_file=root/"plan.json"
    stage=root/"source.usda"
    for file in (manifest,plan_file,stage):
        if file.is_symlink() or not file.is_file():
            raise PermissionError("Missing reviewed immutable source film input")
    source=json.loads(manifest.read_text("utf8"))
    plan=json.loads(plan_file.read_text("utf8"))
    if (type(chunk) is not dict or set(chunk)!={
            "format","plan_sha256","source_manifest_sha256",
            "original_usd_sha256","edit_document_sha256","start_frame",
            "frame_count","source_frames_sha256","attempt"} or
        chunk.get("format")!=CHUNK_FORMAT or
        plan.get("format")!=PLAN_FORMAT or
        source.get("format")!=SOURCE_FORMAT or
        chunk["plan_sha256"]!=digest(plan_file) or
        chunk["source_manifest_sha256"]!=digest(manifest) or
        chunk["original_usd_sha256"]!=digest(stage) or
        chunk["original_usd_sha256"]!=source.get("source_usd_sha256") or
        chunk["edit_document_sha256"]!=plan.get("edit_document_sha256") or
        plan.get("original_performance_sha256")!=
            source.get("original_performance_sha256") or
        plan.get("source_bank_sha256")!=source.get("source_camera_bank_sha256") or
        plan.get("source_manifest_sha256")!=digest(manifest) or
        plan.get("original_usd_sha256")!=digest(stage)):
        raise PermissionError("Selected source viewpoint plan or source USD altered")
    profile=verify_quality(plan.get("render_profile"))
    if quality_hash(profile)!=plan.get("render_profile_sha256"):
        raise PermissionError("Selected view profile changed after director render plan")
    start=chunk["start_frame"]
    count=chunk["frame_count"]
    if (type(start) is not int or start not in range(0,720,8) or
        type(count) is not int or count!=8 or
        type(chunk["attempt"]) is not int or
        not 1<=chunk["attempt"]<=99 or
        len(plan.get("frames",[]))!=720 or
        len(plan.get("chunks",[]))!=90):
        raise ValueError("Only eight exact EDL-selected source frames are admitted")
    frames=plan["frames"][start:start+count]
    scheduled=plan["chunks"][start//8]
    if (scheduled["start_frame"]!=start or
        scheduled["frame_count"]!=count or
        chunk["source_frames_sha256"]!=scheduled["source_frames_sha256"] or
        sha256(canonical(frames)).hexdigest()!=chunk["source_frames_sha256"]):
        raise PermissionError("Selected camera arrangement differs from approved edit")
    original_frames=source.get("original_frame_evidence")
    if type(original_frames) is not list or len(original_frames)!=720:
        raise PermissionError("Source original ActorID evidence missing")
    cameras={x["camera_id"]:x for x in source["cameras"]}
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    props=set(bpy.ops.wm.usd_import.get_rna_type().properties.keys())
    opts={"filepath":str(stage)}
    for key in ("import_cameras","import_lights","import_materials",
                "import_usd_preview","import_meshes","read_mesh_uvs",
                "apply_unit_conversion_scale","set_frame_range"):
        if key in props:opts[key]=True
    if "merge_parent_xform" in props:opts["merge_parent_xform"]=False
    bpy.ops.wm.usd_import(**opts)
    scene=bpy.context.scene
    scene.frame_start=1
    scene.frame_end=720
    scene.render.fps=24
    objects=list(bpy.data.objects)
    if len([o for o in objects if o.type=="MESH" and
            len(o.data.vertices)>=3])<3:
        raise RuntimeError("Genuine original actor geometry missing from USD import")
    actual_cameras={}
    for camera_id in scheduled["camera_ids"]:
        original=cameras.get(camera_id)
        if original is None:
            raise PermissionError("Requested virtual viewpoint not in actual source")
        leaf=original["source_camera_prim"].split("/")[-1]
        match=[o for o in objects if o.type=="CAMERA" and
               (o.name==leaf or o.name.rsplit(".",1)[0]==leaf)]
        if len(match)!=1:
            raise RuntimeError("Actual Blender camera missing/ambiguous")
        if not math.isclose(float(match[0].data.lens),
            original["source_focal_length_mm"],rel_tol=0,abs_tol=.1):
            raise RuntimeError("Blender imported camera lost native optics")
        actual_cameras[camera_id]=match[0]
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=profile["samples"]
    scene.render.resolution_x=profile["resolution_x"]
    scene.render.resolution_y=profile["resolution_y"]
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.use_file_extension=False
    scene["nvp_original_performance_sha256"]=source["original_performance_sha256"]
    scene["nvp_source_edit_sha256"]=plan["edit_document_sha256"]
    scene["nvp_render_only_approved_viewpoints"]=True
    rows=[]
    for frame in frames:
        i=frame["frame"]
        original=original_frames[i]
        if (i!=start+len(rows) or
            frame["original_film_tick"]!=original["original_film_tick"] or
            frame["original_actor_state_sha256"]!=
                original["original_actor_state_sha256"]):
            raise RuntimeError("Original source Film Time/ActorID changed at EDL cut")
        camera_id=frame["camera_id"]
        camera=actual_cameras[camera_id]
        if (camera_id not in cameras or
            cameras[camera_id]["camera_ray_exclusions"]!=
                frame["camera_ray_exclusions"] or
            cameras[camera_id]["source_camera_prim"]!=
                frame["source_camera_prim"]):
            raise PermissionError("Selected camera source differs from original rig")
        scene.frame_set(i+1)
        bpy.context.view_layer.update()
        position=[float(camera.matrix_world.translation[k]) for k in range(3)]
        if any(abs(a-b)>.01 for a,b in zip(
                position,frame["source_camera_position_m"])):
            raise RuntimeError("Original virtual viewpoint motion changed")
        original_actors=original["original_actor_positions"]
        for actor in original_actors:
            leaf=actor["source_prim"].split("/")[-1]
            found=[o for o in objects if o.name==leaf or
                   o.name.rsplit(".",1)[0]==leaf]
            if len(found)!=1:
                raise RuntimeError("Original ActorID not imported uniquely")
            pos=[float(found[0].matrix_world.translation[k]) for k in range(3)]
            if any(abs(a-b)>.01 for a,b in zip(pos,actor["position_m"])):
                raise RuntimeError("Blender changed original performer at EDL frame")
        scene.camera=camera
        name=f"frame_{i:04d}.png"
        picture=root/name
        if picture.is_symlink() or picture.exists():
            raise FileExistsError("No overwriting a previous editor frame")
        scene.render.filepath=str(picture)
        with per_camera_primary_ray_exclusions(
                objects,frame["camera_ray_exclusions"]) as masked:
            if (frame["camera_ray_exclusions"] and
                masked["masked_mesh_object_count"]==0):
                raise RuntimeError("Requested wall-primary-ray mask did not apply")
            bpy.ops.render.render(write_still=True)
        if not picture.is_file() or picture.stat().st_size<100:
            raise RuntimeError("Native original-source selected view pixel missing")
        rows.append({
            "frame":i,"original_film_tick":frame["original_film_tick"],
            "original_actor_state_sha256":frame[
                "original_actor_state_sha256"],
            "selected_camera_id":camera_id,
            "selected_camera_prim":frame["source_camera_prim"],
            "view_cache_sha256":frame["view_cache_sha256"],
            "primary_ray_excluded_prims":frame["camera_ray_exclusions"],
            "rendered_png_file":name,
            "rendered_png_sha256":digest(picture),
            "actual_blender_cycles_pixels":True,
            "original_actors_and_camera_position_reverified":True,
            "camera_ray_mask_restored":True})
    report={
        "format":AUDIT_FORMAT,"passed":True,
        "source_manifest_sha256":chunk["source_manifest_sha256"],
        "source_usd_sha256":chunk["original_usd_sha256"],
        "plan_sha256":chunk["plan_sha256"],
        "edit_document_sha256":plan["edit_document_sha256"],
        "original_world_take_sha256":plan["original_world_take_sha256"],
        "original_performance_sha256":plan["original_performance_sha256"],
        "start_frame":start,"frame_count":count,
        "render_profile_sha256":plan["render_profile_sha256"],
        "render_resolution_x":profile["resolution_x"],
        "render_resolution_y":profile["resolution_y"],
        "render_samples":profile["samples"],
        "attempt":chunk["attempt"],"selected_view_frames":rows,
        "native_rendered_frames":len(rows),
        "native_blender_version":bpy.app.version_string,
        "full_original_camera_rolls_rendered":False,
        "director_picture_reviewed":False}
    files["--audit"].write_bytes(canonical(report))

if __name__=="__main__":
    run()
