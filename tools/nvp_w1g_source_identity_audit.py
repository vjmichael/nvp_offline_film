"""Read-only native compiler-input byte audit against exact Git source head.

CI can independently confirm each checkout source byte equals the canonical
Git blob before native PE/ELF compilation. No signing, licensing, installed
release or source protection is claimed by this engineering-only receipt.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SOURCES=(
    "native/w1g_first_party_worker.cpp",
    "native/original_capture.cpp",
    "native/scene_render.cpp",
    "native/editorial.cpp",
    "native/audio.cpp",
    "native/delivery.cpp",
)

def main():
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    expected=os.environ.get("GITHUB_SHA")
    if expected is not None and expected!=head:
        raise RuntimeError("Native compiled source Git identity differs from CI")
    files={}
    for name in SOURCES:
        local=ROOT/name
        if not local.is_file() or local.is_symlink():
            raise RuntimeError("Original reviewed native compiler input missing: "+name)
        raw=local.read_bytes()
        git_bytes=subprocess.check_output(["git","show",f"HEAD:{name}"],cwd=ROOT)
        if raw!=git_bytes:
            raise RuntimeError("Native compiler checkout source differs from exact-head Git blob: "+name)
        files[name]=sha256(raw).hexdigest()
    print(json.dumps({"format":"nvp.w1g.exact_git_compiler_source.v1",
                      "git_commit_sha":head,"source_sha256":files,
                      "production_release_approved":False},sort_keys=True))
if __name__=="__main__":
    main()
