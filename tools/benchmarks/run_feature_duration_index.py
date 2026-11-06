#!/usr/bin/env python3
"""SCALE-03C: run real NVP-owned frame indexing on feature-duration media.

This checks a three-hour source *timeline* without consuming 3 hours of 24fps
video on cheap CI runners. 1fps 64x64 footage is explicitly a sparse stress
fixture, not representative 4K/24fps decoding or disk throughput.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.nvp_native_frame_index import NVPFrameIndex
from backend.nvp_indexed_preview import extract

PROJECT="c"*32
ASSET="long_source"


def tool(name):
    resolved=shutil.which(name)
    if not resolved:
        raise RuntimeError("Required real native executable missing: "+name)
    return Path(resolved).resolve()


def timed(call):
    start=time.perf_counter()
    result=call()
    return time.perf_counter()-start,result


def digest(path):
    sha=hashlib.sha256()
    with Path(path).open("rb") as src:
        for block in iter(lambda:src.read(4*1024*1024),b""):
            sha.update(block)
    return sha.hexdigest()


def run(args):
    ffmpeg,ffprobe=tool("ffmpeg"),tool("ffprobe")
    if not 10<=args.duration_seconds<=3*3600+600:
        raise ValueError("Expected bounded 10-second to 3-hour benchmark duration")
    if args.fps not in (1,24):
        raise ValueError("Only explicit 1fps sparse or 24fps dense fixtures supported")
    with tempfile.TemporaryDirectory(prefix="nvp-feature-index-") as scratch:
        root=Path(scratch)
        source=Path(args.source).absolute() if args.source else root/"feature.mov"
        if args.source is None:
            subprocess.run([
                str(ffmpeg),"-nostdin","-v","error",
                "-f","lavfi","-i",f"testsrc2=size=64x64:rate={args.fps}",
                "-t",str(args.duration_seconds),"-c:v","mpeg4",
                "-g","48","-bf","2","-q:v","7","-y",str(source),
            ],timeout=max(120,args.duration_seconds//3),check=True)
        before_sha=digest(source)  # setup/ingest proof ONCE, outside timings
        index=NVPFrameIndex(root/"cache",ffprobe=ffprobe)
        created_s,created=timed(
            lambda:index.ensure(PROJECT,ASSET,before_sha,source))
        if created["status"]!="CREATED_SOURCE_STAMP_UNVERIFIED":
            raise RuntimeError("Expected a newly built NVP index")
        reused_s,again=timed(
            lambda:index.ensure(PROJECT,ASSET,before_sha,source))
        if again["status"]!="REUSED_SOURCE_STAMP_UNVERIFIED":
            raise RuntimeError("Warm index must be reused")
        total=created["frame_count"]
        positions=sorted({0,1,total//4,total//2,3*total//4,total-2,total-1})
        timings=[]
        for _ in range(15):
            for pos in positions:
                elapsed,window=timed(lambda:index.window(
                    PROJECT,ASSET,before_sha,source,first_zero=pos,count=1))
                if window["frames"][0]["ordinal"]!=pos:
                    raise RuntimeError("Wrong indexed source frame ordinal")
                timings.append(elapsed)
        output=root/"images"
        output.mkdir()
        near_s,near=timed(lambda:extract(
            index,ffmpeg=ffmpeg,project=PROJECT,asset=ASSET,
            source_sha=before_sha,source=source,
            first_zero=total-1,count=1,output_dir=output))
        if near["frames"][0]["source_frame_zero"]!=total-1:
            raise RuntimeError("Near-end decode does not agree with index")
        data={
            "format":"nvp.feature_duration_index_benchmark.v1",
            "source_duration_requested_seconds":args.duration_seconds,
            "source_fps_requested":args.fps if not args.source else None,
            "synthetic_sparse_fixture":args.source is None and args.fps==1,
            "source_bytes":source.stat().st_size,
            "indexed_frames":total,
            "index_bytes":Path(created["path"]).stat().st_size,
            "initial_index_seconds":created_s,
            "warm_open_seconds":reused_s,
            "window_query_median_ms":1000*statistics.median(timings),
            "window_query_p95_ms":1000*sorted(timings)[int(len(timings)*.95)],
            "near_end_indexed_decode_seconds":near_s,
            "last_source_frame_zero":near["frames"][0]["source_frame_zero"],
            "source_sha_rehashed_during_index_and_queries":False,
            "source_integrity":"SOURCE_STAMP_UNVERIFIED",
            "limitations":(
                "1fps synthetic compressed picture tests long timestamp/ordinal "
                "range and index memory/SQL scaling, NOT a representative "
                "24fps 4K feature, production codec, storage or visual-quality "
                "comparison. Source hash is setup-only. Timecode end is "
                "source-native; no 2D frames for NVP-native Digital Takes."),
        }
        output=Path(args.output).absolute()
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(data,indent=2,sort_keys=True),encoding="utf-8")
        print(json.dumps(data,indent=2,sort_keys=True))
        return data


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",help="Optional actual imported movie source")
    parser.add_argument("--duration-seconds",type=int,default=10800)
    parser.add_argument("--fps",type=int,default=1)
    parser.add_argument("--output",required=True)
    return run(parser.parse_args(argv))


if __name__=="__main__":
    main()
