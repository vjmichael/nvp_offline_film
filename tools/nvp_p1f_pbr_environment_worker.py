"""P1-F fixed native Cycles UV/PBR environment preview — PUBLIC SOURCE TEST ONLY.

This first-party script has NO scene-selected scripts, external USD resolver,
model-chosen paths, network calls, material pack downloads or hidden render
authorization. The trusted caller must SHA-pin exact reviewed original
FilmIndex USD and PNG source bytes before dispatch. Separate native production
private-film authorization and sandbox custody remain mandatory elsewhere.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

FORMAT="nvp.p1f.fixed.reviewed_uv_pbr_cycles_preview.v1"
SLOTS=("baseColor","roughness","metallic","normal")


def _source_files():
    if "--" not in sys.argv:
        raise RuntimeError("Fixed reviewed PBR render arguments missing")
    a=sys.argv[sys.argv.index("--")+1:]
    if len(a)!=8 or a[::2]!=["--plan","--source","--output","--audit"]:
        raise RuntimeError("Only fixed original PBR source/Cycles preview contract accepted")
    cwd=Path.cwd().resolve()
    paths=[Path(x) for x in a[1::2]]
    if (any(not p.is_absolute() or p.resolve().parent!=cwd or p.is_symlink()
            for p in paths) or len(set(paths))!=4 or
            [p.name for p in paths]!=[
                "material_plan.json","original_location.usda",
                "material_preview.png","material_audit.json"]):
        raise RuntimeError("Reviewed PBR operands escaped one fixed job root")
    return paths


def _sha(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    plan_path,usd_path,output,audit=_source_files()
    if output.exists() or audit.exists() or (
            plan_path.stat().st_size>8192 or
            usd_path.stat().st_size>8*1024*1024):
        raise RuntimeError("PBR output replay or original source exceeds finite size")
    plan=json.loads(plan_path.read_text("ascii"))
    expected={
        "format","original_environment_sha256","environment_document_sha256",
        "material_set_document_sha256","material_path","bindings",
        "images","width","height","samples",
    }
    if (type(plan) is not dict or set(plan)!=expected or
            plan["format"]!=FORMAT or _sha(usd_path)!=plan["original_environment_sha256"] or
            type(plan["width"]) is not int or not 128<=plan["width"]<=1280 or
            type(plan["height"]) is not int or not 72<=plan["height"]<=720 or
            type(plan["samples"]) is not int or not 4<=plan["samples"]<=64 or
            type(plan["images"]) is not dict or
            not 1<=len(plan["images"])<=4 or "baseColor" not in plan["images"] or
            set(plan["images"])-set(SLOTS) or
            type(plan["bindings"]) is not list or not plan["bindings"]):
        raise RuntimeError("Pinned original UV/PBR image/geometry source plan is invalid")
    source=usd_path.read_bytes()
    if not source.lstrip().startswith(b"#usda 1.0") or b"@" in source:
        raise RuntimeError("Native PBR preview forbids external USD asset references")
    widths=set()
    for slot,meta in plan["images"].items():
        if type(meta) is not dict or set(meta)!={
                "sha256","width","height","mode","media_type","size_bytes"}:
            raise RuntimeError("Unexpected original texture manifest schema")
        f=plan_path.parent/("map_"+slot+".png")
        if (f.is_symlink() or not f.is_file() or f.stat().st_size!=meta["size_bytes"] or
                _sha(f)!=meta["sha256"] or meta["media_type"]!="image/png"):
            raise RuntimeError("Reviewed native UV/PBR map was altered before Cycles")
        widths.add((meta["width"],meta["height"]))
    if len(widths)!=1:
        raise RuntimeError("PBR original authored maps must share UV resolution")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    properties=set(bpy.ops.wm.usd_import.get_rna_type().properties.keys())
    opts={"filepath":str(usd_path)}
    for name in ("import_meshes","import_materials"):
        if name not in properties:
            raise RuntimeError("Native Blender lacks material-preserving USD importer")
        opts[name]=True
    if "FINISHED" not in bpy.ops.wm.usd_import(**opts):
        raise RuntimeError("Native reviewed environment USD import failed")
    bound=[]
    expected_names={item["mesh_path"].rsplit("/",1)[-1]
                    for item in plan["bindings"]}
    for name in expected_names:
        matches=[o for o in bpy.data.objects if o.type=="MESH" and o.name==name]
        if len(matches)!=1:
            raise RuntimeError("Approved original UV geometry missing or ambiguous in Blender")
        mesh=matches[0]
        if not mesh.data.uv_layers:
            raise RuntimeError("Genuine USD UV primvar did not survive Blender import")
        bound.append(mesh)
    if not bound:
        raise RuntimeError("Reviewed source has no actual imported authored UV mesh")
    mat=bpy.data.materials.new("NVP_DerivedReviewedPBR")
    mat.use_nodes=True
    nodes=mat.node_tree.nodes
    nodes.clear()
    links=mat.node_tree.links
    out=nodes.new("ShaderNodeOutputMaterial")
    bsdf=nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs["BSDF"],out.inputs["Surface"])
    textures={}
    for slot,meta in sorted(plan["images"].items()):
        image_path=plan_path.parent/("map_"+slot+".png")
        img=bpy.data.images.load(str(image_path),check_existing=False)
        if (img.filepath!=str(image_path) or
                list(img.size)!=[meta["width"],meta["height"]]):
            raise RuntimeError("Original texture decoded geometry differs from FilmIndex")
        tex=nodes.new("ShaderNodeTexImage")
        tex.image=img
        if slot!="baseColor":
            tex.image.colorspace_settings.name="Non-Color"
        if slot=="baseColor":
            links.new(tex.outputs["Color"],bsdf.inputs["Base Color"])
        elif slot=="roughness":
            links.new(tex.outputs["Color"],bsdf.inputs["Roughness"])
        elif slot=="metallic":
            links.new(tex.outputs["Color"],bsdf.inputs["Metallic"])
        else:
            normal=nodes.new("ShaderNodeNormalMap")
            links.new(tex.outputs["Color"],normal.inputs["Color"])
            links.new(normal.outputs["Normal"],bsdf.inputs["Normal"])
        textures[slot]={"sha256":meta["sha256"],"width":img.size[0],
                        "height":img.size[1],"actual_image_name":img.name}
    for obj in bound:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    scene=bpy.context.scene
    camera_data=bpy.data.cameras.new("DerivedReviewCamera")
    camera=bpy.data.objects.new("DerivedReviewCamera",camera_data)
    scene.collection.objects.link(camera)
    target=Vector((0.,-1.,2.))
    camera.location=(0.,-9.,2.)
    direction=target-Vector(camera.location)
    camera.rotation_euler=direction.to_track_quat("-Z","Y").to_euler()
    camera_data.lens=35
    scene.camera=camera
    world=bpy.data.worlds.new("DerivedReviewLight")
    world.use_nodes=True
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value=.7
    scene.world=world
    lamp=bpy.data.lights.new("DerivedReviewSoftbox","AREA")
    light=bpy.data.objects.new("DerivedReviewSoftbox",lamp)
    scene.collection.objects.link(light)
    light.location=(0.,-5.,6.)
    lamp.energy=850
    lamp.shape="DISK"
    lamp.size=6
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=plan["samples"]
    scene.render.resolution_x=plan["width"]
    scene.render.resolution_y=plan["height"]
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.filepath=str(output)
    bpy.ops.render.render(write_still=True)
    if not output.is_file() or output.stat().st_size<256:
        raise RuntimeError("Native Blender failed to render original UV/PBR surface")
    receipt={
        "format":FORMAT,"passed":True,
        "source_environment_sha256":plan["original_environment_sha256"],
        "environment_document_sha256":plan["environment_document_sha256"],
        "material_set_document_sha256":plan["material_set_document_sha256"],
        "source_material_path":plan["material_path"],
        "actual_imported_uv_meshes":sorted(o.name for o in bound),
        "actual_pbr_channels":textures,
        "derived_preview_camera":camera.name,
        "render_engine":"CYCLES",
        "width":plan["width"],"height":plan["height"],"samples":plan["samples"],
        "png_sha256":_sha(output),
        "creator_private_film_approved":False,
        "whole_film_rendered":False,
    }
    audit.write_text(json.dumps(receipt,sort_keys=True,separators=(",",":")),
                     encoding="ascii")


if __name__=="__main__":
    main()
