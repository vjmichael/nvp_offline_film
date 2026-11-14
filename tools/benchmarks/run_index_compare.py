"""BENCH-01: native NVP SQLite/FFmpeg vs FFMS2, benchmark-only."""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import platform
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
from tools.benchmarks.ffms2_reference import FFMS2

PID="b"*32
ASSET="benchmark_take"

def tool(name):
    exe=shutil.which(name)
    if not exe:
        raise RuntimeError("Missing real native program: "+name)
    return Path(exe).resolve()

def digest(path):
    sha=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024),b""):
            sha.update(chunk)
    return sha.hexdigest()

def timed(callback):
    before=time.perf_counter()
    result=callback()
    return time.perf_counter()-before,result

def rgb_digest(ffmpeg,png):
    raw=subprocess.run([str(ffmpeg),"-v","error","-nostdin",
                        "-i",str(png),"-frames:v","1","-pix_fmt","rgb24",
                        "-f","rawvideo","pipe:1"],
                       stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                       timeout=30,check=True).stdout
    return hashlib.sha256(raw).hexdigest()

def generate(ffmpeg,path,duration):
    subprocess.run([str(ffmpeg),"-v","error","-nostdin",
                    "-f","lavfi","-i","testsrc2=size=192x108:rate=24000/1001",
                    "-t",str(duration),"-c:v","mpeg4","-bf","2",
                    "-g","48","-q:v","4","-y",str(path)],
                   timeout=max(120,duration*4),check=True)

