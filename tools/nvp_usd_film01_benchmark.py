"""USD-FILM-01 native bounded working-set / restart benchmark receipt.

Creates actual authoritative NVP FilmIndex scene+asset data; no mocked
USD scene, renderer or target machine performance prediction. Measures
Stage.LoadNone and actual payload load/unload, plus point-instancer source
compression. RSS is a process-wide sample only; VRAM is NOT measured.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

from pxr import UsdGeom

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_usd_film01_world import OpenUSDWorldComposer

FORMAT = "nvp.usd_film01.real_world_native_working_set_benchmark.v1"


def exercise(instance_count=1200):
    if type(instance_count) is not int or not 1 <= instance_count <= 2048:
        raise ValueError("Bounded authored native instance benchmark required")
    with TemporaryDirectory(prefix="nvp-usd-film01-benchmark-") as tmp:
        studio = Studio(Path(tmp)/"world.sqlite")
        pid = studio.create_project("Real composed film world benchmark","")["id"]
        index = FilmIndex(studio)
        assets=OpenUSDAssetRegistry(index)
        scenes=OpenUSDSceneBridge(index)
        for name,shape,size in (
            ("BenchTree","sphere",.75),
            ("BenchCrate","cube",1.25),
            ("BenchDoor","cube",3),
        ):
            assets.publish(pid,name,shape=shape,size_m=size)
        for name in ("Street","Interior"):
            scenes.publish(
                pid,name,prims=[
                    {"path":"/World/Camera","role":"camera",
                     "position":[0,3,10]},
                    {"path":"/World/Actor","role":"actor",
                     "position":[0,0,0]},
                ],curves=[],native_schemas=True)
        author=OpenUSDWorldComposer(index)
        sets=[
            {"name":"Exterior","scene_id":"Street","scene_revision":1},
            {"name":"Interior","scene_id":"Interior","scene_revision":1},
        ]
        start=perf_counter()
        original=author.publish(
            pid,"City",sets=sets,
            props=[
                {"name":"Box","asset_id":"BenchCrate",
                 "asset_revision":1,"load":"reference",
                 "position_m":[0,0,0]},
            ],
            variants=[
                {"name":"Door","position_m":[2,0,0],
                 "selected":"Small",
                 "options":[
                    {"name":"Small","asset_id":"BenchCrate",
                     "asset_revision":1},
                    {"name":"Tall","asset_id":"BenchDoor",
                     "asset_revision":1},
                 ]},
            ],
            instancers=[
                {"name":"Trees","asset_id":"BenchTree",
                 "asset_revision":1,
                 "positions_m":[
                    [float((n%40)*2),float((n//40)*2),0.]
                    for n in range(instance_count)],
                },
            ])
        publish_seconds=round(perf_counter()-start,5)
        original_sha=original["document_sha256"]
        reopen=OpenUSDWorldComposer(FilmIndex(Studio(studio.db_path)))
        start=perf_counter()
        with reopen.open(pid,"City",1) as world:
            open_total_s=round(perf_counter()-start,5)
            before=world.receipt()
            if before["loaded_set_names"]:
                raise RuntimeError("World did not start with all source sets unloaded")
            first=world.load(["Exterior"])
            if not world.stage.GetPrimAtPath(
                    "/World/Sets/Exterior/Camera").IsA(UsdGeom.Camera):
                raise RuntimeError("Real payload camera did not resolve after load")
            if world.stage.GetPrimAtPath(
                    "/World/Sets/Interior").IsLoaded():
                raise RuntimeError("Native payload loaded unrelated film set")
            inst=UsdGeom.PointInstancer(world.stage.GetPrimAtPath(
                "/World/Instancers/Trees"))
            count=len(inst.GetProtoIndicesAttr().Get())
            if count!=instance_count:
                raise RuntimeError("Original scene instancer changed on restart")
            second=world.load(["Interior"])
            both=world.receipt()
            world.unload(["Exterior","Interior"])
            after=world.receipt()
            if after["loaded_set_names"]:
                raise RuntimeError("Native USD payload unload did not complete")
            result={
                "format":FORMAT,
                "original_project_id":pid,
                "world_id":"City","world_revision":1,
                "world_document_sha256":original_sha,
                "publish_seconds":publish_seconds,
                "restart_open_load_none_seconds":open_total_s,
                "actual_instanced_prop_count":count,
                "original_asset_prototype_count":1,
                "source_staging_bytes":before["source_staging_bytes"],
                "source_staging_files":before["source_staging_file_count"],
                "native_usd_stage_load_none_ms":before["usd_stage_load_none_ms"],
                "first_set_load_ms":first["elapsed_ms"],
                "second_set_load_ms":second["elapsed_ms"],
                "rss_initial_bytes":before["rss_unloaded_bytes"],
                "rss_after_both_sets_loaded_bytes":both["rss_current_bytes"],
                "rss_after_unload_bytes":after["rss_current_bytes"],
                "gpu_vram_bytes":None,
                "native_rss_samples_are_process_wide":True,
                "renderer_pixels_generated":False,
                "audio_final_mix_verified":False,
                "asset_resolver_supports_external_texture_files":False,
                "digital_take_or_original_scene_changed":False,
                "lazy_payload_load_unload_verified":True,
                "original_source_hash_reopened":(
                    reopen.index.read_revision(pid,"City",1)["document_sha256"]
                    ==original_sha),
            }
        if not result["original_source_hash_reopened"]:
            raise RuntimeError("Restart did not retain original world SHA")
        return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    parser.add_argument("--instances",type=int,default=1200)
    args=parser.parse_args()
    target=Path(args.output)
    if not target.parent.is_dir():
        raise ValueError("Actual native benchmark evidence folder missing")
    result=exercise(args.instances)
    result["python"]=sys.version.split()[0]
    result["os"]=platform.platform()
    result["commit_sha_reported"]=os.environ.get("GITHUB_SHA","NOT_IN_CI")
    target.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n","utf8")
    print(json.dumps({
        "native_usd_working_set_verified":result["lazy_payload_load_unload_verified"],
        "native_instancer_count":result["actual_instanced_prop_count"],
        "first_set_load_ms":result["first_set_load_ms"],
        "evidence":str(target),
    },sort_keys=True))


if __name__=="__main__":
    main()
