"""PIPE-01B independent native cinema workflow: frozen source -> MP4 and ProRes.

Live scene changes AFTER capture. Actual Blender renders 16-frame 24fps
Workbench and Cycles sources. FFmpeg creates two H.264 review clips and a
professional ProRes 422 HQ QuickTime MOV from *exactly the existing PBR
source frames* without rerendering. FFprobe, full decode and SHA audit follow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import FilmIndex
from backend.nvp_full_motion import FullMotionPipeline
from backend.nvp_production_scene import ProductionScene
from backend.nvp_shot_sequence import ShotSequence
from backend.nvp_studio import Studio
from backend.nvp_world_state import WorldState


def fixture(out):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    db=root/"film.sqlite3"
    studio=Studio(db)
    pid=studio.create_project("PIPE-01B First Full Motion","Actual rendered source-to-film")["id"]
    sid=studio.save_screenplay(pid,
        "INT. SET - NIGHT\n\nMARA\nThe door is locked.\n",0)["scenes"][0]["id"]
    prod=ProductionScene(studio)
    prod.create_asset(pid,{"name":"MARA","category":"character","dimensions":[.4,.4,1.68]})
    stage=prod.stage_scene(pid,sid,[8,6,3])
    stage=prod.solve_scene(pid,sid,stage["plan_revision"])
    prod.approve_scene(pid,sid,stage["plan_revision"])
    actor=next(x for x in prod.export_manifest(pid,sid)["instances"] if x["name"]=="MARA")
    bc=BlockingCamera(studio)
    bc.add_mark(pid,sid,actor["instance_id"],
                [actor["pose"]["x"]+.15,actor["pose"]["y"]],
                start_s=.05,end_s=.48)
    ca=bc.solve_shot(pid,sid,[actor["instance_id"]],lens_mm=35)
    cb=bc.solve_shot(pid,sid,[actor["instance_id"]],lens_mm=50)
    line=bc.dialogue(pid,sid)["dialogue"][0]
    bc.set_dialogue_duration(pid,sid,line["id"],.25)
    seq=ShotSequence(studio)
    state=seq.create(pid,sid)
    state=seq.add_shot(pid,sid,ca["id"],8,"single",state["revision"])
    state=seq.add_shot(pid,sid,cb["id"],8,"reaction",state["revision"])
    state=seq.place_cue(pid,sid,line["id"],2,state["revision"])
    if state["review"]["errors"]:
        raise RuntimeError("Director blocking/cue invalid: "+repr(state["review"]))
    if state["review"]["warnings"]:
        state=seq.acknowledge(pid,sid,
            [x["code"] for x in state["review"]["warnings"]],state["revision"])
    seq.approve(pid,sid,state["revision"])
    frozen=DigitalCapture(studio)
    frozen.capture(pid,sid,"take_full_motion")
    saved=frozen.reopen(pid,"take_full_motion")
    original_sha=saved["record"]["document_sha256"]
    WorldState(studio).set_human(pid,sid,actor["instance_id"],"visible",False,0)
    try:
        seq.export(pid,sid)
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Fixture did not invalidate live scene")
    studio=Studio(db)
    movies=FullMotionPipeline(studio)
    a=movies.render_video(pid,"take_full_motion","motion_preview",root/"renders",
        engine="blender_workbench",style="flat",width=128,height=72,
        samples=2,timeout=1200)
    b=movies.render_video(pid,"take_full_motion","motion_pbr",root/"renders",
        engine="blender_cycles",style="pbr_studio",width=256,height=144,
        samples=4,timeout=1200)
    pro=movies.render_video(pid,"take_full_motion","motion_prores_hq",root/"renders",
        engine="blender_cycles",style="pbr_studio",width=256,height=144,
        samples=4,timeout=1200,output_profile="prores_422_hq_mov",
        source_frames_id="motion_pbr_frames")
    dnx=movies.render_video(pid,"take_full_motion","motion_dnxhr_hqx",root/"renders",
        engine="blender_cycles",style="pbr_studio",width=256,height=144,
        samples=4,timeout=1200,output_profile="dnxhr_hqx_mov",
        source_frames_id="motion_pbr_frames")
    fresh=FullMotionPipeline(Studio(db))
    check_a=fresh.reopen(pid,"motion_preview",check_decode=True)
    check_b=fresh.reopen(pid,"motion_pbr",check_decode=True)
    check_pro=fresh.reopen(pid,"motion_prores_hq",check_decode=True)
    check_dnx=fresh.reopen(pid,"motion_dnxhr_hqx",check_decode=True)
    take_again=fresh.capture.reopen(pid,"take_full_motion")
    if take_again["record"]["document_sha256"]!=original_sha:
        raise RuntimeError("Professional and review video jobs mutated original source take")
    if check_a["media"]["sha256"]==check_b["media"]["sha256"]:
        raise RuntimeError("Physically lit PBR and flat video clips are identical")
    if not (check_a["audit"]["frames"]==16 and check_b["audit"]["frames"]==16 and
            check_pro["audit"]["frames"]==16 and check_dnx["audit"]["frames"]==16 and
            check_a["audit"]["all_source_frames_verified"] and
            check_b["audit"]["all_source_frames_verified"] and
            check_pro["audit"]["all_source_frames_verified"] and
            check_dnx["audit"]["all_source_frames_verified"]):
        raise RuntimeError("Full-frame verification did not confirm all source frames")
    if check_a["record"]["data"]["dialogue_timeline"]!=check_b["record"]["data"]["dialogue_timeline"]:
        raise RuntimeError("Backend render changed intended audio timing")
    if (check_pro["audit"]["codec"]!="prores" or
        check_pro["audit"]["container"]!="mov" or
        check_pro["record"]["data"]["output_profile"]!="prores_422_hq_mov" or
        check_pro["record"]["data"]["codec_receipt"].get("codec_tag")!="apch" or
        check_pro["record"]["data"]["codec_receipt"]["pix_fmt"]!="yuv422p10le"):
        raise RuntimeError("Professional ProRes 422 HQ codec/profile/depth not independently confirmed")
    if (check_pro["record"]["data"]["source_frames_sha256"] !=
        check_b["record"]["data"]["source_frames_sha256"] or
        check_pro["record"]["data"]["dialogue_timeline"] !=
        check_b["record"]["data"]["dialogue_timeline"]):
        raise RuntimeError("Professional output should reuse the same frame and audio-time sources")
    if (check_dnx["audit"]["codec"]!="dnxhd" or
        check_dnx["record"]["data"]["output_profile"]!="dnxhr_hqx_mov" or
        check_dnx["record"]["data"]["codec_receipt"].get("codec_profile")!="DNXHR HQX" or
        check_dnx["record"]["data"]["codec_receipt"]["pix_fmt"]!="yuv422p10le" or
        check_dnx["record"]["data"]["source_frames_sha256"] !=
        check_pro["record"]["data"]["source_frames_sha256"]):
        raise RuntimeError("DNxHR HQX encode/decode/source reuse not independently verified")
    deps=fresh.index.direct_dependents(pid,"take_full_motion",1)
    expected={"motion_preview","motion_pbr","motion_preview_frames",
              "motion_pbr_frames","motion_prores_hq","motion_dnxhr_hqx"}
    if {r["object_id"] for r in deps}!=expected:
        raise RuntimeError("Source-to-presentation lineage differs between engines")
    report={
        "format":"nvp.pipe01b.native.acceptance.v1",
        "status":"passed_h264_prores_and_dnxhr_24fps",
        "take_sha256":original_sha,
        "world_modified_after_capture":True,
        "source_actor_had_motion":bool(saved["timed_take"]["actors"][0]["marks"]),
        "frame_count":16,"fps":24,"cameras":len(saved["timed_take"]["shots"]),
        "presentations":[{
           "id":check["record"]["object_id"],
           "engine":check["record"]["data"]["engine"],
           "style":check["record"]["data"]["style"],
           "video_sha256":check["media"]["sha256"],
           "video_size_bytes":check["media"]["size_bytes"],
           "video_path":check["media"]["path"],
           "independent_decoder":check["audit"]["video_independently_decoded"],
           "source_frames_verified":check["audit"]["all_source_frames_verified"],
           "audio_status":check["audit"]["audio_status"],
           "export_profile":check["record"]["data"]["output_profile"],
           "codec_receipt":check["record"]["data"]["codec_receipt"]
        } for check in (check_a,check_b,check_pro,check_dnx)],
        "professional_reencode_reused_exact_pbr_frame_sha":True,
        "limit":"ProRes HQ is 10-bit 4:2:2 *encoding* from existing 8-bit proxy PNGs; not genuine 10-bit/photoreal source or a theatrical DCP; no audio waveforms"
    }
    (root/"pipe01b_summary.json").write_text(json.dumps(report,indent=2,sort_keys=True),"utf-8")
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    args=p.parse_args()
    print(json.dumps(fixture(args.out),indent=2,sort_keys=True))

if __name__=="__main__":
    main()
