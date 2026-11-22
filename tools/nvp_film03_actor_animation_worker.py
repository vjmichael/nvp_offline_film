# SPDX-License-Identifier: GPL-2.0-or-later
"""FILM03-06 first-party real Blender 5.2 actor-motion execution worker.

Only uses trusted, SHA-pinned source stage in the existing contained
BlenderWorkerSupervisor. No AI-provided Python, meshes, executable names,
arbitrary scripts, network assets, FFmpeg or source Take mutations.
"""
from __future__ import annotations

import bpy
from mathutils import Matrix
from pathlib import Path
from hashlib import sha256
import json
import math
import sys

FORMAT="nvp.film03.actor_animation_packet.v1"
RECEIPT="nvp.film03.blender_actor_motion_native_receipt.v1"
FRAME_LIMIT=24
PRESETS={"steady","lopsided_roll","uneven_step"}
FPS=24


def canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False,
                      allow_nan=False).encode("utf8")


def digest(data):
    return sha256(canonical(data)).hexdigest()


def file_sha(path):
    h=sha256()
    with Path(path).open("rb") as inp:
        for block in iter(lambda:inp.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def gait_delta(preset,n):
    if preset=="steady":
        return 0.0,0.0
    if preset=="lopsided_roll":
        return 0.10*math.sin(n*math.pi/2)+0.05*(n%3==2), 0.075*math.sin(n*math.pi/3)
    if preset=="uneven_step":
        return (0.13 if n%4 in (1,2) else 0.0), (0.05 if n%2 else -0.05)
    raise ValueError("Unknown director-approved actor gait")


def animated_matrix(native,preset,n):
    original=Matrix(native).transposed()
    lift,tilt=gait_delta(preset,n)
    return Matrix.Translation((0,0,lift)) @ Matrix.Rotation(tilt,4,"Y") @ original


def packet_paths():
    argv=sys.argv[sys.argv.index("--")+1:]
    if len(argv)!=8 or len(set(argv[::2]))!=4:
        raise PermissionError("Only fixed reviewed native Blender motion options")
    args=dict(zip(argv[::2],argv[1::2]))
    if set(args)!={"--manifest","--output","--audit","--preview"}:
        raise PermissionError("Unreviewed Blender actor animation argument")
    stage=Path(args["--manifest"]).resolve(strict=True)
    root=stage.parent
    outputs=[Path(args[x]).resolve() for x in ("--output","--audit","--preview")]
    if (stage.is_symlink() or any(p.parent!=root or p.exists() or p.is_symlink()
                                  for p in outputs)):
        raise PermissionError("Untrusted actor motion paths or overwritten output")
    return stage,*outputs


def validate(packet):
    if type(packet) is not dict or packet.get("format")!=FORMAT or (
            type(packet.get("source")) is not dict):
        raise PermissionError("No approved source-bound actor motion packet")
    data=packet["source"]
    if packet.get("source_sha256")!=digest(data):
        raise PermissionError("Stage source sha for native actor motion mismatched")
    aid=data.get("actor_id")
    if (type(aid) is not str or len(aid)!=32 or
            any(x not in "0123456789abcdef" for x in aid)):
        raise PermissionError("No exact canonical ActorID")
    profile=data.get("profile")
    if (type(profile) is not dict or
            digest(profile)!=data.get("profile_sha256") or
            profile.get("movement",{}).get("gait_preset") not in PRESETS or
            profile["movement"]["gait_preset"]!=data.get("gait_preset")):
        raise PermissionError("Blender actor gait differs from approved ActorID profile")
    actor=data.get("actor_prim_path")
    cast=data.get("cast_actor_id_by_prim")
    if (type(cast) is not dict or cast.get(actor)!=aid or
            len(cast)<1 or len(set(cast.values()))!=len(cast)):
        raise PermissionError("ActorID is not the one original frozen scene cast")
    frames=data.get("frames")
    if (type(frames) is not list or not 2<=len(frames)<=FRAME_LIMIT or
            type(data.get("assets")) is not dict or
            data.get("fps")!=FPS or
            type(data.get("source_take_sha256")) is not str or
            len(data["source_take_sha256"])!=64):
        raise PermissionError("Not a bounded original ActorID source take")
    paths=set(frames[0]["world_matrices"])
    if (not {"/World/Camera", "/World/PracticalLight"} <= paths or
            set(cast) - paths or actor not in paths or
            set(data["assets"]) != paths-{
                "/World/Camera","/World/PracticalLight"}):
        raise PermissionError("Source actors, camera, light or assets missing")
    for asset_path,asset in data["assets"].items():
        raw=asset.get("source_data")
        if (not isinstance(raw,dict) or raw.get("shape") not in ("mesh","cube","sphere")
                or len(asset.get("source_document_sha256",""))!=64):
            raise PermissionError("Reviewed native Blender does not support this original mesh")
        if raw["shape"]=="mesh":
            if (not 3<=len(raw.get("points",[]))<=5000 or
                    not 1<=len(raw.get("triangles",[]))<=10000):
                raise PermissionError("Unbounded original triangle mesh")
        elif type(raw.get("size_m")) not in (float,int):
            raise PermissionError("Original primitive size invalid")
    for offset,frame in enumerate(frames):
        if (frame["source_take_sha256"]!=data["source_take_sha256"] or
                frame["frame_in_take"]!=data["first_frame_in_take"]+offset or
                set(frame["world_matrices"])!=paths or
                len(frame.get("source_snapshot_sha256",""))!=64):
            raise PermissionError("Actor animation crosses a source revision or unexpected time")
        for m in frame["world_matrices"].values():
            if (type(m) is not list or len(m)!=4 or
                    any(type(row) is not list or len(row)!=4 or
                        any(type(x) not in (int,float) or not math.isfinite(x)
                            for x in row) for row in m)):
                raise PermissionError("Nonfinite original OpenUSD transform")
    return data


def make_material(name,data):
    p=data.get("preview_material") or {}
    rgb=p.get("base_color_rgb",[0.55,0.55,0.6])
    metallic=p.get("metallic",0.1)
    rough=p.get("roughness",0.45)
    mat=bpy.data.materials.new(name)
    mat.use_nodes=True
    node=mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value=(*rgb,1.0)
    node.inputs["Metallic"].default_value=metallic
    node.inputs["Roughness"].default_value=rough
    return mat


def make_geometry(path,entry):
    source=entry["source_data"]
    key=source["shape"]
    if key=="mesh":
        mesh=bpy.data.meshes.new("ActorIDSourceMesh")
        mesh.from_pydata(source["points"],[],source["triangles"])
        mesh.update()
        obj=bpy.data.objects.new("NVP_Frozen_Source_"+path.rsplit("/",1)[-1],mesh)
        bpy.context.collection.objects.link(obj)
    elif key=="cube":
        bpy.ops.mesh.primitive_cube_add(size=source["size_m"])
        obj=bpy.context.object
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=32,ring_count=16,radius=source["size_m"]/2)
        obj=bpy.context.object
    obj.data.materials.append(make_material("source_material_"+path.rsplit("/",1)[-1],source))
    obj["nvp_original_asset_sha256"]=entry["source_document_sha256"]
    obj["nvp_source_prim_path"]=path
    return obj


