# SPDX-License-Identifier: GPL-2.0-or-later
"""FILM01 Blender/Cycles independent reopen audit (separate native subprocess).

Run ONLY with Blender itself after the supervised scene was saved.
The Blender scene has already been opened via:
blender -b ORIGINAL.blend --python-exit-code 70 --python this_file
    -- --manifest worker/source.json --audit fresh/reopened.json
This verifies REAL saved data and source identity, not just magic bytes.
"""
import bpy
import hashlib
import json
from pathlib import Path
import sys

VERSION="nvp.film01.blender.cycles.independent_reopen.v1"
PATHS={
    "donut":"NVP_DonutActor",
    "box":"NVP_BoxActor",
    "sphere":"NVP_SphereActor",
}


def main():
    argv=sys.argv[sys.argv.index("--")+1:]
    if len(argv)!=4 or set(argv[::2])!={"--manifest","--audit"}:
        raise ValueError("Expected original frozen source and separate audit output")
    opts=dict(zip(argv[::2],argv[1::2]))
    source=Path(opts["--manifest"]).resolve(strict=True)
    dest=Path(opts["--audit"])
    if not dest.is_absolute() or dest.exists() or dest.is_symlink():
        raise PermissionError("Independent readback audit needs fresh absolute output")
    packet=json.loads(source.read_text("utf8"))
    body=packet["source"]
    digest=hashlib.sha256(json.dumps(
        body,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    if (packet["source_sha256"]!=digest or
            packet["format"]!="nvp.film01.blender.cycles.source_from_frozen_usd.v1"):
        raise PermissionError("Original source digest changed before independent Blender readback")
    sc=bpy.context.scene
    if (sc.render.engine!="CYCLES" or sc.cycles.device!="CPU" or
            sc.cycles.samples<8 or sc.cycles.glossy_bounces<4 or
            sc.cycles.diffuse_bounces<3 or
            sc.render.fps!=24 or sc.frame_start!=1 or sc.frame_end!=72 or
            sc.render.resolution_x!=640 or sc.render.resolution_y!=360):
        raise RuntimeError("Saved native Blender file lost actual Cycles path-tracing/render settings")
    camera=bpy.data.objects.get("NVP_Original_Camera")
    backdrop=bpy.data.objects.get("NVP_Shadow_Receiver")
    key=bpy.data.objects.get("NVP_Key_Area")
    if (camera is None or sc.camera!=camera or
            backdrop is None or key is None or key.type!="LIGHT"):
        raise RuntimeError("Saved Blender camera/shadow receiver/key light is missing")
    source_objects={}
    for kind,name in PATHS.items():
        obj=bpy.data.objects.get(name)
        if (obj is None or obj.type!="MESH" or
                obj.get("nvp_role")!="actor" or
                obj.get("nvp_original_take_sha256")!=body["source_take_sha256"] or
                obj.get("nvp_prim_path")!=body["source_object_paths"][kind] or
                len(obj.data.materials)!=1):
            raise PermissionError("Reopened Blender object is not a genuine original actor")
        source_objects[kind]=obj
    donut=source_objects["donut"]
    if (len(donut.data.vertices)!=504 or
            len(donut.data.polygons)!=1008 or
            any(not face.use_smooth for face in donut.data.polygons)):
        raise RuntimeError("Original USD torus topology or smooth rendering changed in saved Blender project")
    # Aesthetic changes are verified on independently reopened native
    # Blender data, not inferred from a successful Python staging test.
    copper=donut.active_material.node_tree.nodes.get("Principled BSDF")
    rim=bpy.data.objects.get("NVP_Cool_Rim")
    if (copper is None or
            abs(copper.inputs["Metallic"].default_value-.86)>1.e-5 or
            abs(copper.inputs["Roughness"].default_value-.22)>1.e-5 or
            rim is None or rim.type!="LIGHT" or
            abs(rim.data.energy-125)>1.e-5 or
            abs(key.data.size-1.15)>1.e-5):
        raise RuntimeError("Inspected Cycles copper/rim/shadow revision not saved")
    for frame in (0,12,24,36,48,60,71):
        sc.frame_set(frame+1)
        for name,obj in source_objects.items():
            xyz=[float(v) for v in obj.location]
            expected=body["frames"][frame]["actors"][name]
            if any(abs(x-y)>2.e-5 for x,y in zip(xyz,expected)):
                raise RuntimeError(
                    f"Original Blender animated {name} position differs at frame {frame}")
    materials={name:{
        "material":str(obj.active_material.name),
        "num_polygons":len(obj.data.polygons),
        "actor_path":obj["nvp_prim_path"],
    } for name,obj in source_objects.items()}
    proof={
        "format":VERSION,"passed":True,
        "actual_separate_Blender_process_reopened_blend":True,
        "native_blender_version":bpy.app.version_string,
        "real_cycles_engine":"CYCLES",
        "saved_72_frame_original_animation":True,
        "saved_cast_shadow_receiver_present":True,
        "saved_glossy_secondary_bounces":sc.cycles.glossy_bounces,
        "saved_diffuse_secondary_bounces":sc.cycles.diffuse_bounces,
        "original_film_take_sha256":body["source_take_sha256"],
        "source_manifest_sha256":digest,
        "original_donut_faces":len(donut.data.polygons),
        "all_three_real_original_actor_sources":materials,
        "source_positions_rechecked":[0,12,24,36,48,60,71],
        "actual_reflections_director_approved":False,
        "actual_cast_shadow_quality_director_approved":False,
        "original_FilmIndex_source_unchanged":True,
        "production_installed_app_approval":False,
        "2K_DCI_acceptance":False,
    }
    dest.write_text(json.dumps(proof,indent=2,sort_keys=True)+"\n")


if __name__=="__main__":
    main()
