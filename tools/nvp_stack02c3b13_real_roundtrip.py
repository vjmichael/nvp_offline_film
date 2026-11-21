"""B13 actual external-NLE-style OTIO edit reimport from B12's real film.

Real native Blender 120 FLOAT32 source -> B11 ACES2 review -> B12 OTIO plus
ProRes technical picture, THEN an independently edited/reordered and trimmed
OTIO is staged into B13's admitted OS-contained parser with test-only creator
presence. Two revisions preserve all previous edits and original film media.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.nvp_b13_native_reimport import NativeB13ImportHost
from backend.nvp_b13_editorial_roundtrip import verify_imported_edit
from backend.nvp_b12_editorial_delivery import _otio,verify_editorial_handoff
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from tools.nvp_stack02c3b12_real_delivery import fixture as b12_fixture


def edit_otio(source_path:Path,dest:Path,*,different=False):
    otio=_otio()
    original=otio.adapters.read_from_file(str(source_path),adapter_name="otio_json")
    if len(original.tracks)!=1 or len(original.tracks[0])!=2:
        raise RuntimeError("Original B12 film did not have two camera cuts")
    track=otio.schema.Track(kind=otio.schema.TrackKind.Video,name="NVP director reordered cut")
    first=original.tracks[0][0].deepcopy()
    second=original.tracks[0][1].deepcopy()
    third=original.tracks[0][1].deepcopy()
    choices=([(second,3,9),(first,5,16),(third,0,8)]
             if not different else
             [(first,2,15),(second,10,20),(third,1,14)])
    for clip,offset,length in choices:
        clip.source_range=otio.opentime.TimeRange(
            otio.opentime.RationalTime(offset,24),
            otio.opentime.RationalTime(length,24))
        track.append(clip)
    edited=otio.schema.Timeline(
        name="Independent director picture edit",tracks=[track],
        metadata=original.metadata)
    otio.adapters.write_to_file(edited,str(dest),adapter_name="otio_json")
    return sum(length for _,_,length in choices)


def fixture(out,blender):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    produced=b12_fixture(root/"b12_frozen_delivery",blender)
    if (produced["verified_source_float32_frame_count"]!=120 or
        produced["portable_output_png16_frames"]!=120 or
        produced["real_OpenTimelineIO_0_18_1_schema_parsed"] is not True or
        produced["real_10bit_yuv422_decoded_and_compared"] is not True or
        produced["FilmIndex_verified_after_restart"] is not True):
        raise RuntimeError("Genuine original B12 production delivery not accepted")
    db=root/"b12_frozen_delivery"/"b11_original"/"b9_frozen_source"/"frozen_take_source"/"film.sqlite3"
    studio=Studio(db)
    capture=DigitalCapture(studio)
    with studio._connection() as con:
        pids=[x[0] for x in con.execute("SELECT id FROM projects")]
    if len(pids)!=1:
        raise RuntimeError("Original frozen film is not uniquely identified")
    pid=pids[0]
    deliveries=[]
    for item in capture.index.list_objects(pid,kind="presentation"):
        document=capture.index.read_revision(pid,item["object_id"])
        if document["data"].get("format")=="nvp.presentation.b12.editorial_delivery.v1":
            deliveries.append(item["object_id"])
    if len(deliveries)!=1:
        raise RuntimeError("Exactly one original independently audited B12 delivery required")
    source_delivery_id=deliveries[0]
    package=Path(produced["disk_handoff_directory"])
    source=verify_editorial_handoff(capture,pid,source_delivery_id,package,check_decode=True)
    if source["frames"]!=120 or not source["official_otio_parsed"]:
        raise RuntimeError("No accepted original 120-frame portable OTIO edit")
    edited=root/"incoming_nle_picture_edit.otio"
    edited2=root/"incoming_nle_picture_revision2.otio"
    length_one=edit_otio(package/"timeline.otio",edited)
    length_two=edit_otio(package/"timeline.otio",edited2,different=True)
    ledger=TaskLedger(root/"b13_native_activity")
    creator_signal=object()
    approvals=[]
    def fixture_native_creator(signal,scope):
        approvals.append(scope)
        return (signal is creator_signal and
                scope.get("operation")=="nvp.native.editorial.otio_edited_picture_import" and
                scope.get("project_id")==pid and
                scope.get("delivery_id")==source_delivery_id and
                scope.get("source_fps")==24 and
                scope.get("audio_import_allowed") is False and
                scope.get("effects_import_allowed") is False)
    host=NativeB13ImportHost(
        capture,ledger,root/"native_b13_importer",
        verify_creator_action=fixture_native_creator)
    first=host.stage_and_approve(
        pid,source_delivery_id,package,edited,creator_signal,
        ram_mb=1024,duration_s=3600)
    ledger.sampler=lambda:ResourceSnapshot(1,16384,400,0,())
    refused=host.run_next()
    if refused is None or refused["state"]!="QUEUED":
        raise RuntimeError("Unadmitted B13 NLE input parser started under low memory")
    ledger.sampler=lambda:ResourceSnapshot(1,32768,25000,0,())
    one=host.run_next()
    if one is None or one["state"]!="SUCCEEDED" or one["frames"]!=length_one or one["revision"]!=1:
        raise RuntimeError("First edited timeline not imported and indexed")
    second=host.stage_and_approve(
        pid,source_delivery_id,package,edited2,creator_signal,
        edit_id=first["edit_id"],expected_revision=1,ram_mb=1024,duration_s=3600)
    two=host.run_next()
    if two is None or two["state"]!="SUCCEEDED" or two["frames"]!=length_two or two["revision"]!=2:
        raise RuntimeError("Second persistent non-destructive edit revision not indexed")
    again=NativeB13ImportHost(
        DigitalCapture(Studio(db)),ledger,host.root,
        verify_creator_action=lambda *_:False)
    verified_first=again.verify_completed(first["job_id"])
    verified_second=again.verify_completed(second["job_id"])
    if (verified_first["frames"]!=length_one or
        verified_second["frames"]!=length_two or
        verified_first["revision"]!=1 or verified_second["revision"]!=2):
        raise RuntimeError("Old or latest director edit was lost after restart")
    all_history=again.capture.index.history(pid,first["edit_id"])
    if len(all_history)!=2:
        raise RuntimeError("FilmIndex did not retain both immutable edit revisions")
    original_after=verify_editorial_handoff(
        again.capture,pid,source_delivery_id,package,check_decode=True)
    if (original_after["frames"]!=120 or
        original_after["source_float32_exr_unchanged"] is not True or
        ledger.snapshot()["reservations"]["ram_mb"]!=0):
        raise RuntimeError("Original film master changed or RAM reservation leaked")
    report={
        "format":"nvp.stack02c3b13.real_external_otio_reimport.v1",
        "original_frozen_take_SHA256":produced["original_digital_take_sha256"],
        "original_source_32bit_FLOAT_EXR_frames":120,
        "original_ACES2_16bit_SDR_frames":120,
        "original_ProRes422_HQ_video_preserved":True,
        "official_OpenTimelineIO_0_18_1_parsed":True,
        "original_camera_shots":2,
        "first_reordered_trimmed_picture_frames":length_one,
        "second_reordered_trimmed_picture_frames":length_two,
        "persistent_edit_revisions":len(all_history),
        "split_repeat_original_shot_source_accepted":True,
        "every_edit_frame_has_original_provenance":True,
        "real_native_contained_import_workers":2,
        "native_creator_events":"fixture_only_not_installed_UI",
        "original_FilmIndex_B12_package_reopened_after_restart":True,
        "new_FilmIndex_edit_id":first["edit_id"],
        "physical_RAM_reservations_after_finish_mb":0,
        "audio_imported":False,"transition_effects_imported":False,
        "picture_locked":False,"edited_video_rendered":False,
        "DCP_delivered":False,"lu_DLC_interface_dependency":False,
    }
    (root/"nvp_b13_real_editorial_reimport_acceptance.json").write_text(
        json.dumps(report,sort_keys=True,indent=2),"utf8")
    return report


if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--out",required=True)
    a.add_argument("--blender",default="blender")
    args=a.parse_args()
    print(json.dumps(fixture(args.out,args.blender),sort_keys=True,indent=2))
