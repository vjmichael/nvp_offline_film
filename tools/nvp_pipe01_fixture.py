"""PIPE-01 real Blender media: one frozen take -> two indexed presentations.

Native Blender renders *actual PNG bytes* in two Workbench styles. Every
rendered frame is SHA-verified in FilmIndex. This is NOT a video AI run and
does NOT claim audio synthesis or a final encoded MP4.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_presentation_pipeline import PresentationPipeline
from backend.nvp_film_index import FilmIndex
from tools.nvp_capture01_fixture import fixture as capture_fixture


def fixture(out):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    # Deliberately mutate the LIVE world after freezing the approved take.
    # Its own acceptance also independently reopens original cameras/motion.
    source=capture_fixture(root/"frozen_source",render_preview=False)
    if source["status"]!="passed_frozen_native_blender" or \
       not source["live_scene_was_invalidated"]:
        raise RuntimeError("Source CAPTURE-01 original-take test failed")
    studio=Studio(root/"frozen_source"/"film.sqlite3")
    project=studio.list_projects()[0]["id"]
    film=FilmIndex(studio)
    pipeline=PresentationPipeline(studio,film)
    original=pipeline.capture.reopen(project,"take_real_captured")
    original_sha=original["record"]["document_sha256"]
    prior_world_sha=original["audit"]["world_sha256"]
    root_out=root/"presentations"
    a=pipeline.render(project,"take_real_captured","presentation_studio",
                      root_out,style="studio",frame_mode="keyframes",width=320,height=180)
    b=pipeline.render(project,"take_real_captured","presentation_flat",
                      root_out,style="flat",frame_mode="keyframes",width=320,height=180)
    # Reopen independently, including every actual image byte from the store.
    reopened=PresentationPipeline(Studio(root/"frozen_source"/"film.sqlite3"))
    ra=reopened.reopen(project,"presentation_studio")
    rb=reopened.reopen(project,"presentation_flat")
    again=reopened.capture.reopen(project,"take_real_captured")
    if any(x["audit"]["frame_count"]!=4 or
           x["audit"]["shot_count"]!=2 or
           not x["audit"]["all_images_verified"] for x in (ra,rb)):
        raise RuntimeError("Rendered presentations do not cover the sampled frames")
    if again["record"]["document_sha256"]!=original_sha or \
       again["audit"]["world_sha256"]!=prior_world_sha:
        raise RuntimeError("Presentation job mutated authoritative world or original take")
    hashes_a=ra["audit"]["stored_image_hashes"]
    hashes_b=rb["audit"]["stored_image_hashes"]
    if hashes_a==hashes_b:
        raise RuntimeError("Studio and flat styles produced indistinguishable presentation media")
    deps=film.direct_dependents(project,"take_real_captured",1)
    if {x["object_id"] for x in deps}!={"presentation_studio","presentation_flat"}:
        raise RuntimeError("Expected both presentations to reference exact frozen take")
    result={
        "format":"nvp.pipe01.native.acceptance.v1",
        "status":"passed_two_real_blender_presentations",
        "backend":"blender_workbench","source_took_live_world_change":True,
        "source_take_sha256":original_sha,
        "source_world_sha256":prior_world_sha,
        "presentations":[
            {"id":"presentation_studio","style":"studio","receipt_sha":a["receipt"]["document_sha256"],
             "frame_hashes":hashes_a,"audit":ra["audit"]},
            {"id":"presentation_flat","style":"flat","receipt_sha":b["receipt"]["document_sha256"],
             "frame_hashes":hashes_b,"audit":rb["audit"]}],
        "native_blender":{
            "studio":film.read_revision(project,"presentation_studio")["data"]["engine_version"],
            "flat":film.read_revision(project,"presentation_flat")["data"]["engine_version"]},
        "unaffected_take_sha_verified":True,
        "frame_policy":"keyframes: two stills per shot, NOT full film",
        "full_mode_available_but_not_exercised":True,
        "audio_generated":False,
        "ai_video_generated":False
    }
    (root/"pipe01_summary.json").write_text(json.dumps(result,indent=2,sort_keys=True),"utf8")
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    args=p.parse_args()
    print(json.dumps(fixture(args.out),indent=2,sort_keys=True))


if __name__=="__main__":
    main()
