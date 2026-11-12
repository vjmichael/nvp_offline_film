"""W1-E independently confined fixed native private-film reel supervisor.

Human one-use review and independently attested kernel AppContainer isolation
are mandatory; a Windows Job Object alone NEVER admits private source. The
host decrypts source only into memory, supplies a bounded original window
through anonymous pipes, independently reopens the worker's native AVI, then
seals it through a one-use LiveFilmStore broker. No plaintext temp/output file,
source DB path, crypto key, inherited model token or network service is given
to the child.

Linux private-film sandbox is NOT admitted until independently equivalent
filesystem/network process isolation has been implemented.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import secrets

from backend.nvp_g03_protected_scene_supervisor import (
    _sanitized_worker_env,_stream_write,_stream_read)
from backend.nvp_g09e_chunk import (
    check_assembly,source_digests,MAX_CHUNK_BYTES,FRAMES_PER_CHUNK,
    MAX_FRAMES)
from backend.nvp_g08_native_avi import TICKS_FRAME,verify_movie
from backend.nvp_g09e_pcm import verified_pcm_digest
from backend.nvp_worker_containment import launch_contained
from tools.nvp_w1e_sealed_reel_worker import (
    MAGIC_IN,MAGIC_OUT,FORMAT,MAX_INPUT,MAX_ORIGINAL)

MAX_LOG=4096
MAX_TIMEOUT=30*60


class ProtectedFilmReelError(RuntimeError):
    pass


def _fixed_command():
    if sys.platform!="win32":
        raise ProtectedFilmReelError("Private reel worker requires Windows AppContainer")
    exe=Path(sys.executable).resolve(strict=True)
    if getattr(sys,"frozen",False):
        return [str(exe),"--w1e-sealed-reel-worker"],[]
    tool=Path(__file__).resolve().parents[1]/"tools"/"nvp_w1e_sealed_reel_worker.py"
    if not tool.is_file() or tool.is_symlink():
        raise ProtectedFilmReelError("Reviewed reel worker is not installed")
    # The child has a disposable cwd and a sanitized environment with
    # no PYTHONPATH. -m tools.* would not resolve from that cwd. Execute the
    # exact reviewed file and let its fixed bootstrap resolve backend imports.
    return [str(exe),"-B",str(tool)],[tool]


def _serialize_window(assembly,start,end,total_frames,plan):
    digest=source_digests(assembly)
    check_assembly(assembly,total_frames,start,end,digest)
    binding=sha256(json.dumps(digest,sort_keys=True,
        separators=(",",":")).encode("utf8")).hexdigest()
    media=0
    copies={}
    for tid,take in assembly["original_takes"].items():
        encoded={**take}
        for name in ("original_usd","performance_usd"):
            data=take[name]
            if not isinstance(data,bytes):
                raise ProtectedFilmReelError("Source OpenUSD bytes were not verified")
            media+=len(data)
            encoded[name]=base64.b64encode(data).decode("ascii")
        audio=[]
        for clip in take["audio"]:
            original=clip["pcm16le"]
            if verified_pcm_digest(original)!=clip["pcm_sha256"]:
                raise ProtectedFilmReelError("Original sealed sound SHA mismatch")
            length=len(original)
            media+=length
            if media>MAX_ORIGINAL:
                raise ProtectedFilmReelError("Original protected source exceeds 256MiB")
            pcm=b"".join(original[i:min(length,i+1024*1024)]
                         for i in range(0,length,1024*1024))
            if sha256(pcm).hexdigest()!=clip["pcm_sha256"]:
                raise ProtectedFilmReelError("Source changed during bounded serialization")
            audio.append({**clip,"pcm16le":base64.b64encode(pcm).decode("ascii")})
        encoded["audio"]=audio
        copies[tid]=encoded
    copy={**assembly,"original_takes":copies}
    payload=json.dumps({
        "format":FORMAT,"assembly":copy,"start_frame":start,
        "end_frame":end,"total_frames":total_frames,"plan":plan,
        "source_sha256":binding},sort_keys=True,separators=(",",":"),
        ensure_ascii=False,allow_nan=False).encode("utf8")
    if not 0<len(payload)<=MAX_INPUT:
        raise ProtectedFilmReelError("Bounded source film worker input is too large")
    return payload,binding


class ProtectedSealedReelWorker:
    def __init__(self,store,*,review_authority,os_isolation_attestor):
        if not callable(review_authority) or not callable(os_isolation_attestor):
            raise ValueError("Host-reviewed approval and independent OS isolation required")
        self.store=store
        self.review_authority=review_authority
        self.os_isolation_attestor=os_isolation_attestor

    def render(self,pid,token,job,index,total_frames,assembly,plan,
               approval_id,*,cancel=None):
        if sys.platform!="win32":
            raise ProtectedFilmReelError("No independently isolated private film worker on this OS")
        if (type(index) is not int or index<0 or
            type(total_frames) is not int or not 1<=total_frames<=MAX_FRAMES or
            type(job) is not str or not len(job)==32 or
            type(approval_id) is not str or len(approval_id)<24):
            raise ProtectedFilmReelError("A reviewed owned-film work order is required")
        if cancel is not None and not hasattr(cancel,"is_set"):
            raise ProtectedFilmReelError("Cancellation must be a trusted host event")
        start=index*FRAMES_PER_CHUNK
        end=min(total_frames,start+FRAMES_PER_CHUNK)
        if not start<end:
            raise ProtectedFilmReelError("The private reel falls outside the film")
        self.store._session(pid,token)
        payload,binding=_serialize_window(assembly,start,end,total_frames,plan)
        if not self.os_isolation_attestor(pid,job,index,binding):
            raise ProtectedFilmReelError(
                "Private source requires independently verified Windows AppContainer "
                "filesystem and zero-network isolation")
        if not self.review_authority(pid,job,index,binding,approval_id):
            raise ProtectedFilmReelError("Director review refused, expired or was consumed")
        if cancel is not None and cancel.is_set():
            raise ProtectedFilmReelError("Director cancelled private reel before launch")
        worker_id=secrets.token_hex(16)
        source_name=f"render/{job}/source-{index:05d}"
        output_name=f"render/{job}/reel-{index:05d}-{worker_id}.avi"
        self.store.worker_run_transition(
            pid,token,worker_id,source_name,binding,"RUNNING")
        stdin_r,stdin_w=os.pipe()
        stdout_r,stdout_w=os.pipe()
        stderr_r,stderr_w=os.pipe()
        source=os.fdopen(stdin_r,"rb",buffering=0)
        out=os.fdopen(stdout_w,"wb",buffering=0)
        err=os.fdopen(stderr_w,"wb",buffering=0)
        sink=os.fdopen(stdin_w,"wb",buffering=0)
        answer=os.fdopen(stdout_r,"rb",buffering=0)
        log=os.fdopen(stderr_r,"rb",buffering=0)
        command,code_files=_fixed_command()
        frame=MAGIC_IN+struct.pack("!Q",len(payload))+payload
        stdout=bytearray();stderr=bytearray();errors=[]
        proc=None;code=None;custodied=False
        killed=False
        threads=[]
        try:
            with tempfile.TemporaryDirectory(prefix="nvp-w1e-private-reel-") as cwd:
                code_roots=[Path(command[0]).parent]
                if not getattr(sys,"frozen",False):
                    # Source mode must also admit reviewed read-only backend
                    # modules; do not extend DACLs to the NVP film home.
                    package=Path(__file__).resolve().parents[1]
                    code_roots.extend([package/"backend",package/"tools"])
                proc=launch_contained(command,cwd=cwd,
                    stdin=source,stdout=out,stderr=err,
                    env=_sanitized_worker_env(),memory_mb=4096,
                    windows_appcontainer_required=True,
                    appcontainer_code_roots=code_roots,
                    appcontainer_code_files=code_files)
                source.close();out.close();err.close()
                for fn,args in (
                    (_stream_write,(sink,frame,errors)),
                    (_stream_read,(answer,MAX_CHUNK_BYTES+len(MAGIC_OUT)+8,
                                   stdout,errors)),
                    (_stream_read,(log,MAX_LOG,stderr,errors))
                ):
                    worker=threading.Thread(target=fn,args=args,daemon=True)
                    worker.start();threads.append(worker)
                deadline=time.monotonic()+MAX_TIMEOUT
                while proc.poll() is None:
                    if (cancel is not None and cancel.is_set()):
                        killed=True
                        break
                    try:self.store._session(pid,token)
                    except Exception:
                        killed=True
                        break
                    if errors or time.monotonic()>deadline:
                        break
                    time.sleep(.05)
                if proc.poll() is None:
                    proc.terminate_tree()
                code=proc.wait(timeout=12)
                for worker in threads:worker.join(timeout=6)
                if any(worker.is_alive() for worker in threads):
                    raise ProtectedFilmReelError("Private reel pipe custody is incomplete")
                closed=proc;proc=None
                closed.close()  # kernel Job, AppContainer profile and ACL inspection
                custodied=True
                if killed:
                    raise InterruptedError("Director cancelled the private reel worker")
                if errors or code!=0:
                    raise ProtectedFilmReelError("Confined private reel failed")
                if list(Path(cwd).rglob("*")):
                    raise ProtectedFilmReelError("Private worker left plaintext disk artifacts")
                if (len(stdout)<len(MAGIC_OUT)+8 or
                    not stdout.startswith(MAGIC_OUT)):
                    raise ProtectedFilmReelError("Worker returned an unknown private film envelope")
                n=struct.unpack("!Q",
                    stdout[len(MAGIC_OUT):len(MAGIC_OUT)+8])[0]
                data=bytes(stdout[len(MAGIC_OUT)+8:])
                if not 0<n<=MAX_CHUNK_BYTES or len(data)!=n:
                    raise ProtectedFilmReelError("Derived reel exceeded its output boundary")
                digest=sha256(data).hexdigest()
                receipt=verify_movie(data,end-start,expected_sha=digest)
                if (not receipt["verified"] or
                    receipt["audio_samples_per_channel"]!=(end-start)*2000):
                    raise ProtectedFilmReelError("Independent PCM/frame verification failed")
                self.store._session(pid,token)
                if cancel is not None and cancel.is_set():
                    raise InterruptedError("Director stopped before protected publication")
                lease=self.store.worker_grant(pid,token,output_name,
                    "write_original",human_approved=True)
                sealed=self.store.worker_execute(pid,lease,"write_original",
                    output_name,data=data,media_type="video/x-msvideo")
                if sealed["sha256"]!=digest or sealed["size_bytes"]!=len(data):
                    raise ProtectedFilmReelError("Sealed private reel changed")
                self.store.worker_run_transition(pid,token,worker_id,
                    source_name,binding,"SUCCEEDED",
                    output_sha256=digest,exit_code=code)
                return {"format":FORMAT,"worker_id":worker_id,
                    "job_id":job,"index":index,"start_frame":start,
                    "end_frame":end,"output_name":output_name,
                    "sha256":digest,"size_bytes":len(data),
                    "source_sha256":binding,
                    "pcm_samples_per_channel":(end-start)*2000,
                    "os_process_tree_closed":True,
                    "independent_audio_picture_verified":True,
                    "encrypted_output":True}
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    proc.wait(timeout=12)
                    proc.close()
                    custodied=True
                except Exception:
                    custodied=False
            status=("CANCELLED" if killed and custodied else
                    "FAILED" if custodied else "CUSTODY_UNPROVEN")
            try:
                self.store.worker_run_transition(pid,token,worker_id,
                    source_name,binding,status,exit_code=code)
            except Exception:pass
            raise
        finally:
            for stream in (source,out,err,sink,answer,log):
                try:stream.close()
                except Exception:pass
