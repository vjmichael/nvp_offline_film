"""W1-G: bounded legacy Blender subprocess adapter under native release custody.

Existing trusted Blender art/calibration scripts used subprocess.run directly.
On Windows, EVERY such launch now uses the original suspended-CreateProcess
Job Object/128-slot release gate. No stdout pipes, shell, string commands,
unverified descendants or unbounded logs are admitted.

Linux remains on its existing standalone acceptance subprocess until its
separate cgroup-v2 production migration; these Windows-specific release
claims must never be applied to Linux.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def run_trusted_blender(command, *, cwd=None, timeout=120, text=True,
                        capture_output=True, **extra):
    if (type(command) is not list or not command or
        any(type(value) is not str for value in command) or
        not capture_output or text is not True or
        type(timeout) not in (int,float) or
        type(timeout) is bool or not 0 < timeout <= 7200 or
        extra):
        raise ValueError("Only bounded, unambiguous original Blender tool execution is permitted")
    if os.name!="nt":
        return subprocess.run(command,cwd=cwd,timeout=timeout,
                              text=True,capture_output=True,check=False)
    from backend.nvp_worker_containment import launch_contained
    executable=Path(command[0])
    if not executable.is_absolute():
        resolved=shutil.which(command[0])
        if not resolved:
            raise RuntimeError("Trusted native Blender executable was not found")
        executable=Path(resolved)
    if executable.is_symlink() or not executable.is_file():
        raise RuntimeError("Untrusted native Blender executable path")
    command=[str(executable),*command[1:]]
    root=Path(cwd or os.getcwd()).resolve()
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("Trusted original native Blender workspace is not an ordinary directory")
    with tempfile.TemporaryDirectory(prefix="nvp-owned-blender-",dir=root) as temporary:
        folder=Path(temporary)
        stdout=folder/"stdout.log";stderr=folder/"stderr.log"
        with stdout.open("wb") as out,stderr.open("wb") as err:
            proc=launch_contained(command,cwd=str(root),stdout=out,stderr=err,
                                  memory_mb=0)
            try:
                try:
                    code=proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.terminate_tree()
                    raise subprocess.TimeoutExpired(command,timeout)
            finally:
                # Releasing the launch slot requires independent kernel
                # verification that every Job descendant has exited.
                proc.close()
        # Legacy callers need bounded diagnostics, never unbounded process IO.
        for file in (stdout,stderr):
            if file.stat().st_size>2*1024*1024:
                raise RuntimeError("Native Blender worker exceeded bounded diagnostic output")
        return subprocess.CompletedProcess(
            command,code,
            stdout.read_bytes().decode("utf-8","replace"),
            stderr.read_bytes().decode("utf-8","replace"))
