"""USD-FILM-02M-D first-party native Blender aperture/room light-path test.

Front, inside-looking-rear, reverse real Cycles pictures share ONE
authoritative OpenUSD building mesh. The horizontal doorway ray must
pass the source façade and hit real room geometry; a pier ray must be
occluded by the original façade. No alpha maps or generated PNGs.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


FORMAT="nvp.usd_film02m_d.true_aperture_and_interior_cycles.v1"
INPUT="nvp.usd_film02m_d.native_three_view_original_geometry.v1"
VIEWS=("doorway","interior","reverse")


def sha(path):
    digest=sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite3(value):
    return (type(value) is list and len(value)==3 and
            all(type(x) in (int,float) and math.isfinite(x)
                and abs(x)<100000 for x in value))


def run():
    if "--" not in sys.argv:
        raise PermissionError("Only reviewed 02M-D renderer arguments")
    args=sys.argv[sys.argv.index("--")+1:]
    if len(args)!=4 or set(args[::2])!={"--manifest","--audit"}:
        raise PermissionError("Native Blender aperture review script contract")
    flags=dict(zip(args[::2],args[1::2]))
    base=Path.cwd().resolve()
    for flag,name in flags.items():
        src=Path(name)
        if (src.is_absolute() or len(src.parts)!=1 or
            (base/src).is_symlink() or
            (flag=="--manifest" and not (base/src).is_file()) or
            (flag=="--audit" and (base/src).exists())):
            raise PermissionError("NVP-approved source workspace paths only")
    spec=json.loads((base/flags["--manifest"]).read_text("utf8"))
    if (type(spec) is not dict or set(spec)!={
            "format","source_building_sha256","original_usd_sha256",
            "asset_layer_sha256s","expected_original_meshes",
            "front_door_world_center_m","front_wall_outer_y_m",
            "front_wall_pier_x_m","interior_rear_wall_y_m"} or
        spec["format"]!=INPUT or
        type(spec["expected_original_meshes"]) is not int or
        not 8<=spec["expected_original_meshes"]<=48 or
        not all(finite3(spec[key]) for key in
                ("front_door_world_center_m",)) or
        any(type(spec[k]) not in (int,float) or
            not math.isfinite(spec[k]) for k in (
                "front_wall_outer_y_m","front_wall_pier_x_m",
                "interior_rear_wall_y_m"))):
        raise PermissionError("Only original approved 02M-D geometry contract")
    source=base/"building.usda"
    if source.is_symlink() or not source.is_file() or (
            sha(source)!=spec["original_usd_sha256"]):
        raise RuntimeError("Original building source USD altered")
    pinned=spec["asset_layer_sha256s"]
    if (type(pinned) is not list or not pinned or len(pinned)>48 or
        any(type(x) is not str or len(x)!=64 or
            any(ch not in "0123456789abcdef" for ch in x)
            for x in pinned) or len(set(pinned))!=len(pinned)):
        raise PermissionError("Missing exact original asset source SHAs")
    for digest in pinned:
        asset=base/"assets"/(digest+".usda")
        if asset.is_symlink() or not asset.is_file() or sha(asset)!=digest:
            raise RuntimeError("One source façade/interior/roof layer changed")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    settings={"filepath":str(source)}
    supported=set(bpy.ops.wm.usd_import.get_rna_type().properties.keys())
    for name in ("import_meshes","import_materials",
                 "import_usd_preview","read_mesh_uvs"):
        if name in supported:settings[name]=True
    if "merge_parent_xform" in supported:
        settings["merge_parent_xform"]=False
    bpy.ops.wm.usd_import(**settings)
    meshes=[o for o in bpy.data.objects
            if o.type=="MESH" and len(o.data.vertices)>=8 and
            len(o.data.polygons)>=12]
    if len(meshes)!=spec["expected_original_meshes"]:
        raise RuntimeError("Actual imported original rear/interior source meshes missing")
    source_faces=sum(len(o.data.polygons) for o in meshes)
    scene=bpy.context.scene
    depsgraph=bpy.context.evaluated_depsgraph_get()
    door=Vector(spec["front_door_world_center_m"])
    front_y=float(spec["front_wall_outer_y_m"])
    rear_y=float(spec["interior_rear_wall_y_m"])
    if not rear_y>front_y+5:
        raise ValueError("Original interiors must be deep 3D behind the wall")
    start=Vector((door.x,front_y-3,door.z))
    cast=scene.ray_cast(depsgraph,start,Vector((0,1,0)),distance=100)
    if not cast[0]:
        raise RuntimeError("Door opens to EMPTY scene: original room absent")
    through_hit=cast[1]
    if not through_hit.y>front_y+2:
        raise RuntimeError("Actual doorway is blocked by a solid facade")
    pier=Vector((float(spec["front_wall_pier_x_m"]),
                 front_y-3,door.z))
    solid=scene.ray_cast(depsgraph,pier,Vector((0,1,0)),distance=100)
    if not solid[0] or abs(solid[1].y-front_y)>.25:
        raise RuntimeError("Original real facade piers not present")
    # Three real rendering views use identical static source assets; each
    # viewpoint changes only derived perspective, never the world Take.
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=8
    scene.render.resolution_x=320
    scene.render.resolution_y=180
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.use_file_extension=False
    ambient=bpy.data.worlds.new("NVP D real aperture ambient")
    ambient.use_nodes=True
    ambient.node_tree.nodes.get("Background").inputs[
        "Strength"].default_value=.7
    scene.world=ambient
    sun=bpy.data.lights.new("NVP D review-only sun","SUN")
    sun.energy=2.5
    sun_obj=bpy.data.objects.new("NVP D technical sun",sun)
    scene.collection.objects.link(sun_obj)
    sun_obj.rotation_euler=(.6,-.35,.3)
    camera_positions={
        "doorway":door+Vector((0,-16,1.7)),
        "interior":Vector((door.x,front_y+2,door.z+.35)),
        "reverse":Vector((door.x+12,rear_y+17,door.z+5))}
    targets={
        "doorway":Vector((door.x,rear_y,door.z)),
        "interior":Vector((door.x,rear_y,door.z)),
        "reverse":Vector((door.x,0,door.z+2))}
    pictures=[]
    for view in VIEWS:
        filename="film02m_d_"+view+".png"
        image=base/filename
        if image.exists() or image.is_symlink():
            raise FileExistsError("Original source architecture evidence never overwritten")
        bpy.ops.object.camera_add(location=camera_positions[view])
        camera=bpy.context.object
        camera.name="NVP 02M-D "+view
        camera.rotation_euler=(
            targets[view]-camera.location).to_track_quat("-Z","Y").to_euler()
        camera.data.lens=38
        scene.camera=camera
        scene.render.filepath=str(image)
        bpy.ops.render.render(write_still=True)
        if not image.is_file() or image.stat().st_size<150:
            raise RuntimeError("Genuine aperture/interior Cycles image absent")
        pictures.append({
            "view":view,"image_name":filename,
            "actual_cycles_png_sha256":sha(image)})
        bpy.data.objects.remove(camera,do_unlink=True)
    if len({x["actual_cycles_png_sha256"] for x in pictures})!=3:
        raise RuntimeError("Inside/front/reverse angles produced same fake picture")
    doc={
        "format":FORMAT,"passed":True,
        "original_building_sha256":spec["source_building_sha256"],
        "original_usd_sha256":spec["original_usd_sha256"],
        "actual_native_meshes":len(meshes),
        "actual_native_faces":source_faces,
        "door_ray_passed_original_wall":True,
        "room_rear_wall_ray_hit":True,
        "original_solid_pier_ray_blocked":True,
        "door_real_hit_world_m":[float(x) for x in through_hit],
        "solid_pier_hit_world_m":[float(x) for x in solid[1]],
        "actual_blender_cycles_views":pictures,
        "original_source_geometry_not_modified":True,
        "native_blender_version":bpy.app.version_string,
        "director_visual_look_accepted":False,
        "architectural_safety_verified":False}
    (base/flags["--audit"]).write_text(
        json.dumps(doc,sort_keys=True,separators=(",",":"),
                   allow_nan=False),"utf8")


if __name__=="__main__":
    run()
