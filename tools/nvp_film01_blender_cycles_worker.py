"""Trusted NVP FILM01 Blender 5.2 Cycles worker (external GPL Blender script).

Executed ONLY by the established SHA-pinned BlenderWorkerSupervisor.
Input is an immutable, host-staged, original FilmIndex/OpenUSD Take
manifest. The script does not import NVP, use an AI model, execute
external commands, access a network, or generate unapproved story data.

GPL boundary: Blender-side bpy adapter is separately distributed and
must be treated as GPL-compatible, with exact licensing reviewed before
product distribution. Original FilmIndex data and NVP app are NOT bpy.
"""
import bpy
from mathutils import Vector
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

VERSION="nvp.film01.blender.cycles.original_three_object_actors.v1"
FRAMES=72
KEY=24
FPS=24
PIXELS=(640,360)
ACTORS={"donut":"/World/DonutActor",
        "box":"/World/BoxActor",
        "sphere":"/World/SphereActor"}


def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()


def source_manifest():
    argv=sys.argv[sys.argv.index("--")+1:]
    if len(argv)!=8 or len(set(argv[::2]))!=4:
        raise ValueError("Exactly four worker-owned options required")
    arguments=dict(zip(argv[::2],argv[1::2]))
    if set(arguments)!={"--manifest","--output","--audit","--out"}:
        raise ValueError("Unexpected NVP native worker options")
    source=Path(arguments["--manifest"]).resolve(strict=True)
    scene=Path(arguments["--output"])
    audit=Path(arguments["--audit"])
    frames=Path(arguments["--out"])
    if not all(p.parent==source.parent for p in (scene,audit,frames)):
        raise PermissionError("Only approved fixed Blender job directory paths")
    if scene.exists() or audit.exists() or frames.exists():
        raise FileExistsError("Do not overwrite Blender original outputs")
    doc=json.loads(source.read_text(encoding="utf8"))
    if doc.get("format")!="nvp.film01.blender.cycles.source_from_frozen_usd.v1":
        raise PermissionError("No valid original frozen USD source manifest")
    canonical=json.dumps(doc["source"],sort_keys=True,separators=(",",":"),
                         allow_nan=False).encode()
    if hashlib.sha256(canonical).hexdigest()!=doc["source_sha256"]:
        raise PermissionError("Original FilmIndex source manifest SHA changed")
    take=doc["source"]
    if (take.get("frame_rate")!=FPS or
            len(take.get("frames",[]))!=FRAMES or
            len(take.get("donut_vertices",[]))!=504 or
            len(take.get("donut_triangles",[]))!=1008 or
            not all(len(x)==3 for x in take["donut_vertices"]) or
            not all(len(x)==3 for x in take["donut_triangles"]) or
            len(set(row["frame_zero"] for row in take["frames"]))!=FRAMES or
            any(row["frame_zero"]!=i for i,row in enumerate(take["frames"])) or
            len(take["source_take_sha256"])!=64 or
            not take.get("creator_approval_test_only")):
        raise PermissionError("Malformed test-only original source acting scene")
    frames.mkdir(parents=False,exist_ok=False)
    return take,scene,audit,frames


def material(name,rgb,metallic,roughness):
    mat=bpy.data.materials.new(name=name)
    mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("Actual Blender Principled BSDF unavailable")
    bsdf.inputs["Base Color"].default_value=(*rgb,1)
    bsdf.inputs["Metallic"].default_value=metallic
    bsdf.inputs["Roughness"].default_value=roughness
    return mat


