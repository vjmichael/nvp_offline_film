"""NVP PROD06E2C3B: bounded triangle-BVH surface support measurements.

Uses Blender 5.2's documented Mesh.calc_loop_triangles and
BVHTree.FromPolygons. All ray casting occurs in world coordinates. Report
claims geometry query correctness and marker clearance only, not friction,
center-of-pressure, plantar anatomy, closed-mesh containment or dynamics.
"""
from __future__ import annotations
import json
import math
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
from pathlib import Path

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_plantar_correction import PlantarCorrectionPlan
from backend.nvp_production_scene import compact,digest


NATIVE_BVH_SURFACE_SCRIPT = r'''import bpy,sys,json,math,hashlib
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from pathlib import Path
argv=sys.argv[sys.argv.index("--")+1:]
opts=dict(zip(argv[::2],argv[1::2]))
pkg=json.loads(Path(opts["--manifest"]).read_text("utf8"))
sc=bpy.context.scene
if sc.get("nvp_plantar_correction_sha")!=pkg["plantar_correction"]["approval_sha"]:
    raise RuntimeError("Not the independently corrected native Blender character")
if sc.get("nvp_footlock_approval_sha")!=pkg["foot_lock"]["approval_sha"]:
    raise RuntimeError("Approved original ankle lock missing")
if sc.get("nvp_leg_identity_approval_sha")!=pkg["leg_identity"]["approval_sha"]:
    raise RuntimeError("Approved anatomical rig mapping missing")
floor_name=pkg["plantar"]["plan"]["surface"]["object_name"]
floor=bpy.data.objects.get(floor_name)
if floor is None or floor.type!="MESH" or not floor.get("nvp_proxy"):
    raise RuntimeError("Missing actual approved floor surface")
def source_floor_hash(obj):
    positions=sorted(tuple(round(float(x),7) for x in obj.matrix_world@v.co)
                     for v in obj.data.vertices)
    payload=json.dumps(positions,sort_keys=True,separators=(",",":"),allow_nan=False)
    return hashlib.sha256(payload.encode("utf8")).hexdigest()
if source_floor_hash(floor)!=pkg["plantar"]["plan"]["surface"]["geometry_sha256"]:
    raise RuntimeError("Floor object/transform changed since director plantar approval")
def build_bvh(obj):
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh=evaluated.to_mesh()
    try:
        if not 3<=len(mesh.vertices)<=100000 or not 1<=len(mesh.polygons)<=100000:
            raise RuntimeError("Unsupported empty/oversized support geometry")
        mesh.calc_loop_triangles()
        triangles=[tuple(int(i) for i in tri.vertices) for tri in mesh.loop_triangles]
        verts=[tuple(float(x) for x in evaluated.matrix_world@v.co) for v in mesh.vertices]
        if not triangles or any(not all(math.isfinite(x) for x in p) for p in verts):
            raise RuntimeError("Unsupported nonfinite triangles")
        tree=BVHTree.FromPolygons(verts,triangles,all_triangles=True)
        return tree
    finally:evaluated.to_mesh_clear()
def query(obj,point,*,max_slope_deg=35):
    # Fixed gravity-down ray. The directional floor gap is vertical distance,
    # not a guarantee of manifold signed-distance or dynamic support.
    tree=build_bvh(obj)
    source=point+Vector((0,0,.5))
    location,normal,face_index,distance=tree.ray_cast(source,Vector((0,0,-1)),1.0)
    if location is None:
        return {"status":"unsupported_no_surface"}
    if not all(math.isfinite(x) for x in tuple(location)+tuple(normal)):
        raise RuntimeError("Invalid evaluated support triangle")
    if normal.length<.999 or normal.length>1.001:
        raise RuntimeError("Support triangle normal invalid")
    if normal.z<math.cos(math.radians(max_slope_deg)):
        return {"status":"unsupported_slope","normal_up":float(normal.z)}
    return {"status":"measured","signed_gravity_gap_m":float(point.z-location.z),
            "surface_world_m":[float(v) for v in location],
            "surface_normal_world":[float(v) for v in normal],
            "triangle_index":int(face_index)}
def synthetic_quad(name,angle):
    mesh=bpy.data.meshes.new(name+"_mesh")
    mesh.from_pydata([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)],[],
                     [(0,1,2,3)])
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    sc.collection.objects.link(obj)
    obj.location=(2,2,.35);obj.rotation_euler.y=math.radians(angle)
    bpy.context.view_layer.update()
    return obj
# Independent properties/edge tests on an actual triangulated floor and
# an explicit in-memory sloped support polygon; never save test geometry.
base_points=[floor.matrix_world@v.co for v in floor.data.vertices]
z=max(v.z for v in base_points)
upper=[v for v in base_points if abs(v.z-z)<1e-4]
if len(upper)!=4:raise RuntimeError("Fixture floor lacks a known top face")
center=sum(upper,Vector((0,0,0)))/4
tests={}
tests["flat_above"]=query(floor,center+Vector((0,0,.012)))
tests["flat_below"]=query(floor,center+Vector((0,0,-.009)))
tilt=synthetic_quad("NVP_UNSAVED_SUPPORT_SLOPE",12.0)
middle=tilt.matrix_world@Vector((.1,.15,0))
tests["slope_above"]=query(tilt,middle+Vector((0,0,.014)))
tests["slope_below"]=query(tilt,middle+Vector((0,0,-.011)))
tests["slope_outside"]=query(tilt,middle+Vector((5,0,.014)))
steep=synthetic_quad("NVP_UNSAVED_UNSUPPORTED_STEEP",70.0)
midsteep=steep.matrix_world@Vector((0,0,0))
tests["steep_refused"]=query(steep,midsteep+Vector((0,0,.01)))
report={"format":"nvp.surface.bvh.observation.v1",
        "foot_correction_sha":pkg["plantar_correction"]["approval_sha"],
        "plantar_sha":pkg["plantar"]["approval_sha"],
        "floor_sha":pkg["plantar"]["plan"]["surface"]["geometry_sha256"],
        "blender":bpy.app.version_string,
        "self_tests":tests,"actors":{}}
for a in pkg["plantar"]["plan"]["actors"]:
    approved=next(x for x in pkg["leg_identity"]["actors"] if x["instance_id"]==a)
    rig=bpy.data.objects.get("NVP_CHARACTER_RIG_"+a)
    if rig is None or rig.get("nvp_character_sha")!=approved["asset_sha256"]:
        raise RuntimeError("Imported actor identity does not match edited character")
    author=next(x for x in pkg["foot_lock"]["actors"] if x["instance_id"]==a)
    measures={}
    for side in ("left","right"):
        marker=pkg["plantar"]["plan"]["actors"][a][side]
        obj=bpy.data.objects.get(marker["mesh_name"])
        if (obj is None or obj.type!="MESH" or obj.get("nvp_character_actor")!=a or
            not any(m.type=="ARMATURE" and m.object==rig for m in obj.modifiers)):
            raise RuntimeError("Unrelated mesh substituted for accepted plantar source")
        roles=marker["contact_roles"]
        frames=sorted({i for first,last in author["config"][side]["contact_windows"]
                       for i in range(first,last+1)})
        samples=[]
        for frame in frames:
            sc.frame_set(frame);bpy.context.view_layer.update()
            ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh=ev.to_mesh()
            try:
                if len(mesh.vertices)!=len(obj.data.vertices):
                    raise RuntimeError("Skinned mesh topology changed between original/corrected")
                positions={role:ev.matrix_world@mesh.vertices[marker["markers"][role]].co
                           for role in roles}
            finally:ev.to_mesh_clear()
            samples.append({"frame":frame,
                            "active_roles":{role:query(floor,point) for role,point in positions.items()}})
        measures[side]=samples
    report["actors"][a]={"asset_sha256":approved["asset_sha256"],"sides":measures}
Path(opts["--output"]).write_text(json.dumps(report,indent=2,sort_keys=True),"utf8")
'''


