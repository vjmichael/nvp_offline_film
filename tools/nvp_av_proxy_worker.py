"""Contained, SHA-pinned INDEX-TIME-09 original-footage A/V proxy worker.

This entrypoint is never an HTTP API or browser-exposed subprocess wrapper.
The trusted native host runs it inside its Windows Job Object or Linux
containment boundary with a canonical sealed plan and exact tool digests.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

if __name__=="__main__" and not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backend.nvp_index_time09_av_proxy import canonical,execute

def _sha(path):
    h=sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",required=True)
    parser.add_argument("--destination",required=True)
    parser.add_argument("--studio-db",required=True)
    parser.add_argument("--ffmpeg",required=True)
    parser.add_argument("--ffprobe",required=True)
    parser.add_argument("--ffmpeg-sha",required=True)
    parser.add_argument("--ffprobe-sha",required=True)
    args=parser.parse_args()
    path=Path(args.plan)
    if path.is_symlink() or not path.is_file():
        raise PermissionError("Sealed native A/V plan unavailable")
    raw=path.read_bytes()
    pl=json.loads(raw)
    if raw!=canonical(pl):
        raise PermissionError("Sealed A/V edit decision was altered")
    for file,digest in ((args.ffmpeg,args.ffmpeg_sha),
                        (args.ffprobe,args.ffprobe_sha)):
        p=Path(file)
        if (not p.is_absolute() or p.is_symlink() or
            not p.is_file() or len(digest)!=64 or _sha(p)!=digest):
            raise PermissionError("Native worker tool has changed after approval")
    result=execute(Path(args.studio_db),pl,Path(args.destination),
                   Path(args.ffmpeg),Path(args.ffprobe))
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
