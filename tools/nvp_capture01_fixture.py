"""Real native Blender save/reopen/audit from an independently reopened frozen take.

Unlike PROD-05's live scene fixture, this explicitly changes the live
WorldState AFTER capture, invalidating the live sequence. Blender then rebuilds
and audits the original performance/cameras solely from FilmIndex bytes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_digital_capture import DigitalCapture, run_frozen_take_acceptance
from backend.nvp_film_index import FilmIndex
from backend.nvp_production_scene import ProductionScene
from backend.nvp_shot_sequence import ShotSequence
from backend.nvp_studio import Studio
from backend.nvp_world_state import WorldState


def fixture(out, *, render_preview=True):
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=True)
    studio = Studio(root / "film.sqlite3")
    pid = studio.create_project("CAPTURE-01 real Blender replay","Approved frozen actor and cut")["id"]
    sid = studio.save_screenplay(
        pid, "INT. FILM SET - DAY\n\nMARA\nThe key is here.\n", 0)["scenes"][0]["id"]
    prod = ProductionScene(studio)
    prod.create_asset(pid,{"name":"MARA","category":"character","dimensions":[.4,.4,1.68]})
    plan = prod.stage_scene(pid,sid,[8,6,3])
    plan = prod.solve_scene(pid,sid,plan["plan_revision"])
    prod.approve_scene(pid,sid,plan["plan_revision"])
    actor = next(i for i in prod.export_manifest(pid,sid)["instances"] if i["name"]=="MARA")
    bc = BlockingCamera(studio)
    bc.add_mark(pid,sid,actor["instance_id"],
                [actor["pose"]["x"]+.5,actor["pose"]["y"]],start_s=.8,end_s=3.)
    cam_a = bc.solve_shot(pid,sid,[actor["instance_id"]],lens_mm=50)
    cam_b = bc.solve_shot(pid,sid,[actor["instance_id"]],lens_mm=35)
    line = bc.dialogue(pid,sid)["dialogue"][0]
    bc.set_dialogue_duration(pid,sid,line["id"],.8)
    seq = ShotSequence(studio)
    state = seq.create(pid,sid)
    state = seq.add_shot(pid,sid,cam_a["id"],60,"single",state["revision"])
    state = seq.add_shot(pid,sid,cam_b["id"],60,"reaction",state["revision"])
    state = seq.place_cue(pid,sid,line["id"],5,state["revision"])
    if state["review"]["errors"]:
        raise RuntimeError("Cannot capture invalid source: "+repr(state["review"]))
    if state["review"]["warnings"]:
        state = seq.acknowledge(pid,sid,[w["code"] for w in state["review"]["warnings"]],
                                state["revision"])
    approved = seq.approve(pid,sid,state["revision"])
    if approved["status"]!="approved":
        raise RuntimeError("Director approval failed")

    frozen = DigitalCapture(studio, FilmIndex(studio))
    created = frozen.capture(pid,sid,"take_real_captured")
    originally = frozen.reopen(pid,"take_real_captured")
    if len(originally["timed_take"]["actors"][0]["marks"])!=1:
        raise RuntimeError("Frozen package dropped the source moving actor")

    # Deliberately diverge from the captured source before native Blender runs.
    # The approved old take must continue to play with the old visible actor.
    WorldState(studio).set_human(pid,sid,actor["instance_id"],"visible",False,0)
    try:
        seq.export(pid,sid)
    except RuntimeError:
        live_stale = True
    else:
        live_stale = False
    if not live_stale:
        raise RuntimeError("Test did not invalidate live source before replay")

    # Open via a NEW Studio and FilmIndex; never reuse in-memory live scene.
    restored = DigitalCapture(Studio(root/"film.sqlite3"))
    verified = restored.reopen(pid,"take_real_captured")
    if verified["audit"]!=created["audit"]:
        raise RuntimeError("Frozen source was altered during restart/live edit")
    result = run_frozen_take_acceptance(
        restored,pid,"take_real_captured",root/"frozen_blender",
        render_preview=render_preview)
    expected = "passed_blender" if render_preview else "passed_blender_audit_only"
    if result["status"]!=expected:
        raise RuntimeError("Frozen-source native Blender replay failed: "+repr(result))
    report = {"status":"passed_frozen_native_blender",
              "capture_source_sha256":created["receipt"]["document_sha256"],
              "live_scene_was_invalidated":live_stale,
              "source_actor_moved":True,
              "source_camera_count":len(verified["timed_take"]["shots"]),
              "capture_audit":verified["audit"],
              "native_audit":result}
    (root/"frozen_capture_result.json").write_text(
        json.dumps(report,indent=2,sort_keys=True),"utf8")
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    parser.add_argument("--audit-only",action="store_true")
    args=parser.parse_args()
    print(json.dumps(fixture(args.out,render_preview=not args.audit_only),indent=2))


if __name__=="__main__":
    main()
