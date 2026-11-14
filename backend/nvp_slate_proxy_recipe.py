"""SLATE-05: trusted NVP-owned low-fi blocking proxy, not full mesh render.

A preview is derived from ONE frozen OpenUSD scene/SHOT at an exact tick.
No arbitrary scripts, external USD references, images or uploaded assets run
in Blender. This represents original actor/prop coordinates as geometric
proxies: preview PNG, not complete rigged actors or film finishing.
"""
from __future__ import annotations

import hashlib
import json
import math

from backend.nvp_film_index import FilmIndex
from backend.nvp_slate_lazy_preview import SlateLazyPreview

FORMAT="nvp.slate.blender_blocking_proxy.v1"
RENDERER_VERSION="nvp.slate.blender_proxy.01"
MAX_OBJECTS=16
DIMENSIONS={
    "thumbnail":(256,144),
    "interactive":(512,288),
    "inspection":(640,360),
}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def sha(value):
    return hashlib.sha256(value).hexdigest()


# This executable is a code-reviewed first-party constant, pinned by SHA as
# a BlenderOperation script. Blender reads ONLY the bounded source JSON.
BLENDER_SCRIPT=r'''
import bpy
import json
import math
import os
import sys
from mathutils import Vector

arguments=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
def value(flag):
    if flag not in arguments: raise ValueError("Missing trusted preview argument")
    at=arguments.index(flag)+1
    if at>=len(arguments): raise ValueError("Missing preview argument value")
    result=arguments[at]
    expected={"--manifest":"slate_source_preview.json",
              "--preview":"preview.png"}.get(flag)
    cwd=os.path.realpath(os.getcwd())
    if (not expected or not os.path.isabs(result) or
            os.path.realpath(result)!=os.path.join(cwd,expected) or
            os.path.basename(result)!=expected or
            os.path.islink(result)):
        raise ValueError("Unsafe Blender preview filename")
    return result

manifest=value("--manifest")
filename=value("--preview")
with open(os.path.join(os.getcwd(),manifest),"r",encoding="utf8") as handle:
    doc=json.load(handle)
if doc.get("format")!="nvp.slate.blender_blocking_proxy.v1":
    raise RuntimeError("Invalid trusted NVP blocking preview recipe")
if len(doc["objects"])>16: raise RuntimeError("Too many objects")

bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.render.engine="BLENDER_WORKBENCH"
scene.render.resolution_x=int(doc["width"])
scene.render.resolution_y=int(doc["height"])
scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG"
scene.render.image_settings.color_mode="RGBA"
scene.render.film_transparent=False
scene.display.shading.light="STUDIO"
scene.display.shading.color_type="MATERIAL"
scene.display.shading.show_cavity=True
positions=[]
cam_location=None
for item in doc["objects"]:
    role=item["role"]
    xyz=tuple(float(x) for x in item["xyz"])
    if not all(math.isfinite(x) and abs(x)<=100000 for x in xyz):
        raise ValueError("Invalid scene position")
    if role=="camera":
        if cam_location is None: cam_location=xyz
        continue
    if role=="actor":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,
            radius=0.6, location=xyz)
        rgba=(0.33,0.64,0.96,1.0)
    elif role=="prop":
        bpy.ops.mesh.primitive_cube_add(size=1,location=xyz)
        rgba=(0.87,0.67,0.40,1.0)
    elif role=="light":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,
            radius=0.18,location=xyz)
        rgba=(1.0,0.9,0.44,1.0)
    else:
        bpy.ops.mesh.primitive_cube_add(size=0.65,location=xyz)
        rgba=(0.55,0.74,0.64,1.0)
    obj=bpy.context.object
    obj.name=("NVP_Proxy_"+role+"_"+str(len(positions)))[:63]
    material=bpy.data.materials.new(name="ProxyMat_"+str(len(positions)))
    material.diffuse_color=rgba
    obj.data.materials.append(material)
    positions.append(xyz)

if positions:
    focus=tuple(sum(x[i] for x in positions)/len(positions) for i in range(3))
else:
    focus=(0.0,0.0,0.0)
if cam_location is None or (Vector(cam_location)-Vector(focus)).length<0.1:
    cam_location=(focus[0]+7,focus[1]-11,focus[2]+6)
camera=bpy.data.cameras.new("NVP_Proxy_Review_Camera")
camera_obj=bpy.data.objects.new("NVP_Proxy_Review_Camera",camera)
scene.collection.objects.link(camera_obj)
camera_obj.location=cam_location
camera_obj.rotation_euler=(Vector(focus)-Vector(cam_location)).to_track_quat("-Z","Y").to_euler()
camera.lens=45.0
scene.camera=camera_obj
scene.render.filepath=os.path.join(os.getcwd(),filename)
bpy.ops.render.render(write_still=True)
if not os.path.isfile(scene.render.filepath):
    raise RuntimeError("Trusted Blender did not create preview PNG")
'''


