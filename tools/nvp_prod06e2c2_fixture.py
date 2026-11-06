"""PROD-06E2C2 licensed real-human marker/floor survey fixture.

The fixture proposes vertex indices from explicit ankle/toe weights solely for
repeatable engineering acceptance. These proposals are NOT director-certified
heel, metatarsal-ball, or toe anatomy. Product workflows must have the creator
select/review actual skinned surface points before approving markers.
"""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_plantar import PlantarContactPlan, PLANTAR_FIXTURE_PROBE, run_native_plantar_audit
from backend.nvp_production_scene import compact
from backend.nvp_studio import Studio
from tools.nvp_prod06e2b_fixture import run_fixture


def run_fixture_plantar(out, source, *, blender="blender", audit_only=False, fixture_active_roles=None):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    upstream=run_fixture(out/"real_ankle_ik",source,blender=blender,audit_only=audit_only)
    if upstream.get("status")!="passed_native_ankle_lock_only":
        return {"status":"failed","stage":"real_ankle_ik","upstream":upstream}
    native=out/"real_ankle_ik"/"native_footlock"
    stage=native/"ankle_locked.blend"
    studio_path=out/"real_ankle_ik"/"prod06e2a"/"prod06d_baseline"/"project"/"studio.sqlite"
    if not stage.is_file() or not studio_path.is_file():
        return {"status":"failed","stage":"missing_real_stage"}
    studio=Studio(studio_path);projects=studio.list_projects()
    if len(projects)!=1:raise RuntimeError("External fixture project identity ambiguous")
    pid=projects[0]["id"];scenes=studio.get_project(pid)["scenes"]
    if len(scenes)!=1:raise RuntimeError("External fixture scene identity ambiguous")
    sid=scenes[0]["id"]
    service=PlantarContactPlan(studio)
    pkg=service.lock.export(pid,sid)
    probe=blender_available(blender)
    if not probe["available"]:
        return {"status":"blocked_no_blender","reason":probe["reason"]}
    source_file=out/"locked_manifest.json";source_file.write_text(compact(pkg),"utf8")
    script=out/"propose_fixture_foot_vertices.py";script.write_text(PLANTAR_FIXTURE_PROBE,"utf8")
    proposal_path=out/"fixture_marker_proposal.json";proposal_path.unlink(missing_ok=True)
    cmd=[probe["path"],"-b",str(stage),"-t","2","--python-exit-code","30",
         "--python",str(script),"--","--package",str(source_file),
         "--output",str(proposal_path)]
    try:proc=subprocess.run(cmd,cwd=out,capture_output=True,text=True,timeout=240)
    except subprocess.TimeoutExpired:
        return {"status":"failed","stage":"marker_proposal_timeout"}
    if proc.returncode or not proposal_path.is_file():
        return {"status":"failed","stage":"fixture_marker_proposal",
                "exit_code":proc.returncode,"stdout":proc.stdout[-2000:],
                "stderr":proc.stderr[-2500:]}
    proposal=json.loads(proposal_path.read_text("utf8"))
    if proposal.get("format")!="nvp.plantar.fixture_proposal.v1":
        raise ValueError("Unexpected fixture geometry proposal")
    # Deliberately label the source as fixture-generated, not an artist-
    # approved anatomical sole. Approval here is deterministic test harness
    # action, exercising the real production storage/revision checks.
    config={"surface":{"object_name":"NVP_FLOOR",
                       "geometry_sha256":proposal["surface"]["geometry_sha256"]},
            "actors":{}}
    for actor in pkg["foot_lock"]["actors"]:
        rid=actor["instance_id"]
        recommended=proposal["actors"][rid]
        config["actors"][rid]={
            "left":{k:recommended["left"][k] for k in ("mesh_name","markers","contact_roles")},
            "right":{k:recommended["right"][k] for k in ("mesh_name","markers","contact_roles")},
            "max_penetration_m":.002,
            "max_gap_m":.02,
            "max_slide_m":.012
        }
    if fixture_active_roles is not None:
        if (type(fixture_active_roles) is not dict or set(fixture_active_roles)!={"left","right"} or
            any(type(roles) is not list or not roles or any(r not in ("heel","ball","toe") for r in roles)
                for roles in fixture_active_roles.values())):
            raise ValueError("Fixture active markers must explicitly identify left and right")
        for record in config["actors"].values():
            for side in ("left","right"):
                record[side]["contact_roles"]=fixture_active_roles[side]
    draft=service.create(pid,sid)
    draft=service.configure(pid,sid,config,draft["revision"])
    receipt=service.approve(pid,sid,draft["revision"])
    result=run_native_plantar_audit(service,pid,sid,stage,out/"native_plantar_floor",
                                    blender=blender)
    if result.get("status")=="passed_native_plantar_floor_measurement_only":
        audit=result["audit"]
        result={"status":"passed_native_plantar_floor_measurement_only",
                "approved_plantar_sha":receipt["approval_sha"],
                "floor_geometry_sha":config["surface"]["geometry_sha256"],
                "floor_top_z_m":audit["floor_z_m"],
                "measured_actor_markers":audit["actors"],
                "contact_meets_configured_tolerances":audit["contact_meets_configured_tolerances"],
                "anatomical_sole_certified":False,
                "selection_provenance":"fixture algorithm, not artist-authored anatomical ground truth",
                "note":"A failed contact tolerance is a measured failure, not a failed audit tool"}
    (out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True),"utf8")
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--external-glb",required=True)
    p.add_argument("--blender",default="blender")
    p.add_argument("--audit-only",action="store_true")
    a=p.parse_args(argv)
    result=run_fixture_plantar(a.out,a.external_glb,blender=a.blender,audit_only=a.audit_only)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["status"]=="passed_native_plantar_floor_measurement_only" else 1
if __name__=="__main__":raise SystemExit(main())
