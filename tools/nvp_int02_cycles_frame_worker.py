"""INT-02C Blender Cycles worker: one original-time, static composed USD frame.

Trusted host invokes this *only* through NVP's approved Blender supervisor,
with a SHA-pinned script and exact input hashes. It is not a browser endpoint
or a standalone grant for arbitrary source/render paths.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


def digest(path):
    h=sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1048576), b""):
            h.update(part)
    return h.hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--audit",type=Path,required=True)
    args=parser.parse_args(argv)
    if any(p.is_symlink() for p in (args.plan,args.output,args.audit)):
        raise RuntimeError("CyCles worker paths cannot be symbolic links")
    raw=args.plan.read_bytes()
    if len(raw)>32768:
        raise RuntimeError("Unbounded NVP Cycles frame plan")
    plan=json.loads(raw)
    required={"format","usd_file","usd_sha256","camera_path",
              "source_tick","width","height","samples","renderer",
              "actor_paths","light_paths"}
    if type(plan) is not dict or set(plan)!=required or (
            plan.get("format")!="nvp.int02.cycles.frame_plan.v1" or
            plan.get("renderer")!="CYCLES" or
            type(plan.get("camera_path")) is not str or
            not plan["camera_path"].startswith("/World/") or
            type(plan.get("source_tick")) is not int or
            plan["source_tick"]<0 or
            plan.get("width")!=1920 or plan.get("height")!=1080 or
            type(plan.get("samples")) is not int or
            not 64<=plan["samples"]<=512 or
            any(type(plan.get(k)) is not list or len(plan[k])>64 or
                any(type(p) is not str or not p.startswith("/World/") or
                    len(p)>240 for p in plan[k])
                for k in ("actor_paths","light_paths"))):
        raise RuntimeError("Untrusted or unsupported exact Cycles frame plan")
    usd=args.plan.parent/plan["usd_file"]
    if (usd.parent!=args.plan.parent or usd.is_symlink() or
        not usd.is_file() or digest(usd)!=plan["usd_sha256"]):
        raise RuntimeError("Cycles worker source USD differs from frozen host plan")
    if args.output.exists() or args.audit.exists():
        raise RuntimeError("Native output identity already used")
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not hasattr(bpy.ops.wm,"usd_import"):
        raise RuntimeError("Installed Blender lacks native OpenUSD scene import")
    operator=bpy.ops.wm.usd_import
    available={p.identifier for p in operator.get_rna_type().properties}
    options={"filepath":str(usd)}
    for key in ("import_cameras","import_lights","import_meshes",
                "import_materials","import_skeletons"):
        if key in available:
            options[key]=True
    for key, value in {
            "merge_parent_xform":False,
            "set_frame_range":False,
            "validate_meshes":True,
            "import_visible_only":True,
            "import_render":True,
            "import_usd_preview":True,
        }.items():
        if key in available:
            options[key]=value
    result=operator(**options)
    if "FINISHED" not in result:
        raise RuntimeError("Native Cycles OpenUSD scene import failed")
    name=plan["camera_path"].rsplit("/",1)[-1]
    camera=bpy.data.objects.get(name)
    if camera is None or camera.type!="CAMERA":
        raise RuntimeError("Composed original USD camera not imported by Blender")
    scene=bpy.context.scene
    def imported_descendant(path, accepted):
        name=path.rsplit("/",1)[-1]
        obj=bpy.data.objects.get(name)
        if obj is None:
            return False
        all_objects=[obj]+list(obj.children_recursive)
        return any(x.type in accepted for x in all_objects)
    if any(not imported_descendant(p,{"MESH","ARMATURE"})
           for p in plan["actor_paths"]):
        raise RuntimeError("Source actor lacks real imported geometry or rig")
    if any(not imported_descendant(p,{"LIGHT"})
           for p in plan["light_paths"]):
        raise RuntimeError("Authored USD light was not imported for Cycles")
    if not any(obj.type=="MESH" for obj in scene.objects):
        raise RuntimeError("Real source scene has no Blender-renderable USD geometry")
    scene.camera=camera
    scene.render.engine="CYCLES"
    scene.cycles.samples=plan["samples"]
    if hasattr(bpy.context.view_layer,"cycles") and hasattr(
            bpy.context.view_layer.cycles,"use_denoising"):
        bpy.context.view_layer.cycles.use_denoising=True
    scene.render.resolution_x=plan["width"]
    scene.render.resolution_y=plan["height"]
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.image_settings.color_mode="RGB"
    scene.render.image_settings.color_depth="16"
    scene.render.filepath=str(args.output)
    scene.render.film_transparent=False
    bpy.ops.render.render(write_still=True)
    if not args.output.is_file() or args.output.stat().st_size<64:
        raise RuntimeError("Cycles did not publish an actual native picture")
    record={
        "format":"nvp.int02.cycles.native_frame.v1",
        "passed":True,
        "source_tick":plan["source_tick"],
        "source_usd_sha256":plan["usd_sha256"],
        "camera_path":plan["camera_path"],
        "render_engine":scene.render.engine,
        "cycles_samples":scene.cycles.samples,
        "resolution":[scene.render.resolution_x,scene.render.resolution_y],
        "native_usd_import":True,
        "original_actor_geometry_verified":True,
        "authored_lights_verified":True,
        "native_frame_sha256":digest(args.output),
        "physical_color_calibration_accepted":False,
        "feature_length_acceptance":False,
    }
    with args.audit.open("x",encoding="utf8") as f:
        json.dump(record,f,sort_keys=True,separators=(",",":"))
        f.flush()
    return 0


if __name__=="__main__":
    try:
        start=sys.argv.index("--")+1
    except ValueError:
        start=1
    sys.exit(main(sys.argv[start:]))