def add_actors(take):
    points=take["donut_vertices"]
    triangles=take["donut_triangles"]
    mesh=bpy.data.meshes.new("NVP_Original_Donut_Source_Mesh")
    mesh.from_pydata(points,[],triangles)
    mesh.update()
    if len(mesh.polygons)!=1008:
        raise RuntimeError("Blender did not build 1008 original USD torus triangles")
    for poly in mesh.polygons:poly.use_smooth=True
    donut=bpy.data.objects.new("NVP_DonutActor",mesh)
    bpy.context.collection.objects.link(donut)
    donut.data.materials.append(material("NVP_Donut_Reflective_Copper",
        (.58,.38,.22),.52,.17))
    # source geometry local positions already are original original metres
    bpy.ops.mesh.primitive_cube_add(size=.8)
    box=bpy.context.object
    box.name="NVP_BoxActor"
    box.data.materials.append(material("NVP_Green_Cube",(.07,.63,.16),.12,.35))
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,radius=.3)
    sphere=bpy.context.object
    sphere.name="NVP_SphereActor"
    for polygon in sphere.data.polygons:polygon.use_smooth=True
    sphere.data.materials.append(material("NVP_Blue_Sphere",(.08,.24,.85),.28,.19))
    actors={"donut":donut,"box":box,"sphere":sphere}
    for key,obj in actors.items():
        obj["nvp_prim_path"]=ACTORS[key]
        obj["nvp_original_take_sha256"]=take["source_take_sha256"]
        obj["nvp_role"]="actor"
    for row in take["frames"]:
        for key,obj in actors.items():
            pos=row["actors"][key]
            if len(pos)!=3 or any(not math.isfinite(x) for x in pos):
                raise PermissionError("Non-finite original USD actor motion")
            obj.location=pos
            obj.keyframe_insert(data_path="location",frame=row["frame_zero"]+1)
    return actors


