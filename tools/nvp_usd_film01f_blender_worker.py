# SPDX-License-Identifier: GPL-2.0-or-later
"""01F: fixed first-party Blender 5.2 Cycles importer for real world Take USD.

No Blender-generated substitute actors, externally fetched assets, model code,
raw USD edits, audio synthesis or unreviewed scene building. The only spatial
contents originate from the host-verified frozen USD source snapshot.
"""
from __future__ import annotations

import bpy
from hashlib import sha256
import json
from pathlib import Path
import math
import sys

FORMAT="nvp.usd_film01f.original_world_cycles_packet.v1"
AUDIT="nvp.usd_film01f.native_cycles_original_world_frame.v1"


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,
                      separators=(",",":"),allow_nan=False).encode("ascii")


def digest(path):
    h=sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1<<20),b""):
            h.update(block)
    return h.hexdigest()


def paths():
    tokens=sys.argv[sys.argv.index("--")+1:]
    if len(tokens)!=8 or len(set(tokens[::2]))!=4:
        raise PermissionError("World-render worker requires four fixed reviewed options")
    args=dict(zip(tokens[::2],tokens[1::2]))
    if set(args)!={"--manifest","--output","--audit","--preview"}:
        raise PermissionError("Blender worker refused unknown executable/file option")
    root=Path.cwd().resolve(strict=True)
    found={}
    for flag,name in args.items():
        raw=Path(name)
        path=raw.resolve()
        if (raw.is_symlink() or path.parent!=root or
            (flag=="--manifest" and not path.is_file()) or
            (flag!="--manifest" and path.exists())):
            raise PermissionError("Only a private source-locked native worker directory")
        found[flag]=path
    return found


def check(packet,root):
    if (type(packet) is not dict or
        set(packet)!={"format","source","source_sha256"} or
        packet["format"]!=FORMAT):
        raise PermissionError("Not an original world Take rendering packet")
    source=packet["source"]
    if packet["source_sha256"]!=sha256(canonical(source)).hexdigest():
        raise PermissionError("Original world source manifest SHA mismatch")
    keys={"project_id","original_world_take_id",
          "original_world_take_sha256","original_world_sha256",
          "original_camera_shot_sha256","original_camera_path",
          "original_camera_position_m","original_film_tick",
          "actor_sources","original_pcm_source_count",
          "original_selected_dialogue_count","original_sound_not_mixed",
          "source_usd_file","source_usd_sha256","native_source_usd_size_bytes",
          "source_world_take_checkpoint_sha256","blender_profile",
          "not_a_final_approved_film"}
    if (type(source) is not dict or set(source)!=keys or
        source["source_usd_file"]!="source.usda" or
        source["blender_profile"]!="cycles_cpu_320x180_12samples_v1" or
        source["original_sound_not_mixed"] is not True or
        source["not_a_final_approved_film"] is not True):
        raise PermissionError("Original world shot changed native profile or authority")
    for field in ("original_world_take_sha256","original_world_sha256",
                  "original_camera_shot_sha256","source_usd_sha256",
                  "source_world_take_checkpoint_sha256"):
        sha=source[field]
        if (type(sha) is not str or len(sha)!=64 or
            any(c not in "0123456789abcdef" for c in sha)):
            raise PermissionError("Source hash is not an original SHA-256")
    actors=source["actor_sources"]
    if (type(actors) is not list or not 1<=len(actors)<=24 or
        len({a["actor_id"] for a in actors})!=len(actors) or
        any(type(a) is not dict or set(a)!={
            "actor_id","source_prim","geometry_prims","historical_voice_id"
        } or not a["geometry_prims"] or
            not a["source_prim"].startswith("/World/Sets/")
            for a in actors)):
        raise PermissionError("Source actor/cast list invalid")
    if (type(source["original_film_tick"]) is not int or
        source["original_film_tick"]<0 or
        type(source["original_camera_position_m"]) is not list or
        len(source["original_camera_position_m"])!=3 or
        any(type(x) not in (float,int) or not math.isfinite(x)
            for x in source["original_camera_position_m"])):
        raise PermissionError("Original camera source position/time is invalid")
    file=root/source["source_usd_file"]
    if file.is_symlink() or not file.is_file() or digest(file)!=source["source_usd_sha256"]:
        raise PermissionError("True original USD source layer was substituted")
    if file.stat().st_size!=source["native_source_usd_size_bytes"]:
        raise RuntimeError("Original native USD source stage truncated")
    return source,file


