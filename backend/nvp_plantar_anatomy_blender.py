"""PROD06E2C3B: independent Blender observation of externally annotated plantar vertices.

Never auto-labels mesh vertices. The annotation packet must have a separate
source-evidence file with exact bytes and SHA, a distinct reviewer, and the
corresponding already approved actor and IK. This is read-only geometry audit.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from backend.nvp_w1g_legacy_blender_launch import run_trusted_blender
from pathlib import Path

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_plantar_landmarks import FootAnatomyAttachment, analyze_imported_landmarks
from backend.nvp_production_scene import compact,digest


ANATOMY_ATTACHMENT_NATIVE = r'''import bpy,sys,json,math
from pathlib import Path
from mathutils import Vector
argv=sys.argv[sys.argv.index("--")+1:]
opts=dict(zip(argv[::2],argv[1::2]))
bundle=json.loads(Path(opts["--source"]).read_text("utf8"))
pkg=bundle["package"];annot=bundle["annotation"];sc=bpy.context.scene
if (sc.get("nvp_footlock_approval_sha")!=pkg["foot_lock"]["approval_sha"] or
    sc.get("nvp_plantar_correction_sha")!=pkg["plantar_correction"]["approval_sha"] or
    sc.get("nvp_leg_identity_approval_sha")!=pkg["leg_identity"]["approval_sha"]):
    raise RuntimeError("Saved .blend is not the approved character animation")
shot=min(int(s["start_frame"]) for s in pkg["take"]["shots"])
sc.frame_set(shot);bpy.context.view_layer.update()
report={"format":"nvp.foot.attachment.observation.v1",
        "annotation_sha":bundle["annotation_sha"],
        "leg_identity_sha":pkg["leg_identity"]["approval_sha"],
        "correction_sha":pkg["plantar_correction"]["approval_sha"],
        "blender_version":bpy.app.version_string,"actors":{}}
for rid,sides in annot["actors"].items():
    character=next((a for a in pkg["leg_identity"]["actors"] if a["instance_id"]==rid),None)
    if character is None:raise RuntimeError("Alien source actor in anatomy attachment")
    rig=bpy.data.objects.get("NVP_CHARACTER_RIG_"+rid)
    if (rig is None or rig.type!="ARMATURE" or
        rig.get("nvp_character_sha")!=character["asset_sha256"]):
        raise RuntimeError("Source humanoid mismatch")
    observed={}
    for side,selection in sides.items():
        obj=bpy.data.objects.get(selection["mesh_name"])
        if (obj is None or obj.type!="MESH" or obj.get("nvp_character_actor")!=rid or
            not any(mod.type=="ARMATURE" and mod.object==rig for mod in obj.modifiers)):
            raise RuntimeError("Anatomy labels refer to unapproved or non-skinned geometry")
        bones=character["mapping"][side]
        if any(name not in rig.pose.bones for name in bones.values()):
            raise RuntimeError("Referenced original anatomical chain unavailable")
        groups={g.index for g in obj.vertex_groups
                if g.name in (bones["ankle"],bones["toe"])}
        if len(groups)!=2:raise RuntimeError("No genuine source side foot deformation groups")
        ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh=ev.to_mesh()
        try:
            if len(mesh.vertices)!=len(obj.data.vertices) or len(mesh.vertices)>250000:
                raise RuntimeError("Skin deformation cannot preserve source anatomy vertex IDs")
            normal_mat=ev.matrix_world.to_3x3().inverted().transposed()
            verts={}
            for label,index in selection["vertex_indices"].items():
                if index>=len(mesh.vertices):raise RuntimeError("Anatomy vertex out of imported source topology")
                weight=sum(x.weight for x in obj.data.vertices[index].groups if x.group in groups)
                if weight<.25:raise RuntimeError("Anatomy point is not on the approved side's deforming foot")
                v=mesh.vertices[index]
                loc=ev.matrix_world@v.co
                normal=(normal_mat@v.normal).normalized()
                if not all(math.isfinite(x) for x in tuple(loc)+tuple(normal)):
                    raise RuntimeError("Nonfinite evaluated anatomical surface position or normal")
                verts[label]={"position_world_m":[float(x) for x in loc],
                              "normal_world":[float(x) for x in normal]}
        finally:ev.to_mesh_clear()
        observed[side]={"ankle_world_m":[float(x) for x in rig.matrix_world@rig.pose.bones[bones["ankle"]].head],
                        "toe_joint_world_m":[float(x) for x in rig.matrix_world@rig.pose.bones[bones["toe"]].head],
                        "points":verts}
    report["actors"][rid]={"asset_sha256":character["asset_sha256"],"sides":observed}
Path(opts["--result"]).write_text(json.dumps(report,indent=2,sort_keys=True),"utf8")
'''


def inspect_imported_anatomy(service:FootAnatomyAttachment,pid,sid,
                             source_blend,reference_file,directory,*,blender="blender",timeout=240):
    """Require actual supplied reviewed evidence *bytes* and Blender audit.

    The host checks source bytes; the native process checks imported mesh
    identity and plausible geometry. Neither establishes medical credentials.
    """
    pkg,upstream=service._context(pid,sid)
    row=service.read(pid,sid)
    if row["stale"] or row["status"]!="draft" or not row["attachment"]:
        raise RuntimeError("Only current annotated foot draft can be inspected")
    reference=Path(reference_file).resolve()
    if not reference.is_file() or reference.stat().st_size>8*1024*1024:
        raise ValueError("Real independent foot anatomy reference file is required, <=8 MiB")
    raw=reference.read_bytes()
    evidence_sha=hashlib.sha256(raw).hexdigest()
    if evidence_sha!=row["attachment"]["evidence"]["reference_sha256"]:
        raise ValueError("Foot anatomy reference does not match approved evidence bytes")
    if b'\x00' in raw:
        raise ValueError("Anatomy reference must be a reviewable text document")
    source=Path(source_blend).resolve()
    if not source.is_file() or source.suffix.lower()!=".blend":
        raise ValueError("Saved approved corrected real Blender human is required")
    exe=blender_available(blender)
    if not exe["available"]:
        return {"status":"blocked_no_blender","reason":exe["reason"]}
    out=Path(directory).resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=out/"anatomy_source.json";script=out/"inspect_reviewed_anatomy.py"
    report_path=out/"native_anatomy_points.json";report_path.unlink(missing_ok=True)
    manifest.write_text(compact({"package":pkg,"annotation":row["attachment"],
                                 "annotation_sha":digest(row["attachment"])}),"utf8")
    script.write_text(ANATOMY_ATTACHMENT_NATIVE,"utf8")
    cmd=[exe["path"],"-b",str(source),"-t","2","--python-exit-code","30",
         "--python",str(script),"--","--source",str(manifest),"--result",str(report_path)]
    try:r=run_trusted_blender(cmd,cwd=out,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:return {"status":"failed","reason":"Native anatomy survey timed out"}
    if r.returncode or not report_path.is_file():
        return {"status":"failed","reason":"External Blender imported foot anatomy inspection refused",
                "returncode":r.returncode,"stderr":r.stderr[-2000:],"stdout":r.stdout[-1600:]}
    native=json.loads(report_path.read_text("utf8"))
    # Double check upstream identity after external process, not just at start.
    _,after=service._context(pid,sid)
    if upstream!=after or row["revision"]!=service.read(pid,sid)["revision"]:
        raise RuntimeError("Anatomy/source changed during native inspection")
    examined=analyze_imported_landmarks(native,row["attachment"],pkg)
    result=service.attest_imported_geometry(pid,sid,native,row["revision"])
    return {"status":"passed_reviewed_landmark_geometry_only",
            "annotation_sha":digest(row["attachment"]),
            "native_report_sha":digest(native),
            "geometry_sha":digest(examined),
            "revision":result["revision"],
            "clinical_anatomy_certified":False,
            "source_rights_cleared_for_distribution":False,
            "directory":str(out)}
