"""Independent STACK-02C2 cgroup guardian, outside the Blender cgroup.

The kernel notifies us of the host death through a pipe EOF. Because the
guardian does not belong to the worker leaf, it survives the Blender cgroup
kill and can tear down the entire descendant tree even after a hard crash.

Only an immediate child of the guardian's own current delegated cgroup with
an NVP-generated name is eligible. No arbitrary paths, PIDs, shell or systemd
units can be supplied by the model or a project.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time

CGROOT=Path("/sys/fs/cgroup")
PREFIX="nvp-worker-"


def own_cgroup():
    for entry in Path("/proc/self/cgroup").read_text("utf8").splitlines():
        if entry.startswith("0::"):
            return (CGROOT/entry[3:].lstrip("/")).resolve()
    raise RuntimeError("Unified Linux cgroups v2 missing")


def validate_owned_leaf(candidate):
    target=Path(candidate).resolve(strict=True)
    parent=own_cgroup()
    delegated=target.parent
    try:
        marker=os.getxattr(delegated,"user.delegate")==b"1"
    except (OSError,AttributeError):
        marker=False
    if (not parent.is_relative_to(delegated) or not marker or
        not target.name.startswith(PREFIX) or
        len(target.name)!=len(PREFIX)+32 or
        any(ch not in "0123456789abcdef" for ch in target.name[len(PREFIX):]) or
        not (target/"cgroup.kill").is_file() or
        not (target/"cgroup.events").is_file()):
        raise RuntimeError("Guardian cannot operate outside its own delegated NVP leaf")
    if not os.access(target/"cgroup.kill",os.W_OK):
        raise RuntimeError("Guardian has no permission to cgroup.kill")
    return target


def populated(path):
    values=dict(line.split() for line in (path/"cgroup.events").read_text("ascii").splitlines())
    if values.get("populated") not in ("0","1"):
        raise RuntimeError("Kernel cgroup.events lacks populated state")
    return values["populated"]=="1"


def cleanup_after_parent_death(path):
    # Kernel cgroup.kill kills the entire subtree atomically against forking
    # or migration. This is not a PID enumeration or an unreliable killpg.
    (path/"cgroup.kill").write_text("1",encoding="ascii")
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        if not populated(path):
            for _ in range(12):
                try:
                    path.rmdir()
                    return
                except OSError:
                    time.sleep(.1)
        time.sleep(.05)
    raise RuntimeError("Kernel did not verify cgroup tree empty after kill")


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--cgroup",required=True)
    parser.add_argument("--watch-fd",required=True,type=int)
    parser.add_argument("--ready-fd",required=True,type=int)
    args=parser.parse_args(argv)
    if (args.watch_fd<3 or args.ready_fd<3 or args.watch_fd==args.ready_fd):
        raise RuntimeError("Invalid guardian host-watch descriptors")
    target=validate_owned_leaf(args.cgroup)
    # Signal readiness only AFTER cgroup.kill and events ownership are proven.
    os.write(args.ready_fd,b"1")
    os.close(args.ready_fd)
    try:
        # All surviving host-owned watch pipe writers close on crash even if
        # no Python 'finally' gets a chance to execute.
        while os.read(args.watch_fd,1):
            pass
    finally:
        os.close(args.watch_fd)
    cleanup_after_parent_death(target)


if __name__=="__main__":
    main()
