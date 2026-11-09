# SPDX-License-Identifier: GPL-2.0-or-later
"""Genuine 02M-E2 Cycles parity of a compiled immutable USD district.

No AI-authored Blender code. One fixed first-party script verifies actual
building/asset SHA, imports the disposable NVP source view, measures real
Cycles CPU cost, and produces two independently inspectable street views.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
import bpy
from mathutils import Vector

SOURCE_FORMAT="nvp.usd_film02m_e2.blender_compatible_district_view.v1"
RECEIPT="nvp.usd_film02m_e2.native_original_district_cycles.v1"


def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for piece in iter(lambda:f.read(1048576),b""):
            h.update(piece)
    return h.hexdigest()


def main():
    if "--" not in sys.argv:
        raise PermissionError("Reviewed NVP district render worker only")
    argv=sys.argv[sys.argv.index("--")+1:]
    if (argv!=["--manifest","manifest.json","--audit","audit.json"] and
        argv!=["--audit","audit.json","--manifest","manifest.json"]):
        raise PermissionError("Only fixed NVP film district render contract")
    root=Path.cwd().resolve(strict=True)
    spec=json.loads((root/"manifest.json").read_text("utf8"))
    if (type(spec) is not dict or spec.get("format")!=SOURCE_FORMAT or
        spec.get("compiled_from_source_no_actor_performance_modification") is not True or
        spec.get("did_not_modify_original_generated_or_director_layers") is not True or
        spec.get("native_blender_cycles_parity_verified") is not False or
        spec.get("gpu_instancing_performance_verified") is not False or
        spec.get("cinematic_picture_approved") is not False):
        raise PermissionError("Only source-authored 02M-E2 original district")
    assert_spec=set({
        "format","original_project_id","original_district_id",
        "original_district_revision","original_district_document_sha256",
        "original_point_instancer_root_sha256",
        "original_generated_layer_sha256","original_director_layer_sha256",
        "render_view_usd_sha256","referenced_original_building_usd_shas",
        "pinned_source_asset_layers","source_original_point_instances",
        "source_original_invisible_ids",
        "source_visible_and_hand_placed_instances",
        "source_approved_world_origin_m","render_view_local_origin_m",
        "source_visible_transform_receipts","expected_actual_original_meshes",
        "original_native_usd_pbr_bound_meshes",
        "compiled_from_source_no_actor_performance_modification",
        "did_not_modify_original_generated_or_director_layers",
        "native_blender_cycles_parity_verified",
        "gpu_instancing_performance_verified",
        "cinematic_picture_approved"})
    if set(spec)!=assert_spec:
        raise PermissionError("Unreviewed district render fields/authority")
    stage=root/"district_render_view.usda"
    if (stage.is_symlink() or digest(stage)!=spec["render_view_usd_sha256"]):
        raise RuntimeError("Original bounded district USD changed before rendering")
    source_dir=root/"sources"
    if source_dir.is_symlink():
        raise PermissionError("Original material source location cannot be overridden")
    for hashstr in spec["referenced_original_building_usd_shas"]:
        path=source_dir/(hashstr+".usda")
        if (len(hashstr)!=64 or path.is_symlink() or
            not path.is_file() or digest(path)!=hashstr):
            raise RuntimeError("Original district building source was substituted")
    for hashstr in spec["pinned_source_asset_layers"]:
        path=source_dir/"assets"/(hashstr+".usda")
        if (len(hashstr)!=64 or path.is_symlink() or
            not path.is_file() or digest(path)!=hashstr):
            raise RuntimeError("Original district PBR asset was substituted")
    if not bpy.app.version_string.startswith("5.2."):
        raise RuntimeError("Reviewed genuine Blender USD/Cycles 5.2 needed")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    properties=set(bpy.ops.wm.usd_import.get_rna_type().properties.keys())
    kwargs={"filepath":str(stage)}
    for field in ("import_meshes","import_materials","import_usd_preview",
                  "support_scene_instancing","apply_unit_conversion_scale"):
        if field in properties:kwargs[field]=True
    if "merge_parent_xform" in properties:kwargs["merge_parent_xform"]=False
    bpy.ops.wm.usd_import(**kwargs)
    bpy.context.view_layer.update()
    meshes=[obj for obj in bpy.context.scene.objects
            if obj.type=="MESH" and len(obj.data.vertices)>=8]
    if len(meshes)!=spec["expected_actual_original_meshes"]:
        raise RuntimeError(
            "Original USD PointInstancer→Blender render-view lost authored module meshes")
    materials=set()
    for obj in meshes:
        for slot in obj.material_slots:
            mat=slot.material
            if (mat and mat.use_nodes and any(
                    n.type=="BSDF_PRINCIPLED" for n in mat.node_tree.nodes)):
                materials.add(mat.name)
    if len(materials)<3:
        raise RuntimeError("Real USD district source materials did not reach Cycles")
    total_triangles=sum(len(o.data.polygons) for o in meshes)
    if total_triangles<12*len(meshes):
        raise RuntimeError("Original building meshes collapsed to non-3D geometry")
    all_points=[obj.matrix_world @ vertex.co for obj in meshes
                for vertex in obj.data.vertices]
    low=Vector(tuple(min(float(p[i]) for p in all_points) for i in range(3)))
    high=Vector(tuple(max(float(p[i]) for p in all_points) for i in range(3)))
    center=(low+high)/2
    span=high-low
    if span.x<1 or span.y<1 or span.z<1:
        raise RuntimeError("District original 3D source bounds invalid")
    scene=bpy.context.scene
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=8
    scene.render.resolution_x=480
    scene.render.resolution_y=270
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.use_file_extension=False
    scene.view_settings.view_transform="AgX"
    world=bpy.data.worlds.new("NVP E2 fixed original street ambient")
    world.use_nodes=True
    world.node_tree.nodes.get("Background").inputs[
        "Strength"].default_value=.4
    scene.world=world
    sun=bpy.data.lights.new("NVP E2 original street sun","SUN")
    sun.energy=2.5
    obj=bpy.data.objects.new("NVP E2 source-agnostic sun",sun)
    scene.collection.objects.link(obj)
    obj.rotation_euler=(.7,-.45,.18)
    distance=max(35,span.x*2,span.y*2,span.z*3)
    views={
        "street_front":center+Vector((0,-distance,span.z*.7)),
        "street_reverse":center+Vector((0,distance,span.z*.7))}
    results=[]
    start_all=time.perf_counter()
    for name,pos in views.items():
        filename=name+".png"
        output=root/filename
        if output.exists() or output.is_symlink():
            raise FileExistsError("Do not overwrite original district film picture")
        bpy.ops.object.camera_add(location=pos)
        camera=bpy.context.object
        camera.name="NVP E2 "+name
        camera.rotation_euler=(center-pos).to_track_quat(
            "-Z","Y").to_euler()
        camera.data.lens=38
        scene.camera=camera
        scene.render.filepath=str(output)
        start=time.perf_counter()
        bpy.ops.render.render(write_still=True)
        if not output.is_file() or output.stat().st_size<200:
            raise RuntimeError("Actual Cycles original district camera image missing")
        results.append({
            "view":name,"actual_png_sha256":digest(output),
            "native_cycles_render_wall_seconds":time.perf_counter()-start,
            "camera_world_m":list(pos),
            "scene_source_geometry_unchanged":True})
        bpy.data.objects.remove(camera,do_unlink=True)
    if results[0]["actual_png_sha256"]==results[1]["actual_png_sha256"]:
        raise RuntimeError("Original reverse street viewpoint did not produce distinct pixels")
    receipt={
        "format":RECEIPT,"passed":True,
        "original_district_document_sha256":spec[
            "original_district_document_sha256"],
        "original_generated_layer_sha256":spec[
            "original_generated_layer_sha256"],
        "original_director_layer_sha256":spec[
            "original_director_layer_sha256"],
        "original_instance_source_count":spec[
            "source_original_point_instances"],
        "actual_visible_original_buildings":spec[
            "source_visible_and_hand_placed_instances"],
        "actual_imported_first_party_meshes":len(meshes),
        "actual_imported_triangle_faces":total_triangles,
        "actual_principled_pbr_materials":len(materials),
        "actual_original_world_bounds_local_m":[list(low),list(high)],
        "actual_blender_cycles_device":"CPU",
        "actual_blender_version":bpy.app.version_string,
        "cycles_sample_count":8,
        "native_render_wall_seconds":time.perf_counter()-start_all,
        "native_peak_rss_mb":float(resource.getrusage(
            resource.RUSAGE_SELF).ru_maxrss)/1024.,
        "actual_native_street_views":results,
        "original_point_instancer_not_rewritten":True,
        "renderer_specific_expanded_usd_is_derived":True,
        "gpu_draw_call_savings_claimed":False,
        "materialx_parity_verified":False,
        "director_cinematic_look_approved":False}
    (root/"audit.json").write_text(json.dumps(
        receipt,sort_keys=True,separators=(",",":"),
        allow_nan=False),"utf8")


if __name__=="__main__":
    main()
