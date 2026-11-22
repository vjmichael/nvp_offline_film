"""Blender bake and independent reopen verification for PROD-06E2C3.

The anatomical sample/mesh marker plans are approved separately. This worker
touches only imported thigh and shin pose keys, saving a NEW Blender file.
All approval receipts, actual evaluated skinned vertices and real NVP_FLOOR
geometry are rechecked. This does NOT certify plantar anatomy or locomotion.
"""
from __future__ import annotations

import json
import math
import subprocess
from backend.nvp_w1g_legacy_blender_launch import run_trusted_blender
from pathlib import Path

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_plantar import run_native_plantar_audit
from backend.nvp_plantar_correction import PlantarCorrectionPlan
from backend.nvp_production_scene import compact, digest


PLANTAR_CORRECTION_BUILD = r'''import bpy,sys,json,math,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
argv=sys.argv[sys.argv.index("--")+1:]
opts=dict(zip(argv[::2],argv[1::2]))
pkg=json.loads(Path(opts["--package"]).read_text("utf8"))
sc=bpy.context.scene
corr=pkg["plantar_correction"]; plantar=pkg["plantar"]; lock=pkg["foot_lock"]
identity=pkg["leg_identity"]
if corr["format"]!="nvp.plantar.correction.approved.v1" or plantar["format"]!="nvp.plantar.approved.v1":
    raise RuntimeError("Missing approved corrective and plantar plans")
if (sc.get("nvp_footlock_approval_sha")!=lock["approval_sha"] or
    sc.get("nvp_leg_identity_approval_sha")!=identity["approval_sha"] or
    sc.get("nvp_retarget_approval_sha")!=pkg["retarget"]["approval_sha"]):
    raise RuntimeError("Source stage approval is stale or unrelated")
end=max(int(shot["stop_frame"])-1 for shot in pkg["take"]["shots"])
if end<1 or end>2400:raise RuntimeError("Take too long for bounded contact pass")
floor=bpy.data.objects.get(plantar["plan"]["surface"]["object_name"])
if floor is None or floor.type!="MESH" or floor.get("nvp_proxy")!=True:
    raise RuntimeError("Missing real supported NVP floor")
points=sorted(tuple(round(float(v),7) for v in floor.matrix_world@v.co)
              for v in floor.data.vertices)
data=json.dumps(points,sort_keys=True,separators=(",",":"),allow_nan=False)
if hashlib.sha256(data.encode("utf8")).hexdigest()!=plantar["plan"]["surface"]["geometry_sha256"]:
    raise RuntimeError("Floor mesh/transform altered since marker approval")
if len(points)!=8:raise RuntimeError("Only approved level rectangular floor supported")
floor_z=max(p[2] for p in points)
if sum(abs(p[2]-floor_z)<.0001 for p in points)!=4:
    raise RuntimeError("Floor does not have a level upper surface")
bounds=(min(p[0] for p in points),max(p[0] for p in points),
        min(p[1] for p in points),max(p[1] for p in points))
def valid_xy(p):
    return bounds[0]-1e-6<=p.x<=bounds[1]+1e-6 and bounds[2]-1e-6<=p.y<=bounds[3]+1e-6
def solve(hip,ankle,pole,upper,lower):
    direct=ankle-hip;distance=direct.length
    if (distance<1e-7 or distance>=upper+lower-1e-7 or
        distance<=abs(upper-lower)+1e-7):
        raise RuntimeError("Anatomical IK target is unreachable or singular")
    direct.normalize()
    projection=(upper*upper-lower*lower+distance*distance)/(2*distance)
    radius=upper*upper-projection*projection
    if radius<=1e-13:raise RuntimeError("Knee bend radius is degenerate")
    ortho=(pole-hip)-direct*((pole-hip).dot(direct))
    if ortho.length<1e-7:raise RuntimeError("Knee bend pole is collinear")
    return hip+direct*projection+ortho.normalized()*math.sqrt(radius)
def turn_bone(pbone,child,point):
    bpy.context.view_layer.update()
    center=pbone.head.copy()
    source=child.head.copy()-center;desired=point-center
    if source.length<1e-7 or desired.length<1e-7 or abs(source.length-desired.length)>.002:
        raise RuntimeError("Unsafe limb rotation would change segment length")
    q=source.rotation_difference(desired)
    start=pbone.matrix.copy()
    pbone.matrix=Matrix.Translation(center)@q.to_matrix().to_4x4()@Matrix.Translation(-center)@start
    bpy.context.view_layer.update()
def vertical_correction(gaps,penetration,max_gap,limit,target):
    if not gaps:raise RuntimeError("No active foot marker for ground contact")
    low=max([-limit]+[-penetration-g for g in gaps])
    high=min([limit]+[max_gap-g for g in gaps])
    if low>high+1e-9:
        raise RuntimeError("Heel/ball/toe surface geometry cannot fit the contact plane under approved movement budget")
    desired=target-sum(gaps)/len(gaps)
    return max(low,min(high,desired))
def geom_points(obj,markers):
    deps=bpy.context.evaluated_depsgraph_get()
    ev=obj.evaluated_get(deps);mesh=ev.to_mesh()
    try:
        if len(obj.data.vertices)!=len(mesh.vertices):
            raise RuntimeError("Altered skinned geometry topology")
        return {role:ev.matrix_world@mesh.vertices[index].co
                for role,index in markers.items()}
    finally:ev.to_mesh_clear()
# Pre-sample the whole original take before introducing correction keys.
# Interpolation of previously inserted keys must not be treated as baseline.
stored={}
for rid in corr["plan"]["actors"]:
    rig=bpy.data.objects.get("NVP_CHARACTER_RIG_"+rid)
    character=next((x for x in identity["actors"] if x["instance_id"]==rid),None)
    if (character is None or rig is None or rig.type!="ARMATURE" or
        rig.get("nvp_character_sha")!=character["asset_sha256"] or
        rig.get("nvp_retarget_approval_sha")!=pkg["retarget"]["approval_sha"]):
        raise RuntimeError("Approved character source/retarget not present")
    actor=bpy.data.objects.get("NVP_"+rid)
    if rig.parent!=actor:raise RuntimeError("Approved actor hierarchy missing")
    record={}
    for side in ("left","right"):
        cfg=plantar["plan"]["actors"][rid][side]
        obj=bpy.data.objects.get(cfg["mesh_name"])
        if (obj is None or obj.type!="MESH" or obj.get("nvp_character_actor")!=rid or
            not any(m.type=="ARMATURE" and m.object==rig for m in obj.modifiers)):
            raise RuntimeError("Selected plantar markers not bound to approved external mesh")
        if len(obj.data.vertices)>250000:raise RuntimeError("Oversized source geometry")
        bones=character["mapping"][side]
        if any(n not in rig.pose.bones for n in bones.values()):
            raise RuntimeError("Source imported bone missing")
        if any(rig.pose.bones[bones[a]].parent!=rig.pose.bones[bones[b]]
               for a,b in (("knee","hip"),("ankle","knee"),("toe","ankle"))):
            raise RuntimeError("Anatomy hierarchy changed after approval")
        groups={g.index for g in obj.vertex_groups
                if g.name in (bones["ankle"],bones["toe"])}
        if len(groups)!=2:raise RuntimeError("Missing exact ankle/toe skin influence")
        for role,i in cfg["markers"].items():
            if i>=len(obj.data.vertices):
                raise RuntimeError("Unresolved creator-selected plantar mesh vertex")
            weight=sum(x.weight for x in obj.data.vertices[i].groups if x.group in groups)
            if weight<.25:raise RuntimeError("Plantar source vertex lacks approved foot weights")
        record[side]={"mesh":obj,"mapping":bones}
    frames={}
    for frame in range(1,end+1):
        sc.frame_set(frame);bpy.context.view_layer.update()
        data={}
        for side in ("left","right"):
            chain=record[side]["mapping"]
            data[side]={part:list(rig.pose.bones[chain[part]].rotation_quaternion)
                        for part in ("hip","knee")}
        frames[frame]=data
    stored[rid]={"rig":rig,"actor":actor,"frames":frames,"sides":record}
build={"format":"nvp.plantar.correction.bake.v1",
       "approval_sha":corr["approval_sha"],"plantar_sha":plantar["approval_sha"],
       "foot_lock_sha":lock["approval_sha"],"floor_sha":plantar["plan"]["surface"]["geometry_sha256"],
       "frames":end,"actors":{}}
for rid, settings in corr["plan"]["actors"].items():
    bundle=stored[rid];rig=bundle["rig"];actor=bundle["actor"]
    artist=plantar["plan"]["actors"][rid]
    original=next(x for x in lock["actors"] if x["instance_id"]==rid)
    contact={side:{n for a,b in original["config"][side]["contact_windows"]
                   for n in range(a,b+1)} for side in ("left","right")}
    if any(not frames for frames in contact.values()):
        raise RuntimeError("Both sides require authored stance windows")
    moves={"left":[],"right":[]}
    for frame in range(1,end+1):
        sc.frame_set(frame);bpy.context.view_layer.update()
        for side in ("left","right"):
            chain=bundle["sides"][side]["mapping"]
            for part in ("hip","knee"):
                pose=rig.pose.bones[chain[part]]
                pose.rotation_mode="QUATERNION"
                pose.rotation_quaternion=tuple(bundle["frames"][frame][side][part])
        bpy.context.view_layer.update()
        for side in ("left","right"):
            if frame not in contact[side]:continue
            src=bundle["sides"][side];mesh=src["mesh"];chain=src["mapping"]
            names=artist[side];roles=names["contact_roles"]
            original_ankle=(rig.matrix_world@rig.pose.bones[chain["ankle"]].head).copy()
            initial_rots={part:rig.pose.bones[chain[part]].rotation_quaternion.copy()
                          for part in ("hip","knee")}
            for iteration in range(settings["max_iterations"]):
                bpy.context.view_layer.update()
                positions=geom_points(mesh,names["markers"])
                active={role:positions[role] for role in roles}
                if any(not valid_xy(pos) for pos in active.values()):
                    raise RuntimeError("Contact point lies outside approved floor support")
                gaps=[float(pos.z-floor_z) for pos in active.values()]
                if all(-artist["max_penetration_m"]-1e-6<=g<=artist["max_gap_m"]+1e-6
                       for g in gaps):
                    break
                moved=(rig.matrix_world@rig.pose.bones[chain["ankle"]].head-original_ankle).length
                remaining=settings["max_ankle_delta_m"]-moved
                if remaining<=1e-6:
                    raise RuntimeError("Foot contact correction budget exhausted")
                delta=vertical_correction(gaps,artist["max_penetration_m"],
                    artist["max_gap_m"],remaining,settings["target_clearance_m"])
                if abs(delta)<1e-7:
                    raise RuntimeError("No meaningful correction possible within bounded ankle movement")
                hip=rig.pose.bones[chain["hip"]]
                knee=rig.pose.bones[chain["knee"]]
                ankle=rig.pose.bones[chain["ankle"]]
                native_hip=hip.head.copy()
                upper=(knee.head-native_hip).length
                lower=(ankle.head-knee.head).length
                ankle_target_world=rig.matrix_world@ankle.head+Vector((0,0,delta))
                ankle_target=rig.matrix_world.inverted()@ankle_target_world
                pole_world=rig.matrix_world@knee.head+actor.matrix_world.to_quaternion()@Vector(
                    original["config"][side]["pole_offset_actor_m"])
                local_pole=rig.matrix_world.inverted()@pole_world
                knee_target=solve(native_hip,ankle_target,local_pole,upper,lower)
                turn_bone(hip,knee,knee_target)
                turn_bone(knee,ankle,ankle_target)
                if (rig.matrix_world@ankle.head-original_ankle).length>settings["max_ankle_delta_m"]+1e-5:
                    raise RuntimeError("Source ankle exceeded approved correction bound")
                for part in ("hip","knee"):
                    rotation=rig.pose.bones[chain[part]].rotation_quaternion
                    ang=math.degrees(rotation.rotation_difference(initial_rots[part]).angle)
                    if ang>settings["max_joint_delta_deg"]+.05:
                        raise RuntimeError("Pose rotation exceeded approved thigh/shin ceiling")
            else:
                raise RuntimeError("Contact mesh failed to reach floor tolerances within bounded iterations")
            # Re-evaluate and validate after convergence, not just the IK ankle.
            positions=geom_points(mesh,names["markers"])
            active={role:positions[role] for role in roles}
            if not all(valid_xy(pos) and
                       -artist["max_penetration_m"]-1e-6 <= float(pos.z-floor_z) <= artist["max_gap_m"]+1e-6
                       for pos in active.values()):
                raise RuntimeError("Evaluated skin foot markers still violate floor bounds")
            moves[side].append({
                "frame":frame,"iterations":iteration,
                "ankle_delta_m":float((rig.matrix_world@rig.pose.bones[chain["ankle"]].head-original_ankle).length),
                "role_clearance_m":{k:float(p.z-floor_z) for k,p in active.items()}})
        # Preserve original noncontact keys by dense rebake.
        for side in ("left","right"):
            chain=bundle["sides"][side]["mapping"]
            for part in ("hip","knee"):
                bone=rig.pose.bones[chain[part]]
                bone.keyframe_insert(data_path="rotation_quaternion",frame=frame,group=bone.name)
    rig["nvp_plantar_correction_sha"]=corr["approval_sha"]
    build["actors"][rid]={"contacts":moves,"original_frames_preserved":end}
sc["nvp_plantar_correction_sha"]=corr["approval_sha"]
sc["nvp_plantar_approval_sha"]=plantar["approval_sha"]
bpy.ops.wm.save_as_mainfile(filepath=str(Path(opts["--output"]).resolve()))
Path(opts["--report"]).write_text(json.dumps(build,indent=2,sort_keys=True),"utf8")
'''


