"""W1-G original native synchronous tool execution with release-wide Windows custody.

Windows child processes must hold the central suspended-CreateProcess Job Object
and one independent release-lifetime slot. Original stdin bytes are spooled to
a private file, never pushed through an unowned PIPE; stdout/stderr go to
bounded files, not unbounded Python pipes. The original Job is closed only
after its actual kernel accounting proves all descendants gone.

Linux preserves existing legacy tooling for source/technical tests. It does
NOT claim Linux cgroup-v2 custody or authorize a production Windows upgrade.
New protected production Linux roles must use launch_contained(...,
linux_cgroup_tree_required=True) instead.
"""
from __future__ import annotations

from contextlib import ExitStack
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import shutil
import secrets
import subprocess
import tempfile


MAX_STREAM = 256 * 1024 * 1024


def run_owned_subprocess(command, *, cwd=None, timeout=120, check=False,
                         capture_output=False, stdin=None, stdout=None, stderr=None,
                         input=None, text=False, encoding=None, errors="replace"):
    if (type(command) is not list or not command or
        any(not isinstance(value,(str,os.PathLike)) for value in command) or
        type(timeout) not in (int,float) or type(timeout) is bool or
        not math.isfinite(timeout) or not 0 < timeout <= 21600 or
        type(check) is not bool or type(capture_output) is not bool or
        type(text) is not bool or
        encoding is not None and type(encoding) is not str or
        errors not in ("replace","strict","ignore")):
        raise ValueError("Bounded explicit original native worker invocation required")
    command=[os.fspath(arg) for arg in command]
    if input is not None:
        if stdin is not None or type(input) not in (bytes,str):
            raise ValueError("Native worker input must be explicit bounded bytes or text")
        if isinstance(input,str):
            if not text:
                raise TypeError("Native text input requires text=True")
            input=input.encode(encoding or "utf8",errors)
        if len(input)>MAX_STREAM:
            raise ValueError("Original worker input exceeds bounded spool budget")
    elif stdin not in (None,subprocess.DEVNULL):
        raise ValueError("Native worker stdin must be DEVNULL or sealed input")
    if capture_output:
        if stdout is not None or stderr is not None:
            raise ValueError("capture_output cannot be combined with output streams")
        stdout=stderr=subprocess.PIPE
    if stdout not in (None,subprocess.PIPE,subprocess.DEVNULL) and not hasattr(stdout,"fileno"):
        raise ValueError("Unsupported original worker stdout destination")
    if stderr not in (None,subprocess.PIPE,subprocess.DEVNULL) and not hasattr(stderr,"fileno"):
        raise ValueError("Unsupported original worker stderr destination")
    if os.name != "nt":
        return subprocess.run(
            command,cwd=cwd,timeout=timeout,check=check,capture_output=capture_output,
            stdin=stdin,stdout=None if capture_output else stdout,
            stderr=None if capture_output else stderr,input=input,text=text,
            encoding=encoding,errors=errors)
    from backend.nvp_worker_containment import launch_contained

    binary=Path(command[0])
    if not binary.is_absolute():
        found=shutil.which(command[0])
        if not found:
            raise RuntimeError("Original native worker executable was not found")
        binary=Path(found)
    if binary.is_symlink() or not binary.is_file():
        raise PermissionError("Original native worker executable cannot be linked or missing")
    command[0]=str(binary.resolve())
    directory=Path(cwd or os.getcwd())
    if directory.is_symlink() or not directory.resolve().is_dir():
        raise RuntimeError("Original native worker cwd must be an ordinary directory")
    # Register BEFORE the Job is created. A hard process death leaves a
    # durable pending marker and the updater refuses upgrade until an
    # independent source/output reconciliation has cleared it.
    from backend.nvp_w1g_release_gate import release_gate_path
    registration=release_gate_path().parent/"legacy-jobs"
    if registration.is_symlink():
        raise RuntimeError("Linked original legacy worker registration refused")
    registration.mkdir(mode=0o700,exist_ok=True)
    if registration.is_symlink():
        raise RuntimeError("Original worker registration was replaced by a link")
    marker=registration/("original-"+secrets.token_hex(16)+".pending")
    identity=sha256("\\0".join(command).encode("utf8")).hexdigest()
    with marker.open("xb") as ticket:
        payload=json.dumps({"format":"nvp.w1g.legacy_release_worker.v1",
            "identity_sha256":identity,"status":"START_PENDING",
            "requires_original_journal_reconciliation":True},
            sort_keys=True,separators=(",",":")).encode("utf8")
        ticket.write(payload)
        ticket.flush()
        os.fsync(ticket.fileno())
    with tempfile.TemporaryDirectory(prefix="nvp-release-owned-") as workspace:
        root=Path(workspace)
        with ExitStack() as streams:
            sealed=None
            if input is not None:
                sealed=streams.enter_context((root/"stdin.bin").open("w+b"))
                sealed.write(input)
                sealed.flush()
                os.fsync(sealed.fileno())
                sealed.seek(0)
            out_capture=stdout==subprocess.PIPE
            err_capture=stderr==subprocess.PIPE
            out_file=streams.enter_context((root/"stdout.log").open("w+b")) if (
                stdout in (None,subprocess.PIPE)) else (
                streams.enter_context(open(os.devnull,"wb")) if stdout==subprocess.DEVNULL else stdout)
            err_file=streams.enter_context((root/"stderr.log").open("w+b")) if (
                stderr in (None,subprocess.PIPE)) else (
                streams.enter_context(open(os.devnull,"wb")) if stderr==subprocess.DEVNULL else stderr)
            proc=launch_contained(command,cwd=str(directory.resolve()),
                stdout=out_file,stderr=err_file,stdin=sealed,memory_mb=0)
            try:
                try:
                    code=proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.terminate_tree()
                    raise subprocess.TimeoutExpired(command,timeout)
            finally:
                # No success, failure or timeout may drop release ownership
                # until original Job accounting verifies all descendants gone.
                proc.close()
            def read_bounded(stream):
                stream.flush()
                size=stream.seek(0,os.SEEK_END)
                if size>MAX_STREAM:
                    raise RuntimeError("Original native worker output exceeds spool budget")
                stream.seek(0)
                return stream.read()
            raw_out=read_bounded(out_file) if out_capture else None
            raw_err=read_bounded(err_file) if err_capture else None
        if text:
            raw_out=raw_out.decode(encoding or "utf8",errors) if raw_out is not None else None
            raw_err=raw_err.decode(encoding or "utf8",errors) if raw_err is not None else None
        result=subprocess.CompletedProcess(command,code,raw_out,raw_err)
        if code != 0:
            # Even after Job cleanup, an unsuccessful legacy tool may have
            # left a partial frame, render or external derivative. Do not
            # silently certify its interrupted artifact for a release swap.
            if check:
                result.check_returncode()
            return result
        # Tree-empty kernel proof came from proc.close() above; an original
        # successful worker has now released the kernel slot and no future
        # launch can race an updater holding the all-slots gate.
        marker.unlink()
        if check:
            result.check_returncode()
        return result
