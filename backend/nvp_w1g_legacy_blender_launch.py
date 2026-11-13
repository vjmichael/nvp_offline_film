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
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess


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
    # The canonical native process adapter supervises the original Windows
    # Job Object AND keeps original stdout/stderr diagnostics in bounded RAM,
    # not an unencrypted worker log in the authored Blender scene directory.
    result=run_owned_subprocess(command,cwd=cwd,timeout=timeout,
                                text=True,capture_output=True,check=False)
    if (len(result.stdout.encode("utf8"))>2*1024*1024 or
        len(result.stderr.encode("utf8"))>2*1024*1024):
        raise RuntimeError("Original Blender native diagnostics exceeded 2 MiB bound")
    return result