def main():
    manifest,blend,audit,preview=packet_paths()
    packet=json.loads(manifest.read_text("utf8"))
    source=validate(packet)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=8
    scene.render.resolution_x=640
    scene.render.resolution_y=360
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.fps=FPS
    objects={p:make_geometry(p,data) for p,data in source["assets"].items()}
    cam=bpy.data.objects.new("NVP_Original_Camera",bpy.data.cameras.new("Camera"))
    bpy.context.collection.objects.link(cam)
    cam.data.lens=50
    scene.camera=cam
    objects["/World/Camera"]=cam
    lamp=bpy.data.objects.new("NVP_Original_Light",
                               bpy.data.lights.new("PracticalLight","AREA"))
    bpy.context.collection.objects.link(lamp)
    lamp.data.energy=700
    lamp.data.shape="DISK"
    lamp.data.size=2
    objects["/World/PracticalLight"]=lamp
    # Distinct source objects are never moved by a different actor's
    # gait. Their exact source matrices are keyed unchanged.
    paths=sorted(objects)
    motion_rows=[]
    for n,row in enumerate(source["frames"]):
        for prim in paths:
            obj=objects[prim]
            m=(animated_matrix(row["world_matrices"][prim],
                    source["gait_preset"],n)
               if prim==source["actor_prim_path"]
               else Matrix(row["world_matrices"][prim]).transposed())
            obj.matrix_world=m
            for component in ("location","rotation_euler","scale"):
                obj.keyframe_insert(data_path=component,frame=n+1)
        native=row["world_matrices"][source["actor_prim_path"]]
        derived=animated_matrix(native,source["gait_preset"],n)
        motion_rows.append({
            "frame_in_take":row["frame_in_take"],
            "source_snapshot_sha256":row["source_snapshot_sha256"],
            "source_actor_matrix_sha256":digest(native),
            "generated_actor_matrix_sha256":digest(
                [[round(derived[i][j],8) for j in range(4)] for i in range(4)]),
            "gait_lift_m":round(gait_delta(source["gait_preset"],n)[0],8),
            "gait_tilt_radians":round(gait_delta(source["gait_preset"],n)[1],8),
            "other_actors_motion_source_unchanged":True,
        })
    scene.frame_start=1
    scene.frame_end=len(source["frames"])
    scene.frame_set(max(1,len(source["frames"])//2))
    for prim,obj in objects.items():
        obj["nvp_actor_identity"]=source["actor_id"] if prim==source["actor_prim_path"] else ""
        obj["nvp_profile_sha256"]=source["profile_sha256"] if prim==source["actor_prim_path"] else ""
    bpy.ops.wm.save_as_mainfile(filepath=str(blend),check_existing=False)
    if blend.stat().st_size<100:
        raise RuntimeError("Real Blender animation failed to save")
    scene.render.filepath=str(preview)
    bpy.ops.render.render(write_still=True)
    if not preview.is_file() or preview.read_bytes()[:8]!=b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Real Cycles character animation preview was not rendered")
    report={
        "format":RECEIPT,"passed":True,
        "actor_id":source["actor_id"],
        "actor_prim_path":source["actor_prim_path"],
        "voice_id":source["voice_id"],
        "source_take_sha256":source["source_take_sha256"],
        "profile_sha256":source["profile_sha256"],
        "source_packet_sha256":packet["source_sha256"],
        "gait_preset":source["gait_preset"],
        "frame_count":len(motion_rows),
        "generated_keyframes":motion_rows,
        "all_other_actors_source_transforms_unchanged":True,
        "original_frozen_take_modified":False,
        "original_voice_modified":False,
        "actual_renderer":"Blender Cycles",
        "actual_blender_version":bpy.app.version_string,
        "blend_sha256":file_sha(blend),
        "preview_png_sha256":file_sha(preview),
        "gait_procedurally_keyframed":True,
        "no_film_editorial_approval":True,
        "source_human_director_review_pending":True,
    }
    audit.write_bytes(canonical(report))


if __name__=="__main__":
    main()
