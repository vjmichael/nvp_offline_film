"""W1-F sustained original-film reel audit; read-only source-authority inspection.

60 independently committed and fully verified native 30-second edited Takes
can comprise a 30-minute rehearsal sequence. Every real 720-frame picture
and original PCM window is reopened using INT-02C's existing native verifier.
This does NOT manufacture a final conventional film, fill missing reels,
conform sound across cuts, or claim owner sight/sound acceptance.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_int02_cycles_renderer import _blender_version
from backend.nvp_blender_worker import BlenderWorkerSupervisor, sha_file
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from tools.nvp_int02_native_acceptance import inspect_real_native_edit

FORMAT="nvp.w1f.original_sustained_reel_manifest.v1"
SEGMENT_TICKS=30*TICKS_PER_SECOND
PICTURES_PER_SEGMENT=720
PCM_PER_SEGMENT=30*48000


def validate_reel(manifest):
    if (type(manifest) is not dict or manifest.get("format")!=FORMAT or
        type(manifest.get("project_id")) is not str or
        type(manifest.get("segments")) is not list or
        len(manifest["segments"]) not in (60,360)):
        raise RuntimeError("Only exact 30-minute or 3-hour committed reel sequences are accepted")
    from backend.nvp_film_index import _require_pid,_id
    _require_pid(manifest["project_id"])
    seen=set()
    for i,row in enumerate(manifest["segments"]):
        if (type(row) is not dict or
            set(row)!={"index","timeline_start_tick","timeline_end_tick",
                      "edit_id","edit_revision","package_directory"} or
            type(row["index"]) is not int or row["index"]!=i or
            type(row["timeline_start_tick"]) is not int or
            row["timeline_start_tick"]!=i*SEGMENT_TICKS or
            type(row["timeline_end_tick"]) is not int or
            row["timeline_end_tick"]!=(i+1)*SEGMENT_TICKS or
            type(row["edit_revision"]) is not int or row["edit_revision"]<1 or
            type(row["package_directory"]) is not str or
            not Path(row["package_directory"]).is_absolute()):
            raise RuntimeError("Sustained film has a gap, overlap, retime or foreign package")
        _id(row["edit_id"],"original approved reel edit")
        key=(row["edit_id"],row["edit_revision"])
        if key in seen:
            raise RuntimeError("A repeated original edit cannot masquerade as new film time")
        seen.add(key)
    return {"segment_count":len(manifest["segments"]),
            "duration_seconds":len(manifest["segments"])*30}


def inspect_sustained_reel(manifest,index:FilmIndex,worker:BlenderWorkerSupervisor):
    plan=validate_reel(manifest)
    if not isinstance(index,FilmIndex) or not isinstance(worker,BlenderWorkerSupervisor):
        raise TypeError("Original FilmIndex and genuine native worker required")
    sources=[]
    native_frames=0
    for segment in manifest["segments"]:
        package=Path(segment["package_directory"])
        if package.is_symlink() or not package.is_dir():
            raise RuntimeError("Original reel package missing or linked")
        proof=inspect_real_native_edit(
            index,manifest["project_id"],segment["edit_id"],
            segment["edit_revision"],package,worker)
        if (proof.get("status")!="NATIVE_CYCLES_EDITED_30S_AUTOMATED_ARTIFACTS_VERIFIED" or
            proof.get("total_picture_samples")!=PICTURES_PER_SEGMENT or
            proof.get("source_pcm_samples_verified")!=PCM_PER_SEGMENT or
            proof.get("project_id")!=manifest["project_id"] or
            proof.get("edit_id")!=segment["edit_id"] or
            proof.get("edit_revision")!=segment["edit_revision"] or
            proof.get("no_ffmpeg") is not True):
            raise RuntimeError("Original sustained reel failed actual native film verification")
        native_frames+=proof["supervised_cycles_pictures_verified"]
        sources.append(sha256((
            str(segment["index"])+"|"+proof["manifest_sha256"]+"|"+
            proof["worker_provenance_sha256"]).encode("ascii")).digest())
    return {
        "status":"W1F_ORIGINAL_REEL_SEGMENTS_NATIVE_VERIFIED_NO_MASTER",
        "source_reel_count":plan["segment_count"],
        "duration_seconds":plan["duration_seconds"],
        "original_picture_samples_verified":plan["segment_count"]*PICTURES_PER_SEGMENT,
        "original_pcm_samples_verified":plan["segment_count"]*PCM_PER_SEGMENT,
        "verified_native_cycles_pictures":native_frames,
        "sequence_provenance_sha256":sha256(b"".join(sources)).hexdigest(),
        "source_films_mutated":False,
        "conventional_single_file_master":False,
        "original_audio_across_reels_conformed":False,
        "owner_physical_color_sound_accepted":False,
        "sustained_production_complete":False,
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--studio-sqlite",type=Path,required=True)
    p.add_argument("--worker-workspace",type=Path,required=True)
    p.add_argument("--blender",type=Path,required=True)
    p.add_argument("--receipt",type=Path,required=True)
    args=p.parse_args(argv)
    if (args.manifest.is_symlink() or not args.manifest.is_file() or
        args.manifest.stat().st_size>512*1024 or
        not args.studio_sqlite.is_file() or args.studio_sqlite.is_symlink()
        or not args.blender.is_file() or args.blender.is_symlink() or
        args.receipt.exists() or args.receipt.is_symlink()):
        raise RuntimeError("Real original native film inputs and an unused output receipt required")
    manifest=json.loads(args.manifest.read_text("utf8"))
    validate_reel(manifest)
    worker=BlenderWorkerSupervisor(
        args.worker_workspace,
        blender_executable=args.blender,
        blender_sha256=sha_file(args.blender),
        blender_version=_blender_version(args.blender))
    report=inspect_sustained_reel(
        manifest,FilmIndex(Studio(args.studio_sqlite)),worker)
    args.receipt.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(json.dumps(report,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