def _number(v,what,lo=-1e5,hi=1e5):
    if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:
        raise ValueError(what+" is missing or nonfinite")
    return float(v)


def check_native_bvh_evidence(report,package):
    if type(report) is not dict or report.get("format")!="nvp.surface.bvh.observation.v1":
        raise ValueError("Unsupported Blender surface evidence format")
    if (report.get("foot_correction_sha")!=package["plantar_correction"]["approval_sha"] or
        report.get("plantar_sha")!=package["plantar"]["approval_sha"] or
        report.get("floor_sha")!=package["plantar"]["plan"]["surface"]["geometry_sha256"]):
        raise ValueError("Surface audit not tied to current director-approved rig/floor")
    tests=report.get("self_tests")
    expected={"flat_above":.012,"flat_below":-.009,
              "slope_above":.014,"slope_below":-.011}
    if type(tests) is not dict or set(tests)!=set(expected)|{"slope_outside","steep_refused"}:
        raise ValueError("Missing explicit flat/sloped/outside/steep native tests")
    for name,expect in expected.items():
        t=tests[name]
        if type(t) is not dict or t.get("status")!="measured":
            raise ValueError("Blender BVH did not find the supported geometry")
        gap=_number(t.get("signed_gravity_gap_m"),name+" gravity gap")
        normal=t.get("surface_normal_world")
        if type(normal) is not list or len(normal)!=3 or _number(normal[2],name+" normal",-1,1)<.8:
            raise ValueError("Native query returned invalid support slope")
        if abs(gap-expect)>.0001:
            raise ValueError("Actual Blender BVH gravity gap differs from independent expected value")
    if (tests["slope_outside"].get("status")!="unsupported_no_surface" or
        tests["steep_refused"].get("status")!="unsupported_slope"):
        raise ValueError("Unsupported surface/grade was silently accepted")
    authored={x["instance_id"]:x for x in package["foot_lock"]["actors"]}
    planted=package["plantar"]["plan"]["actors"]
    sources={x["instance_id"]:x for x in package["leg_identity"]["actors"]}
    observed=report.get("actors")
    if type(observed) is not dict or set(observed)!=set(authored) or set(observed)!=set(planted):
        raise ValueError("Real Blender actor/marker BVH roster mismatch")
    samples=0;max_penetration=0;max_gap=0
    for rid,data in observed.items():
        if type(data) is not dict or data.get("asset_sha256")!=sources[rid]["asset_sha256"]:
            raise ValueError("Native character source changed")
        sides=data.get("sides")
        if type(sides) is not dict or set(sides)!={"left","right"}:
            raise ValueError("Real corrected scene has no bilateral foot support")
        for side in ("left","right"):
            expected_frames=sorted({i for first,last in authored[rid]["config"][side]["contact_windows"]
                                    for i in range(first,last+1)})
            trace=sides[side]
            if not isinstance(trace,list) or [x.get("frame") for x in trace]!=expected_frames:
                raise ValueError("Native correction BVH omitted/duplicated stance frames")
            roles=planted[rid][side]["contact_roles"]
            for frame in trace:
                observed_roles=frame.get("active_roles")
                if type(observed_roles) is not dict or set(observed_roles)!=set(roles):
                    raise ValueError("Skinned contact role observations incomplete")
                for item in observed_roles.values():
                    if type(item) is not dict or item.get("status")!="measured":
                        raise ValueError("Actual foot marker lies outside supported ground geometry")
                    value=_number(item.get("signed_gravity_gap_m"),"Real skinned foot gap")
                    if (value < -planted[rid]["max_penetration_m"]-1e-5 or
                        value > planted[rid]["max_gap_m"]+1e-5):
                        raise RuntimeError("Corrected real character fails BVH floor contact")
                    max_penetration=max(max_penetration,max(0,-value))
                    max_gap=max(max_gap,max(0,value))
                    samples+=1
    if samples<2:
        raise ValueError("No real licensed human foot markers were independently ray-cast")
    return {"status":"passed_real_character_bvh_geometry_only",
            "self_test_gaps_m":{k:_number(v["signed_gravity_gap_m"],k) for k,v in tests.items()
                                if k in expected},
            "real_active_contact_marker_samples":samples,
            "max_active_penetration_m":max_penetration,
            "max_active_gap_m":max_gap,
            "floor_sha":report["floor_sha"],
            "slope_queries_verified":True,
            "anatomically_verified_plantar_foot":False,
            "moving_slope_contact_verified":False,
            "limitations":"Exact foot vertex contact on actual flat stage; triangle BVH tested separately on synthetic 12-degree slope, no reviewed anatomical landmarks"}


