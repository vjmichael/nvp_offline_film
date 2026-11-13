"""NVP P1-F FIXED supervised Blender/Cycles actor frame worker.

Runs ONLY under BlenderWorkerSupervisor with a SHA-pinned script, finite
original USDA+manifest, and a strict OS-owned process boundary. No internet,
external asset resolver, user code execution, image generator or FFmpeg.
This script cannot authorize a creator action, production reel or master.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import bpy

SHAPES=("jawOpen","lipClose","eyeBlink","browRaise")
FORMAT="nvp.p1f.supervised_original_actor_frame.v1"


def _args():
    if "--" not in sys.argv:
        raise RuntimeError("NVP fixed Cycles operation arguments missing")
    args=sys.argv[sys.argv.index("--")+1:]
    if len(args)!=8 or args[::2]!=["--plan","--take","--output","--audit"]:
        raise RuntimeError("Only finite P1-F plan/take/output/audit contract permitted")
    files=[Path(v).resolve() for v in args[1::2]]
    cwd=Path.cwd().resolve()
    if (any(p.parent!=cwd or p.is_symlink() for p in files)
            or len(set(files))!=4):
        raise RuntimeError("Worker input/output must stay in unique job-root files")
    return files


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan_path,usd_path,png_path,audit_path=_args()
    if png_path.exists() or audit_path.exists():
        raise RuntimeError("P1-F output must not exist before supervised launch")
    if plan_path.stat().st_size>8192 or usd_path.stat().st_size>8*1024*1024:
        raise RuntimeError("Actor input exceeds finite worker resource contract")
    plan=json.loads(plan_path.read_text("utf8"))
    if (type(plan) is not dict or
            set(plan)!={"format","scene_sha256","usd_sha256","camera",
                        "actor_id","actor_path","source_tick",
                        "expected_face_weights","width","height","samples"} or
            plan["format"]!=FORMAT or
            not 128<=plan["width"]<=1920 or
            not 72<=plan["height"]<=1080 or
            not 4<=plan["samples"]<=128 or
            _sha(usd_path)!=plan["usd_sha256"] or
            type(plan["expected_face_weights"]) is not list or
            len(plan["expected_face_weights"])!=4):
        raise RuntimeError("Worker original source SHA/strict render plan rejected")
    usd=usd_path.read_bytes()
    if not usd.lstrip().startswith(b"#usda 1.0") or b"@" in usd:
        raise RuntimeError("Cycles worker refuses external USD references")
    if tuple(float(v) for v in plan["expected_face_weights"])<tuple(0. for _ in SHAPES):
        raise RuntimeError("Invalid facial performance values")
    # The trusted host passed a flattened, SHA-reviewed stage, not a filename
    # chosen by a model or a user. Native Blender USD import is required.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    properties=bpy.ops.wm.usd_import.get_rna_type().properties.keys()
    options={"filepath":str(usd_path)}
    for name in ("import_meshes","import_cameras","import_skeletons",
                 "import_blendshapes"):
        if name in properties:
            options[name]=True
    if (not {"import_meshes","import_cameras","import_skeletons",
             "import_blendshapes"} <= set(properties)):
        raise RuntimeError("Blender lacks the required native USD importer")
    result=bpy.ops.wm.usd_import(**options)
    if "FINISHED" not in result:
        raise RuntimeError("Native USD actor import was not completed")
    scene=bpy.context.scene
    cameras=[o for o in bpy.data.objects
             if o.type=="CAMERA" and o.name==plan["camera"].rsplit("/",1)[-1]]
    if len(cameras)!=1:
        raise RuntimeError("Imported authored original USD camera is missing/ambiguous")
    scene.camera=cameras[0]
    if not any(o.type=="ARMATURE" for o in bpy.data.objects):
        raise RuntimeError("Imported original skeleton was not preserved")
    shaped=[]
    for mesh in (o for o in bpy.data.objects if o.type=="MESH"):
        keys=mesh.data.shape_keys
        if keys and all(n in keys.key_blocks for n in SHAPES):
            shaped.append(mesh)
    if len(shaped)!=1:
        raise RuntimeError("Original facial blendshapes were lost in USD→Blender transfer")
    mesh=shaped[0]
    # 7,056,000,000 exact USD ticks/second; 24 derived presentation fps.
    if (type(plan["source_tick"]) is not int or
            plan["source_tick"]<0 or
            plan["source_tick"]%(7056000000//24)):
        raise RuntimeError("Source clock cannot map to a complete 24fps frame")
    index=plan["source_tick"]//(7056000000//24)
    if index>259200:
        raise RuntimeError("Source frame index beyond three-hour bound")
    scene.render.fps=24
    scene.frame_set(index+1)
    actual=[float(mesh.data.shape_keys.key_blocks[n].value) for n in SHAPES]
    expected=[float(v) for v in plan["expected_face_weights"]]
    if any(abs(a-b)>.035 for a,b in zip(actual,expected)):
        raise RuntimeError("Native Blender facial animation differs from original USD")
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=int(plan["samples"])
    scene.render.resolution_x=int(plan["width"])
    scene.render.resolution_y=int(plan["height"])
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.film_transparent=False
    scene.render.filepath=str(png_path)
    world=bpy.data.worlds.new("NVP_DerivedNeutralLighting")
    world.use_nodes=True
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value=.8
    scene.world=world
    light=bpy.data.lights.new("NVP_DerivedKey","AREA")
    obj=bpy.data.objects.new("NVP_DerivedKey",light)
    scene.collection.objects.link(obj)
    obj.location=(2.,-3.,5.)
    light.energy=550.
    light.shape="DISK"
    light.size=4.
    bpy.ops.render.render(write_still=True)
    if not png_path.exists() or png_path.stat().st_size<256:
        raise RuntimeError("Genuine Cycles original-character PNG missing")
    # Report actual Blender state. Independent host reopens and compares the
    # source/camera/shape weights and output bytes after process custody closes.
    audit={
        "format":FORMAT,"passed":True,
        "render_engine":scene.render.engine,
        "source_tick":plan["source_tick"],
        "scene_sha256":plan["scene_sha256"],
        "input_usd_sha256":plan["usd_sha256"],
        "original_camera":cameras[0].name,
        "imported_skinned_mesh":mesh.name,
        "imported_armature_count":len([o for o in bpy.data.objects if o.type=="ARMATURE"]),
        "actual_shape_keys":dict(zip(SHAPES,actual)),
        "width":scene.render.resolution_x,
        "height":scene.render.resolution_y,
        "samples":scene.cycles.samples,
        "png_sha256":_sha(png_path),
    }
    audit_path.write_text(json.dumps(audit,sort_keys=True,separators=(",",":")),
                          encoding="utf8")


if __name__=="__main__":
    main()