def run():
    files=paths()
    root=files["--manifest"].parent
    packet=json.loads(files["--manifest"].read_text("utf8"))
    source,usd=check(packet,root)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    # No generated placeholder/camera geometry. Use only actual imported USD.
    props=set(bpy.ops.wm.usd_import.get_rna_type().properties.keys())
    keyword={"filepath":str(usd)}
    for key in ("import_cameras","import_lights","import_materials",
                "import_usd_preview","import_meshes",
                "read_mesh_uvs","import_render","apply_unit_conversion_scale"):
        if key in props:
            keyword[key]=True
    # Blender's default merge_parent_xform=True may eliminate the very
    # source ActorID Xform used to prove original casting. Preserve each
    # authored USD hierarchy and original camera/actor object identity.
    if "merge_parent_xform" in props:
        keyword["merge_parent_xform"]=False
    if "set_frame_range" in props:
        keyword["set_frame_range"]=False
    bpy.ops.wm.usd_import(**keyword)
    imported=list(bpy.data.objects)
    meshes=[o for o in imported if o.type=="MESH" and len(o.data.vertices)>=3]
    cameras=[o for o in imported if o.type=="CAMERA"]
    lights=[o for o in imported if o.type=="LIGHT"]
    if not meshes or not cameras:
        raise RuntimeError("Real USD scene produced no native Blender geometry/camera")
    target=source["original_camera_path"].split("/")[-1]
    matching=[o for o in cameras if o.name==target or
              o.name.rsplit(".",1)[0]==target]
    if len(matching)!=1:
        raise RuntimeError("Imported native USD camera is ambiguous or missing")
    camera=matching[0]
    expected=source["original_camera_position_m"]
    position=[float(camera.matrix_world.translation[i]) for i in range(3)]
    if any(abs(a-b)>0.002 for a,b in zip(expected,position)):
        raise RuntimeError("Blender USD camera moved from original FilmIndex coordinates")
    scene=bpy.context.scene
    scene.camera=camera
    # Original imported USD geometry must contain each source actor root or
    # its unique Blender hierarchy; never invent a replacement performer.
    known_names={o.name.split(".")[0] for o in imported}
    absent=[]
    for actor in source["actor_sources"]:
        name=actor["source_prim"].split("/")[-1]
        if name not in known_names:
            absent.append(name)
    if absent:
        raise RuntimeError("Original imported USD actor roots absent: "+",".join(absent))
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=12
    scene.render.resolution_x=320
    scene.render.resolution_y=180
    scene.render.resolution_percentage=100
    scene.render.film_transparent=False
    scene.render.image_settings.file_format="PNG"
    scene.render.filepath=str(files["--preview"])
    scene.render.use_file_extension=False
    scene["nvp_original_world_take_sha256"]=source["original_world_take_sha256"]
    scene["nvp_original_world_sha256"]=source["original_world_sha256"]
    scene["nvp_original_camera_shot_sha256"]=source["original_camera_shot_sha256"]
    scene["nvp_source_usd_sha256"]=source["source_usd_sha256"]
    scene["nvp_original_film_tick"]=source["original_film_tick"]
    scene["nvp_source_actors_json"]=json.dumps(source["actor_sources"],sort_keys=True)
    scene["nvp_original_camera_path"]=source["original_camera_path"]
    scene["nvp_no_film_master_approval"]=True
    scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    if not files["--preview"].is_file() or files["--preview"].stat().st_size<100:
        raise RuntimeError("Actual Cycles original film frame was not rendered")
    bpy.ops.wm.save_as_mainfile(filepath=str(files["--output"]))
    if not files["--output"].is_file():
        raise RuntimeError("Original imported Blender scene was not saved")
    report={
        "format":AUDIT,"passed":True,
        "source_packet_sha256":packet["source_sha256"],
        "source_usd_sha256":source["source_usd_sha256"],
        "original_world_take_sha256":source["original_world_take_sha256"],
        "original_world_sha256":source["original_world_sha256"],
        "original_camera_shot_sha256":source["original_camera_shot_sha256"],
        "original_film_tick":source["original_film_tick"],
        "imported_native_mesh_count":len(meshes),
        "imported_native_camera_count":len(cameras),
        "imported_native_light_count":len(lights),
        "original_actor_roots_found":len(source["actor_sources"]),
        "original_camera_position_m":position,
        "blender_version":bpy.app.version_string,
        "rendered_png_sha256":digest(files["--preview"]),
        "saved_blend_sha256":digest(files["--output"]),
        "actual_native_cycles_image":True,
        "source_actor_mesh_unchanged_in_original_usd":True,
        "original_voice_not_synthesized":True,
        "original_audio_not_mixed":True,
        "real_actor_motion_sequence_not_rendered":True,
        "director_approved_complete_film":False,
    }
    files["--audit"].write_text(
        json.dumps(report,sort_keys=True,separators=(",",":")),"utf8")


if __name__=="__main__":
    run()