def run_native_bvh_geometry(service:PlantarCorrectionPlan,pid,sid,blend,out,
                            *,blender="blender",timeout=240):
    pkg=service.export(pid,sid)
    exe=blender_available(blender)
    if not exe["available"]:
        return {"status":"blocked_no_blender","reason":exe["reason"]}
    blend=Path(blend).resolve()
    if not blend.is_file() or blend.suffix.lower()!=".blend":
        raise ValueError("Need actual approved Blender corrected external character")
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=out/"real_bvh_source.json"
    script=out/"inspect_real_floor_bvh.py"
    report=out/"real_bvh_geometry.json";report.unlink(missing_ok=True)
    manifest.write_text(compact(pkg),"utf8")
    script.write_text(NATIVE_BVH_SURFACE_SCRIPT,"utf8")
    cmd=[exe["path"],"-b",str(blend),"-t","2","--python-exit-code","30",
         "--python",str(script),"--","--manifest",str(manifest),"--output",str(report)]
    try:proc=run_owned_subprocess(cmd,cwd=out,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status":"failed","reason":"Real Blender BVH measurement timed out"}
    if proc.returncode or not report.is_file():
        return {"status":"failed","reason":"Native BVH floor/foot inspection failed",
                "returncode":proc.returncode,"stderr":proc.stderr[-3000:],
                "stdout":proc.stdout[-1800:]}
    checked=check_native_bvh_evidence(json.loads(report.read_text("utf8")),pkg)
    if digest(service.export(pid,sid)["plantar_correction"])!=digest(pkg["plantar_correction"]):
        raise RuntimeError("Foot corrections changed while native BVH audit ran")
    (out/"reviewed_bvh_geometry.json").write_text(json.dumps(checked,indent=2,sort_keys=True),"utf8")
    return checked
