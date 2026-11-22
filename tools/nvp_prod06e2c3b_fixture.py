"""PROD-06E2C3B real imported Blender humanoid BVH surface acceptance.

A source Cesium Man is used strictly as a *source-licensed fixture*. There
is no reviewed heel/MT1/MT5/hallux annotation attached to this model yet,
so this command MUST NOT produce an anatomical certification success.
It does verify the current corrected toe candidate on an actual triangulated
floor, plus independent flat and sloped BVH geometry on native Blender.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_plantar_correction import PlantarCorrectionPlan
from backend.nvp_surface_bvh import run_native_bvh_geometry
from tools.nvp_prod06e2c3_fixture import run_fixture


def run_real_surface_fixture(out, external_glb, *, blender="blender",audit_only=False):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    base=out/"c3a_accepted_marker"
    prior=run_fixture(base,external_glb,blender=blender,audit_only=audit_only)
    if prior.get("status")!="passed_native_marker_floor_correction_only":
        return {"status":"failed","phase":"bounded_real_character_marker_correction",
                "prior":prior}
    blend=base/"native_contact_correction"/"corrected_contact.blend"
    db=base/"real_plantar_baseline"/"real_ankle_ik"/"prod06e2a"/"prod06d_baseline"/"project"/"studio.sqlite"
    if not blend.is_file() or not db.is_file():
        return {"status":"failed","phase":"missing_real_blender_prerequisites"}
    studio=Studio(db)
    projects=studio.list_projects()
    if len(projects)!=1:
        raise RuntimeError("Expected exactly one approved real character film fixture")
    pid=projects[0]["id"]
    scenes=studio.get_project(pid)["scenes"]
    if len(scenes)!=1:
        raise RuntimeError("Expected one approved source scene")
    svc=PlantarCorrectionPlan(studio)
    reviewed=run_native_bvh_geometry(
        svc,pid,scenes[0]["id"],blend,out/"real_native_bvh",
        blender=blender)
    if reviewed.get("status")=="passed_real_character_bvh_geometry_only":
        result={
            "status":reviewed["status"],
            "real_active_contact_marker_samples":reviewed["real_active_contact_marker_samples"],
            "flat_slope_world_gap_tests_m":reviewed["self_test_gaps_m"],
            "max_actual_marker_penetration_m":reviewed["max_active_penetration_m"],
            "max_actual_marker_gap_m":reviewed["max_active_gap_m"],
            "approved_floor_sha":reviewed["floor_sha"],
            "slope_geometry_queries_verified":reviewed["slope_queries_verified"],
            "real_actor_on_slope_verified":False,
            "plantar_anatomy_independently_certified":False,
            "medical_anatomy_annotation_available_for_cesium_man":False,
            "real_character_source_status":"pinned external Cesium Man; toe fixture is not certified plantar anatomy",
            "result_evidence":str(out/"real_native_bvh"/"reviewed_bvh_geometry.json")}
    else:
        result={"status":"failed","phase":"native_bvh_audit","details":reviewed}
    (out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True),"utf8")
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--external-glb",required=True)
    p.add_argument("--blender",default="blender")
    p.add_argument("--audit-only",action="store_true")
    args=p.parse_args(argv)
    result=run_real_surface_fixture(
        args.out,args.external_glb,blender=args.blender,audit_only=args.audit_only)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result.get("status")=="passed_real_character_bvh_geometry_only" else 1


if __name__=="__main__":raise SystemExit(main())