def capture_proxy(index:FilmIndex,ticket):
    """Open only selected frozen OpenUSD source; return bounded prim snapshot."""
    if not isinstance(index,FilmIndex) or type(ticket) is not dict:
        raise TypeError("Trusted source index and source-time preview ticket required")
    take=index.read_revision(
        ticket["project_id"],ticket["source_take_id"],
        ticket["source_take_revision"])
    scene=index.read_revision(
        ticket["project_id"],take["data"]["scene_id"],
        take["data"]["scene_revision"])
    if scene["document_sha256"]!=take["data"]["scene_document_sha256"]:
        raise RuntimeError("Source scene no longer matches frozen Digital Take")
    roles=scene["data"]["prim_roles"]
    priority={"camera":0,"actor":1,"prop":2,"light":3}
    paths=sorted(roles,key=lambda x:(priority.get(roles[x],4),x))[:MAX_OBJECTS]
    sample=SlateLazyPreview(index).structural_sample(ticket,prim_paths=paths)
    positions=[]
    for state in sample["prim_states"]:
        path=state["prim_path"]
        role=roles[path]
        xyz=state["world_translation"]
        if any(type(n) not in (float,int) or not math.isfinite(n) or
               abs(n)>100_000 for n in xyz):
            raise RuntimeError("Preview source coordinate outside safe bounded domain")
        positions.append({
            "path":path,"role":role,
            "xyz":[float(n) for n in xyz],
        })
    return {
        "format":FORMAT,
        "source_take_sha256":ticket["source_take_document_sha256"],
        "source_shot_sha256":ticket["source_shot_document_sha256"],
        "source_tick":ticket["source_tick"],
        "cache_key":ticket["cache_key"],
        "objects":positions,
        "source_3d_data_used":True,
        "original_actor_mesh_rendered":False,
        "source_data_modified":False,
    }


def recipe(snapshot,quality):
    if type(snapshot) is not dict or snapshot.get("format")!=FORMAT:
        raise ValueError("Invalid NVP trusted OpenUSD source snapshot")
    if quality not in DIMENSIONS:
        raise ValueError("Invalid bounded proxy preview quality")
    width,height=DIMENSIONS[quality]
    return {
        **snapshot,
        "width":width,"height":height,
        "quality":quality,"renderer_version":RENDERER_VERSION,
        "worker_script_sha256":sha(BLENDER_SCRIPT.encode("utf-8")),
    }


def preview_cache_key(ticket,quality):
    """Compute cache identity BEFORE loading OpenUSD geometry.

    Take SHA freezes the scene and performance; SHOT SHA freezes overrides.
    A deterministic renderer recipe version + script SHA fixes appearances.
    This makes repeated scrubs an inexpensive SQLite/disk lookup.
    """
    if type(ticket) is not dict or ticket.get("status")!="SOURCE_REFERENCE_SELECTED":
        raise ValueError("Source reference ticket required for cache lookup")
    if quality not in DIMENSIONS:
        raise ValueError("Invalid preview quality")
    width,height=DIMENSIONS[quality]
    return sha(canonical({
        "format":FORMAT,"renderer":RENDERER_VERSION,
        "source_take_sha256":ticket["source_take_document_sha256"],
        "source_shot_sha256":ticket["source_shot_document_sha256"],
        "source_tick":ticket["source_tick"],
        "width":width,"height":height,
        "script_sha256":sha(BLENDER_SCRIPT.encode("utf-8")),
    }))
