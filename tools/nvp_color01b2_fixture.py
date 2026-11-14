"""Native full-motion COLOR-01B2: frozen take -> Cycles HALF EXR -> two graded MOVs."""
from __future__ import annotations
import json
from pathlib import Path
from shutil import copyfile

from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import FilmIndex
from backend.nvp_production_scene import ProductionScene
from backend.nvp_shot_sequence import ShotSequence
from backend.nvp_studio import Studio
from backend.nvp_world_state import WorldState
from backend.nvp_presentation_pipeline import PresentationPipeline, PBR_ENGINE
from backend.nvp_color_exr import PIXEL_EXR
from backend.nvp_color_mastering import ColorMasteringPipeline, grade_recipe


def fixture(out):
    root=Path(out).resolve();root.mkdir(parents=True,exist_ok=True)
    db=root/"film.sqlite3"
    studio=Studio(db)
    pid=studio.create_project("COLOR-01B2 Frozen Take","Actual grade mastering test")["id"]
    sid=studio.save_screenplay(pid,"INT. STUDIO - DAY\n\nMARA\nThe frame is alive.\n",0)["scenes"][0]["id"]
    prod=ProductionScene(studio)
    prod.create_asset(pid,{"name":"MARA","category":"character","dimensions":[.4,.4,1.68]})
    plan=prod.stage_scene(pid,sid,[8,6,3])
    plan=prod.solve_scene(pid,sid,plan["plan_revision"])
    prod.approve_scene(pid,sid,plan["plan_revision"])
    actor=next(x for x in prod.export_manifest(pid,sid)["instances"] if x["name"]=="MARA")
    bc=BlockingCamera(studio)
    bc.add_mark(pid,sid,actor["instance_id"],
                [actor["pose"]["x"]+.15,actor["pose"]["y"]],start_s=.05,end_s=.5)
    first=bc.solve_shot(pid,sid,[actor["instance_id"]],lens_mm=35)
    second=bc.solve_shot(pid,sid,[actor["instance_id"]],lens_mm=50)
    dialogue=bc.dialogue(pid,sid)["dialogue"][0]
    bc.set_dialogue_duration(pid,sid,dialogue["id"],.25)
    seq=ShotSequence(studio)
    state=seq.create(pid,sid)
    state=seq.add_shot(pid,sid,first["id"],8,"single",state["revision"])
    state=seq.add_shot(pid,sid,second["id"],8,"reaction",state["revision"])
    state=seq.place_cue(pid,sid,dialogue["id"],2,state["revision"])
    if state["review"]["errors"]:
        raise RuntimeError("Original frozen shot sequence rejected")
    if state["review"]["warnings"]:
        state=seq.acknowledge(pid,sid,[w["code"] for w in state["review"]["warnings"]],
                              state["revision"])
    seq.approve(pid,sid,state["revision"])
    DigitalCapture(studio).capture(pid,sid,"take_color01b2_16f")
    take=DigitalCapture(studio).reopen(pid,"take_color01b2_16f")
    take_sha=take["record"]["document_sha256"]
    WorldState(studio).set_human(pid,sid,actor["instance_id"],"visible",False,0)
    image=PresentationPipeline(Studio(db))
    image.render(pid,"take_color01b2_16f","exr_source_16f",root/"render",
        engine=PBR_ENGINE,style="pbr_studio",pixel_contract=PIXEL_EXR,
        frame_mode="full",width=256,height=144,samples=2,timeout=1800)
    src=PresentationPipeline(Studio(db)).reopen(pid,"exr_source_16f")
    if src["audit"]["pixel_contract"]!=PIXEL_EXR or src["audit"]["frame_count"]!=16:
        raise RuntimeError("Real source is not a contiguous 16-frame HALF EXR")
    masters=ColorMasteringPipeline(Studio(db))
    cases=[
      ("prores_422_hq_mov","prores_graded_neutral",grade_recipe()),
      ("dnxhr_hqx_mov","dnxhr_graded_warm",
       grade_recipe(exposure_stops=.15,saturation=1.05,red_gain=1.03,blue_gain=.97))
    ]
    result=[]
    for profile,oid,grade in cases:
        created=masters.encode(pid,"exr_source_16f",oid,root/"masters",
            output_profile=profile,recipe=grade,source_primaries_declared=True)
        new=ColorMasteringPipeline(Studio(db)).reopen(pid,oid,check_decode=True)
        if not new["check_decode"] or new["frame_count"]!=16:
            raise RuntimeError("Mastered MOV failed independent restart and full source regrade")
        rec=new["record"];audit=rec["data"]["video_audit"]
        edges={x["object_id"] for x in rec["dependencies"]}
        if edges!={"exr_source_16f","take_color01b2_16f"}:
            raise RuntimeError("Original Digital Take was lost from mastered video direct dependencies")
        if (audit["decoded"]["illegal_samples"]!=0 or
            audit["decoded"]["reference_comparison"]!="passed_bounded_lossy_10bit_yuv"):
            raise RuntimeError("Mastered MOV rejected by reference/YUV legal range audit")
        movie=root/(oid+".mov")
        copyfile(new["media"]["path"],movie)
        result.append({
            "id":oid,"profile":profile,"record_sha256":rec["document_sha256"],
            "mov_sha256":new["media"]["sha256"],"mov_path":str(movie),
            "movie_bytes":movie.stat().st_size,"grade":grade,"audit":audit,
            "filmin_index_direct_dependencies":sorted(edges),
        })
    if result[0]["mov_sha256"]==result[1]["mov_sha256"]:
        raise RuntimeError("Different actual graded ProRes and DNxHR outputs have same SHA")
    idx=FilmIndex(Studio(db))
    stored=idx._blob_path(pid,result[0]["mov_sha256"])
    original=stored.read_bytes()
    try:
        corrupt=bytearray(original);corrupt[-1]^=1;stored.write_bytes(corrupt)
        try:
            ColorMasteringPipeline(Studio(db)).reopen(pid,"prores_graded_neutral")
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Corrupted MOV was trusted by FilmIndex")
    finally:
        stored.write_bytes(original)
    ColorMasteringPipeline(Studio(db)).reopen(pid,"prores_graded_neutral",check_decode=True)
    if DigitalCapture(Studio(db)).reopen(pid,"take_color01b2_16f")["record"]["document_sha256"]!=take_sha:
        raise RuntimeError("Frozen Digital Take changed after grading")
    other=studio.create_project("Unrelated film","cross-project refusal")["id"]
    try:
        ColorMasteringPipeline(Studio(db)).reopen(other,"prores_graded_neutral")
    except KeyError:
        pass
    else:
        raise RuntimeError("Mastered MOV leaked across project boundaries")
    report={
        "format":"nvp.color01b2.native.acceptance.v1",
        "status":"real_two_codec_rec1886_graded_10bit_filmin_index_reopen_passed",
        "source_take_sha256":take_sha,
        "source_exr_revision_sha256":src["record"]["document_sha256"],
        "input":{"frames":16,"fps":24,"width":256,"height":144,
                 "pixel_contract":PIXEL_EXR},
        "outputs":result,"same_exr_source_two_grades":True,
        "independent_full_decoder_and_legal_range_audit":True,
        "corrupted_mov_refused":True,"source_unchanged":True,
        "fresh_process_reopen":True,"cross_project_refused":True,
        "not_certified":["full-length mastering","approved audio","color-calibrated display",
            "measured source primaries","cinema DCP XYZ","director-approved grade","Windows native Blender render"],
    }
    (root/"color01b2_report.json").write_text(json.dumps(report,indent=2,sort_keys=True),"utf8")
    return report


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--out",required=True)
    a=p.parse_args()
    print(json.dumps(fixture(a.out),indent=2))
