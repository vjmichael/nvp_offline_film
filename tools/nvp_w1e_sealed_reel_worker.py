#!/usr/bin/env python3
"""Fixed W1-E private AVI reel worker: anonymous pipes ONLY, no filesystem.

The host owns all source decryption, exact original-SHA validation and the
one-use director approval. This child receives bounded SOURCE windows, creates
one derived 10-second native reel and returns it through an inherited pipe.
It receives no DB path, encryption key, network access, URL or user token.

Real encrypted-project invocation MUST be confined by a Windows AppContainer
with zero network capabilities and reviewed code ACLs. Running this module as
a normal console utility proves no protected custody.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from io import BytesIO
import json
import os
import struct
import sys

# Source-development role: invoked by the host using this exact reviewed
# script path from a disposable, empty AppContainer cwd. Import the fixed
# repository package root derived from this file, not a client-supplied
# path, PYTHONPATH or inherited working directory. Frozen role imports as
# a normal tools package and does not alter sys.path.
if not __package__:
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backend.nvp_g09e_chunk import (
    render_reel,check_assembly,source_digests,
    FRAMES_PER_CHUNK,MAX_CHUNK_BYTES)
from backend.nvp_g08_native_avi import (
    TICKS_FRAME,verify_movie)
from tools.nvp_g03_protected_scene_worker import _binary_stdio,read_exact

MAGIC_IN=b"NVPW1ERIN1"
MAGIC_OUT=b"NVPW1EROUT1"
FORMAT="nvp.w1e.reviewed_protected_reel.v1"
MAX_INPUT=384*1024*1024
MAX_ORIGINAL=256*1024*1024


def _decode(raw):
    if len(raw)>MAX_INPUT:
        raise RuntimeError("Protected reel input exceeded fixed source budget")
    document=json.loads(raw)
    if not isinstance(document,dict) or set(document)!={
        "format","assembly","start_frame","end_frame","total_frames",
        "plan","source_sha256"} or document["format"]!=FORMAT:
        raise RuntimeError("Untrusted protected reel operation")
    assembly=document["assembly"]
    start=document["start_frame"];end=document["end_frame"]
    total=document["total_frames"]
    if (type(start) is not int or type(end) is not int or
        type(total) is not int or not 0<=start<end<=total or
        end-start>FRAMES_PER_CHUNK):
        raise RuntimeError("Protected reel cannot use arbitrary source time")
    takes=assembly.get("original_takes")
    if type(takes) is not dict or not 1<=len(takes)<=24:
        raise RuntimeError("Protected film Take count is unbounded")
    amount=0
    for tid,take in takes.items():
        for field,checksum in (("original_usd","original_sha256"),
                               ("performance_usd","performance_sha256")):
            original=base64.b64decode(take[field],validate=True)
            amount+=len(original)
            if sha256(original).hexdigest()!=take[checksum]:
                raise RuntimeError("Original OpenUSD source SHA mismatch")
            take[field]=original
        for clip in take["audio"]:
            source=base64.b64decode(clip["pcm16le"],validate=True)
            amount+=len(source)
            if (len(source)!=clip["sample_count"]*2 or
                sha256(source).hexdigest()!=clip["pcm_sha256"]):
                raise RuntimeError("Original microphone source SHA mismatch")
            clip["pcm16le"]=source
    if amount>MAX_ORIGINAL:
        raise RuntimeError("Protected input source payload exceeds 256 MiB")
    digests=source_digests(assembly)
    if sha256(json.dumps(digests,sort_keys=True,separators=(",",":")).encode(
            "utf8")).hexdigest()!=document["source_sha256"]:
        raise RuntimeError("Protected edit decision binding changed")
    check_assembly(assembly,total,start,end,digests)
    return assembly,start,end,document["plan"]


def run():
    inp,out,err=_binary_stdio()
    if read_exact(inp,len(MAGIC_IN))!=MAGIC_IN:
        raise RuntimeError("Fixed native reel pipe protocol missing")
    n=struct.unpack("!Q",read_exact(inp,8))[0]
    if not 1<=n<=MAX_INPUT:
        raise RuntimeError("Unreviewed native film worker input size")
    assembly,start,end,plan=_decode(read_exact(inp,n))
    stream=BytesIO()
    render_reel(assembly,start,end,plan,stream)
    finished=stream.getvalue()
    if not 0<len(finished)<=MAX_CHUNK_BYTES:
        raise RuntimeError("Native reel exceeded its approved output bound")
    verified=verify_movie(finished,end-start,
                           expected_sha=sha256(finished).hexdigest())
    if not verified["verified"] or (
            verified["audio_samples_per_channel"]!=(end-start)*2000):
        raise RuntimeError("Native rendered film time was not preserved")
    out.write(MAGIC_OUT+struct.pack("!Q",len(finished)))
    out.write(finished)
    out.flush()
    return 0


def main(argv=None):
    if list(sys.argv[1:] if argv is None else argv):
        return 2  # Never accept an arbitrary asset path, script or argv.
    try:
        return run()
    except BaseException as exc:
        # Only the exception class is logged, never private movie data.
        if sys.stderr is not None:
            print("Protected film reel failure: "+type(exc).__name__,
                  file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
