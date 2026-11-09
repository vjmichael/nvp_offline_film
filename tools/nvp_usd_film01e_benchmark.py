"""USD-FILM-01E test-only original 30s film world Take acceptance evidence.

Reuses the existing original NVP Donut/Box/Sphere/ServiceCraft 3D source,
native OpenUSD camera and real FilmIndex original PCM blobs. New world
scene/take does not edit existing original source Takes. No synthetic
speaker voice, Blender image rendering or film master is claimed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys
import os
from tempfile import TemporaryDirectory
from time import perf_counter

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_story_bible import StoryBible
from backend.nvp_production_bible_actors import ProductionBibleActors
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_usd_film01d_shot_working_set import FilmWorldShotPlanner
from backend.nvp_usd_film01e_world_take import OpenUSDWorldTakeCapture
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from tools.nvp_film01_original_30s import write_original_30s_source

FORMAT="nvp.usd_film01e.native_original_30s_world_take_evidence.v1"


def exercise():
    with TemporaryDirectory(prefix="nvp-usd-film01e-evidence-") as tmp:
        src=Path(tmp).resolve()/"original"
        start=perf_counter()
        original=write_original_30s_source(src,approve_test_only=True)
        pid=original["project_id"]
        studio=Studio(src/"short.sqlite3")
        index=FilmIndex(studio)
        old=index.read_revision(pid,"RelayRekindleTake",1)
        before_sha=old["document_sha256"]
        old_src_scene_sha=old["data"]["scene_document_sha256"]
        b=StoryBible(studio)
        registry=ProductionBibleActors(studio)
        prims=[
            ("DONUT","/World/Engineer"),
            ("BOX","/World/CrossingBox"),
            ("SPHERE","/World/PassingSphere"),
            ("SERVICE CRAFT","/World/ServiceCraft"),
        ]
        for label,prim in prims:
            actor=b.create_entity(pid,"character",label)
            current=registry.actor(pid,actor["id"])
            registry.link(
                pid,actor["id"],role="actor_prim",
                source_family="filmindex",
                target_id="RelayRekindleTake",target_revision=1,
                actor_prim_path=prim,
                expected_actor_revision=current["bible_revision"],
                director_note="CI-only authored original object-actor source binding")
        complete=registry.require_complete_cast(pid,"RelayRekindleTake")
        if len(complete["actor_id_by_prim"])!=4:
            raise RuntimeError("Original four-actor film source is not fully cast")
        world=OpenUSDWorldComposer(index).publish(
            pid,"EvidenceWorld",
            sets=[{"name":"Relay","scene_id":"Relay30Scene",
                   "scene_revision":3}],
            props=[],variants=[],instancers=[])
        shot=FilmWorldShotPlanner(index).publish(
            pid,"RekindleWorldShot",
            world_id="EvidenceWorld",world_revision=1,
            camera_set="Relay",camera_prim="/World/Camera",
            sample_ticks=[0,5*T,9*T],
            required_sets=["Relay"],max_loaded_sets=1)
        capture=OpenUSDWorldTakeCapture(
            index,verify_creator_action=lambda event,scope:(
                event=="DISPOSABLE_TEST_DIRECTOR" and
                scope["operation"]=="nvp.freeze.usd_film01e_world_take.v1"))
        begun=perf_counter()
        combined=capture.freeze(
            pid,"EvidenceWorldTake",world_id="EvidenceWorld",
            world_revision=1,shot_id="RekindleWorldShot",
            shot_revision=1,
            scene_takes=[{
                "set":"Relay","take_id":"RelayRekindleTake",
                "take_sha256":before_sha}],
            creator_event="DISPOSABLE_TEST_DIRECTOR")
        freeze_duration_ms=round((perf_counter()-begun)*1000,4)
        reopened=OpenUSDWorldTakeCapture(
            FilmIndex(Studio(src/"short.sqlite3")),
            verify_creator_action=lambda *_:False)
        begun=perf_counter()
        proof=reopened.verify_take(pid,"EvidenceWorldTake")
        verify_duration_ms=round((perf_counter()-begun)*1000,4)
        state=reopened.sample(pid,"EvidenceWorldTake",tick=9*T)
        after=index.read_revision(pid,"RelayRekindleTake",1)
        if (after["document_sha256"]!=before_sha or
            after["data"]["scene_document_sha256"]!=old_src_scene_sha or
            state["tick"]!=9*T or
            proof["take_document_sha256"]!=combined["document_sha256"] or
            proof["canonical_actor_count"]!=4 or
            proof["original_audio_event_count"] < 1):
            raise RuntimeError("Original multi-actor world Take source continuity failed")
        return {
            "format":FORMAT,
            "original_source_take_sha256":before_sha,
            "original_source_take_unchanged":True,
            "composed_world_sha256":world["document_sha256"],
            "original_director_shot_sha256":shot["document_sha256"],
            "world_take_document_sha256":combined["document_sha256"],
            "original_actor_count":proof["canonical_actor_count"],
            "original_pcm_event_count":proof["original_audio_event_count"],
            "original_scene_takes_verified":proof["original_take_count"],
            "exact_checkpoint_count":proof["checkpoint_count"],
            "original_camera_from_real_usd":state["original_camera_path"],
            "original_actor_prim_count_in_snapshot":
                len(state["scenes"][0]["actors"]),
            "source_publication_seconds":round(
                (perf_counter()-start),4),
            "world_take_freeze_ms":freeze_duration_ms,
            "world_take_reverify_after_restart_ms":verify_duration_ms,
            "native_source_take_reopened_after_restart":True,
            "source_original_audio_not_voice_model":True,
            "native_render_frame_count":0,
            "finished_original_audio_mix":False,
            "human_photorealism_accepted":False,
            "original_render_pipeline_consumes_world_take":False,
        }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    args=p.parse_args()
    output=Path(args.output).resolve()
    if not output.parent.is_dir():
        raise ValueError("Native evidence folder missing")
    report=exercise()
    report["host"]=platform.platform()
    report["python"]=sys.version.split()[0]
    report["github_head_sha"]=os.environ.get("GITHUB_SHA","NOT_IN_CI")
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n","utf8")
    print(json.dumps({
        "source_take_continuity":report["original_source_take_unchanged"],
        "world_take_actor_count":report["original_actor_count"],
        "original_audio_events":report["original_pcm_event_count"],
        "rendered_pixels":False,
    },sort_keys=True))


if __name__=="__main__":
    main()