def add_set_and_lights():
    # A matte ground BACKSTOP behind all performers receives visible
    # Cycles cast shadows; it is not a fake pre-rendered background.
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,-6))
    wall=bpy.context.object
    wall.name="NVP_Shadow_Receiver"
    wall.data.materials.append(material("NVP_Backdrop",(.12,.14,.17),0,.9))

    camera_data=bpy.data.cameras.new("NVP_Original_Camera")
    camera=bpy.data.objects.new("NVP_Original_Camera",camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location=(0,0,9)
    camera.rotation_euler=(0,0,0)
    camera.data.lens=50
    bpy.context.scene.camera=camera
    camera["nvp_prim_path"]="/World/Camera"

    light=bpy.data.lights.new("NVP_Key_Area","AREA")
    key=bpy.data.objects.new("NVP_Key_Area",light)
    bpy.context.collection.objects.link(key)
    key.location=(2.8,3.,5.)
    direction=Vector((0.,0.,-1.))-key.location
    key.rotation_euler=direction.to_track_quat("-Z","Y").to_euler()
    light.energy=850
    light.shape="DISK"
    light.size=1.8

    fill_data=bpy.data.lights.new("NVP_Artist_Fill","AREA")
    fill=bpy.data.objects.new("NVP_Artist_Fill",fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location=(-3.,0.5,3.5)
    direction=Vector((0.,0.,0.))-fill.location
    fill.rotation_euler=direction.to_track_quat("-Z","Y").to_euler()
    fill_data.shape="DISK";fill_data.size=3.2
    fill_data.energy=0

    sun_data=bpy.data.lights.new("NVP_Fixed_Summer_3PM","SUN")
    sun=bpy.data.objects.new("NVP_Fixed_Summer_3PM",sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler=(math.radians(35),math.radians(-22),math.radians(18))
    sun_data.angle=math.radians(3)
    sun_data.energy=0

    world=bpy.data.worlds.new("NVP_Original_Studio_Sky")
    world.use_nodes=True
    world.node_tree.nodes["Background"].inputs["Color"].default_value=(
        .22,.27,.35,1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value=.25
    bpy.context.scene.world=world
    return fill,sun


def look(lighting,fill,sun):
    opts={
        "neutral":(0,(1,1,1),0),
        "silver":(380,(.68,.84,1),0),
        "gold":(450,(1,.65,.30),0),
        "fixed_summer_3pm":(0,(1,1,1),2.1),
    }
    power,color,sun_energy=opts[lighting]
    fill.data.energy=power
    fill.data.color=color
    sun.data.energy=sun_energy


def main():
    take,blend,audit,frames=source_manifest()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=8
    scene.cycles.max_bounces=6
    scene.cycles.diffuse_bounces=3
    scene.cycles.glossy_bounces=4
    scene.render.resolution_x=PIXELS[0]
    scene.render.resolution_y=PIXELS[1]
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.image_settings.color_mode="RGB"
    scene.render.film_transparent=False
    scene.render.film_transparent=False
    scene.frame_start=1;scene.frame_end=FRAMES;scene.render.fps=FPS
    actors=add_actors(take)
    fill,sun=add_set_and_lights()

    # Save ORIGINAL Blender scene and original baked animation before
    # preview look changes; this is a derived .blend, not source truth.
    scene.frame_set(KEY+1)
    look("neutral",fill,sun)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend),check_existing=False)
    if not blend.is_file() or blend.stat().st_size<100:
        raise RuntimeError("Genuine Blender scene did not save")

    images=[]
    for frame in range(FRAMES):
        scene.frame_set(frame+1)
        look("neutral",fill,sun)
        file=frames/f"frame_{frame:03d}.png"
        scene.render.filepath=str(file)
        bpy.ops.render.render(write_still=True)
        if not file.is_file() or file.read_bytes()[:8]!=b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("Cycles failed to render actual native picture")
        images.append({
            "frame_zero":frame,
            "source_film_tick":take["frames"][frame]["film_tick"],
            "original_scene_take_sha256":take["source_take_sha256"],
            "image_sha256":sha(file),
            "image_bytes":file.stat().st_size,
        })
    stills={}
    shutil.copyfile(frames/f"frame_{KEY:03d}.png",blend.parent/"neutral_024.png")
    stills["neutral"]=sha(blend.parent/"neutral_024.png")
    for kind in ("silver","gold","fixed_summer_3pm"):
        scene.frame_set(KEY+1)
        look(kind,fill,sun)
        still=blend.parent/f"{kind}_024.png"
        scene.render.filepath=str(still)
        bpy.ops.render.render(write_still=True)
        if not still.is_file() or still.read_bytes()[:8]!=b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("Actual Cycles light variant missing")
        stills[kind]=sha(still)
    if len(set(stills.values()))!=4:
        raise RuntimeError("Artistic Cycles variants did not render different pixels")
    source_positions={}
    for frame in (0,24,48,71):
        scene.frame_set(frame+1)
        source_positions[str(frame)]={
            name:[round(float(v),6) for v in obj.location]
            for name,obj in actors.items()}
        for name in actors:
            expected=take["frames"][frame]["actors"][name]
            if any(abs(x-y)>2e-5 for x,y in
                   zip(source_positions[str(frame)][name],expected)):
                raise RuntimeError("Blender actor deviated from original frozen USD motion")
    report={
        "format":VERSION,"passed":True,
        "engine":"CYCLES","cycles_device":"CPU",
        "samples":scene.cycles.samples,
        "indirect_diffuse_bounces":scene.cycles.diffuse_bounces,
        "indirect_glossy_bounces":scene.cycles.glossy_bounces,
        "actual_native_blender_version":bpy.app.version_string,
        "original_scene_take_sha256":take["source_take_sha256"],
        "original_scene_document_sha256":take["scene_sha256"],
        "original_torus_mesh_sha256":take["torus_mesh_sha256"],
        "source_manifest_sha256":hashlib.sha256(
            json.dumps(take,sort_keys=True,separators=(",",":"),
                       allow_nan=False).encode()).hexdigest(),
        "exact_frame_rate":FPS,"rendered_frames":FRAMES,
        "original_actor_prim_roles":ACTORS,
        "true_3d_actors_from_original_frozen_take":True,
        "blender_geometry_polygon_count":len(
            actors["donut"].data.polygons),
        "shading_smooth_normals":all(
            f.use_smooth for f in actors["donut"].data.polygons),
        "cycles_traced_cast_shadows_enabled":True,
        "cycles_indirect_reflection_bounces_enabled":True,
        "actual_shadows_and_reflections_human_review_required":True,
        "exact_source_positions_at_frames":source_positions,
        "all_native_source_frames":images,
        "artistic_light_still_sha256":stills,
        "blend_scene_sha256":sha(blend),
        "uncalibrated_preview_not_DCI":True,
        "actual_native_screen_playback_verified":False,
    }
    audit.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                     encoding="utf8")


if __name__=="__main__":
    main()