PLANTAR_CORRECTION_SNAPSHOT = r'''import bpy,sys,json,math
from pathlib import Path
argv=sys.argv[sys.argv.index("--")+1:]
opts=dict(zip(argv[::2],argv[1::2]))
pkg=json.loads(Path(opts["--package"]).read_text("utf8"))
sc=bpy.context.scene; identity=pkg["leg_identity"]; lock=pkg["foot_lock"]
mode=opts["--mode"]
if mode not in ("baseline","output"):raise RuntimeError("Snapshot mode unknown")
if (sc.get("nvp_footlock_approval_sha")!=lock["approval_sha"] or
    sc.get("nvp_leg_identity_approval_sha")!=identity["approval_sha"]):
    raise RuntimeError("Saved scene differs from approved ankle-lock source")
if mode=="output":
    if sc.get("nvp_plantar_correction_sha")!=pkg["plantar_correction"]["approval_sha"]:
        raise RuntimeError("Output missing actual correction approval receipt")
else:
    if sc.get("nvp_plantar_correction_sha") is not None:
        raise RuntimeError("Original saved scene is no longer pristine")
end=max(int(s["stop_frame"])-1 for s in pkg["take"]["shots"])
if end<1 or end>2400:raise RuntimeError("Unbounded animation snapshot")
def flat(mat):return [float(v) for row in mat for v in row]
result={"format":"nvp.plantar.correction.snapshot.v1","mode":mode,
        "approved_lock_sha":lock["approval_sha"],
        "approved_correction_sha":pkg["plantar_correction"]["approval_sha"],
        "blender":bpy.app.version_string,
        "cuts":[(mark.frame,mark.camera.name if mark.camera else None)
                for mark in sc.timeline_markers],
        "frames":{}}
for frame in range(1,end+1):
    sc.frame_set(frame);bpy.context.view_layer.update()
    row={"actors":{},"cameras":{}}
    for camera in (o for o in bpy.data.objects if o.type=="CAMERA"):
        row["cameras"][camera.name]={"world":flat(camera.matrix_world),
                                     "lens":float(camera.data.lens)}
    for original in pkg["leg_identity"]["actors"]:
        rid=original["instance_id"]
        rig=bpy.data.objects["NVP_CHARACTER_RIG_"+rid]
        actor=bpy.data.objects["NVP_"+rid]
        if rig.parent!=actor or rig.get("nvp_character_sha")!=original["asset_sha256"]:
            raise RuntimeError("Wrong actor in full take audit")
        legs={}
        for side in ("left","right"):
            names=original["mapping"][side]
            hip=rig.pose.bones[names["hip"]];knee=rig.pose.bones[names["knee"]]
            ankle=rig.pose.bones[names["ankle"]]
            legs[side]={"hip_rotation":[float(v) for v in hip.rotation_quaternion],
                        "knee_rotation":[float(v) for v in knee.rotation_quaternion],
                        "upper_local_m":float((knee.head-hip.head).length),
                        "lower_local_m":float((ankle.head-knee.head).length)}
        row["actors"][rid]={"root":flat(actor.matrix_world),
                            "rig":flat(rig.matrix_world),"legs":legs}
    result["frames"][str(frame)]=row
Path(opts["--report"]).write_text(json.dumps(result,sort_keys=True,indent=2),"utf8")
'''


