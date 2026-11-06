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