def benchmark_one(source,source_sha,root,ffmpeg,ffprobe,ffms,order):
    native=NVPFrameIndex(root/"nvp_index",ffprobe=ffprobe)
    ffms_index=root/"ffms_index.ffindex"
    create_nvp=lambda:native.ensure(PID,ASSET,source_sha,source)
    create_ffms=lambda:ffms.create_index(source,ffms_index)
    result={"order":order,"fresh_index_is_os_cold":False}
    for label in (("nvp","ffms2") if order=="nvp_first"
                  else ("ffms2","nvp")):
        elapsed,info=timed(create_nvp if label=="nvp" else create_ffms)
        result[label+"_index_seconds"]=elapsed
        result[label+"_frame_count"]=(
            info["frame_count"] if label=="nvp" else info["num_frames"])
    if result["nvp_frame_count"]!=result["ffms2_frame_count"]:
        raise RuntimeError("NVP and FFMS2 indexed different frame counts")
    count=result["nvp_frame_count"]
    positions=sorted({0,1,count//4,count//2,3*count//4,count-2,count-1})
    result["tested_positions"]=positions
    result["nvp_index_bytes"]=Path(native._path(PID,ASSET,source_sha)).stat().st_size
    result["ffms2_index_bytes"]=ffms_index.stat().st_size
    result["nvp_warm_open_seconds"]=timed(create_nvp)[0]
    t,video=timed(lambda:ffms.open_video(source,ffms_index))
    result["ffms2_warm_decoder_open_seconds"]=t
    nvp_latencies=[]
    ffms_latencies=[]
    frame_checks=[]
    try:
        for position in positions:
            output_dir=root/("nvp_%d"%position)
            output_dir.mkdir()
            nvp_seconds,observed=timed(lambda:extract(
                native,ffmpeg=ffmpeg,project=PID,asset=ASSET,
                source_sha=source_sha,source=source,first_zero=position,
                count=1,output_dir=output_dir,first_output=1))
            nvp_latencies.append(nvp_seconds)
            nvp_png=output_dir/"review_000000001.png"
            ffms_png=root/("ffms_%d.png"%position)
            ffms_seconds,_=timed(lambda:video.save_png(position,ffms_png))
            ffms_latencies.append(ffms_seconds)
            nvpi=native.window(PID,ASSET,source_sha,source,
                               first_zero=position,count=1)
            ffmsi=video.frame_metadata(position)
            nvp_pts=Fraction(
                nvpi["frames"][0]["pts"]*nvpi["time_base_num"],
                nvpi["time_base_den"])
            ffms_pts=Fraction(
                ffmsi["pts"]*ffmsi["time_base_num"],
                ffmsi["time_base_den"])
            frame_checks.append({
                "frame":position,"timestamps_equivalent":nvp_pts==ffms_pts,
                "nvp_timestamp":str(nvp_pts),
                "ffms2_timestamp":str(ffms_pts),
                "rgb24_hash_equal":(
                    rgb_digest(ffmpeg,nvp_png)==rgb_digest(ffmpeg,ffms_png)),
                "both_pngs_created":nvp_png.is_file() and ffms_png.is_file(),
                "nvp_preview_explicitly_unverified":not observed[
                    "source_sha_verified_this_operation"],
            })
    finally:
        video.close()
    result.update({
        "nvp_seek_seconds":nvp_latencies,
        "ffms2_seek_seconds":ffms_latencies,
        "nvp_seek_median_seconds":statistics.median(nvp_latencies),
        "ffms2_seek_median_seconds":statistics.median(ffms_latencies),
        "frame_checks":frame_checks,
        "all_frame_timestamps_agree":all(
            item["timestamps_equivalent"] for item in frame_checks),
        "all_rgb24_pixels_agree":all(
            item["rgb24_hash_equal"] for item in frame_checks),
    })
    return result

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--ffms2-library",required=True)
    parser.add_argument("--source",help="Optional creator-provided test video")
    parser.add_argument("--duration-seconds",type=int,default=30)
    parser.add_argument("--output",required=True)
    args=parser.parse_args(argv)
    if not 2<=args.duration_seconds<=3600:
        raise ValueError("Fixture duration outside bounded CI range")
    lib=Path(args.ffms2_library).absolute()
    if not lib.is_file():
        raise RuntimeError("Real FFMS2 native library required; no mocks")
    ffmpeg,ffprobe=tool("ffmpeg"),tool("ffprobe")
    ffms=FFMS2(lib)
    with tempfile.TemporaryDirectory(prefix="nvp-ffms2-ab-") as tmp:
        root=Path(tmp)
        source=Path(args.source).absolute() if args.source else root/"source.mov"
        if not args.source:
            generate(ffmpeg,source,args.duration_seconds)
        # One initial checksum outside all timed trials; no repeated original
        # SHA inside index lookup, presentation preview, or frame decode.
        source_sha=digest(source)
        rounds=[]
        for order in ("nvp_first","ffms2_first"):
            work=root/order
            work.mkdir()
            rounds.append(benchmark_one(
                source,source_sha,work,ffmpeg,ffprobe,ffms,order))
        result={
            "format":"nvp.benchmark.index_ab.v1",
            "status":"MEASURED_NOT_RELEASE_ACCEPTANCE",
            "platform":platform.platform(),"python":sys.version.split()[0],
            "source_bytes":source.stat().st_size,
            "source_sha256_at_fixture_setup":source_sha,
            "native_ffms2_version":ffms.version,
            "native_ffms2_library_sha256":ffms.library_sha256,
            "methodology":(
                "Both systems use the same recording and exact source ordinals. "
                "Fresh index builds do not start with preexisting index files, "
                "but OS page cache is not flushed. Both orderings are run. "
                "NVP uses FFmpeg CLI and writes PNG on each request; FFMS2 "
                "keeps a warm decoder and encodes a PNG using Python. "
                "Warm decoder reuse and process startup are not normalized. "
                "Output RGB24 and rational PTS are compared independently "
                "after timing. Use results only with these qualifications."),
            "rounds":rounds,
            "reference_backend_is_not_shipped":True,
        }
        path=Path(args.output).absolute()
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    for r in result["rounds"]:
        print(r["order"],
              "index_s NVP=",round(r["nvp_index_seconds"],4),
              "FFMS2=",round(r["ffms2_index_seconds"],4),
              "seek_median_s NVP=",round(r["nvp_seek_median_seconds"],4),
              "FFMS2=",round(r["ffms2_seek_median_seconds"],4),
              "PTSmatch=",r["all_frame_timestamps_agree"],
              "RGBmatch=",r["all_rgb24_pixels_agree"])
    if not all(r["all_frame_timestamps_agree"] for r in result["rounds"]):
        raise RuntimeError("Actual native frame PTS comparison failed")
    if not all(r["all_rgb24_pixels_agree"] for r in result["rounds"]):
        raise RuntimeError("Actual native decoded RGB comparison failed")

if __name__=="__main__":
    main()