def _distance(a,b):
    if len(a)!=len(b):
        raise ValueError("Mismatched numeric snapshot widths")
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in list(a)+list(b)):
        raise ValueError("Nonfinite native geometry/pose value")
    return max(abs(x-y) for x,y in zip(a,b))


def compare_correction_audits(before,after,bake,package,before_plantar,after_plantar):
    """Independent host decision: true contact, preserved rest of film."""
    correction=package["plantar_correction"]
    if (before.get("format")!="nvp.plantar.correction.snapshot.v1" or
        after.get("format")!="nvp.plantar.correction.snapshot.v1" or
        before.get("mode")!="baseline" or after.get("mode")!="output" or
        bake.get("format")!="nvp.plantar.correction.bake.v1" or
        bake.get("approval_sha")!=correction["approval_sha"] or
        before.get("approved_lock_sha")!=package["foot_lock"]["approval_sha"] or
        after.get("approved_lock_sha")!=package["foot_lock"]["approval_sha"] or
        before.get("approved_correction_sha")!=correction["approval_sha"] or
        after.get("approved_correction_sha")!=correction["approval_sha"]):
        raise ValueError("Native independent audit/source identity mismatch")
    if before["cuts"]!=after["cuts"] or before["frames"].keys()!=after["frames"].keys():
        raise RuntimeError("Approved cut markers or full animation frame range changed")
    if before_plantar.get("approved_plantar_sha")!=package["plantar"]["approval_sha"] or after_plantar.get("approved_plantar_sha")!=package["plantar"]["approval_sha"]:
        raise ValueError("Actual skinned marker audit belongs to another approved source")
    if not after_plantar["contact_meets_configured_tolerances"]:
        raise RuntimeError("Native corrected mesh markers still violate authored floor contact tolerances")
    protected=0;inside=0;changed=0;max_segment=0;max_delta=0
    original_authored={x["instance_id"]:x for x in package["foot_lock"]["actors"]}
    for key in before["frames"]:
        one=before["frames"][key];two=after["frames"][key]
        if set(one["cameras"])!=set(two["cameras"]) or set(one["actors"])!=set(two["actors"]):
            raise RuntimeError("Scene camera/actor roster changed")
        for name in one["cameras"]:
            if (_distance(one["cameras"][name]["world"],two["cameras"][name]["world"])>1e-5 or
                abs(one["cameras"][name]["lens"]-two["cameras"][name]["lens"])>1e-6):
                raise RuntimeError("Camera movement or optics changed during correction")
        for rid in one["actors"]:
            src=one["actors"][rid];dst=two["actors"][rid]
            if _distance(src["root"],dst["root"])>1e-5 or _distance(src["rig"],dst["rig"])>1e-5:
                raise RuntimeError("Actor root/visual rig changed instead of articulated leg")
            for side in ("left","right"):
                leg1=src["legs"][side];leg2=dst["legs"][side]
                for part in ("upper_local_m","lower_local_m"):
                    err=abs(leg1[part]-leg2[part])
                    max_segment=max(max_segment,err)
                    if err>1e-4:raise RuntimeError("Correction stretched a native bone")
                stance=any(a<=int(key)<=b for a,b in
                    original_authored[rid]["config"][side]["contact_windows"])
                delta=max(_distance(leg1[f"{joint}_rotation"],leg2[f"{joint}_rotation"])
                          for joint in ("hip","knee"))
                max_delta=max(max_delta,delta)
                if not stance:
                    protected+=1
                    if delta>1e-4:
                        raise RuntimeError("Previously approved noncontact pose changed")
                else:
                    inside+=1
                    if delta>1e-5:changed+=1
    if not inside or not changed:
        raise RuntimeError("No real permitted contact pose adjustment demonstrated")
    return {"status":"passed_native_marker_floor_correction_only",
            "source_plantar_contact":before_plantar["contact_meets_configured_tolerances"],
            "corrected_marker_contact":after_plantar["contact_meets_configured_tolerances"],
            "anatomical_sole_certified":False,"gait_dynamics_verified":False,
            "protected_noncontact_leg_frames":protected,
            "changed_contact_leg_frames":changed,
            "max_segment_delta_m":max_segment,
            "max_pose_quat_component_delta":max_delta,
            "full_take_frames":len(before["frames"]),
            "source_plantar_sha":package["plantar"]["approval_sha"],
            "correction_approval_sha":correction["approval_sha"],
            "limitations":"Vertex-only static floor contact measured. Anatomical heel/ball verification, whole mesh collisions, dynamics and moving root unverified"}


