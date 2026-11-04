"""GRADE-UI-02B1: authentic two-shot EXR curve/reference FilmIndex proof."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from backend.nvp_grade_advanced import make_plan
from backend.nvp_grade_curves import CurveGradeWorkspace, make_curve_plan, neutral_curve
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from tools.nvp_grade_ui02a_fixture import fixture as original_native


def fixture(out):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    original_native(root/"source")
    db=root/"source"/"base"/"frozen"/"film.sqlite3"
    studio=Studio(db)
    idx=FilmIndex(studio)
    matches=[]
    for entry in studio.list_projects():
        try:
            idx.read_revision(entry["id"],"exr_source_16f")
        except KeyError:
            continue
        matches.append(entry["id"])
    if len(matches)!=1:
        raise RuntimeError("Could not isolate the actual frozen source film")
    project=matches[0]
    ws=CurveGradeWorkspace(studio,idx)
    timeline=ws.timeline(project,"exr_source_16f")
    if len(timeline["shots"])!=2 or timeline["frames"]!=16:
        raise RuntimeError("Two-shot original frozen timeline was modified")
    first,second=[s["shot_id"] for s in timeline["shots"]]
    neutral=make_curve_plan()
    test_curve=neutral_curve()
    test_curve["ev_offsets"][1]=.35
    test_curve["ev_offsets"][2]=.3
    edited=make_curve_plan(curves={first:test_curve})
    first_before=ws.render_curve_preview(project,"exr_source_16f",1,neutral)
    first_after=ws.render_curve_preview(project,"exr_source_16f",1,edited)
    second_before=ws.render_curve_preview(project,"exr_source_16f",9,neutral)
    second_after=ws.render_curve_preview(project,"exr_source_16f",9,edited)
    if first_before["png_sha256"]==first_after["png_sha256"]:
        raise RuntimeError("Curve editor did not change actual first-shot pixels")
    if second_before["png_sha256"]!=second_after["png_sha256"]:
        raise RuntimeError("First-shot tone curve leaked into the second shot")
    for preview in (first_before,first_after,second_before,second_after):
        scope=preview["scope"]
        pixels=timeline["width"]*timeline["height"]
        if (scope["pixels"]!=pixels or sum(scope["histogram"]["luma"])!=pixels or
            sum(map(sum,scope["waveform"]))!=pixels or
            sum(map(sum,scope["vectorscope"]))!=pixels):
            raise RuntimeError("Curve preview scopes do not conserve output pixels")
    # Inspectable reference calculation must NOT save a grade automatically.
    edits_before=len(idx.list_objects(project,kind="edit"))
    suggestion=ws.compare_reference(
        project,"exr_source_16f",target_frame=1,reference_frame=9,
        base_plan=make_plan())
    if (suggestion["status"]!="inspectable_heuristic_only_not_applied" or
        not -.75<=suggestion["suggested_exposure_stops"]<=.75 or
        len(idx.list_objects(project,kind="edit"))!=edits_before):
        raise RuntimeError("Reference comparison forged an automatic color edit")
    first_save=ws.save_curve(project,"exr_source_16f","shot_curves_native",edited,0)
    second_plan=make_curve_plan(curves={second:test_curve})
    second_save=ws.save_curve(project,"exr_source_16f","shot_curves_native",second_plan,1)
    restarted=CurveGradeWorkspace(Studio(db))
    old=restarted.reopen_curve(project,"shot_curves_native",1)
    new=restarted.reopen_curve(project,"shot_curves_native")
    if old["plan"]!=edited or new["plan"]!=second_plan:
        raise RuntimeError("Original curve versions lost across restart")
    try:
        restarted.save_curve(project,"exr_source_16f","shot_curves_native",edited,1)
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Stale curve revision overwrite incorrectly permitted")
    foreign=studio.create_project("Other color project","")["id"]
    try:
        restarted.reopen_curve(foreign,"shot_curves_native")
    except KeyError:
        pass
    else:
        raise RuntimeError("Cross-project curve edit incorrectly accessible")
    document=idx.read_revision(project,"shot_curves_native")
    path=idx._blob_path(project,document["document_sha256"])
    good=path.read_bytes()
    try:
        bad=bytearray(good);bad[-1]^=1
        path.write_bytes(bad)
        try:
            CurveGradeWorkspace(Studio(db)).reopen_curve(project,"shot_curves_native")
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Corrupted curve document incorrectly validated")
    finally:
        path.write_bytes(good)
    CurveGradeWorkspace(Studio(db)).reopen_curve(project,"shot_curves_native")
    if (idx.read_revision(project,"exr_source_16f")["document_sha256"]!=timeline["source_sha256"] or
        idx.read_revision(project,timeline["take_id"])["document_sha256"]!=timeline["take_sha256"]):
        raise RuntimeError("Curve experiment altered original source or Digital Take")
    images={
        "shot1_curve_neutral":first_before,
        "shot1_curve_graded":first_after,
        "shot2_curve_neutral":second_before,
        "shot2_curve_unchanged":second_after,
    }
    for name,p in images.items():
        data=base64.b64decode(p["png_base64"],validate=True)
        if hashlib.sha256(data).hexdigest()!=p["png_sha256"]:
            raise RuntimeError("Curve preview PNG evidence changed")
        (root/(name+".png")).write_bytes(data)
    report={
        "format":"nvp.grade.ui02b1.native.acceptance.v1",
        "status":"real_scene_linear_tone_curves_reference_advice_and_filmin_index_replay",
        "frames":16,"shots":timeline["shots"],
        "source_sha256":timeline["source_sha256"],
        "take_sha256":timeline["take_sha256"],
        "curve_shot1_only":True,
        "second_shot_identical_when_only_first_is_changed":True,
        "png_sha256s":{k:p["png_sha256"] for k,p in images.items()},
        "measured_pixels_per_scope":timeline["width"]*timeline["height"],
        "reference_match_advice":suggestion,
        "reference_not_automatically_saved":True,
        "revision1_sha256":first_save["sha256"],
        "revision2_sha256":second_save["sha256"],
        "reopened_two_revisions":True,
        "refused_stale_revision":True,
        "refused_corrupted_document":True,
        "refused_other_project":True,
        "source_take_unchanged":True,
        "director_approved":False,
        "calibrated_display":False,
        "final_movie_export":False,
    }
    (root/"grade_ui02b1_report.json").write_text(
        json.dumps(report,indent=2,sort_keys=True),encoding="utf8")
    return report


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    print(json.dumps(fixture(args.out),indent=2,sort_keys=True))
