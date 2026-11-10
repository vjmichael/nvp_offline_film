# SPDX-License-Identifier: GPL-2.0-or-later
"""USD-FILM-02M-E: genuine first-party Blender/Cycles three-angle smoke.

This is test-only visual evidence, NOT a new NVP render engine or an
arbitrary project script. Immutable original geometry and SHA-pinned
stage/asset sources are loaded through native Blender USD import. The
front, rear and oblique camera photographs test true building depth
and retained rear/roof geometry. Lighting and floor here are temporary
review scaffolding, not original actors or modified source film Takes.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import math
import sys

import bpy
from mathutils import Vector


FORMAT="nvp.usd_film02m.native_original_three_view_cycles.v1"
SOURCE_FORMAT="nvp.usd_film02m.original_module_assembly.v1"


def file_sha(path):
    result=sha256()
    with Path(path).open("rb") as stream:
        for piece in iter(lambda:stream.read(1048576),b""):
            result.update(piece)
    return result.hexdigest()


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def main():
    argv=sys.argv[sys.argv.index("--")+1:]
    if len(argv)!=4 or set(argv[::2])!={"--manifest","--audit"}:
        raise PermissionError("Only reviewed modular architecture smoke arguments")
    args=dict(zip(argv[::2],argv[1::2]))
    cwd=Path.cwd().resolve(strict=True)
    files={}
    for name,path in args.items():
        requested=Path(path)
        resolved=requested.resolve()
        if (requested.is_symlink() or resolved.parent!=cwd or
            (name=="--manifest" and not resolved.is_file()) or
            (name=="--audit" and resolved.exists())):
            raise PermissionError("Architecture source paths must stay in reviewed workspace")
        files[name]=resolved
    spec=json.loads(files["--manifest"].read_text("utf8"))
    if (type(spec) is not dict or set(spec)!={
            "format","building_source_format","usd_root_sha256",
            "assets","expected_modules","source_building_sha256","camera_views"} or
        spec["format"]!="nvp.usd_film02m.cycles_three_angle_request.v1" or
        spec["building_source_format"]!=SOURCE_FORMAT or
        spec["camera_views"]!=["front","rear","oblique"]):
        raise PermissionError("Unreviewed source film architecture scene")
    source=cwd/"building.usda"
    if (source.is_symlink() or not source.is_file() or
        file_sha(source)!=spec["usd_root_sha256"]):
        raise RuntimeError("Actual source building USD bytes changed")
    assets=spec["assets"]
    if (type(assets) is not dict or not 1<=len(assets)<=24 or
        any(type(name) is not str or
            len(name)!=64 or
            any(ch not in "0123456789abcdef" for ch in name) or
            value!=name
            for name,value in assets.items())):
        raise RuntimeError("Unrecognized source-locked architecture module assets")
    for digest in assets:
        source_layer=cwd/"assets"/(digest+".usda")
        if (source_layer.is_symlink() or
            not source_layer.is_file() or file_sha(source_layer)!=digest):
            raise PermissionError("Native source mesh reference changed")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    opts={"filepath":str(source)}
    props=set(bpy.ops.wm.usd_import.get_rna_type().properties.keys())
    for key in ("import_meshes","import_cameras","import_lights",
                "import_materials","import_usd_preview",
                "read_mesh_uvs","apply_unit_conversion_scale"):
        if key in props:opts[key]=True
    if "merge_parent_xform" in props:opts["merge_parent_xform"]=False
    bpy.ops.wm.usd_import(**opts)
    scene=bpy.context.scene
    meshes=[o for o in bpy.data.objects if o.type=="MESH" and
            len(o.data.vertices)>=8 and len(o.data.polygons)>=12]
    if (len(meshes)!=spec["expected_modules"] or
        len({o.name for o in meshes})!=len(meshes)):
        raise RuntimeError("Genuine native USD imported building missing 3D module meshes")
    source_vertices=sum(len(x.data.vertices) for x in meshes)
    source_faces=sum(len(x.data.polygons) for x in meshes)
    if source_vertices<8*spec["expected_modules"]:
        raise RuntimeError("Cannot accept flat or absent rear architecture source")
    # Center and bounds are computed from actual Blender world mesh vertices,
    # not a guessed 3D silhouette. Evaluate source transforms once.
    low=Vector((1e12,1e12,1e12))
    high=Vector((-1e12,-1e12,-1e12))
    for mesh in meshes:
        for vertex in mesh.data.vertices:
            pos=mesh.matrix_world @ vertex.co
            for j in range(3):
                low[j]=min(low[j],pos[j])
                high[j]=max(high[j],pos[j])
    dims=[float(high[i]-low[i]) for i in range(3)]
    if any(not math.isfinite(x) or x<.3 for x in dims):
        raise RuntimeError("Native rear/side/roof original geometry collapsed")
    center=(low+high)/2
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=8
    scene.render.resolution_x=320
    scene.render.resolution_y=180
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.render.use_file_extension=False
    world=bpy.data.worlds.new("NVP Technical Building Ambient")
    scene.world=world
    world.use_nodes=True
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value=.55
    lamp=bpy.data.lights.new("NVP 02M Technical Sun","SUN")
    lamp.energy=2.8
    obj=bpy.data.objects.new("NVP 02M Technical Sun",lamp)
    scene.collection.objects.link(obj)
    obj.rotation_euler=(.7,-.45,.15)
    views={
        "front":center+Vector((0,-max(20,dims[1]*2.6),max(5,dims[2]*1.3))),
        "rear":center+Vector((0,max(20,dims[1]*2.6),max(5,dims[2]*1.3))),
        "oblique":center+Vector((
            max(20,dims[0]*2.0),-max(20,dims[1]*2.0),max(6,dims[2]*1.8)))}
    rows=[]
    for label in spec["camera_views"]:
        name="film02m_"+label+".png"
        output=cwd/name
        if output.exists() or output.is_symlink():
            raise FileExistsError("No overwriting previously rendered original building")
        bpy.ops.object.camera_add(location=views[label])
        camera=bpy.context.object
        camera.name="NVP 02M "+label+" Director Review View"
        camera.rotation_euler=(center-camera.location).to_track_quat(
            "-Z","Y").to_euler()
        camera.data.lens=38
        scene.camera=camera
        scene.render.filepath=str(output)
        bpy.ops.render.render(write_still=True)
        if not output.is_file() or output.stat().st_size<100:
            raise RuntimeError("Native 02M original building Cycles pixels missing")
        rows.append({
            "view":label,"image_name":name,
            "original_source_sha256":spec["usd_root_sha256"],
            "real_source_triangles":source_faces,
            "image_sha256":file_sha(output)})
        bpy.data.objects.remove(camera,do_unlink=True)
    if len({x["image_sha256"] for x in rows})!=3:
        raise RuntimeError("Original front, rear and oblique geometry collapsed to identical images")
    receipt={
        "format":FORMAT,"passed":True,
        "source_building_sha256":spec["source_building_sha256"],
        "usd_root_sha256":spec["usd_root_sha256"],
        "referenced_asset_shas":sorted(assets),
        "actual_original_native_meshes":len(meshes),
        "actual_original_native_vertices":source_vertices,
        "actual_original_native_faces":source_faces,
        "actual_original_world_bounds_m":[list(low),list(high)],
        "source_original_real_3d":True,
        "front_rear_and_oblique_cameras_rendered":True,
        "native_blender_version":bpy.app.version_string,
        "cycles_samples":8,
        "render_width":320,"render_height":180,
        "rendered_views":rows,
        "director_visual_quality_reviewed":False,
        "materialx_parity_verified":False,
        "full_cinema_render_quality_accepted":False}
    files["--audit"].write_bytes(canonical(receipt))


if __name__=="__main__":
    main()