def run_native_marker_correction(service:PlantarCorrectionPlan,pid,sid,
                                 baseline_blend,directory,*,blender="blender",timeout=240):
    """Five independent native runs: baseline survey, bake, reopen, compare."""
    pkg=service.export(pid,sid)
    probe=blender_available(blender)
    if not probe["available"]:
        return {"status":"blocked_no_blender","reason":probe["reason"]}
    baseline_blend=Path(baseline_blend).resolve()
    if not baseline_blend.is_file() or baseline_blend.suffix.lower()!=".blend":
        raise FileNotFoundError("Approved real Blender ankle-lock baseline missing")
    out=Path(directory).resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=out/"correction_package.json";manifest.write_text(compact(pkg),"utf8")
    (out/"apply_plantar_correction.py").write_text(PLANTAR_CORRECTION_BUILD,"utf8")
    (out/"snapshot_plantar_correction.py").write_text(PLANTAR_CORRECTION_SNAPSHOT,"utf8")
    repaired=out/"corrected_contact.blend";repaired.unlink(missing_ok=True)
    native_report=out/"correction_bake.json"
    native_report.unlink(missing_ok=True)
    before_path=out/"pristine_full_take.json";after_path=out/"corrected_full_take.json"
    for p in (before_path,after_path):p.unlink(missing_ok=True)
    commands=[
        [probe["path"],"-b",str(baseline_blend),"-t","2","--python-exit-code","30",
         "--python",str(out/"snapshot_plantar_correction.py"),"--","--mode","baseline",
         "--package",str(manifest),"--report",str(before_path)],
        [probe["path"],"-b",str(baseline_blend),"-t","2","--python-exit-code","30",
         "--python",str(out/"apply_plantar_correction.py"),"--",
         "--package",str(manifest),"--report",str(native_report),"--output",str(repaired)],
        [probe["path"],"-b",str(repaired),"-t","2","--python-exit-code","30",
         "--python",str(out/"snapshot_plantar_correction.py"),"--","--mode","output",
         "--package",str(manifest),"--report",str(after_path)]]
    before=run_native_plantar_audit(service.plantar,pid,sid,baseline_blend,
                                    out/"before_plantar_marker_audit",blender=blender)
    if before.get("status")!="passed_native_plantar_floor_measurement_only":
        return {"status":"failed","step":"before_marker_audit","details":before}
    logs=[]
    for step,cmd in enumerate(commands,1):
        try:ret=run_trusted_blender(cmd,capture_output=True,text=True,cwd=out,timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status":"failed","step":step,"reason":"Native contact correction timed out"}
        logs.append({"step":step,"exit_code":ret.returncode,
                     "stderr":ret.stderr[-2600:],"stdout":ret.stdout[-2600:]})
        if ret.returncode:
            return {"status":"failed","step":step,"reason":"Native contact correction/refusal",
                    "attempts":logs}
    after=run_native_plantar_audit(service.plantar,pid,sid,repaired,
                                   out/"after_plantar_marker_audit",blender=blender)
    if after.get("status")!="passed_native_plantar_floor_measurement_only":
        return {"status":"failed","step":"after_marker_audit","details":after}
    if any(not p.is_file() for p in (repaired,native_report,before_path,after_path)):
        return {"status":"failed","reason":"Missing expected native proof artifact"}
    # Do not claim completion if the director changed any approval mid-process.
    if digest(service.export(pid,sid)["plantar_correction"])!=digest(pkg["plantar_correction"]):
        raise RuntimeError("Approved contact correction changed while Blender executed")
    verified=compare_correction_audits(
        json.loads(before_path.read_text("utf8")),
        json.loads(after_path.read_text("utf8")),
        json.loads(native_report.read_text("utf8")),pkg,
        before["audit"],after["audit"])
    verified.update({"real_blender_version":probe["version"],
                     "output_blend":str(repaired),
                     "before_marker_audit":str(out/"before_plantar_marker_audit"),
                     "after_marker_audit":str(out/"after_plantar_marker_audit"),
                     "pristine_full_take_audit":str(before_path),
                     "modified_full_take_audit":str(after_path)})
    (out/"verified_marker_contact_result.json").write_text(json.dumps(verified,indent=2,sort_keys=True),"utf8")
    return verified
