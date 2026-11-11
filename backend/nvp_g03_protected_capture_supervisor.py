"""G03-F2: host-authorized Windows native microphone -> encrypted original PCM.

Separate one-use human authorization (host only) and an actual native OS
approval callback are mandatory. PortAudio runs in a suspended-start Windows
Job Object child, stdout is a bounded anonymous binary pipe, and only an
authenticated encrypted original reaches durable storage.

Native OS prompt approval does not attest that Windows microphone access was
granted; physical microphone/device acceptance remains a separate gate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import sys
import tempfile
import threading
import time

from backend.nvp_g03_live_store import LiveFilmError
from backend.nvp_g03_protected_scene_supervisor import (
    _pinned_command as _scene_command, _sanitized_worker_env,
    _stream_read, _stream_write
)
from backend.nvp_worker_containment import launch_contained
from tools.nvp_g03_protected_capture_worker import (
    CAP_IN, CAP_OUT, MAX_REQUEST, MAX_PCM_BYTES, MAX_SECONDS, SAMPLE_RATE
)


class ProtectedCaptureError(LiveFilmError):
    pass


class ProtectedCaptureSupervisor:
    def __init__(self,store,*,review_authority,native_os_prompt,
                 os_isolation_attestor=None):
        if not callable(review_authority) or not callable(native_os_prompt):
            raise TypeError("Host one-use review and native OS prompt are both required")
        self.store=store
        self.review_authority=review_authority
        self.native_os_prompt=native_os_prompt
        self.os_isolation_attestor=os_isolation_attestor

    @staticmethod
    def _command():
        if sys.platform!="win32":
            raise ProtectedCaptureError("Real Windows native job custody is required")
        executable=Path(sys.executable).resolve(strict=True)
        if getattr(sys,"frozen",False):
            return [str(executable),"--g03-protected-capture-worker"]
        source=(Path(__file__).resolve().parents[1]/"tools"/
                "nvp_g03_protected_capture_worker.py")
        if not source.is_file() or source.is_symlink():
            raise ProtectedCaptureError("Native reviewed capture worker missing")
        return [str(executable),"-B",str(source)]

    def capture(self,pid,token,source_name,approval_id,
                *,device_id,channels,frames,cancel=None,
                synthetic_owner_only=False):
        if sys.platform!="win32":
            raise ProtectedCaptureError("Windows mic capture is unavailable here")
        if (type(device_id) is not int or not -1<=device_id<=65535 or
            type(channels) is not int or channels not in (1,2) or
            type(frames) is not int or not 1<=frames<=MAX_SECONDS*SAMPLE_RATE):
            raise ValueError("Bounded, exact physical capture settings required")
        if type(approval_id) is not str or len(approval_id)<24:
            raise ProtectedCaptureError("No reviewed native capture permission")
        if cancel is not None and not hasattr(cancel,"is_set"):
            raise TypeError("Host cancellation event required")
        scope=(pid,source_name,device_id,channels,frames,approval_id)
        if not self.review_authority(*scope):
            raise ProtectedCaptureError("Creator review refused or replayed")
        if not self.native_os_prompt(*scope):
            raise ProtectedCaptureError("Native operator refused microphone capture")
        # Job Objects contain process trees but give a worker the same user's
        # filesystem/network access. Do not expose private original audio to a
        # full-account PortAudio child before a separately verified sandbox.
        # Synthetic owner hardware diagnosis is an explicit test-only exception.
        isolated=(callable(self.os_isolation_attestor) and
                  self.os_isolation_attestor(pid,source_name,device_id))
        synthetic=(synthetic_owner_only is True and
                   source_name=="capture/physical-owner-test.pcm16le" and
                   os.environ.get("GITHUB_ACTIONS") is None and
                   os.environ.get("CI") is None)
        if not (isolated or synthetic):
            raise ProtectedCaptureError(
                "Private microphone capture requires independently verified "
                "Windows AppContainer filesystem/network confinement")
        self.store._session(pid,token)
        if cancel is not None and cancel.is_set():
            raise ProtectedCaptureError("Microphone capture cancelled before launch")
        doc={"device_id":device_id,"channels":channels,"frames":frames}
        body=json.dumps(doc,sort_keys=True,separators=(",",":")).encode()
        if len(body)>MAX_REQUEST:
            raise ProtectedCaptureError("Native capture request oversized")
        input_bytes=CAP_IN+struct.pack("!I",len(body))+body
        original_request_sha=hashlib.sha256(body).hexdigest()
        run_id=secrets.token_hex(16)
        self.store.worker_run_transition(
            pid,token,run_id,source_name,original_request_sha,"RUNNING")
        ins=os.pipe(); outs=os.pipe(); errs=os.pipe()
        input_reader=os.fdopen(ins[0],"rb",buffering=0)
        input_writer=os.fdopen(ins[1],"wb",buffering=0)
        output_reader=os.fdopen(outs[0],"rb",buffering=0)
        output_writer=os.fdopen(outs[1],"wb",buffering=0)
        error_reader=os.fdopen(errs[0],"rb",buffering=0)
        error_writer=os.fdopen(errs[1],"wb",buffering=0)
        proc=None
        stdout=bytearray();stderr=bytearray();errors=[]
        threads=[]
        outcome="FAILED";exit_code=None;job_closed=False
        try:
            with tempfile.TemporaryDirectory(prefix="nvp-protected-mic-") as empty:
                proc=launch_contained(
                    self._command(),cwd=empty,
                    stdin=input_reader,stdout=output_writer,stderr=error_writer,
                    memory_mb=1024,env=_sanitized_worker_env(),
                    windows_appcontainer_required=isolated)
                input_reader.close();output_writer.close();error_writer.close()
                for fn,args in (
                    (_stream_write,(input_writer,input_bytes,errors)),
                    (_stream_read,(output_reader,MAX_PCM_BYTES+len(CAP_OUT)+8,stdout,errors)),
                    (_stream_read,(error_reader,4096,stderr,errors))):
                    thread=threading.Thread(target=fn,args=args,daemon=True)
                    thread.start();threads.append(thread)
                deadline=time.monotonic()+max(12,frames/SAMPLE_RATE+10)
                while proc.poll() is None:
                    if cancel is not None and cancel.is_set():
                        outcome="CANCELLED";break
                    if errors or time.monotonic()>deadline:
                        break
                    time.sleep(.025)
                if proc.poll() is None:
                    proc.terminate_tree()
                exit_code=proc.wait(timeout=12)
                for thread in threads:thread.join(timeout=5)
                if any(t.is_alive() for t in threads):
                    raise ProtectedCaptureError("Native audio pipe custody uncertain")
                # Only after closing the actual Job Object kill-on-close
                # handle may encrypted publication commence.
                proc.close();proc=None;job_closed=True
                if outcome=="CANCELLED":
                    raise ProtectedCaptureError("Native capture was cancelled")
                if errors or exit_code!=0:
                    raise ProtectedCaptureError("Native device capture failed")
                if list(Path(empty).rglob("*")):
                    raise ProtectedCaptureError("Native capture worker wrote plaintext disk data")
                if not stdout.startswith(CAP_OUT) or len(stdout)<len(CAP_OUT)+8:
                    raise ProtectedCaptureError("Native PCM output protocol invalid")
                size=struct.unpack(
                    "!Q",stdout[len(CAP_OUT):len(CAP_OUT)+8])[0]
                pcm=bytes(stdout[len(CAP_OUT)+8:])
                if size!=len(pcm) or size!=frames*channels*2:
                    raise ProtectedCaptureError("Native original PCM sample count mismatch")
                if cancel is not None and cancel.is_set():
                    raise ProtectedCaptureError("Capture cancelled before encryption")
                original_sha=hashlib.sha256(pcm).hexdigest()
                write=self.store.worker_grant(
                    pid,token,source_name,"write_original",human_approved=True)
                stored=self.store.worker_execute(
                    pid,write,"write_original",source_name,data=pcm,
                    media_type="application/vnd.nvp.pcm16le")
                if stored["sha256"]!=original_sha:
                    raise ProtectedCaptureError("Encrypted PCM changed after commit")
                self.store.worker_run_transition(
                    pid,token,run_id,source_name,original_request_sha,
                    "SUCCEEDED",output_sha256=original_sha,exit_code=exit_code)
                outcome="SUCCEEDED"
                return {"status":"RECORDED_ORIGINAL_ENCRYPTED",
                    "take_frozen":False,
                    "worker_id":run_id,"sample_rate":SAMPLE_RATE,
                    "frames":frames,"channels":channels,
                    "pcm_sha256":original_sha,
                    "native_job_handle_closed":job_closed,
                    "physical_device_owner_acceptance":False}
        except Exception:
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.terminate_tree()
                    proc.close()
                    proc=None
                    job_closed=True
                except Exception:
                    job_closed=False
            state=("CANCELLED" if outcome=="CANCELLED" and job_closed else
                   "FAILED" if job_closed else "CUSTODY_UNPROVEN")
            try:
                self.store.worker_run_transition(
                    pid,token,run_id,source_name,original_request_sha,
                    state,exit_code=exit_code)
            except Exception:
                # Lock/restart leaves the prior encrypted RUNNING record;
                # cold recovery marks it interrupted, never auto-freezes.
                pass
            raise
        finally:
            for stream in (input_reader,input_writer,output_reader,output_writer,
                           error_reader,error_writer):
                try:stream.close()
                except OSError:pass
