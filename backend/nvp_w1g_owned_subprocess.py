"""W1-G release-owned original native process execution with memory-only pipes.

Windows children run in central suspended/assigned Job Objects with a release
lifetime slot. Unlike legacy spool-based adapters, input/output bytes remain
in bounded RAM: NO plaintext stdin.bin, PCM stdout.log or media staging on
unprotected OS temp storage. This is not an EFS/key custody substitute for
the worker's own original source files.

Linux preserves original standalone test behavior, not production cgroup
acceptance. Arbitrary shell, unbounded streams, missing pinned executable,
and unresolved Windows descendants fail closed.
"""
from __future__ import annotations

from contextlib import ExitStack
from hashlib import sha256
import json
import secrets
import math
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time


MAX_STREAM=256*1024*1024


def run_owned_subprocess(command, *, cwd=None, timeout=120, check=False,
                         capture_output=False, stdin=None, stdout=None, stderr=None,
                         input=None, text=False, encoding=None, errors="replace"):
    if (type(command) is not list or not command or
        any(not isinstance(value,(str,os.PathLike)) for value in command) or
        type(timeout) not in (int,float) or type(timeout) is bool or
        not math.isfinite(timeout) or not 0<timeout<=21600 or
        type(check) is not bool or type(capture_output) is not bool or
        type(text) is not bool or
        (encoding is not None and type(encoding) is not str) or
        errors not in ("replace","strict","ignore")):
        raise ValueError("Bounded explicit original native worker invocation required")
    command=[os.fspath(arg) for arg in command]
    if input is not None:
        if stdin is not None or type(input) not in (bytes,str):
            raise ValueError("Original native stdin must be explicit bounded bytes/text")
        if isinstance(input,str):
            if text is not True:
                raise TypeError("Native string input requires text=True")
            if len(input)>MAX_STREAM:
                raise ValueError("Original worker text exceeds bounded input memory")
        elif len(input)>MAX_STREAM:
            raise ValueError("Original worker input exceeds bounded memory")
    elif stdin not in (None,subprocess.DEVNULL):
        raise ValueError("Original native stdin must be DEVNULL or sealed input")
    if capture_output:
        if stdout is not None or stderr is not None:
            raise ValueError("capture_output cannot be combined with explicit outputs")
        stdout=stderr=subprocess.PIPE
    for stream in (stdout,stderr):
        if (stream not in (None,subprocess.PIPE,subprocess.DEVNULL)
            and not hasattr(stream,"fileno")):
            raise ValueError("Untrusted original native output destination")
    if os.name!="nt":
        return subprocess.run(
            command,cwd=cwd,timeout=timeout,check=check,
            stdin=stdin,stdout=stdout,stderr=stderr,
            input=input,capture_output=False,text=text,
            encoding=encoding if text else None,
            errors=errors if text else None)

    from backend.nvp_worker_containment import launch_contained
    binary=Path(command[0])
    if not binary.is_absolute():
        found=shutil.which(command[0])
        if not found:
            raise RuntimeError("Original native executable unavailable")
        binary=Path(found)
    if binary.is_symlink() or not binary.is_file():
        raise PermissionError("Original native executable linked or missing")
    command[0]=str(binary.resolve())
    directory=Path(cwd or os.getcwd())
    if directory.is_symlink() or not directory.resolve().is_dir():
        raise RuntimeError("Original native process cwd cannot be linked or missing")
    if isinstance(input,str):
        input=input.encode(encoding or "utf8",errors)

    # Preserve original release-wide crash admission from the reviewed
    # previous adapter. A kernel host death must leave a durable marker even
    # though the Win32 Job closes and the shared launch slot disappears.
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
        ticket.flush();os.fsync(ticket.fileno())

    output_count=[0]
    failures=[]
    overflow=threading.Event()
    budget=threading.Lock()

    with ExitStack() as stack:
        def output_stream(wanted):
            if wanted==subprocess.PIPE:
                r,w=os.pipe()
                read=stack.enter_context(os.fdopen(r,"rb",buffering=0))
                write=stack.enter_context(os.fdopen(w,"wb",buffering=0))
                return read,write,bytearray()
            if wanted is None or wanted==subprocess.DEVNULL:
                return None,stack.enter_context(open(os.devnull,"wb")),None
            return None,wanted,None

        out_r,out_w,out_data=output_stream(stdout)
        err_r,err_w,err_data=output_stream(stderr)
        input_writer=None
        child_input=None
        if input is not None:
            in_r,in_w=os.pipe()
            child_input=stack.enter_context(os.fdopen(in_r,"rb",buffering=0))
            input_writer=stack.enter_context(os.fdopen(in_w,"wb",buffering=0))
        proc=launch_contained(command,cwd=str(directory.resolve()),
            stdout=out_w,stderr=err_w,stdin=child_input,memory_mb=0)
        # Close inherited pipe ends on the host immediately after the child
        # has inherited them; a grandchild cannot keep an unowned pipe open
        # beyond the original kill-on-close Windows Job Object.
        if out_r is not None:out_w.close()
        if err_r is not None:err_w.close()
        if child_input is not None:child_input.close()

        def drain(reader,buffer):
            try:
                while True:
                    block=reader.read(65536)
                    if not block:return
                    with budget:
                        if output_count[0]+len(block)>MAX_STREAM:
                            overflow.set();return
                        output_count[0]+=len(block)
                    buffer.extend(block)
            except BaseException as exc:
                failures.append("stdout/stderr read "+type(exc).__name__)

        def send_input():
            try:
                for start in range(0,len(input),65536):
                    input_writer.write(input[start:start+65536])
            except BrokenPipeError:
                failures.append("original worker closed input before verified consumption")
            except BaseException as exc:
                failures.append("original stdin write "+type(exc).__name__)
            finally:
                input_writer.close()

        threads=[]
        for reader,buffer in ((out_r,out_data),(err_r,err_data)):
            if reader is not None:
                thread=threading.Thread(target=drain,args=(reader,buffer),
                                        daemon=True)
                thread.start();threads.append(thread)
        if input_writer is not None:
            thread=threading.Thread(target=send_input,daemon=True)
            thread.start();threads.append(thread)

        try:
            deadline=time.monotonic()+timeout
            while True:
                if overflow.is_set():
                    proc.terminate_tree()
                    raise RuntimeError("Original native stdout/stderr exceeded RAM bound")
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    proc.terminate_tree()
                    raise subprocess.TimeoutExpired(command,timeout)
                try:
                    code=proc.wait(timeout=min(remaining,.15))
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            # A success, failure, timeout or cancellation MUST recheck the
            # original Job Object and reap descendants before dropping its
            # release-wide admission slot and durable launch journal.
            proc.close()
            for thread in threads:
                thread.join(timeout=7)
        if any(thread.is_alive() for thread in threads):
            raise RuntimeError("Original native worker pipe still owned after Job closure")
        if overflow.is_set() or failures:
            raise RuntimeError("Original native pipe verification failed: "+
                               ",".join(failures))
        out=bytes(out_data) if out_data is not None else None
        err=bytes(err_data) if err_data is not None else None
        if text:
            out=out.decode(encoding or "utf8",errors) if out is not None else None
            err=err.decode(encoding or "utf8",errors) if err is not None else None
        result=subprocess.CompletedProcess(command,code,out,err)
        # A nonzero native return can leave partial output artifacts. An
        # interrupted or uncertain worker must stay on the release ledger
        # until independently reviewed, despite an empty kernel Job tree.
        if code==0:
            marker.unlink()
        if check:
            result.check_returncode()
        return result
