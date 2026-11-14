"""NVP-PROD-06E2C2: explicit plantar mesh markers and an actual floor audit.

Foot morphology reference and BVH principles: OpenSim, Rice NMSM, Blender API.
Neither the research reference nor a fixture-generated candidate marker is
creator-authored anatomy. Production requires explicit review and approval.
This module is a developer-side native audit, not a new movement solver.
"""
from __future__ import annotations
import hashlib
import json
import math
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
from pathlib import Path

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_foot_contact import FootLockPlan
from backend.nvp_production_scene import compact, digest

ROLES = ("heel", "ball", "toe")
SIDES = ("left", "right")
MAX_V = 250000
MAX_FRAMES = 2400
FORMAT = "nvp.plantar.approved.v1"


def _num(x, name, lo, hi):
    if type(x) not in (int, float) or not math.isfinite(x) or not lo <= x <= hi:
        raise ValueError(name + " must be finite and bounded")
    return float(x)


def validate_plantar_config(value, approved_actors):
    """Validate *author-specified* Blender mesh indices and named floor."""
    if type(value) is not dict or set(value) != {"surface", "actors"}:
        raise ValueError("Require named approved surface and actor marker records")
    surface = value["surface"]
    if type(surface) is not dict or set(surface) != {"object_name", "geometry_sha256"}:
        raise ValueError("Floor requires a named Blender object and geometry digest")
    name, sha = surface["object_name"], surface["geometry_sha256"]
    if name != "NVP_FLOOR" or type(sha) is not str or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Only exact, pinned NVP_FLOOR is supported by this gate")
    roster = {x["instance_id"] for x in approved_actors}
    actors = value["actors"]
    if type(actors) is not dict or set(actors) != roster:
        raise ValueError("Approved actor roster must be mapped exactly")
    result = {"surface": surface, "actors": {}}
    for actor in approved_actors:
        rid = actor["instance_id"]
        item = actors[rid]
        if type(item) is not dict or set(item) != {"left", "right", "max_penetration_m", "max_gap_m", "max_slide_m"}:
            raise ValueError("Both feet and all physical tolerances must be specified")
        checked = {
            "max_penetration_m": _num(item["max_penetration_m"], "penetration", 0.0, .03),
            "max_gap_m": _num(item["max_gap_m"], "gap", 0.0, .05),
            "max_slide_m": _num(item["max_slide_m"], "slide", 0.0, .05)
        }
        for side in SIDES:
            entry = item[side]
            if type(entry) is not dict or set(entry) != {"mesh_name", "markers", "contact_roles"}:
                raise ValueError(side + " requires exact mesh, marker IDs and contact roles")
            mesh = entry["mesh_name"]
            if type(mesh) is not str or not 1 <= len(mesh) <= 128 or "\x00" in mesh:
                raise ValueError("Invalid approved source mesh name")
            markers = entry["markers"]
            if type(markers) is not dict or set(markers) != set(ROLES) or any(
                type(i) is not int or not 0 <= i < MAX_V for i in markers.values()):
                raise ValueError("Heel, ball and toe must be explicit mesh-vertex indices")
            if len(set(markers.values())) != 3:
                raise ValueError("Plantar markers cannot reuse the same vertex")
            active = entry["contact_roles"]
            if type(active) is not list or not active or len(active) > 3 or len(set(active)) != len(active) or any(x not in ROLES for x in active):
                raise ValueError("Explicit subset of heel/ball/toe contact markers required")
            checked[side] = {"mesh_name": mesh, "markers": markers,
                             "contact_roles": sorted(active)}
        if checked["left"]["mesh_name"] == checked["right"]["mesh_name"]:
            if set(checked["left"]["markers"].values()) & set(checked["right"]["markers"].values()):
                raise ValueError("Left/right plantar geometry cannot share physical vertices")
        result["actors"][rid] = checked
    return result


