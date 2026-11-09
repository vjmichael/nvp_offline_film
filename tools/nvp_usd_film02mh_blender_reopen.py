# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent Blender process: verify saved 02M district + 01D/01E actors.

Never generate missing actors, cameras, PBR materials or district structures.
Called by the existing Blender supervisor with a real saved source .blend.
"""
from __future__ import annotations

import bpy
from hashlib import sha256
import json
from pathlib import Path
import sys

FORMAT="nvp.usd_film02m_h.independent_cycles_district_reopen.v1"
EVIDENCE="nvp.usd_film02m_h.real_original_actor_district_cycles_source.v1"


def digest(path):
    h=sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda:source.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    argv=sys.argv[sys.argv.index("--")+1:]
    if (len(argv)!=4 or argv[::2]!=["--manifest","--audit"]):
        raise PermissionError("Only reviewed district scene reopener options")
    args=dict(zip(argv[::2],argv[1::2]))
    root=Path.cwd().resolve(strict=True)
    manifest=Path(args["--manifest"])
    audit=Path(args["--audit"])
    if (manifest.is_symlink() or audit.is_symlink() or
        manifest.resolve()!=root/"source.json" or
        audit.resolve()!=root/"audit.json" or audit.exists()):
        raise PermissionError("Independent district evidence must remain in private worker folder")
    data=json.loads(manifest.read_text("utf8"))
    if (type(data) is not dict or set(data)!={
            "source","district","source_blend_sha256"}):
        raise PermissionError("Only exact independently preserved source packet")
    src=data["source"]
    district=data["district"]
    if (type(src) is not dict or type(district) is not dict or
        district.get("format")!=EVIDENCE or
        src.get("original_world_take_sha256")!=district.get("world_take_sha256") or
        src.get("original_camera_shot_sha256")!=district.get(
            "source_camera_shot_sha256") or
        src.get("source_usd_sha256")!=district.get("derived_usd_sha256") or
        type(district.get("district_render_meshes")) is not int or
        district["district_render_meshes"]<1 or
        type(district.get("original_actor_source_paths")) is not list or
        not district["original_actor_source_paths"] or
        district.get("actual_cycles_png_rendered") is not False):
        raise PermissionError("Bound original district / frozen performer evidence invalid")
    original=root/"scene.blend"
    if original.is_symlink() or not original.is_file() or (
            digest(original)!=data["source_blend_sha256"]):
        raise RuntimeError("Saved original district film scene was replaced")
    scene=bpy.context.scene
    if (scene.render.engine!="CYCLES" or
        scene.get("nvp_original_world_take_sha256")!=district[
            "world_take_sha256"] or
        scene.get("nvp_original_camera_shot_sha256")!=district[
            "source_camera_shot_sha256"] or
        scene.get("nvp_source_usd_sha256")!=district["derived_usd_sha256"] or
        scene.get("nvp_original_film_tick")!=district["source_film_tick"] or
        scene.camera is None or scene.camera.type!="CAMERA"):
        raise RuntimeError("Original source Take/camera missing in saved Cycles scene")
    imported=list(scene.objects)
    object_names={o.name.split(".")[0] for o in imported}
    actor_roots={a["source_prim"].split("/")[-1]
                 for a in src["actor_sources"]}
    if not actor_roots.issubset(object_names):
        raise RuntimeError("Frozen performer ActorID source objects did not reopen")
    camera_name=district["source_camera_path"].split("/")[-1]
    if camera_name not in object_names:
        raise RuntimeError("Original authored camera was substituted")
    real_meshes=[o for o in imported if o.type=="MESH" and
                 len(o.data.vertices)>=3 and len(o.data.polygons)>=1]
    if len(real_meshes)<district["district_render_meshes"]:
        raise RuntimeError("Saved scene lacks native source building geometry")
    actual_pbr=0
    for obj in real_meshes:
        if any(slot.material is not None and slot.material.use_nodes and
            slot.material.node_tree is not None and
            any(node.type=="BSDF_PRINCIPLED" for node in
                slot.material.node_tree.nodes)
               for slot in obj.material_slots):
            actual_pbr+=1
    if actual_pbr<district["district_render_bound_materials"]:
        raise RuntimeError("Saved original source district lost real PBR geometry")
    # The native USD imported building root must remain recognizable in
    # Blender; actor meshes cannot be miscounted as an original district.
    if (not any(name.startswith(("Generated_","Director_"))
                for name in object_names) or
        not district["source_district_point_instancer_not_rewritten"]):
        raise RuntimeError("No native source-approved building root in saved scene")
    proof={
        "format":FORMAT,"passed":True,
        "source_blend_sha256":digest(original),
        "world_take_sha256":district["world_take_sha256"],
        "source_usd_sha256":district["derived_usd_sha256"],
        "district_document_sha256":district["district_document_sha256"],
        "native_saved_scene_blender_version":bpy.app.version_string,
        "actor_count":len(actor_roots),
        "imported_native_meshes":len(real_meshes),
        "actual_imported_principled_meshes":actual_pbr,
        "source_district_meshes_expected":district["district_render_meshes"],
        "actual_saved_source_district_meshes_verified":True,
        "source_actor_camera_unchanged":True,
        "native_film_frame_was_rendered_in_first_worker":True,
        "new_performance_or_pcm_generated":False,
        "director_approved_film_master":False}
    audit.write_text(json.dumps(
        proof,sort_keys=True,separators=(",",":"),allow_nan=False),"utf8")


if __name__=="__main__":
    main()
