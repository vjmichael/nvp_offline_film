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


def _reviewed_material(plan,root):
    """Translate ONLY the exact source-scene-bound reviewed maps, no resolver."""
    review=plan.get("reviewed_material")
    if review is None:
        return None
    required={
        "look_id","look_document_sha256","material_set_id",
        "material_set_document_sha256","composed_material_path",
        "bound_mesh_paths","texture_sources",
    }
    if (type(review) is not dict or set(review)!=required or
            type(review["composed_material_path"]) is not str or
            not review["composed_material_path"].startswith("/World/") or
            type(review["bound_mesh_paths"]) is not list or
            not 1<=len(review["bound_mesh_paths"])<=64 or
            len(set(review["bound_mesh_paths"]))!=len(review["bound_mesh_paths"]) or
            type(review["texture_sources"]) is not dict or
            "baseColor" not in review["texture_sources"] or
            not 1<=len(review["texture_sources"])<=4 or
            set(review["texture_sources"])-{
                "baseColor","roughness","metallic","normal"}):
        raise RuntimeError("Reviewed original scene PBR scope invalid")
    imported=[]
    for path in review["bound_mesh_paths"]:
        if (type(path) is not str or not path.startswith("/World/") or
                not path.endswith(tuple("/"+x for x in
                    ("Wall","Floor","Hallway","Ceiling","Door")) + ("/Geometry",))
                and "/Geometry/" not in path):
            raise RuntimeError("Unrecognized original imported PBR mesh identity")
        name=path.rsplit("/",1)[-1]
        matches=[o for o in bpy.data.objects if o.type=="MESH" and o.name==name]
        if len(matches)!=1 or not matches[0].data.uv_layers:
            raise RuntimeError("Original scene reviewed UV mesh unavailable after USD import")
        imported.append(matches[0])
    if not imported:
        raise RuntimeError("No authored UV mesh to carry reviewed original PBR material")
    material=bpy.data.materials.new("NVP_SourceBoundOriginalPBR")
    material.use_nodes=True
    nodes=material.node_tree.nodes
    nodes.clear()
    links=material.node_tree.links
    output=nodes.new("ShaderNodeOutputMaterial")
    principled=nodes.new("ShaderNodeBsdfPrincipled")
    links.new(principled.outputs["BSDF"],output.inputs["Surface"])
    seen={}
    for slot,meta in sorted(review["texture_sources"].items()):
        if (type(meta) is not dict or
                set(meta)!={"sha256","width","height","mode",
                            "media_type","size_bytes"} or
                type(meta["sha256"]) is not str or len(meta["sha256"])!=64):
            raise RuntimeError("Original material image channel manifest malformed")
        image_path=root/("reviewed_"+slot+".png")
        if (image_path.is_symlink() or not image_path.is_file() or
                image_path.parent!=root or
                image_path.stat().st_size!=meta["size_bytes"] or
                _sha(image_path)!=meta["sha256"] or
                meta["media_type"]!="image/png"):
            raise RuntimeError("SHA-pinned original PBR texture bytes changed in worker")
        img=bpy.data.images.load(str(image_path),check_existing=False)
        if list(img.size)!=[meta["width"],meta["height"]]:
            raise RuntimeError("Actual image pixels differ from approved PBR texture")
        tex=nodes.new("ShaderNodeTexImage")
        tex.image=img
        if slot!="baseColor":
            img.colorspace_settings.name="Non-Color"
        if slot=="baseColor":
            links.new(tex.outputs["Color"],principled.inputs["Base Color"])
        elif slot=="roughness":
            links.new(tex.outputs["Color"],principled.inputs["Roughness"])
        elif slot=="metallic":
            links.new(tex.outputs["Color"],principled.inputs["Metallic"])
        else:
            normal=nodes.new("ShaderNodeNormalMap")
            links.new(tex.outputs["Color"],normal.inputs["Color"])
            links.new(normal.outputs["Normal"],principled.inputs["Normal"])
        seen[slot]={"sha256":meta["sha256"],"width":img.size[0],
                    "height":img.size[1],"actual_image_name":img.name}
    for mesh in imported:
        mesh.data.materials.clear()
        mesh.data.materials.append(material)
    return {
        "look_id":review["look_id"],
        "look_document_sha256":review["look_document_sha256"],
        "material_set_document_sha256":review["material_set_document_sha256"],
        "composed_material_path":review["composed_material_path"],
        "bound_mesh_paths":review["bound_mesh_paths"],
        "imported_uv_meshes":sorted(o.name for o in imported),
        "textures":seen,
    }


def main():
    plan_path,usd_path,png_path,audit_path=_args()
    if png_path.exists() or audit_path.exists():
        raise RuntimeError("P1-F output must not exist before supervised launch")
    if plan_path.stat().st_size>8192 or usd_path.stat().st_size>8*1024*1024:
        raise RuntimeError("Actor input exceeds finite worker resource contract")
    plan=json.loads(plan_path.read_text("utf8"))
    expected={"format","scene_sha256","usd_sha256","camera",
              "actor_id","actor_path","source_tick",
              "expected_face_weights","width","height","samples"}
    if type(plan) is not dict or (
            set(plan)!=expected and
            set(plan)!=expected|{"reviewed_material"}):
        raise RuntimeError("Worker original source contract has unexpected fields")
    if (
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
    if any(type(v) not in (int,float) or not 0<=float(v)<=1
           for v in plan["expected_face_weights"]):
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
    # Blender may map USD's 7,056,000,000 timecodes/second onto its own
    # action-frame domain differently. NVP's Film Time is authoritative.
    # Imported mesh/rig/shape-key GEOMETRY must remain genuine. Apply the
    # independently SHA-bound USD weights for THIS exact picture instant
    # explicitly, rather than silently trusting Blender's time conversion.
    keys=mesh.data.shape_keys
    basis=keys.key_blocks.get("Basis")
    if basis is None or len(basis.data)!=len(mesh.data.vertices):
        raise RuntimeError("Imported character has no genuine base facial topology")
    for name in SHAPES:
        target=keys.key_blocks[name]
        if (len(target.data)!=len(basis.data) or
                not any((target.data[i].co-basis.data[i].co).length>1e-6
                        for i in range(len(basis.data)))):
            raise RuntimeError("Imported USD facial key has no actual mesh deformation")
    # The USD stage retains original authored time curves. In this derivative
    # single-frame Blender shot, the pinned source values supersede importer
    # action curves; otherwise render evaluation could reapply a different
    # unapproved frame and silently change the actor's expression.
    if keys.animation_data:
        keys.animation_data_clear()
    expected=[float(v) for v in plan["expected_face_weights"]]
    for name,value in zip(SHAPES,expected):
        keys.key_blocks[name].value=value
    bpy.context.view_layer.update()
    # Original UV/PBR set metadata is separately bound to THIS exact
    # frozen scene/Take by the host. Read only named, SHA-verified local
    # material files; no external resolver, arbitrary script or URL.
    reviewed_material=_reviewed_material(plan,plan_path.parent)
    actual=[float(keys.key_blocks[name].value) for name in SHAPES]
    if any(abs(a-b)>1e-5 for a,b in zip(actual,expected)):
        raise RuntimeError("Exact original USD facial weights did not transfer into Blender")
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
    if reviewed_material is not None:
        audit["reviewed_material"]=reviewed_material
    audit_path.write_text(json.dumps(audit,sort_keys=True,separators=(",",":")),
                          encoding="utf8")


if __name__=="__main__":
    main()