class PlantarContactPlan:
    """Creator-approved marker and floor identity, but not movement permission."""
    def __init__(self, studio):
        self.studio = studio
        self.lock = FootLockPlan(studio)
        with studio._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS prod_plantar_plans (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL,
                upstream_sha TEXT NOT NULL, plan_json TEXT NOT NULL,
                approval_sha TEXT, PRIMARY KEY(project_id,scene_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_plantar_history (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                action TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,revision))''')

    def _context(self, pid, sid):
        pkg = self.lock.export(pid, sid)
        return pkg, digest([pkg["foot_lock"], pkg["leg_identity"], pkg["take"]])

    def _row(self, db, pid, sid):
        row = db.execute("SELECT * FROM prod_plantar_plans WHERE project_id=? AND scene_id=?",
                         (pid,sid)).fetchone()
        if row is None: raise KeyError("No plantar plan exists for this project and scene")
        return dict(row)

    def create(self, pid, sid):
        pkg, upstream = self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM prod_plantar_plans WHERE project_id=? AND scene_id=?", (pid,sid)).fetchone():
                raise RuntimeError("Existing plantar plan cannot be silently reset")
            db.execute("INSERT INTO prod_plantar_plans VALUES (?,?,?,?,?,?,?)",
                       (pid,sid,0,"draft",upstream,compact({}),None))
            db.execute("INSERT INTO prod_plantar_history VALUES (?,?,?,?,?)",
                       (pid,sid,0,"create","{}"))
        return self.read(pid,sid)

    def read(self,pid,sid):
        _, upstream = self._context(pid,sid)
        with self.studio._connection() as db: row = self._row(db,pid,sid)
        return {"revision":row["revision"],"status":row["status"],
                "stale":row["upstream_sha"]!=upstream,"approval_sha":row["approval_sha"],
                "plan":json.loads(row["plan_json"])}

    def configure(self,pid,sid,config,expected_revision):
        pkg,upstream=self._context(pid,sid)
        checked=validate_plantar_config(config,pkg["foot_lock"]["actors"])
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,pid,sid)
            if (row["status"]!="draft" or row["upstream_sha"]!=upstream or
                type(expected_revision) is not int or row["revision"]!=expected_revision):
                raise RuntimeError("Plantar edit is stale, conflicted or already approved")
            revision=row["revision"]+1
            db.execute("UPDATE prod_plantar_plans SET revision=?,plan_json=? WHERE project_id=? AND scene_id=?",
                       (revision,compact(checked),pid,sid))
            db.execute("INSERT INTO prod_plantar_history VALUES (?,?,?,?,?)",
                       (pid,sid,revision,"configure",compact(checked)))
        return self.read(pid,sid)

    def approve(self,pid,sid,expected_revision):
        pkg,upstream=self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,pid,sid)
            if (row["status"]!="draft" or row["upstream_sha"]!=upstream or
                type(expected_revision) is not int or row["revision"]!=expected_revision):
                raise RuntimeError("Plantar approval requires current unmodified draft")
            current_plan=json.loads(row["plan_json"])
            if not current_plan:
                raise RuntimeError("An unconfigured plantar marker draft cannot be approved")
            plan=validate_plantar_config(current_plan,pkg["foot_lock"]["actors"])
            approval=digest([upstream,plan])
            revision=row["revision"]+1
            db.execute("UPDATE prod_plantar_plans SET revision=?,status=?,approval_sha=? WHERE project_id=? AND scene_id=?",
                       (revision,"approved",approval,pid,sid))
            db.execute("INSERT INTO prod_plantar_history VALUES (?,?,?,?,?)",
                       (pid,sid,revision,"approve",compact({"sha":approval})))
        return self.read(pid,sid)

    def export(self,pid,sid):
        pkg,upstream=self._context(pid,sid)
        with self.studio._connection() as db: row=self._row(db,pid,sid)
        plan=json.loads(row["plan_json"])
        if (row["status"]!="approved" or row["upstream_sha"]!=upstream or
            row["approval_sha"]!=digest([upstream,plan])):
            raise RuntimeError("No current approved plantar marker plan")
        return {**pkg,"plantar":{
            "format":FORMAT,"approval_sha":row["approval_sha"],
            "upstream_sha":upstream,"plan":plan,
            "physical_contact_verified":False,
            "limitations":"Approval is of exact mesh indices and floor identity, not biomechanical sole validity or gap-free contact"}}


# Native probe computes exact NVP_FLOOR geometry and *fixture-only* marker
# suggestions from candidate skin groups. The product must never call this an
# author-approved anatomical map without a creator review.
PLANTAR_FIXTURE_PROBE = r'''import bpy,json,sys,math,hashlib
from pathlib import Path
from mathutils import Vector
argv=sys.argv[sys.argv.index("--")+1:]
opts=dict(zip(argv[::2],argv[1::2]))
pkg=json.loads(Path(opts["--package"]).read_text("utf8"))
sc=bpy.context.scene
if sc.get("nvp_footlock_approval_sha")!=pkg["foot_lock"]["approval_sha"]:
    raise RuntimeError("Not the approved foot-locked stage")
floor=bpy.data.objects.get("NVP_FLOOR")
if floor is None or floor.type!="MESH" or floor.get("nvp_proxy")!=True:
    raise RuntimeError("Scene has no approved physical floor mesh")
def floor_data():
    points=sorted([tuple(round(float(c),7) for c in floor.matrix_world@v.co) for v in floor.data.vertices])
    if len(points)!=8:raise RuntimeError("Unsupported non-box fixture floor")
    top=max(v[2] for v in points)
    if len([p for p in points if abs(p[2]-top)<.0001])!=4:
        raise RuntimeError("Unsupported non-horizontal fixture floor")
    payload=json.dumps(points,sort_keys=True,separators=(",",":"),allow_nan=False)
    return {"geometry_sha256":hashlib.sha256(payload.encode("utf8")).hexdigest(),
            "top_z_m":top,"bounds_xy_m":[min(p[0] for p in points),max(p[0] for p in points),
                                          min(p[1] for p in points),max(p[1] for p in points)]}
record={"format":"nvp.plantar.fixture_proposal.v1","surface":{"object_name":"NVP_FLOOR",**floor_data()},"actors":{}}
for user in pkg["foot_lock"]["actors"]:
    rid=user["instance_id"]
    meta=next(a for a in pkg["leg_identity"]["actors"] if a["instance_id"]==rid)
    rig=bpy.data.objects["NVP_CHARACTER_RIG_"+rid]
    if rig.get("nvp_character_sha")!=meta["asset_sha256"]:
        raise RuntimeError("Source asset mismatch")
    meshes=[x for x in bpy.data.objects if x.type=="MESH" and x.get("nvp_character_actor")==rid
            and any(m.type=="ARMATURE" and m.object==rig for m in x.modifiers)]
    if not meshes:raise RuntimeError("No evaluated external mesh")
    result={}
    for side in ("left","right"):
        start=user["config"][side]["contact_windows"][0][0]
        sc.frame_set(start);bpy.context.view_layer.update()
        pose=rig.pose.bones
        mapping=meta["mapping"][side]
        ankle=rig.matrix_world@pose[mapping["ankle"]].head
        toe=rig.matrix_world@pose[mapping["toe"]].head
        forward=(toe-ankle)
        if forward.length<.005:raise RuntimeError("Unresolved foot length")
        forward.normalize()
        best=None
        for obj in meshes:
            groups={x.index for x in obj.vertex_groups
                    if x.name in (mapping["ankle"],mapping["toe"])}
            if len(groups)!=2:continue
            deps=bpy.context.evaluated_depsgraph_get()
            ev=obj.evaluated_get(deps);geom=ev.to_mesh()
            try:
                if len(geom.vertices)!=len(obj.data.vertices):continue
                candidates=[]
                for vertex in obj.data.vertices:
                    if sum(x.weight for x in vertex.groups if x.group in groups)<.25:continue
                    pos=ev.matrix_world@geom.vertices[vertex.index].co
                    candidates.append((float((pos-ankle).dot(forward)),float(pos.z),vertex.index))
            finally:ev.to_mesh_clear()
            if len(candidates)<9:continue
            if best is None or len(candidates)>len(best[1]):best=(obj,candidates)
        if best is None:raise RuntimeError("Cannot propose three ankle/toe-weighted test regions")
        obj,candidates=best
        candidates.sort(key=lambda x:x[0])
        n=len(candidates)
        groups=(candidates[:n//3],candidates[n//3:2*n//3],candidates[2*n//3:])
        chosen=[min(group,key=lambda x:(x[1],x[2]))[2] for group in groups]
        if len(set(chosen))!=3:raise RuntimeError("Fixture marker proposals overlap")
        result[side]={"mesh_name":obj.name,"markers":dict(zip(("heel","ball","toe"),chosen)),
                      "contact_roles":["heel","ball","toe"],
                      "provenance":"algorithmic fixture proposal; NOT anatomical authoring"}
    record["actors"][rid]=result
Path(opts["--output"]).write_text(json.dumps(record,sort_keys=True,indent=2),"utf8")
'''


PLANTAR_NATIVE_AUDIT = r'''import bpy,json,sys,math,hashlib
from pathlib import Path
argv=sys.argv[sys.argv.index("--")+1:]
opts=dict(zip(argv[::2],argv[1::2]))
pkg=json.loads(Path(opts["--package"]).read_text("utf8"))
sc=bpy.context.scene
plan=pkg["plantar"]
if (plan["format"]!="nvp.plantar.approved.v1" or
    sc.get("nvp_footlock_approval_sha")!=pkg["foot_lock"]["approval_sha"] or
    sc.get("nvp_leg_identity_approval_sha")!=pkg["leg_identity"]["approval_sha"]):
    raise RuntimeError("Unapproved source, rig or plantar revision")
def floor_data():
    floor=bpy.data.objects.get(plan["plan"]["surface"]["object_name"])
    if floor is None or floor.type!="MESH" or floor.get("nvp_proxy")!=True:
        raise RuntimeError("Missing real NVP floor mesh")
    points=sorted([tuple(round(float(c),7) for c in floor.matrix_world@v.co) for v in floor.data.vertices])
    if len(points)!=8:raise RuntimeError("Unsupported non-box floor")
    payload=json.dumps(points,sort_keys=True,separators=(",",":"),allow_nan=False)
    sha=hashlib.sha256(payload.encode("utf8")).hexdigest()
    if sha!=plan["plan"]["surface"]["geometry_sha256"]:
        raise RuntimeError("Floor geometry changed after approved authoring")
    z=max(p[2] for p in points)
    if sum(abs(p[2]-z)<1e-4 for p in points)!=4:
        raise RuntimeError("Floor is not a level upper surface")
    return {"top_z_m":z,"bounds_xy_m":[min(p[0] for p in points),max(p[0] for p in points),
                                      min(p[1] for p in points),max(p[1] for p in points)],
            "geometry_sha256":sha}
surface=floor_data()
report={"format":"nvp.plantar.native_observation.v1",
        "plantar_approval_sha":plan["approval_sha"],
        "foot_lock_sha":pkg["foot_lock"]["approval_sha"],
        "floor":surface,"blender":bpy.app.version_string,"actors":{}}
for rid,authored in plan["plan"]["actors"].items():
    info=next(x for x in pkg["leg_identity"]["actors"] if x["instance_id"]==rid)
    original=next(x for x in pkg["foot_lock"]["actors"] if x["instance_id"]==rid)
    rig=bpy.data.objects.get("NVP_CHARACTER_RIG_"+rid)
    if rig is None or rig.get("nvp_character_sha")!=info["asset_sha256"]:
        raise RuntimeError("Imported skinned rig identity mismatch")
    sides={}
    meshes={}
    for side in ("left","right"):
        conf=authored[side]
        obj=bpy.data.objects.get(conf["mesh_name"])
        if (obj is None or obj.type!="MESH" or obj.get("nvp_character_actor")!=rid or
            not any(m.type=="ARMATURE" and m.object==rig for m in obj.modifiers)):
            raise RuntimeError("Selected plantar mesh is not bound to approved human")
        if len(obj.data.vertices)>250000:raise RuntimeError("Oversized character geometry")
        groups={g.index for g in obj.vertex_groups if g.name in
                (info["mapping"][side]["ankle"], info["mapping"][side]["toe"])}
        if len(groups)!=2:raise RuntimeError("Ankle/toe skin group mismatch")
        for role,index in conf["markers"].items():
            if index>=len(obj.data.vertices):raise RuntimeError("Unresolved explicit plantar vertex")
            if sum(v.weight for v in obj.data.vertices[index].groups if v.group in groups)<.25:
                raise RuntimeError("Creator-selected vertex is not influenced by intended foot")
        meshes[side]=obj
    frames=sorted({i for side in ("left","right") for a,b in original["config"][side]["contact_windows"]
                   for i in range(a,b+1)})
    if not frames or len(frames)>2400:raise RuntimeError("Out-of-budget authored foot windows")
    observations=[]
    for frame in frames:
        sc.frame_set(frame);bpy.context.view_layer.update()
        deps=bpy.context.evaluated_depsgraph_get()
        datum={"frame":frame,"sides":{}}
        for side in ("left","right"):
            obj=meshes[side]; conf=authored[side]
            ev=obj.evaluated_get(deps);mesh=ev.to_mesh()
            try:
                if len(mesh.vertices)!=len(obj.data.vertices):
                    raise RuntimeError("Skinned geometry topology changed")
                points={}
                for role,index in conf["markers"].items():
                    p=ev.matrix_world@mesh.vertices[index].co
                    if not all(math.isfinite(x) for x in p):
                        raise RuntimeError("Nonfinite animated plantar vertex")
                    points[role]=[float(v) for v in p]
            finally:ev.to_mesh_clear()
            datum["sides"][side]=points
        observations.append(datum)
    report["actors"][rid]={"asset_sha256":info["asset_sha256"],
                            "frames":frames,"observations":observations}
Path(opts["--output"]).write_text(json.dumps(report,sort_keys=True,indent=2),"utf8")
'''


def analyze_plantar_observation(obs, package):
    """Audit actual floor and all artist-selected marker frames outside Blender.

    Valid native geometry can have *failed* physical contact. Report both.
    """
    plantar=package["plantar"]
    if (type(obs) is not dict or obs.get("format")!="nvp.plantar.native_observation.v1" or
        obs.get("plantar_approval_sha")!=plantar["approval_sha"] or
        obs.get("foot_lock_sha")!=package["foot_lock"]["approval_sha"]):
        raise ValueError("Observation/approval mismatch")
    expected=plantar["plan"]
    floor=obs.get("floor")
    if type(floor) is not dict or floor.get("geometry_sha256")!=expected["surface"]["geometry_sha256"]:
        raise ValueError("Observed floor geometry is not the approved floor")
    z=_num(floor.get("top_z_m"),"floor height",-10000,10000)
    bounds=floor.get("bounds_xy_m")
    if type(bounds) is not list or len(bounds)!=4:
        raise ValueError("Need an actual measured floor surface extent")
    lo_x,hi_x,lo_y,hi_y=[_num(v,"floor extent",-10000,10000) for v in bounds]
    if not lo_x<hi_x or not lo_y<hi_y:raise ValueError("Degenerate floor mesh bounds")
    observed=obs.get("actors")
    approved=expected["actors"]
    authored={x["instance_id"]:x for x in package["foot_lock"]["actors"]}
    sources={x["instance_id"]:x for x in package["leg_identity"]["actors"]}
    if type(observed) is not dict or set(observed)!=set(approved) or set(observed)!=set(authored) or set(observed)!=set(sources):
        raise ValueError("Observed actor roster does not match approved film")
    summary={}
    all_actors_ok=True
    for rid,record in observed.items():
        if type(record) is not dict or record.get("asset_sha256")!=sources[rid]["asset_sha256"]:
            raise ValueError("Plantar source mesh identity mismatch")
        expected_frames=sorted({i for side in SIDES for a,b in authored[rid]["config"][side]["contact_windows"]
                                for i in range(a,b+1)})
        if record.get("frames")!=expected_frames or not isinstance(record.get("observations"),list) or len(record["observations"])!=len(expected_frames):
            raise ValueError("Missing or altered native plantar frame observations")
        samples={side:{role:[] for role in ROLES} for side in SIDES}
        for frame,item in zip(expected_frames,record["observations"]):
            if type(item) is not dict or item.get("frame")!=frame or type(item.get("sides")) is not dict or set(item["sides"])!=set(SIDES):
                raise ValueError("Wrong native sample identity/frame")
            for side in SIDES:
                pts=item["sides"][side]
                if type(pts) is not dict or set(pts)!=set(ROLES):raise ValueError("Incomplete authored plantar markers")
                for role in ROLES:
                    point=pts[role]
                    if type(point) is not list or len(point)!=3:
                        raise ValueError("Malformed animated plantar marker")
                    point=[_num(v,"marker position",-10000,10000) for v in point]
                    samples[side][role].append((frame,point))
        side_results={}
        overall=True
        for side in SIDES:
            contact={f for a,b in authored[rid]["config"][side]["contact_windows"] for f in range(a,b+1)}
            result={}
            for role in ROLES:
                trajectory=[point for frame,point in samples[side][role] if frame in contact]
                if not trajectory:raise ValueError("No native samples for approved contact stance")
                gaps=[p[2]-z for p in trajectory]
                slides=[math.dist(p[:2],trajectory[0][:2]) for p in trajectory]
                within_floor=all(lo_x-1e-5<=p[0]<=hi_x+1e-5 and lo_y-1e-5<=p[1]<=hi_y+1e-5 for p in trajectory)
                active=role in approved[rid][side]["contact_roles"]
                ok=(within_floor and min(gaps)>=-approved[rid]["max_penetration_m"]-1e-6 and
                    max(gaps)<=approved[rid]["max_gap_m"]+1e-6 and
                    max(slides)<=approved[rid]["max_slide_m"]+1e-6)
                if active:overall=overall and ok
                result[role]={"active":active,"min_clearance_m":min(gaps),
                              "max_clearance_m":max(gaps),"max_slide_m":max(slides),
                              "inside_floor":within_floor,"contact_meets_tolerances":ok if active else None}
            side_results[side]=result
        summary[rid]=side_results
        all_actors_ok = all_actors_ok and overall
    return {"format":"nvp.plantar.floor_contact_audit.v1","observation_sha":digest(obs),
            "actors":summary,"floor_z_m":z,
            "approved_plantar_sha":plantar["approval_sha"],
            "contact_meets_configured_tolerances":all_actors_ok,
            "anatomical_sole_certified":False,
            "limitations":"Mesh-vertex markers are authored surface points, not certified plantar pads; no dynamics/normal forces or balance"}


def run_native_plantar_audit(service:PlantarContactPlan,pid,sid,blend,output,
                            *,blender="blender",timeout=240):
    package=service.export(pid,sid)
    binary=blender_available(blender)
    if not binary["available"]:return {"status":"blocked_no_blender","reason":binary["reason"]}
    blend=Path(blend).resolve()
    if not blend.is_file() or blend.suffix.lower()!=".blend":
        raise FileNotFoundError("Approved foot-locked .blend is required")
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=out/"plantar_manifest.json";manifest.write_text(compact(package),"utf8")
    script=out/"audit_plantar.py";script.write_text(PLANTAR_NATIVE_AUDIT,"utf8")
    report=out/"plantar_observation.json";report.unlink(missing_ok=True)
    cmd=[binary["path"],"-b",str(blend),"-t","2","--python-exit-code","30",
         "--python",str(script),"--","--package",str(manifest),"--output",str(report)]
    try:proc=run_owned_subprocess(cmd,cwd=out,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status":"failed","reason":"Native plantar floor survey timed out"}
    if proc.returncode or not report.exists():
        return {"status":"failed","reason":"Native plantar floor geometry rejected",
                "returncode":proc.returncode,"stderr":proc.stderr[-2200:],
                "stdout":proc.stdout[-1300:]}
    audited=analyze_plantar_observation(json.loads(report.read_text("utf8")),package)
    (out/"plantar_floor_audit.json").write_text(json.dumps(audited,indent=2,sort_keys=True),"utf8")
    return {"status":"passed_native_plantar_floor_measurement_only",
            "audit":audited,"anatomical_sole_certified":False,"output_dir":str(out)}
