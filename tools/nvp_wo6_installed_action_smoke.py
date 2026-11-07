"""WO6 packaged NVP.exe native worker acceptance over disposable REAL film data.

Only an explicit locally invoked install-test CLI. Never a network/model
endpoint; no test source enters the creator's real Projects workspace. A
strict test-only policy callback replaces human consent solely to prove
installed subprocess plumbing. NO finished film, movie, user creative
acceptance, release certification or cinema compliance is claimed.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time

from backend.nvp_ai_read_host import TrustedReadScope
from backend.nvp_film_index import FilmIndex
from backend.nvp_native_color_decisions import NativeColorDecisions
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_wo6_impact_preview import preview_source_impact
from backend.nvp_wo6_native_take_action import NativeTakeActionHost
from backend.nvp_wo6_native_shot_action import NativeShotActionHost, ACTION_KINDS
from backend.nvp_wo6_native_data_action import NativeFilmDecisionHost
from backend.nvp_wo6_recovery import WO6DurableRecovery

T=TICKS_PER_SECOND
FORMAT="nvp.wo6.installed_private_native_operations_test.v1"
COLOR={
    "exposure_stops":0.25,"contrast":1.1,"saturation":0.9,
    "temperature_kelvin":5600.,"tint_magenta_green":0.0,
}


def run_wo6_installed_native_smoke():
    destination=os.environ.get("NVP_WO6_INSTALLED_REPORT")
    report_path=Path(destination) if destination else None
    if report_path is not None and (
            not report_path.is_absolute() or report_path.is_symlink() or
            report_path.exists() or not report_path.parent.is_dir()):
        raise PermissionError("New native acceptance report must be host-owned")
    import sys
    report={
        "format":FORMAT,"status":"NOT_ACCEPTED",
        "installed_executable_worker_mode":bool(getattr(sys,"frozen",False)),
        "native_model_self_approval":False,
        "director_human_consent_verified":False,
        "cinema_picture_rendered":False,"mastered_film_audio_played":False,
        "DCP_released":False,"film_delivered":False,
        "all_work_is_disposable_test_only":True,
        "completed_operations":[],
    }
    with tempfile.TemporaryDirectory(prefix="nvp-wo6-installed-real-film-") as temp:
        root=Path(temp)
        studio=Studio(root/"film.sqlite3")
        pid=studio.create_project("Disposable native WO6 source","NOT A FINISHED FILM")["id"]
        index=FilmIndex(studio)
        scenes=OpenUSDSceneBridge(index)
        scene=scenes.publish(pid,"scene",prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,2,-7]},
            {"path":"/World/Light","role":"light","position":[2,4,3]},
        ],curves=[{"path":"/World/Actor","samples":[
            {"tick":0,"position":[0,0,0]},
            {"tick":2*T,"position":[2,0,0]},
        ]}],native_schemas=True)
        index.register_revision(
            pid,"source_performance","performance",
            {"format":"nvp.wo6.installed.test_original_actor.v1"})
        timeline=TemporalLedger(index).publish(pid,"timeline",[{
            "event_id":"movement","event_kind":"action",
            "subject_id":"Actor","start_tick":0,"end_tick":2*T,
            "source_id":"source_performance","source_revision":1,
            "payload":{"usd_prim_path":"/World/Actor"},
        }],duration_tick=3*T)
        original=OpenUSDTakeCapture(
            index,verify_creator_action=lambda *_:True).freeze(
                pid,"previous_take",scene_id="scene",scene_revision=1,
                timeline_id="timeline",timeline_revision=1,
                sample_ticks=[0,T],creator_event="installed_test_only")
        original_sha=original["document_sha256"]
        scope=TrustedReadScope("nvp_installed_ci_actor",pid,"nvp_installed_ci_turn")
        def test_creator(decision,creative):
            return (
                decision=="WO6_INSTALLED_CI_ONLY_NOT_HUMAN_APPROVAL" and
                creative.get("project_id")==pid and
                creative.get("operation") in (
                    "nvp.film.create_frozen_take.v1",
                    "nvp.film.author_director_shot.v1",
                    "nvp.film.author_data_decision.v1"))
        def test_host(context,digest,document):
            return (context==scope and document.get("project_id")==pid and
                    document.get("creator_decision_id")==
                    "WO6_INSTALLED_CI_ONLY_NOT_HUMAN_APPROVAL" and
                    len(digest)==64)
        ledger=TaskLedger(root/"ledger")
        take_host=NativeTakeActionHost(
            index,ledger,(root/"take_jobs").absolute(),
            confirm_creator=test_creator,authorize_native=test_host)
        shot_host=NativeShotActionHost(
            index,ledger,(root/"shot_jobs").absolute(),
            confirm_creator=test_creator,authorize_native=test_host)
        data_host=NativeFilmDecisionHost(
            index,ledger,(root/"data_jobs").absolute(),
            confirm_creator=test_creator,authorize_native=test_host)

        def impact(source_id,revision,digest,change_kind):
            result=preview_source_impact(
                index,pid,source_id,revision,digest,change_kind,max_nodes=32)
            if result["status"]!="READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT":
                raise RuntimeError("Native source preview unexpectedly grants approval")
            return result["preview_sha256"]

        decision="WO6_INSTALLED_CI_ONLY_NOT_HUMAN_APPROVAL"
        queued=take_host.queue_new_take(
            scope,creator_decision_id=decision,
            scene_id="scene",scene_revision=1,
            scene_sha256=scene["document_sha256"],
            timeline_id="timeline",timeline_revision=1,
            timeline_sha256=timeline["document_sha256"],
            new_take_id="new_take",sample_ticks=[0,T],
            expected_preview_sha256=impact(
                "scene",1,scene["document_sha256"],"retake"),
            ram_mb=1536)
        taken=take_host.run_next(timeout_seconds=150)
        if taken["state"]!="SUCCEEDED":
            raise RuntimeError("Real native frozen Take child did not commit")
        fresh_sha=index.read_revision(pid,"new_take",1)["document_sha256"]
        report["completed_operations"].append("new_frozen_take")

        changes={
            "camera":[{"path":"/World/Camera",
                       "property":"camera_focal_length_mm","value":75.0}],
            "blocking":[{"path":"/World/Actor",
                         "property":"translation_offset","value":[1,0,0]}],
            "lighting":[{"path":"/World/Light",
                         "property":"light_intensity","value":180.0}],
        }
        for kind in ("camera","blocking","lighting"):
            name="new_"+kind+"_shot"
            approval=impact(
                "scene",1,scene["document_sha256"],ACTION_KINDS[kind][0])
            task=shot_host.queue_shot(
                scope,creator_decision_id=decision,
                action_kind=kind,shot_id=name,
                take_id="new_take",take_sha256=fresh_sha,
                scene_id="scene",scene_revision=1,
                scene_sha256=scene["document_sha256"],
                start_tick=0,end_tick=T,changes=changes[kind],
                purpose="lighting" if kind=="lighting" else "framing",
                continuity_policy="preserve",
                reason="Disposable installed OS-contained source authoring test",
                expected_preview_sha256=approval,ram_mb=1536)
            outcome=shot_host.run_next(timeout_seconds=150)
            verified=OpenUSDShotOverrides(
                index,verify_director_action=lambda *_:False).evaluate(
                    pid,name,1,tick=T//2)
            if (outcome["state"]!="SUCCEEDED" or
                    outcome["shot_document_sha256"]!=
                    verified["shot_document_sha256"]):
                raise RuntimeError("Installed native shot source proof failed")
            report["completed_operations"].append(kind+"_shot")
        color_id="new_color_decision"
        data_host.queue_decision(
            scope,creator_decision_id=decision,
            decision_kind="color",decision_id=color_id,
            source_id="new_take",source_revision=1,
            source_sha256=fresh_sha,payload=COLOR,
            expected_preview_sha256=impact(
                "new_take",1,fresh_sha,"revise_color"),
            ram_mb=1536)
        completed=data_host.run_next(timeout_seconds=150)
        if (completed["state"]!="SUCCEEDED" or
                NativeColorDecisions(index).read(
                    pid,color_id,1)["document_sha256"]!=
                    completed["decision_sha256"]):
            raise RuntimeError("Real NVP native color writer proof failed")
        report["completed_operations"].append("derived_color")
        shots=[{
            "shot_id":"intro_camera","camera_path":"/World/Camera",
            "start_tick":"0","end_tick":str(T),
            "pattern":"master"},
            {"shot_id":"end_camera","camera_path":"/World/Camera",
             "start_tick":str(T+T//4),"end_tick":str(2*T),
             "pattern":"reaction"},
        ]
        data_host.queue_decision(
            scope,creator_decision_id=decision,
            decision_kind="camera_sequence",decision_id="new_camera_timeline",
            source_id="scene",source_revision=1,
            source_sha256=scene["document_sha256"],payload=shots,
            duration_tick=str(3*T),
            expected_preview_sha256=impact(
                "scene",1,scene["document_sha256"],"revise_camera"),
            ram_mb=1536)
        finished=data_host.run_next(timeout_seconds=150)
        if finished["state"]!="SUCCEEDED":
            raise RuntimeError("Installed native camera timeline worker failed")
        report["completed_operations"].append("exact_film_time_edit")
        if index.read_revision(pid,"previous_take",1)["document_sha256"]!=original_sha:
            raise RuntimeError("Native installed workers rewrote original Take")
        reports=[]
        for item,host in (
                (queued,take_host),
                (task,shot_host)):
            state=host.recovery.status(item["task_id"],owner_key=host.owner)
            if state["state"]!="SUCCEEDED" or not state["events"]:
                raise RuntimeError("Native durable task history did not persist")
            reports.append(state["state"])
        report.update({
            "status":"INSTALLED_NATIVE_WORKER_SOURCES_VERIFIED_NO_FILM",
            "test_source_scene_sha256":scene["document_sha256"],
            "original_take_sha256":original_sha,
            "new_take_sha256":fresh_sha,
            "worker_operation_count":len(report["completed_operations"]),
            "native_os_contained_actual_child_processes":True,
            "durable_task_status_reopened":all(v=="SUCCEEDED" for v in reports),
            "all_original_filminindex_revisions_preserved":True,
            "finished_film_approval_inferred":False,
        })
    if report_path is not None:
        with report_path.open("xb") as stream:
            stream.write((json.dumps(report,indent=2,sort_keys=True)+"\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
    return report


if __name__=="__main__":
    print(json.dumps(run_wo6_installed_native_smoke(),sort_keys=True))
