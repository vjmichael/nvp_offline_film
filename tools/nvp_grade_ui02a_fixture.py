"""GRADE-UI-02A: real frozen Blender EXR, two distinct shot looks and scopes.

Native acceptance is successful only when all the source/corruption, scopes,
round-trip grade and independently reopened shot identities are checked.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from backend.nvp_color_mastering import grade_recipe
from backend.nvp_grade_advanced import (
    AdvancedGradeWorkspace, make_plan, neutral_wheels,
)
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from tools.nvp_grade_ui01_fixture import fixture as existing_grade_acceptance


def fixture(root):
    root=Path(root).resolve()
    root.mkdir(parents=True,exist_ok=True)
    # Proven 01B2/01A original scene-linear Cycles render, including independent
    # full-frame 16-frame EXR source and previously proven edit restart.
    existing_grade_acceptance(root/"base")
    db=root/"base"/"frozen"/"film.sqlite3"
    studio=Studio(db)
    index=FilmIndex(studio)
    matches=[]
    for p in studio.list_projects():
        try:
            index.read_revision(p["id"],"exr_source_16f")
            matches.append(p["id"])
        except KeyError:
            continue
    if len(matches)!=1:
        raise RuntimeError("Ambiguous original native EXR FilmIndex identity")
    pid=matches[0]
    ws=AdvancedGradeWorkspace(studio,index)
    tl=ws.timeline(pid,"exr_source_16f")
    if tl["frames"]!=16 or len(tl["shots"])!=2:
        raise RuntimeError("Expected two actual frozen 8-frame authored shots")
    if [(s["start_frame"],s["end_frame"]) for s in tl["shots"]] != [(1,8),(9,16)]:
        raise RuntimeError("NVP authored shot boundaries have shifted")
    a,b=[s["shot_id"] for s in tl["shots"]]
    neutral=make_plan()
    shot_a=neutral_wheels();shot_a["gain"]=[1.08,1.,.92]
    shot_b=neutral_wheels();shot_b["lift"]=[.018,0,-.012]
    changed=make_plan(grade_recipe(),{a:shot_a,b:shot_b})
    before_a=ws.render_scope_preview(pid,"exr_source_16f",1,neutral)
    after_a=ws.render_scope_preview(pid,"exr_source_16f",1,changed)
    before_b=ws.render_scope_preview(pid,"exr_source_16f",9,neutral)
    after_b=ws.render_scope_preview(pid,"exr_source_16f",9,changed)
    if (before_a["png_sha256"]==after_a["png_sha256"] or
        before_b["png_sha256"]==after_b["png_sha256"]):
        raise RuntimeError("Shot-level color controls produced no physical pixel changes")
    unaffected=make_plan(grade_recipe(),{b:shot_b})
    frame1=ws.render_scope_preview(pid,"exr_source_16f",1,unaffected)
    if frame1["png_sha256"]!=before_a["png_sha256"]:
        raise RuntimeError("Grade of shot B erroneously modified shot A's pixels")
    for frame in (before_a,after_a,before_b,after_b):
        scope=frame["scope"]
        if (scope["pixels"]!=tl["width"]*tl["height"] or
            sum(scope["histogram"]["luma"])!=scope["pixels"] or
            sum(map(sum,scope["waveform"]))!=scope["pixels"] or
            sum(map(sum,scope["vectorscope"]))!=scope["pixels"]):
            raise RuntimeError("Real scope sample counts do not conserve pixels")
    first=ws.save_advanced(pid,"exr_source_16f","shot_look_native",changed,0)
    second_plan=make_plan(grade_recipe(exposure_stops=.12),{a:shot_a,b:shot_b})
    second=ws.save_advanced(pid,"exr_source_16f","shot_look_native",second_plan,1)
    reopened=AdvancedGradeWorkspace(Studio(db))
    old=reopened.reopen_advanced(pid,"shot_look_native",revision=1)
    current=reopened.reopen_advanced(pid,"shot_look_native")
    if (old["plan"]!=changed or current["plan"]!=second_plan or
        old["timeline"]["timeline_sha256"]!=tl["timeline_sha256"]):
        raise RuntimeError("Shot-graded edit history changed during restart")
    try:
        reopened.save_advanced(pid,"exr_source_16f","shot_look_native",changed,1)
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Stale advanced shot edit rewrote newer revision")
    project=studio.create_project("Other production","unauthorized source")["id"]
    try:
        reopened.reopen_advanced(project,"shot_look_native")
    except KeyError:
        pass
    else:
        raise RuntimeError("Cross-project advanced shot edit was accessible")
    doc=index.read_revision(pid,"shot_look_native")
    saved_path=index._blob_path(pid,doc["document_sha256"])
    correct=saved_path.read_bytes()
    try:
        corrupted=bytearray(correct);corrupted[-1]^=1
        saved_path.write_bytes(corrupted)
        try:
            AdvancedGradeWorkspace(Studio(db)).reopen_advanced(pid,"shot_look_native")
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Corrupted shot-look document incorrectly reopened")
    finally:
        saved_path.write_bytes(correct)
    reopened.reopen_advanced(pid,"shot_look_native")
    source=index.read_revision(pid,"exr_source_16f")
    if source["document_sha256"]!=tl["source_sha256"]:
        raise RuntimeError("Original HALF EXR presentation was modified")
    take=index.read_revision(pid,tl["take_id"])
    if take["document_sha256"]!=tl["take_sha256"]:
        raise RuntimeError("Original Digital Take was modified")
    import base64
    images={"shot1_neutral":before_a,"shot1_graded":after_a,
            "shot2_neutral":before_b,"shot2_graded":after_b}
    for key,result in images.items():
        (root/(key+".png")).write_bytes(base64.b64decode(result["png_base64"]))
    proof={
        "format":"nvp.grade.ui02a.native.acceptance.v1",
        "status":"independently_verified_real_two_shot_lgg_scopes_and_revision_replay",
        "frames":tl["frames"],"shots":tl["shots"],
        "source_sha256":tl["source_sha256"],"take_sha256":tl["take_sha256"],
        "timeline_sha256":tl["timeline_sha256"],
        "first_edit_sha256":first["sha256"],"second_edit_sha256":second["sha256"],
        "scope_type":"post_aces_rgb48_exact_counts",
        "scope_pixels_each":tl["width"]*tl["height"],
        "scope_histogram_waveform_vectorscope_total_conservation":True,
        "true_source_preview_sha256":{key:value["png_sha256"] for key,value in images.items()},
        "shot1_unchanged_by_shot2_edit":True,
        "stale_revisions_rejected":True,
        "cross_project_rejected":True,
        "corrupted_edit_rejected":True,
        "reopen_after_recovery":True,
        "original_take_and_source_unchanged":True,
        "creative_approval":False,
        "calibrated_monitor":False,
        "film_export_from_advanced_ui":False,
    }
    (root/"grade_ui02a_report.json").write_text(
        json.dumps(proof,sort_keys=True,indent=2),encoding="utf8")
    return proof


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--out",required=True)
    args=p.parse_args()
    print(json.dumps(fixture(args.out),indent=2,sort_keys=True))
