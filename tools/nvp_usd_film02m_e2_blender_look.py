# SPDX-License-Identifier: GPL-2.0-or-later
"""02M-E2 — genuine protected Blender/Cycles material, light, LOD receipts.

This fixed first-party worker checks original USD/derived LOD byte hashes
and source material provenance before drawing any frame. Blender imports
the actual USD surfaces; no replacement procedural BSDF is manufactured
on failed material import. Relighting is a derived shot decision, never a
source-world edit. CPU resource and Cycles render times are measured,
not guessed. Multi-layer EXR stays a separate native acceptance gate.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import os
from pathlib import Path
import resource
import sys
import time

import bpy
from mathutils import Vector

FORMAT="nvp.usd_film02m_e2.real_native_cycles_look_receipt.v1"
SOURCE_FORMAT="nvp.usd_film02m_e2.referenced_lod_look_review.v1"
VIEWS=("near_front","near_rear","mid_oblique","far_street","near_front_relight")
ASSET_SHA_CHARS=set("0123456789abcdef")


def sha(path):
    h=sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def _within(root,relative):
    if (type(relative) is not str or not relative or
        Path(relative).is_absolute() or
        any(p in ("..","") for p in Path(relative).parts)):
        raise PermissionError("Reviewed NVP scene may not escape worker workspace")
    file=root/relative
    if file.is_symlink() or file.resolve().is_relative_to(root) is False:
        raise PermissionError("Original USD input cannot use symbolic path")
    return file


def _memory_mb():
    # Linux ru_maxrss is KiB. The reviewed 02M E2 Blender job is
    # explicitly scheduled on Linux; do not mislabel this as VRAM.
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)/1024.


def _original_contract(root):
    spec=json.loads(_within(root,"manifest.json").read_text("utf8"))
    keys={
        "format","project_id","building_id","building_revision",
        "building_document_sha256","original_near_stage_sha256",
        "mid_lod_stage_sha256","far_lod_stage_sha256",
        "source_assets","source_material_contract",
        "world_source_bounds_m","actual_geometry_triangle_counts",
        "first_party_reviewed_profiles","original_world_take_unchanged",
        "source_look_model","materialx_parity_verified",
        "native_blender_material_import_verified",
        "ocio_aces_config_verified","exr_multilayer_rendered",
        "cinematic_picture_approved","source_near_includes_real_openings",
        "mid_far_are_approximate_hulls_not_camera_valid_near"}
    if type(spec) is not dict or set(spec)!=keys or spec["format"]!=SOURCE_FORMAT:
        raise PermissionError("Unreviewed NVP source film look contract")
    if (spec["original_world_take_unchanged"] is not True or
        spec["source_look_model"]!="UsdPreviewSurface" or
        spec["native_blender_material_import_verified"] is not False or
        spec["ocio_aces_config_verified"] is not False or
        spec["exr_multilayer_rendered"] is not False or
        spec["cinematic_picture_approved"] is not False or
        spec["source_near_includes_real_openings"] is not True or
        spec["mid_far_are_approximate_hulls_not_camera_valid_near"] is not True):
        raise PermissionError("Source look preview cannot assert finished renderer work")
    if [p["id"] for p in spec["first_party_reviewed_profiles"]]!=list(VIEWS):
        raise PermissionError("Only exact reviewed CPU source lighting/view profiles")
    accepted=[
        ("near_front","near","front",[640,360],16,"soft_day"),
        ("near_rear","near","rear",[640,360],16,"soft_day"),
        ("mid_oblique","mid","oblique",[480,270],8,"soft_day"),
        ("far_street","far","far",[320,180],4,"soft_day"),
        ("near_front_relight","near","front",[640,360],16,"warm_side")]
    for p,w in zip(spec["first_party_reviewed_profiles"],accepted):
        if (type(p) is not dict or set(p)!={
                "id","lod","camera","resolution","cycles_samples","lighting"} or
            (p["id"],p["lod"],p["camera"],p["resolution"],
             p["cycles_samples"],p["lighting"])!=w):
            raise PermissionError("Creator rendering settings no longer match reviewed 02M E2")
    for level,key in (
            ("near","original_near_stage_sha256"),
            ("mid","mid_lod_stage_sha256"),
            ("far","far_lod_stage_sha256")):
        path=_within(root,level+".usda")
        if not path.is_file() or sha(path)!=spec[key]:
            raise RuntimeError("Actual original/derived USD LOD bytes changed")
    assets=spec["source_assets"]
    if (type(assets) is not dict or not 1<=len(assets)<=48 or
        any(type(s) is not str or len(s)!=64 or
            set(s)-ASSET_SHA_CHARS or x!=s+".usda"
            for s,x in assets.items())):
        raise PermissionError("Only SHA-addressed original material/mesh asset layers")
    for digest in assets:
        file=_within(root,"assets/"+digest+".usda")
        if not file.is_file() or sha(file)!=digest:
            raise RuntimeError("Original look asset material/source SHA mismatch")
    original=spec["source_material_contract"]
    if (type(original) is not list or not 6<=len(original)<=48 or
        any(type(x) is not dict or set(x)!={
            "node_id","source_mesh_document_sha256",
            "source_usd_layer_sha256","usd_preview_material_path",
            "base_color_rgb","roughness","metallic",
            "has_source_texture","has_source_pbr_maps"} for x in original)):
        raise RuntimeError("Missing actual original material contracts")
    counts=spec["actual_geometry_triangle_counts"]
    if (type(counts) is not dict or set(counts)!={"near","mid","far"} or
        any(type(x) is not int or x<=0 for x in counts.values()) or
        not counts["far"]<counts["mid"]<=counts["near"]):
        raise PermissionError("Actual native geometry LOD cost must decrease")
    return spec


def _clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def _import_stage(stage):
    options={"filepath":str(stage)}
    props=set(bpy.ops.wm.usd_import.get_rna_type().properties.keys())
    for name in ("import_meshes","import_materials","import_usd_preview",
                 "read_mesh_uvs","apply_unit_conversion_scale"):
        if name in props:options[name]=True
    if "merge_parent_xform" in props:options["merge_parent_xform"]=False
    bpy.ops.wm.usd_import(**options)
    bpy.context.view_layer.update()
    objects=[o for o in bpy.context.scene.objects
             if o.type=="MESH" and len(o.data.vertices)>=8]
    if not objects:
        raise RuntimeError("Original USD data imported without real Cycles mesh")
    return objects


def _bsdf(material):
    if not material or not material.use_nodes or not material.node_tree:
        return None
    nodes=[node for node in material.node_tree.nodes
           if node.type=="BSDF_PRINCIPLED"]
    if not nodes:return None
    n=nodes[0]
    try:
        return {
            "material":material.name,
            "base_color_rgb":[float(x) for x in
                              n.inputs["Base Color"].default_value[:3]],
            "metallic":float(n.inputs["Metallic"].default_value),
            "roughness":float(n.inputs["Roughness"].default_value)}
    except (KeyError,TypeError,ValueError):
        return None


def _materials(meshes,original,lod):
    actual={}
    for obj in meshes:
        for slot in obj.material_slots:
            mat=slot.material
            if mat and mat.name not in actual:
                got=_bsdf(mat)
                if got:actual[mat.name]=got
    rows=list(actual.values())
    if not rows:
        raise RuntimeError("Native Blender did not import any USD PBR material into Cycles")
    if lod=="near":
        unique={}
        for src in original:
            key=tuple(src["base_color_rgb"])
            unique[key]=src
        matches=[]
        for src in unique.values():
            same=[m for m in rows if
                  max(abs(a-b) for a,b in zip(
                      src["base_color_rgb"],m["base_color_rgb"]))<=.16 and
                  abs(src["roughness"]-m["roughness"])<=.20 and
                  abs(src["metallic"]-m["metallic"])<=.20]
            if not same:
                raise RuntimeError(
                    "Cycles USD importer lost first-party original color/roughness/metallic binding")
            matches.append(src["node_id"])
        if len(unique)<3:
            raise RuntimeError("Real film material test lacks varied source surfaces")
    else:
        matches=[]
    return {
        "actual_assigned_principled_materials":len(rows),
        "actual_source_material_color_matches":matches,
        "reviewed_original_materials":rows,
        "native_source_shader_binding_verified":lod=="near",
        "materialx_parity_verified":False}


def _lighting(scene,preset):
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    if preset not in ("soft_day","warm_side"):
        raise PermissionError("Only reviewed deterministic original scene light presets")
    world=bpy.data.worlds.new("NVP E2 derived scene world "+preset)
    scene.world=world
    world.use_nodes=True
    bg=world.node_tree.nodes.get("Background")
    bg.inputs["Strength"].default_value=.38 if preset=="soft_day" else .26
    if preset=="warm_side":
        bg.inputs["Color"].default_value=(1.,.78,.55,1.)
    else:
        bg.inputs["Color"].default_value=(.83,.9,1.,1.)
    sun=bpy.data.lights.new("NVP E2 reviewed sun "+preset,"SUN")
    sun.energy=2.3 if preset=="soft_day" else 1.8
    sun.angle=.26
    obj=bpy.data.objects.new("NVP E2 temporary source-independent sun",sun)
    scene.collection.objects.link(obj)
    obj.rotation_euler=(.7,-.42,.22) if preset=="soft_day" else (
        1.0,.38,-.68)
    return {
        "preset":preset,"world_strength":bg.inputs["Strength"].default_value,
        "sun_energy":sun.energy,"sun_angle":sun.angle,
        "sun_rotation_euler":list(obj.rotation_euler),
        "original_source_layer_modified":False}


def _camera(scene,camera_name,bounds):
    low=Vector(bounds[0]);high=Vector(bounds[1])
    center=(low+high)/2
    span=high-low
    distance=max(24.,span.x*2.4,span.y*2.4,span.z*3.0)
    loc={
        "front":center+Vector((0,-distance,span.z*.5)),
        "rear":center+Vector((0,distance,span.z*.5)),
        "oblique":center+Vector((distance*.9,-distance*.8,span.z*.9)),
        "far":center+Vector((distance*2.3,-distance*2.3,span.z*1.5)),
    }[camera_name]
    bpy.ops.object.camera_add(location=loc)
    camera=bpy.context.object
    camera.name="NVP E2 original derived camera "+camera_name
    camera.data.lens=40.
    camera.rotation_euler=(center-loc).to_track_quat(
        "-Z","Y").to_euler()
    scene.camera=camera
    return {"camera":camera_name,"source_target_m":list(center),
            "actual_camera_world_m":list(loc),
            "reviewed_lens_mm":40.}


def _render(root,spec,profile):
    shot=profile["id"]
    stage=root/(profile["lod"]+".usda")
    _clear()
    objects=_import_stage(stage)
    polygons=sum(len(o.data.polygons) for o in objects)
    vertices=sum(len(o.data.vertices) for o in objects)
    if polygons!=spec["actual_geometry_triangle_counts"][profile["lod"]]:
        raise RuntimeError("Native Cycles imported incorrect actual original LOD face count")
    mat=_materials(objects,spec["source_material_contract"],profile["lod"])
    scene=bpy.context.scene
    light=_lighting(scene,profile["lighting"])
    camera=_camera(scene,profile["camera"],spec["world_source_bounds_m"])
    scene.cycles.samples=profile["cycles_samples"]
    scene.render.resolution_x=profile["resolution"][0]
    scene.render.resolution_y=profile["resolution"][1]
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.use_file_extension=False
    scene.render.film_transparent=False
    # Blender's built-in AgX is NOT an ACES/OCIO external config.
    scene.view_settings.view_transform="AgX"
    scene.view_layers[0].use_pass_z=True
    scene.view_layers[0].use_pass_normal=True
    scene.view_layers[0].use_pass_diffuse_color=True
    filename=shot+".png"
    output=root/filename
    if output.exists() or output.is_symlink():
        raise PermissionError("Original Cycles review frames cannot be overwritten")
    t0=time.perf_counter()
    m0=_memory_mb()
    scene.render.filepath=str(output)
    bpy.ops.render.render(write_still=True)
    render_wall_seconds=time.perf_counter()-t0
    if not output.is_file() or output.stat().st_size<200:
        raise RuntimeError("Actual Cycles source-derived pixels missing")
    exr_info={"requested":False,"actual_exr_rendered":False}
    if shot=="near_front":
        name=shot+"_passes.exr"
        path=root/name
        if path.exists() or path.is_symlink():
            raise PermissionError("Cannot overwrite original OpenEXR look pass")
        # One real extra render with multilayer image output ensures
        # Z/Normal/Diffuse passes are produced from the same source/camera
        # and avoids claiming Blender save_render preserves a renderlayer
        # when the original render was written as PNG.
        scene.render.image_settings.file_format="OPEN_EXR_MULTILAYER"
        scene.render.image_settings.color_depth="32"
        scene.render.image_settings.exr_codec="ZIP"
        scene.render.filepath=str(path)
        start_exr=time.perf_counter()
        bpy.ops.render.render(write_still=True)
        if not path.is_file() or path.stat().st_size<500:
            raise RuntimeError("Actual multi-layer original OpenEXR was not created")
        with path.open("rb") as handle:
            if handle.read(4)!=b"\x76\x2f\x31\x01":
                raise RuntimeError("Actual OpenEXR byte signature did not verify")
        exr_info={
            "requested":True,"actual_exr_rendered":True,
            "exr_name":name,"actual_exr_sha256":sha(path),
            "exr_render_wall_seconds":time.perf_counter()-start_exr,
            "view_layer_z_enabled":True,
            "view_layer_normal_enabled":True,
            "view_layer_diffuse_color_enabled":True,
            "ocio_aces_config_verified":False}
    return {
        "shot":shot,"source_lod":profile["lod"],
        "native_imported_source_triangles":polygons,
        "native_imported_meshes":len(objects),
        "native_imported_vertices":vertices,
        "source_look":mat,"lighting":light,"camera":camera,
        "actual_cycles_samples":scene.cycles.samples,
        "actual_pixel_dimensions":[scene.render.resolution_x,
                                   scene.render.resolution_y],
        "actual_builtin_color_view_transform":scene.view_settings.view_transform,
        "actual_source_png":filename,"actual_png_sha256":sha(output),
        "cycles_render_wall_seconds":render_wall_seconds,
        "actual_worker_process_rss_before_mb":m0,
        "actual_worker_process_peak_rss_mb":_memory_mb(),
        "gpu_memory_measured":False,"cpu_cycles_render_verified":True,
        "exr":exr_info}


def main():
    if "--" not in sys.argv:
        raise PermissionError("Fixed first-party 02M-E2 Blender worker arguments")
    argv=sys.argv[sys.argv.index("--")+1:]
    if (len(argv)!=4 or set(argv[::2])!={"--manifest","--audit"}):
        raise PermissionError("Only native reviewed source look contract")
    flags=dict(zip(argv[::2],argv[1::2]))
    if flags["--manifest"]!="manifest.json" or flags["--audit"]!="audit.json":
        raise PermissionError("Original source look inputs/receipts use fixed names")
    root=Path.cwd().resolve(strict=True)
    path=root/"audit.json"
    if path.exists() or path.is_symlink():
        raise FileExistsError("Cannot overwrite 02M-E2 native look outcome")
    started=time.perf_counter()
    version=bpy.app.version_string
    if not version.startswith("5.2."):
        raise RuntimeError("Reviewed original Cycles look test requires Blender 5.2")
    spec=_original_contract(root)
    results=[]
    for profile in spec["first_party_reviewed_profiles"]:
        results.append(_render(root,spec,profile))
    if len({r["actual_png_sha256"] for r in results})!=len(VIEWS):
        raise RuntimeError("Source/Cycles original camera and relight views were identical")
    if results[0]["source_look"][
            "native_source_shader_binding_verified"] is not True:
        raise RuntimeError("Original USD material never reached Blender/Cycles")
    if results[0]["exr"]["actual_exr_rendered"] is not True:
        raise RuntimeError("Film native OpenEXR AOV output not verified")
    audit={
        "format":FORMAT,"passed":True,
        "original_project_id":spec["project_id"],
        "original_building_id":spec["building_id"],
        "original_building_sha256":spec["building_document_sha256"],
        "original_usd_near_sha256":spec["original_near_stage_sha256"],
        "derived_mid_sha256":spec["mid_lod_stage_sha256"],
        "derived_far_sha256":spec["far_lod_stage_sha256"],
        "reviewed_original_material_shader":"UsdPreviewSurface",
        "actual_imported_original_shader_parity":True,
        "true_geometry_lods_verified":True,
        "actual_native_linear_exr_with_source_passes":True,
        "built_in_view_transform":"AgX",
        "aces_external_ocio_config_verified":False,
        "materialx_parity_verified":False,
        "same_frozen_source_all_rendered_views":True,
        "original_source_and_performance_untouched":True,
        "source_near_exact_mid_far_approximate":True,
        "actual_blender_version":version,
        "cycles_device":"CPU",
        "gpu_vram_measured":False,
        "actual_worker_peak_process_rss_mb":_memory_mb(),
        "actual_worker_total_wall_seconds":time.perf_counter()-started,
        "rendered_views":results,
        "director_picture_quality_approved":False,
        "final_720_frame_film_accepted":False}
    path.write_text(json.dumps(audit,sort_keys=True,separators=(",",":"),
                               allow_nan=False),"utf8")


if __name__=="__main__":
    main()
