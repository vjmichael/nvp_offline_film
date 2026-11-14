"""Prepare ONLY a public synthetic USD/PCM source bundle for native SCM test.

No confidential project, real filmmaker authorization, external downloaded
character asset, network egress or production-mode renderer is accepted.
Actual native Blender execution is performed later by the Windows SCM service
under its own AppContainer/WFP/Job and finite admin one-use ticket.
"""
from __future__ import annotations
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

from backend.nvp_p1f_cycles_picture_sound import (
    P1FOriginalPictureSound,FORMAT,WORKER,_wav_pcm,_canonical)
from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_p1f_p2_reel_plan import SAMPLES_PER_FRAME
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

PUBLIC_ID="public_scm_actor0"


def stage():
    if os.name!="nt" or os.environ.get("NVP_PUBLIC_SYNTHETIC_CI")!="1":
        raise PermissionError("Native source-only SCM fixture cannot run for private film")
    if len(sys.argv)!=2:
        raise SystemExit("Usage: python -m tools.nvp_p1f_scm_public_fixture <blender.exe>")
    from tests.test_nvp_p1f_imported_actor_native import RealImportedActorTests

    binary=Path(sys.argv[1]).resolve(strict=True)
    program=Path(os.environ["ProgramData"])
    dest=program/"NVP"/"P1F"/"ApprovedJobs"/PUBLIC_ID
    dest.mkdir(parents=True,exist_ok=False)
    fixture=RealImportedActorTests(
        "test_composed_facial_actor_in_real_source_take_shot")
    fixture.setUp()
    try:
        fixture.test_composed_facial_actor_in_real_source_take_shot()
        supervisor=BlenderWorkerSupervisor(
            dest.parent/"source_fixture_supervisor",blender_executable=binary,
            blender_sha256=sha_file(binary),blender_version="Blender 5.3.0")
        renderer=P1FOriginalPictureSound(
            fixture.index,supervisor,
            approve_render=lambda *_:False,
            verify_isolated_worker=lambda *_:False)
        original,path,actor_id,face,usda=renderer._original(
            fixture.pid,"rigged_reel_plan",0,12)
        plan=renderer.plan.read(fixture.pid,"rigged_reel_plan")
        source=renderer.plan.picture_instant(fixture.pid,"rigged_reel_plan",0,12)
        first=source["output_tick"]//(TICKS_PER_SECOND//48000)
        mix=renderer.plan.audio_window(
            fixture.pid,"rigged_reel_plan",0,
            first_sample=first,count=SAMPLES_PER_FRAME)
        pcm=base64.b64decode(mix["pcm_base64"],validate=True)
        if sha256(pcm).hexdigest()!=mix["pcm_sha256"]:
            raise RuntimeError("Public synthetic PCM source changed during staging")
        spec={
            "format":FORMAT,
            "scene_sha256":original["scene_document_sha256"],
            "usd_sha256":sha256(usda).hexdigest(),
            "camera":original["camera_path"],
            "actor_id":actor_id,
            "actor_path":path,
            "source_tick":original["source_tick"],
            "expected_face_weights":face,
            "width":320,"height":180,"samples":8,
        }
        data={
            "fixed_cycles.py":WORKER.read_bytes(),
            "original.usda":usda,
            "original_pcm.wav":_wav_pcm(pcm),
            "frame_spec.json":_canonical(spec),
        }
        for name,value in data.items():
            p=dest/name
            with p.open("xb") as f:
                f.write(value)
                f.flush()
                os.fsync(f.fileno())
        manifest={
            "format":"nvp.p1f.scm_public_staged_source.v1",
            "JobId":PUBLIC_ID,
            "ProjectId":fixture.pid,
            "OriginalPlanSha256":plan["document_sha256"],
            "BlenderSha256":sha_file(binary),
            "FixedScriptSha256":sha256(data["fixed_cycles.py"]).hexdigest(),
            "OriginalUsdSha256":sha256(data["original.usda"]).hexdigest(),
            "OriginalPcmSha256":sha256(data["original_pcm.wav"]).hexdigest(),
            "FrameSpecSha256":sha256(data["frame_spec.json"]).hexdigest(),
            "PublicFixtureOnly":"1",
            "source_is_confidential":False,
            "film_master_created":False,
        }
        output=Path("scm_public_fixture_source_manifest.json")
        with output.open("x",encoding="ascii") as f:
            json.dump(manifest,f,sort_keys=True,indent=2)
            f.flush()
            os.fsync(f.fileno())
        return manifest
    finally:
        fixture.doCleanups()


if __name__=="__main__":
    print(json.dumps(stage(),sort_keys=True))
