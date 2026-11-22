"""B8: genuine frozen Digital Take -> native Blender animation -> independent audit.

The creator action below is an isolated CI fixture, NOT an installed desktop
user-presence verifier. Blender worker processes, camera/actor animation,
resource admission and output bytes are genuine; no Lu or external AI used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_frozen_take_stage import stage_frozen_take,verify_frozen_stage
from backend.nvp_frozen_take_render import NativeFrozenTakeRender
from backend.nvp_frozen_take_audit import NativeFrozenTakeAuditor
from backend.nvp_frozen_take_presentation import publish_verified_preview,verify_presentation
from backend.nvp_production_scene import ProductionScene
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_shot_sequence import ShotSequence
from backend.nvp_studio import Studio
from backend.nvp_world_state import WorldState


def prepare_capture(root):
    """Use actual approved Studio/DigitalCapture/FIlmIndex, not synthetic take JSON."""
    studio=Studio(Path(root)/"film.sqlite3")
    pid=studio.create_project("Captured film shot","Frozen original performance")["id"]
    sid=studio.save_screenplay(pid,
      "INT. FILM STUDIO - DAY\n\nMARA\nWe are moving.\n\nBOB\nConfirmed.\n",0)["scenes"][0]["id"]
    prod=ProductionScene(studio)
    for name in ("MARA","BOB"):
        prod.create_asset(pid,{"name":name,"category":"character","dimensions":[.4,.4,1.7]})
    p=prod.stage_scene(pid,sid,[10,8,3])
    p=prod.solve_scene(pid,sid,p["plan_revision"])
    prod.approve_scene(pid,sid,p["plan_revision"])
    world=prod.export_manifest(pid,sid)
    actors={x["name"]:x for x in world["instances"]}
    bc=BlockingCamera(studio)
    mara=actors["MARA"]
    bc.add_mark(pid,sid,mara["instance_id"],
                [mara["pose"]["x"]+.5,mara["pose"]["y"]],start_s=0,end_s=2)
    camera=bc.solve_shot(pid,sid,[mara["instance_id"]])
    lines=bc.dialogue(pid,sid)["dialogue"]
    for line in lines:
        bc.set_dialogue_duration(pid,sid,line["id"],1.5)
    seq=ShotSequence(studio)
    seq.create(pid,sid)
    seq.add_shot(pid,sid,camera["id"],48,"single",0)
    seq.add_shot(pid,sid,camera["id"],72,"reaction",1)
    seq.place_cue(pid,sid,lines[0]["id"],1,2)
    seq.place_cue(pid,sid,lines[1]["id"],49,3)
    state=seq.read(pid,sid)
    if state["review"]["errors"]:
        raise RuntimeError("Native frozen capture source has invalid measured dialogue/cuts: "+
                           str(state["review"]["errors"]))
    if state["review"]["warnings"]:
        state=seq.acknowledge(pid,sid,
              [row["code"] for row in state["review"]["warnings"]],state["revision"])
    seq.approve(pid,sid,state["revision"])
    capture=DigitalCapture(studio)
    receipt=capture.capture(pid,sid,"take_original")
    reopened=capture.reopen(pid,"take_original")
    if (receipt["audit"]["frames"]!=120 or
        len(reopened["timed_take"]["shots"])!=2 or
        not reopened["timed_take"]["actors"][0]["marks"]):
        raise RuntimeError("Real frozen capture lacked two shots or actor motion")
    return studio,capture,pid,sid,"take_original",actors


def fixture(out,blender):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    executable=Path(shutil.which(blender) or blender).resolve()
    if not executable.is_file():
        raise RuntimeError("Blender missing; cannot claim native frozen-take acceptance")
    version=subprocess.run([str(executable),"-b","--version"],
                           capture_output=True,text=True,check=True,timeout=20).stdout.splitlines()[0].strip()
    if not version.startswith("Blender "):
        raise RuntimeError("Unexpected Blender version output")

    studio,capture,pid,sid,tid,actors=prepare_capture(root)
    frozen_before=capture.reopen(pid,tid)
    # Demonstrate a director edit AFTER capture cannot mutate frozen take.
    changed=WorldState(studio).read(pid,sid)
    WorldState(studio).set_human(pid,sid,actors["BOB"]["instance_id"],
                                "visible",False,changed["revision"])
    frozen_after=capture.reopen(pid,tid)
    if frozen_before["audit"]!=frozen_after["audit"]:
        raise RuntimeError("Frozen Digital Take changed after editable world mutation")

    ledger=TaskLedger(root/"activity")
    worker=BlenderWorkerSupervisor(root/"workers",blender_executable=executable,
        blender_sha256=sha_file(executable),blender_version=version,activity_ledger=ledger)
    staged=stage_frozen_take(capture,worker,pid,tid,ram_mb=2048)
    if not verify_frozen_stage(capture,worker,staged):
        raise RuntimeError("Frozen staged source validation refused")
    event=object()
    events=[]
    def fixture_creator_action(incoming,scope):
        events.append(scope)
        return (incoming is event and scope.get("project_id")==pid and
                scope.get("take_id")==tid and
                scope.get("capture_sha256")==staged["capture_sha256"])
    host=NativeFrozenTakeRender(capture,worker,ledger,verify_creator_action=fixture_creator_action)
    grant=host.consent_from_trusted_native_action(staged,event,duration_s=1800)
    queued=host.enqueue_approved(staged,grant["approval_id"],lane="interactive")
    if queued["state"]!="QUEUED":raise RuntimeError("Native timed build did not queue")
    sampler=ledger.sampler
    ledger.sampler=lambda:ResourceSnapshot(1,16384,1024,0,())
    refused=host.run_next()
    if refused["state"]!="QUEUED" or (staged["stage_dir"]/"frozen_take.blend").exists():
        raise RuntimeError("Frozen take Blender was not denied under unsafe RAM")
    ledger.sampler=sampler
    built=host.run_next()
    if built["state"]!="SUCCEEDED":
        raise RuntimeError("Real timed native Blender build did not complete: "+str(built))
    checked=NativeFrozenTakeAuditor(host).reopen_and_verify(grant["approval_id"],ram_mb=2048)
    if checked["state"]!="VERIFIED" or not checked["actual_native_blender_reopen"]:
        raise RuntimeError("Independent Blender actor-motion audit did not pass: "+str(checked))
    repeated=NativeFrozenTakeAuditor(host).reopen_and_verify(grant["approval_id"],ram_mb=2048)
    if repeated!=checked:
        raise RuntimeError("Frozen take verified audit changed after restart")
    if ledger.snapshot()["reservations"]["ram_mb"]!=0:
        raise RuntimeError("Frozen native Blender workers retained memory reservations")
    if checked["independently_checked_timeline_features"]<18:
        raise RuntimeError("Insufficient independent camera/actor frame checks")
    published=publish_verified_preview(NativeFrozenTakeAuditor(host),grant["approval_id"])
    # New Studio/FilmIndex process must re-open indexed native artifacts and
    # exactly the original source take. The current editable world has since
    # changed and must NOT be used to verify this derived presentation.
    reopened_index=DigitalCapture(Studio(studio.db_path))
    indexed_check=verify_presentation(reopened_index,pid,published["presentation_id"])
    if (indexed_check["status"]!="VERIFIED_INDEXED_PREVIEW" or
        indexed_check["source_capture_sha256"]!=staged["capture_sha256"] or
        indexed_check["blend_sha256"]!=checked["build_blend_sha256"] or
        indexed_check["png_sha256"]!=checked["preview_png_sha256"]):
        raise RuntimeError("Derived FilmIndex presentation lacks original frozen source/artifact identity")
    if len(reopened_index.index.list_objects(pid,kind="presentation"))!=1:
        raise RuntimeError("Indexed technical presentation identity missing or duplicated")

    output={
        "format":"nvp.stack02c3b8.real_frozen_timed_blender.v1",
        "blender_version":version,
        "blender_binary_sha256":sha_file(executable),
        "actual_native_blender_build":True,
        "second_real_blender_reopen":True,
        "frozen_source_survives_director_world_edit":True,
        "approved_take_id":tid,
        "approved_capture_sha256":staged["capture_sha256"],
        "source_timed_sha256":staged["timed_source_sha256"],
        "frozen_timed_render_sha256":staged["timed_render_sha256"],
        "script_sha256":staged["script_sha256"],
        "frame_rate":checked["frame_rate"],
        "frame_count":checked["frame_count"],
        "shot_count":checked["shot_count"],
        "actor_count":checked["actor_count"],
        "native_actor_cut_checks":checked["independently_checked_timeline_features"],
        "blender_take_sha256":checked["build_blend_sha256"],
        "independent_timeline_audit_sha256":checked["audit_json_sha256"],
        "blender_preview_png_sha256":checked["preview_png_sha256"],
        "filmindex_derived_presentation_id":published["presentation_id"],
        "filmindex_presentation_document_sha256":published["presentation_document_sha256"],
        "filmindex_presentation_restart_verification":True,
        "filmindex_presentation_source_take_revision":1,
        "frozen_take_was_not_modified_by_render":True,
        "refused_build_on_low_memory":True,
        "remaining_resource_reservation_mb":0,
        "creator_approval":"simulated_native_host_event_in_ci_only",
        "native_host_approval_ui_implemented":False,
        "full_frame_sequence_rendered":False,
        "high_bit_depth_scene_linear_output":False,
        "lu_dlc_dependency":False,
    }
    (root/"nvp_stack02c3b8_frozen_native_acceptance.json").write_text(
        json.dumps(output,indent=2,sort_keys=True),"utf8")
    return output


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True)
    p.add_argument("--blender",default="blender")
    args=p.parse_args()
    print(json.dumps(fixture(args.out,args.blender),indent=2,sort_keys=True))
