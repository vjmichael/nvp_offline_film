"""COLOR-01B: real frozen FilmIndex Cycles EXR -> pinned ACES 2 SDR PNG16.

This is independently decoded display-referred RGB48 review imagery, not an
approved grade, calibrated mastering monitor, sound master, or theatrical DCP.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_color_ocio import ColorReviewPipeline, color_policy, _deps, apply_view
from tools.nvp_color01a_fixture import fixture as source_fixture


def fixture(output):
    root=Path(output).resolve()
    root.mkdir(parents=True,exist_ok=True)
    source=source_fixture(root/"real_exr")
    db=root/"real_exr"/"frozen"/"film.sqlite3"
    studio=Studio(db)
    projects=studio.list_projects()
    if len(projects)!=1:
        raise RuntimeError("Not exactly one independently reopened source film")
    project_id=projects[0]["id"]
    index=FilmIndex(studio)
    original=index.read_revision(project_id,"take_real_captured")
    source_record=index.read_revision(project_id,"color01a_scene_linear_exr")
    if source_record["data"].get("pixel_contract")!="openexr_half_rgba_scene_linear":
        raise RuntimeError("Source frames were not genuinely scene-linear EXR")
    pipeline=ColorReviewPipeline(studio,index)
    # Test fixture explicitly exercises the required creator source-space
    # declaration, which is not a real director sign-off of a finished master.
    result=pipeline.render(project_id,"color01a_scene_linear_exr",
        "color01b_aces2_sdr_review",root/"graded",
        director_source_space_approval=True)
    receipt=result["record"]
    restarted=ColorReviewPipeline(Studio(db))
    readback=restarted.reopen(project_id,"color01b_aces2_sdr_review",
                              check_decode=True)
    if (readback["record"]["document_sha256"]!=receipt["document_sha256"] or
        readback["frame_count"]!=4 or not readback["decoded"]):
        raise RuntimeError("Independent FilmIndex/PNG16 restart-readback failed")
    if index.read_revision(project_id,"take_real_captured")["document_sha256"]!=original["document_sha256"]:
        raise RuntimeError("Original source Digital Take was mutated")
    if index.read_revision(project_id,"color01a_scene_linear_exr")["document_sha256"]!=source_record["document_sha256"]:
        raise RuntimeError("Original Cycles EXR presentation was mutated")
    rows=readback["record"]["data"]["graded_frames"]
    with (root/"graded"/"COLOR01B_SHA256SUMS").open("w",encoding="utf8") as f:
        for row in rows:
            f.write(row["png16_sha256"]+"  "+f"frame_{row['frame']:06d}.png" + "\n")
            original_blob=index.get_blob(project_id,row["png16_sha256"])
            (root/"graded"/f"frame_{row['frame']:06d}.png").write_bytes(original_blob)
    # Tamper with one *indexed* output, require SHA rejection, restore, reopen.
    file=index._blob_path(project_id,rows[0]["png16_sha256"])
    original_png=file.read_bytes()
    try:
        fake=bytearray(original_png);fake[-1]^=1
        file.write_bytes(fake)
        try:
            ColorReviewPipeline(Studio(db)).reopen(
                project_id,"color01b_aces2_sdr_review",check_decode=False)
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Corrupted color-managed PNG reopened as genuine")
    finally:
        file.write_bytes(original_png)
    again=ColorReviewPipeline(Studio(db)).reopen(
        project_id,"color01b_aces2_sdr_review",check_decode=True)
    if not again["decoded"]:
        raise RuntimeError("Recovery after corruption did not independently decode")
    # A forged but structurally valid FilmIndex color receipt must not pass
    # simply because it points to legitimate PNGs and approved EXR frames.
    forged=copy.deepcopy(readback["record"]["data"])
    forged["color_policy"]["view"]="Raw"
    forged_id="color01b_forged_raw_view"
    idx2=FilmIndex(Studio(db))
    idx2.register_revision(project_id,forged_id,"presentation",forged,
        dependencies=[
            {"object_id":"color01a_scene_linear_exr","revision":1,"role":"presentation"},
            {"object_id":"take_real_captured","revision":1,"role":"source_take"},
        ])
    try:
        ColorReviewPipeline(Studio(db)).reopen(project_id,forged_id)
    except RuntimeError as err:
        if "processor identity" not in str(err):
            raise
    else:
        raise RuntimeError("Forged Raw OCIO view passed color-managed reopen")
    # Deliberately mix approved and disapproved source-project identities.
    other=studio.create_project("COLOR-01B other project","source isolation")["id"]
    try:
        restarted.reopen(other,"color01b_aces2_sdr_review")
    except KeyError:
        pass
    else:
        raise RuntimeError("Color review leaked across project scopes")
    _,np=_deps()
    policy,cpu=color_policy()
    hdr=np.array([[[2.25,.370361328125,.05859375,1.]]],dtype=np.float32)
    quant,stats=apply_view(hdr,cpu)
    report={
        "format":"nvp.color01b.native.acceptance.v1",
        "status":"real_aces2_sdr16_review_filmin_index_restart_verified",
        "source_color_contract":"linear_rec709_primaries_creator_declared_not_colorimeter_verified",
        "scene_linear_original_exr_sha256":source_record["document_sha256"],
        "source_take_sha256":original["document_sha256"],
        "graded_review_revision_sha256":receipt["document_sha256"],
        "source_frames":len(source_record["data"]["rendered_frames"]),
        "graded_frames":len(rows),
        "all_png16_independently_decoded":True,
        "reference_source_hdr_rgb":[float(x) for x in hdr[0,0,:3]],
        "reference_display_16bit_rgb":[int(x) for x in quant[0,0]],
        "reference_display_clip_audit":stats,
        "ocio_policy":policy,
        "outputs":[{
            "frame":row["frame"],"exr_sha256":row["source_exr_sha256"],
            "png16_sha256":row["png16_sha256"],
            "raw_rgb48_sha256":row["decoded_rgb48le_sha256"],
            "clip_audit":row["clip_audit"]
        } for row in rows],
        "source_take_unchanged":True,
        "exr_source_unchanged":True,
        "tampered_png_rejected":True,
        "forged_ocio_view_refused":True,
        "cross_project_read_rejected":True,
        "restart_and_recovery":True,
        "grading_and_color_calibration_approved":False,
        "final_video_master_approved":False,
    }
    (root/"color01b_report.json").write_text(
        json.dumps(report,indent=2,sort_keys=True),encoding="utf8")
    return report


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    print(json.dumps(fixture(args.out),indent=2,sort_keys=True))
