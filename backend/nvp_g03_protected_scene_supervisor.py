"""G03-F1 supervised native OpenUSD production scene worker.

Only the host can issue a reviewed one-use grant. No model/browser can provide
an executable, source path, script, arbitrary operation, or cryptographic key.
Source and output move in anonymous pipes; verified output is immediately
sealed through LiveFilmStore's authenticated source index. Worker cancellation
uses the native suspended-start Windows Job Object with kill-on-close.

This currently produces three actual OpenUSD camera definitions, not a film
render; protected Blender/Cycles/full capture are still blocked.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
import tempfile
import threading
import time

from backend.nvp_g03_live_store import LiveFilmError
from backend.nvp_worker_containment import launch_contained
from tools.nvp_g03_protected_scene_worker import (
    MAGIC_IN, MAGIC_OUT, MAX_SOURCE, MAX_OUTPUT
)


class ProtectedWorkerError(LiveFilmError):
    pass

# Exact public, synthetic fixture, never an arbitrary director film.
SYNTHETIC_SCENE_CI_USDA=(
    b'#usda 1.0\n\ndef Xform "Original" {}\n')


def _sanitized_worker_env():
    # No NVP_HOME, API token, user secrets or optional cloud credentials.
    allow={"SYSTEMROOT","WINDIR","PATH","TEMP","TMP"}
    allowed={key:value for key,value in os.environ.items()
             if key.upper() in allow and value}
    allowed["PYTHONDONTWRITEBYTECODE"]="1"
    allowed["PYTHONIOENCODING"]="utf-8"
    return allowed


def _pinned_command():
    if sys.platform!="win32":
        raise ProtectedWorkerError("Windows Job Object custody required")
    exe=Path(sys.executable).resolve(strict=True)
    if getattr(sys,"frozen",False):
        return [str(exe),"--g03-protected-scene-worker"]
    # Not an arbitrary imported script; one fixed versioned NVP module.
    trusted=Path(__file__).resolve().parents[1]/"tools"/"nvp_g03_protected_scene_worker.py"
    if not trusted.is_file() or trusted.is_symlink():
        raise ProtectedWorkerError("Reviewed native scene script unavailable")
    return [str(exe),"-B",str(trusted)]


def _stream_read(file, maximum, output, errors):
    try:
        while True:
            chunk=file.read(65536)
            if not chunk:break
            if len(output)+len(chunk)>maximum:
                errors.append("Native worker exceeded bounded output")
                break
            output.extend(chunk)
    except Exception:
        errors.append("Native worker output pipe failed")


def _stream_write(file, payload, errors):
    try:
        file.write(payload)
        file.flush()
    except (OSError,BrokenPipeError):
        errors.append("Native worker input pipe failed")
    finally:
        file.close()


class ProtectedSceneSupervisor:
    def __init__(self,store,*,review_authority,os_isolation_attestor=None):
        if not callable(review_authority):
            raise ValueError("Trusted human approval checker is required")
        self.store=store
        self.review_authority=review_authority
        self.os_isolation_attestor=os_isolation_attestor

    def run(self,pid,token,source_name,output_name,approval_id,
            *,cancel=None,timeout=60,synthetic_ci_only=False):
        """Synchronously publish a new encrypted OpenUSD camera-coverage layer.

        The injected host authority must independently consume the creator's
        one-use review ticket and validate the exact project/input/output.
        Nothing in the HTTP API automatically grants production execution.
        """
        if sys.platform!="win32":
            raise ProtectedWorkerError("No native Windows job custody")
        isolated=(callable(self.os_isolation_attestor) and
                  self.os_isolation_attestor(pid,source_name,output_name))
        synthetic=(synthetic_ci_only is True and
                   os.environ.get("GITHUB_ACTIONS")=="true")
        if not isolated and not synthetic:
            raise ProtectedWorkerError(
                "Private scene worker requires independently verified AppContainer "
                "filesystem/network sandbox, not Job Object custody")
        if type(timeout) not in (int,float) or not 5<=timeout<=90:
            raise ValueError("Worker timeout must be 5..90 seconds")
        if not isinstance(approval_id,str) or len(approval_id)<24:
            raise ProtectedWorkerError("Missing one-use human review")
        if not self.review_authority(pid,source_name,output_name,approval_id):
            raise ProtectedWorkerError("Human approval refused or consumed")
        if cancel is not None and not hasattr(cancel,"is_set"):
            raise TypeError("Cancellation requires a trusted host event")
        run_id=secrets.token_hex(16)
        grant=self.store.worker_grant(pid,token,source_name,"read_original",
                                     human_approved=True)
        source=self.store.worker_execute(pid,grant,"read_original",source_name)
        if synthetic and (source_name!="original/scene.usda" or
                          output_name!="review/camera-coverage.usda" or
                          source!=SYNTHETIC_SCENE_CI_USDA):
            raise ProtectedWorkerError(
                "Synthetic scene CI exception refuses non-fixture original film")
        if len(source)>MAX_SOURCE:
            raise ProtectedWorkerError("Native OpenUSD worker source exceeds cap")
        source_hash=hashlib.sha256(source).hexdigest()
        if cancel is not None and cancel.is_set():
            raise ProtectedWorkerError("Operation cancelled before worker launch")
        self.store.worker_run_transition(pid,token,run_id,source_name,
                                         source_hash,"RUNNING")
        payload=MAGIC_IN+struct.pack("!Q",len(source))+source
        # All three channels are anonymous OS pipes. No decrypted source or
        # output is opened as a filesystem file, including temporary files.
        infd,outfd,errfd=(os.pipe(),os.pipe(),os.pipe())
        proc=None
        inread,inwrite=infd
        outread,outwrite=outfd
        errread,errwrite=errfd
        input_stream=os.fdopen(inread,"rb",buffering=0)
        output_stream=os.fdopen(outwrite,"wb",buffering=0)
        error_stream=os.fdopen(errwrite,"wb",buffering=0)
        output_recv=os.fdopen(outread,"rb",buffering=0)
        error_recv=os.fdopen(errread,"rb",buffering=0)
        input_send=os.fdopen(inwrite,"wb",buffering=0)
        stdout=bytearray();stderr=bytearray();errors=[]
        status="FAILED";code=None;published=None;custody_verified=False
        threads=[]
        try:
            with tempfile.TemporaryDirectory(prefix="nvp-g03-protected-scene-") as empty_cwd:
                command=_pinned_command()
                trusted=([] if getattr(sys,"frozen",False)
                         else [Path(command[-1])])
                proc=launch_contained(command,cwd=empty_cwd,
                      stdin=input_stream,stdout=output_stream,
                      stderr=error_stream,memory_mb=2048,
                      env=_sanitized_worker_env(),
                      windows_appcontainer_required=isolated,
                      appcontainer_code_roots=[Path(command[0]).parent],
                      appcontainer_code_files=trusted)
                # Closing the parent's copies is vital for EOF and cancellation.
                input_stream.close();output_stream.close();error_stream.close()
                for fn,args in (
                    (_stream_write,(input_send,payload,errors)),
                    (_stream_read,(output_recv,MAX_OUTPUT+len(MAGIC_OUT)+8,
                                   stdout,errors)),
                    (_stream_read,(error_recv,4096,stderr,errors))
                ):
                    th=threading.Thread(target=fn,args=args,daemon=True)
                    th.start();threads.append(th)
                deadline=time.monotonic()+timeout
                while proc.poll() is None:
                    if cancel is not None and cancel.is_set():
                        status="CANCELLED"
                        break
                    if errors or time.monotonic()>=deadline:
                        status="FAILED"
                        break
                    time.sleep(.03)
                if proc.poll() is None:
                    proc.terminate_tree()
                code=proc.wait(timeout=12)
                # A cancelled worker may still have output in its buffer;
                # never publish that output, even if the worker exits zero.
                for th in threads:th.join(timeout=6)
                if any(th.is_alive() for th in threads):
                    raise ProtectedWorkerError("Worker pipe custody is incomplete")
                # Mandatory pre-publication boundary: close the actual Job
                # and audit disposable cwd + AppContainer profile BEFORE
                # issuing any encrypted output grant or success receipt.
                exited=proc
                proc=None
                exited.close()
                custody_verified=True
                if status=="CANCELLED":
                    raise ProtectedWorkerError("Creator cancelled contained scene worker")
                if errors or code!=0:
                    raise ProtectedWorkerError("Contained OpenUSD worker failed")
                if list(Path(empty_cwd).rglob("*")):
                    raise ProtectedWorkerError("Protected worker wrote a plaintext file")
                if not stdout.startswith(MAGIC_OUT) or len(stdout)<len(MAGIC_OUT)+8:
                    raise ProtectedWorkerError("Native worker output protocol invalid")
                count=struct.unpack("!Q",
                    stdout[len(MAGIC_OUT):len(MAGIC_OUT)+8])[0]
                derived=bytes(stdout[len(MAGIC_OUT)+8:])
                if count!=len(derived) or count>MAX_OUTPUT:
                    raise ProtectedWorkerError("Native output length mismatch")
                # Independently verify derived native USD in the trusted host
                # before its immutable encrypted original is committed.
                from pxr import Sdf
                check=Sdf.Layer.CreateAnonymous("trusted_verified.usda")
                if not check.ImportFromString(derived.decode("utf8")):
                    raise ProtectedWorkerError("Native output did not parse")
                if cancel is not None and cancel.is_set():
                    status="CANCELLED"
                    raise ProtectedWorkerError("Cancelled after worker returned")
                write_grant=self.store.worker_grant(
                    pid,token,output_name,"write_original",human_approved=True)
                published=self.store.worker_execute(pid,write_grant,
                    "write_original",output_name,data=derived)
                self.store.worker_run_transition(pid,token,run_id,source_name,
                    source_hash,"SUCCEEDED",
                    output_sha256=published["sha256"],exit_code=code)
                status="SUCCEEDED"
                return {"state":status,"worker_id":run_id,
                    "native_job_tree_exited":custody_verified,
                    "source_sha256":source_hash,
                    "output_sha256":published["sha256"],
                    "output_name":output_name,"encrypted_output":True,
                    "frames_rendered":0,
                    "kind":"native_opensud_three_camera_staging"}
        except Exception:
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate_tree()
                    custody_verified=proc.poll() is not None
                except Exception:
                    custody_verified=False
            state=("CANCELLED" if status=="CANCELLED" and custody_verified else
                   "FAILED" if custody_verified else "CUSTODY_UNPROVEN")
            try:
                self.store.worker_run_transition(pid,token,run_id,source_name,
                    source_hash,state,exit_code=code)
            except Exception:
                # Source may have been locked midflight. The durable RUNNING
                # encrypted receipt remains and cold recovery must mark it
                # interrupted, never automatically replay or publish output.
                pass
            raise
        finally:
            for file in (input_stream,output_stream,error_stream,
                         input_send,output_recv,error_recv):
                try:file.close()
                except OSError:pass
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.terminate_tree()
                    proc.close()
                except Exception:
                    # Native custody cannot be inferred from a PID.
                    pass
