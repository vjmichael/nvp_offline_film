"""W1-G compile-time declaration of release-wide launch-fence coverage.

This is an audited PACKAGE CLAIM, not OS proof. Both source launcher and
desktop entry hashes are pinned in a file incorporated into the external
build receipt and independently signed redistribution inventory. A production
upgrade refuses an older runtime lacking the protocol; the first fenced
release therefore must be installed as a new clean installation.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

FORMAT="nvp.w1g.windows_release_fence_build_marker.v1"
FILENAME="nvp-release-custody.json"
DOMAINS=["audio","cycles","delivery","editorial","filming"]
HASH=re.compile(r"[a-f0-9]{64}\Z")


def marker_from_sources(launcher:Path,desktop:Path) -> dict:
    hashes=[]
    for path in (launcher,desktop):
        path=Path(path)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Original release-fenced source file missing")
        hashes.append(sha256(path.read_bytes()).hexdigest())
    return {
        "format":FORMAT,
        "os":"windows-amd64",
        "fence":"exclusive-128-slot-locks-v1",
        "worker_domains":DOMAINS,
        "host_lifetime_gated":True,
        "all_launch_contained_windows_workers_gated":True,
        "contained_launcher_source_sha256":hashes[0],
        "desktop_entry_source_sha256":hashes[1],
        "original_worker_tree_cleanup_method":"windows-job-object-kernel-accounting",
        "physical_owner_accepted":False,
    }


def verify_build_marker(bundle:Path):
    target=Path(bundle)/FILENAME
    if target.is_symlink() or not target.is_file() or target.stat().st_size>4096:
        raise PermissionError("Original NVP release predates the kernel launch-fence contract")
    document=json.loads(target.read_text("utf8"))
    if (type(document) is not dict or
        document.get("format")!=FORMAT or
        document.get("os")!="windows-amd64" or
        document.get("fence")!="exclusive-128-slot-locks-v1" or
        document.get("worker_domains")!=DOMAINS or
        document.get("host_lifetime_gated") is not True or
        document.get("all_launch_contained_windows_workers_gated") is not True or
        document.get("original_worker_tree_cleanup_method")!="windows-job-object-kernel-accounting" or
        document.get("physical_owner_accepted") is not False or
        any(type(document.get(key)) is not str or not HASH.fullmatch(document[key])
            for key in ("contained_launcher_source_sha256","desktop_entry_source_sha256"))):
        raise PermissionError("Installed NVP native launch-fence build marker is invalid")
    return {"status":"NVP_RELEASE_FENCED_SOURCE_BUILD_MARKER_PRESENT",
            "actual_kernel_process_tree_custody_verified":False}


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--bundle",type=Path,required=True)
    ap.add_argument("--launcher",type=Path,default=Path("backend/nvp_worker_containment.py"))
    ap.add_argument("--desktop",type=Path,default=Path("tools/nvp_desktop_alpha.py"))
    args=ap.parse_args(argv)
    target=args.bundle/FILENAME
    if target.exists() or target.is_symlink():
        raise FileExistsError("Release build marker cannot be overwritten")
    target.write_text(json.dumps(marker_from_sources(
        args.launcher,args.desktop),sort_keys=True,separators=(",",":"))+"\n",encoding="utf8")
    print(json.dumps(verify_build_marker(args.bundle),sort_keys=True))


if __name__=="__main__":
    main()
