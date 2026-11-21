"""Pinned external humanoid actual Blender mesh-marker contact correction.

This is *not* biomechanical validation of Cesium Man's unlabeled heel/ball.
The fixture intentionally approves only a toe candidate selected by a
deterministic algorithm and never certifies anatomical plantar landmarks.
The full three-marker contact plan has already been measured as infeasible.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_plantar_correction import PlantarCorrectionPlan
from backend.nvp_plantar_blender import run_native_marker_correction
from tools.nvp_prod06e2c2_fixture import run_fixture_plantar


def run_fixture(out,source,*,blender="blender",audit_only=False):
    out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=True)
    base=out/"real_plantar_baseline"
    previous=run_fixture_plantar(base,source,blender=blender,audit_only=audit_only,
                                fixture_active_roles={"left":["toe"],"right":["toe"]})
    if previous.get("status")!="passed_native_plantar_floor_measurement_only":
        return {"status":"failed","step":"native_plantar_baseline","result":previous}
    # We expect real contact to fail before correction. A future source that
    # already contacts correctly requires a separate fixture and baseline.
    if previous["contact_meets_configured_tolerances"]:
        return {"status":"failed","step":"unexpected_precorrected_fixture"}
    db=base/"real_ankle_ik"/"prod06e2a"/"prod06d_baseline"/"project"/"studio.sqlite"
    stage=base/"real_ankle_ik"/"native_footlock"/"ankle_locked.blend"
    if not db.is_file() or not stage.is_file():
        return {"status":"failed","step":"pristine_stage_missing"}
    studio=Studio(db);projects=studio.list_projects()
    if len(projects)!=1:raise RuntimeError("Expected one actual pinned fixture film")
    pid=projects[0]["id"];scenes=studio.get_project(pid)["scenes"]
    if len(scenes)!=1:raise RuntimeError("Expected one pinned authored scene")
    sid=scenes[0]["id"]
    svc=PlantarCorrectionPlan(studio)
    approved_actors=svc.plantar.export(pid,sid)["plantar"]["plan"]["actors"]
    plan={"actors":{rid:{"max_ankle_delta_m":.025,
                         "max_iterations":6,
                         "target_clearance_m":.001,
                         "max_joint_delta_deg":60.}
                    for rid in approved_actors}}
    p=svc.create(pid,sid)
    p=svc.configure(pid,sid,plan,p["revision"])
    p=svc.approve(pid,sid,p["revision"])
    actual=run_native_marker_correction(svc,pid,sid,stage,out/"native_contact_correction",
                                        blender=blender)
    actual["stage"]="nvp.prod06e2c3.bounded_marker_ik.v1"
    actual["test_marker_origin"]="fixture-proposed toe candidate, not artist-certified plantar anatomy"
    actual["full_sole_anatomy_verified"]=False
    (out/"result.json").write_text(json.dumps(actual,indent=2,sort_keys=True),"utf8")
    return actual


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True)
    ap.add_argument("--external-glb",required=True)
    ap.add_argument("--blender",default="blender")
    ap.add_argument("--audit-only",action="store_true")
    args=ap.parse_args(argv)
    result=run_fixture(args.out,args.external_glb,blender=args.blender,
                       audit_only=args.audit_only)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result.get("status")=="passed_native_marker_floor_correction_only" else 1


if __name__=="__main__":raise SystemExit(main())
