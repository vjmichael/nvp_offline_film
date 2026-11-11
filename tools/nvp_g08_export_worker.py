#!/usr/bin/env python3
"""Fixed reviewed NVP G08 render / independent readback executable.

The host always starts a supervised, OS-contained child. This worker receives
only the trusted host's fixed movie identity/revision/owned output paths,
reopens frozen source from the local Studio database (not from arbitrary
URL/media upload), and reports narrow structured receipts. No shell, FFmpeg,
network access or source writes. Cancellation is host process-tree custody.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys


def _write_json(path,data):
    target=Path(path)
    if target.is_symlink() or target.parent.is_symlink():
        raise RuntimeError("Export progress path is not trusted")
    raw=json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    temp=target.with_suffix(".tmp")
    with open(temp,"xb") as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temp,target)


def _owned(args):
    from backend.nvp_g06_filming import HEX
    if type(args.project) is not str or not HEX.fullmatch(args.project):
        raise ValueError("Invalid film identity")
    if type(args.job) is not str or not HEX.fullmatch(args.job):
        raise ValueError("Invalid film export")
    db=Path(args.db).resolve(strict=True)
    root=db.parent/"nvp_g08_exports"/args.project
    root_resolved=root.resolve(strict=True)
    if root_resolved!=root or root.is_symlink():
        raise ValueError("The film export directory is not an owned NVP directory")
    # Independent verifier reads the unpublished candidate; the host makes
    # the final movie visible only AFTER verification succeeds.
    file=root/(args.job+".partial.avi")
    if file.is_symlink():
        raise RuntimeError("Movie output path is not a regular file")
    if args.action=="verify" and not file.is_file():
        raise RuntimeError("There is no complete candidate movie to verify")
    return db,file,root


def _render(args):
    from backend.nvp_studio import Studio
    from backend.nvp_g07_edit import G07Editor
    from backend.nvp_g08_native_avi import render_film
    if type(args.revision) is not int or args.revision<1:
        raise ValueError("Choose an actual saved editing revision")
    if len(args.edit_sha)!=64 or any(c not in "0123456789abcdef" for c in args.edit_sha):
        raise ValueError("The original edit digest is unavailable")
    db,output,root=_owned(args)
    studio=Studio(db)
    assembly=G07Editor(studio).native_assembly(args.project,args.revision)
    if assembly["edit_document_sha256"]!=args.edit_sha:
        raise RuntimeError("Source edit changed after director approval")
    if assembly["duration_tick"]<=0:
        raise ValueError("Record and edit a film before exporting")
    if output.exists():
        raise RuntimeError("A partial movie file already exists; reconcile it first")
    last=[-1]
    def progress(done,total):
        if done==last[0]:return
        last[0]=done
        _write_json(args.progress,{
            "job_id":args.job,"frames_completed":done,"frames_total":total,
            "status":"rendering","edit_sha256":args.edit_sha})
    with open(output,"xb") as file:
        result=render_film(assembly,file,progress=progress)
        file.flush()
        os.fsync(file.fileno())
    result.update({"job_id":args.job,"edit_sha256":args.edit_sha,
                   "sha256":sha256(output.read_bytes()).hexdigest()})
    _write_json(args.receipt,result)
    return 0


def _verify(args):
    from backend.nvp_g08_native_avi import verify_movie
    db,file,root=_owned(args)
    if type(args.frames) is not int or not 1<=args.frames<=720:
        raise ValueError("Expected movie length is invalid")
    with file.open("rb") as f:
        result=verify_movie(f,args.frames,expected_sha=args.output_sha)
    _write_json(args.receipt,result)
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description="NVP offline fixed native export worker")
    parser.add_argument("action",choices=("render","verify"))
    parser.add_argument("--db",required=True)
    parser.add_argument("--project",required=True)
    parser.add_argument("--job",required=True)
    parser.add_argument("--revision",type=int,default=0)
    parser.add_argument("--edit-sha",default="")
    parser.add_argument("--frames",type=int,default=0)
    parser.add_argument("--output-sha",default="")
    parser.add_argument("--progress",default="")
    parser.add_argument("--receipt",required=True)
    args=parser.parse_args(argv)
    try:
        if args.action=="render":
            return _render(args)
        return _verify(args)
    except BaseException as exc:
        # Do not print screenplay contents, plaintext project paths, PCM,
        # protected file secrets or G06 film content into child logs.
        print("NVP native export did not complete: "+type(exc).__name__,
              file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
