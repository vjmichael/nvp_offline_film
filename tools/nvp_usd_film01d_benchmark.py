"""USD-FILM-01D real native 20-shot camera/payload/recovery benchmark.

Creates genuine native FilmIndex scenes and USD PointInstancer geometry.
Reports source SHA, observed exact camera transitions, source cache hits,
CPU process RSS, staging bytes and optional NVP OS GPU telemetry only.

No Blender, pixels, interactive editor FPS, stage-attributable VRAM or
photorealism is claimed by this benchmark.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_usd_film01d_shot_working_set import (
    FilmWorldShotPlanner, FilmShotWorkingSet, native_gpu_device_sampler,
)

FORMAT = "nvp.usd_film01d.real_native_shot_stream_measurements.v1"


def measure(*, shot_count=20, instance_count=1200, gpu_device=None):
    if (type(shot_count) is not int or not 2 <= shot_count <= 40 or
        type(instance_count) is not int or not 1 <= instance_count <= 2048):
        raise ValueError("Bounded real native film world measurements required")
    with TemporaryDirectory(prefix="nvp-usd-film01d-") as tmp:
        studio = Studio(Path(tmp) / "film.sqlite")
        pid = studio.create_project(
            "Real camera-sampled original film world","")["id"]
        index = FilmIndex(studio)
        assets = OpenUSDAssetRegistry(index)
        scenes = OpenUSDSceneBridge(index)
        assets.publish(pid,"Tree",shape="sphere",size_m=.6)
        assets.publish(pid,"Crate",shape="cube",size_m=1.5)
        scene_specs = (
            ("Exterior","/World/ExteriorCamera",[0,4,10]),
            ("Interior","/World/InteriorCamera",[0,2,5]),
        )
        for name,cam,pos in scene_specs:
            scenes.publish(pid,name,native_schemas=True,prims=[
                {"path":cam,"role":"camera","position":pos},
                {"path":"/World/Actor","role":"actor",
                 "position":[1,0,0]},
                {"path":"/World/Key","role":"light",
                 "position":[1,3,8]},
            ],curves=[])
        composer = OpenUSDWorldComposer(index)
        start = perf_counter()
        original = composer.publish(
            pid,"World",sets=[
                {"name":name,"scene_id":name,"scene_revision":1}
                for name,_,_ in scene_specs
            ],props=[
                {"name":"CrateProp","asset_id":"Crate","asset_revision":1,
                 "position_m":[0,0,0],"load":"reference"},
            ],instancers=[{
                "name":"Forest","asset_id":"Tree","asset_revision":1,
                "positions_m":[
                    [float((i%40)*2),float((i//40)*2),0.]
                    for i in range(instance_count)
                ],
            }])
        source_publish_seconds = round(perf_counter()-start,5)
        shots=FilmWorldShotPlanner(index)
        for name,cam,_ in scene_specs:
            shots.publish(
                pid,"Shot"+name,world_id="World",world_revision=1,
                camera_set=name,camera_prim=cam,
                sample_ticks=[0,7056000000],
                required_sets=[name],max_loaded_sets=1)
        timings=[]
        samples=[]
        source_sha=original["document_sha256"]
        # Recreate actual Studio/FilmIndex: no in-memory authoring state
        # from prior publish is needed to stream real native USD.
        reopened_index=FilmIndex(Studio(Path(tmp)/"film.sqlite"))
        gpu=(native_gpu_device_sampler(gpu_device)
             if gpu_device is not None else None)
        begin=perf_counter()
        with FilmShotWorkingSet(
            reopened_index,pid,"World",1,gpu_probe=gpu) as player:
            for n in range(shot_count):
                shot="ShotExterior" if n%2==0 else "ShotInterior"
                t=perf_counter()
                item=player.transition(
                    shot,1,receipt_id="ShotWorkingReceipt"+str(n))
                timings.append(round((perf_counter()-t)*1000,5))
                samples.append({
                    "step":n,"shot":shot,
                    "sets_loaded":item["sets_actually_loaded"],
                    "source_camera_ok":item["camera_positions_reopened_exactly"],
                    "original_set_cache_hits":item[
                        "actual_native_working_set_receipt"][
                        "sha_verified_cached_set_loads"],
                    "process_rss_bytes":item["resource_after"]["rss_process_bytes"],
                    "gpu_device_bytes":item["resource_after"]["gpu_device_used_bytes"],
                })
                if len(item["sets_actually_loaded"]) != 1:
                    raise RuntimeError("Native shot streaming loaded unintended film set")
        total=round(perf_counter()-begin,5)
        original_again=reopened_index.read_revision(pid,"World",1)
        if original_again["document_sha256"]!=source_sha:
            raise RuntimeError("Shot streaming changed authoritative film world")
        # Simulate host-side interruption with an explicit cancelled
        # transition; new process/stage recovers solely from durable sources.
        with FilmShotWorkingSet(reopened_index,pid,"World",1) as interrupted:
            try:
                interrupted.transition(
                    "ShotInterior",1,receipt_id="CancelledOriginal",
                    should_cancel=lambda:True)
            except InterruptedError:
                pass
            else:
                raise RuntimeError("Trusted NVP cancellation was ignored")
        cancelled=reopened_index.read_revision(
            pid,"CancelledOriginal",1)["data"]["state"]
        if cancelled!="INTERRUPTED":
            raise RuntimeError("Native cancellation did not persist interruption")
        with FilmShotWorkingSet(
            FilmIndex(Studio(Path(tmp)/"film.sqlite")),pid,"World",1
        ) as recovered:
            receipt=recovered.transition(
                "ShotExterior",1,receipt_id="RecoveredOriginal")
        if not receipt["camera_positions_reopened_exactly"]:
            raise RuntimeError("Native shot source could not recover")
        return {
            "format":FORMAT,
            "original_world_sha256":source_sha,
            "world_revision":1,
            "native_UsdGeom_original_cameras_verified":True,
            "source_scene_count":len(scene_specs),
            "shot_transition_count":shot_count,
            "genuine_point_instancer_positions":instance_count,
            "source_world_publication_seconds":source_publish_seconds,
            "all_native_shot_transitions_seconds":total,
            "shot_transition_ms_min":min(timings),
            "shot_transition_ms_median":statistics.median(timings),
            "shot_transition_ms_max":max(timings),
            "per_shot":samples,
            "cancelled_receipt_persisted":cancelled=="INTERRUPTED",
            "native_fresh_restart_resumed":True,
            "source_film_world_unchanged":True,
            "gpu_vram_attributable_to_world_stage":False,
            "gpu_measurement_available":gpu is not None,
            "whole_process_rss_not_usd_only":True,
            "actual_editor_ui_latency_measured":False,
            "actual_renderer_pixels_produced":False,
            "actor_identity_association_verified_by_world_01e":False,
            "native_final_film_accepted":False,
        }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    parser.add_argument("--shots",type=int,default=20)
    parser.add_argument("--instances",type=int,default=1200)
    parser.add_argument("--gpu-device",default=None)
    opts=parser.parse_args()
    path=Path(opts.output).resolve()
    if not path.parent.is_dir():
        raise ValueError("Evidence folder must exist")
    row=measure(
        shot_count=opts.shots,instance_count=opts.instances,
        gpu_device=opts.gpu_device)
    row["os"]=platform.platform()
    row["python"]=sys.version.split()[0]
    row["github_sha"]=os.environ.get("GITHUB_SHA","NOT_IN_CI")
    path.write_text(json.dumps(row,indent=2,sort_keys=True)+"\n","utf8")
    print(json.dumps({
        "shot_transitions":row["shot_transition_count"],
        "median_ms":row["shot_transition_ms_median"],
        "cancel_reopen_ok":row["native_fresh_restart_resumed"],
        "rendered_picture":False,
    },sort_keys=True))


if __name__ == "__main__":
    main()
