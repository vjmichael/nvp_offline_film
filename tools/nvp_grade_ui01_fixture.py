"""GRADE-UI-01 actual frozen Digital Take -> EXR -> editable look -> real OCIO preview.

Uses the already accepted COLOR-01B2 source fixture, then proves immutable
edit revision history, after/neutral preview pixels, source and project
isolation, modified-file rejection, and independent Studio restart.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from backend.nvp_color_mastering import grade_recipe
from backend.nvp_grade_workspace import GradeWorkspace
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from tools.nvp_color01b2_fixture import fixture as full_exr_fixture


def fixture(out):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    mastered=full_exr_fixture(root/"frozen")
    db=root/"frozen"/"film.sqlite3"
    studio=Studio(db)
    # FilmIndex source identity is authoritative; fixture display titles
    # are presentation metadata and can differ between acceptance runs.
    matching=[]
    for project in studio.list_projects():
        try:
            FilmIndex(studio).read_revision(project["id"],"exr_source_16f")
        except KeyError:
            continue
        matching.append(project)
    if len(matching)!=1:
        raise RuntimeError("Expected exactly one project with the frozen 16-frame EXR source")
    pid=matching[0]["id"]
    workspace=GradeWorkspace(studio)
    candidates=workspace.sources(pid)
    source_id="exr_source_16f"
    source=next((x for x in candidates if x["id"]==source_id),None)
    if not source or source["frames"]!=16 or source["fps"]!=24:
        raise RuntimeError("Real 16-frame HALF source not exposed to grading UI")
    index=FilmIndex(studio)
    source_revision=index.read_revision(pid,source_id)["document_sha256"]
    take_revision=index.read_revision(pid,source["take_id"])["document_sha256"]
    neutral=workspace.preview(pid,source_id,1,grade_recipe())
    warm=grade_recipe(exposure_stops=0.15,red_gain=1.03,blue_gain=0.97)
    modified=workspace.preview(pid,source_id,1,warm)
    if (not neutral["bytes"].startswith(b"\x89PNG\r\n\x1a\n") or
        neutral["bytes"]==modified["bytes"] or modified["calibrated"] is not False):
        raise RuntimeError("Before/after technical OCIO PNGs were not genuinely different")
    (root/"grade_before_neutral.png").write_bytes(neutral["bytes"])
    (root/"grade_after_warm.png").write_bytes(modified["bytes"])
    first=workspace.save(pid,source_id,"look_director_draft",warm,0)
    second_grade=grade_recipe(exposure_stops=0.21,red_gain=1.04,blue_gain=0.97)
    second=workspace.save(pid,source_id,"look_director_draft",second_grade,1)
    if first["revision"]!=1 or second["revision"]!=2:
        raise RuntimeError("Saved grade did not preserve optimistic immutable revision history")
    restarted=GradeWorkspace(Studio(db))
    historic=restarted.reopen(pid,"look_director_draft",revision=1)
    current=restarted.reopen(pid,"look_director_draft",revision=2)
    if (historic["recipe"]!=warm or current["recipe"]!=second_grade or
        len(restarted.history(pid,"look_director_draft"))!=2):
        raise RuntimeError("FilmIndex grading revisions failed independent source-bound reopen")
    try:
        restarted.save(pid,source_id,"look_director_draft",grade_recipe(),expected_revision=1)
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Stale client grade write overwrote newer edits")
    try:
        other=next(x for x in studio.list_projects() if x["id"]!=pid)["id"]
        restarted.reopen(other,"look_director_draft")
    except KeyError:
        pass
    else:
        raise RuntimeError("Grading history leaked to another project")
    # Direct tamper of immutable FilmIndex edit document is rejected.
    sha=second["document_sha256"]
    blob=index._blob_path(pid,sha)
    good=blob.read_bytes()
    try:
        bad=bytearray(good)
        bad[-1]^=1
        blob.write_bytes(bad)
        try:
            GradeWorkspace(Studio(db)).reopen(pid,"look_director_draft")
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Tampered saved grade reopened as authentic")
    finally:
        blob.write_bytes(good)
    GradeWorkspace(Studio(db)).reopen(pid,"look_director_draft")
    if (index.read_revision(pid,source_id)["document_sha256"]!=source_revision or
        index.read_revision(pid,source["take_id"])["document_sha256"]!=take_revision):
        raise RuntimeError("Color grading UI changed the authoritative frozen source")
    summary={
        "format":"nvp.grade.ui01.native.acceptance.v1",
        "status":"verified_real_exr_ocio_before_after_and_immutable_grade_history",
        "source_id":source_id,"source_frames":16,
        "source_sha256":source_revision,"take_sha256":take_revision,
        "first_grade_revision_sha256":first["document_sha256"],
        "second_grade_revision_sha256":second["document_sha256"],
        "neutral_preview_sha256":hashlib.sha256(neutral["bytes"]).hexdigest(),
        "graded_preview_sha256":hashlib.sha256(modified["bytes"]).hexdigest(),
        "before_after_differ":True,
        "real_oc_software_preview":True,
        "source_take_unchanged":True,
        "source_exr_unchanged":True,
        "stored_grade_revisions":2,
        "stale_write_refused":True,
        "cross_project_refused":True,
        "corrupted_grade_refused":True,
        "restart_reopen_passed":True,
        "director_grade_approved":False,
        "master_video_automatically_exported_from_ui":False,
        "calibrated_viewer":False,
    }
    (root/"grade_ui01_report.json").write_text(
        json.dumps(summary,indent=2,sort_keys=True),"utf8")
    return summary


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    print(json.dumps(fixture(args.out),indent=2,sort_keys=True))
