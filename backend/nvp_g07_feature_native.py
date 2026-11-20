"""Installed Windows private reel execution. No ordinary subprocess fallback.
The fixed worker receives only the bounded source through anonymous pipes.
The host must independently verify returned media before encrypted publication.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time

from backend.nvp_g03_protected_scene_supervisor import _sanitized_worker_env,_stream_read
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_g09e_chunk import MAX_CHUNK_BYTES
from tools.nvp_g07_feature_reel_worker import MAGIC_IN,MAGIC_OUT,request


def _write(stream,data,errors):
    try:
        view=memoryview(data)
        while view:
            count=stream.write(view[:65536])
            if not count:raise OSError('Short native pipe write')
            view=view[count:]
    except Exception:errors.append('Native input pipe failed')
    finally:stream.close()


def _sha(path):
    with path.open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()


def installed_identity():
    if sys.platform!='win32' or not getattr(sys,'frozen',False):
        raise PermissionError('Installed Windows private rendering runtime required')
    exe=Path(sys.executable).resolve(strict=True)
    return {'role':'protected_feature_reel','executable_sha256':_sha(exe),'os':'windows-appcontainer-job'}


class NativeReelInterrupted(InterruptedError):
    """Host-only stop result; active termination is attested after cleanup."""
    active_worker_stopped=False


def render(assembly,start,end,plan,identity,guard,*,timeout=180,started=None):
    if identity!=installed_identity() or type(timeout) is not int or not 10<=timeout<=600:
        raise PermissionError('Exact installed reel worker review required')
    if started is not None and not callable(started):raise TypeError('Trusted worker-start callback required')
    raw=request(assembly,start,end,plan);source_hash=hashlib.sha256(raw).digest()
    payload=MAGIC_IN+struct.pack('!Q',len(raw))+raw
    guard();proc=None;threads=[];streams=[];errors=[];output=bytearray();diagnostic=bytearray();interrupted=None;terminated=False
    from backend.nvp_worker_containment import launch_contained
    from backend.nvp_g03_windows_appcontainer import AppContainerJobProcess
    with tempfile.TemporaryDirectory(prefix='nvp-private-feature-') as cwd:
        try:
            for read,write in (os.pipe(),os.pipe(),os.pipe()):
                streams.extend([os.fdopen(read,'rb',buffering=0),os.fdopen(write,'wb',buffering=0)])
            command=[str(Path(sys.executable).resolve()),'--g07-protected-reel-worker']
            proc=launch_contained(command,cwd=cwd,stdin=streams[0],stdout=streams[3],stderr=streams[5],memory_mb=2048,env=_sanitized_worker_env(),windows_appcontainer_required=True,appcontainer_code_roots=[Path(command[0]).parent])
            if type(proc) is not AppContainerJobProcess:raise VaultError('Private native worker custody absent')
            for i in (0,3,5):streams[i].close()
            for fn,args in ((_write,(streams[1],payload,errors)),(_stream_read,(streams[2],MAX_CHUNK_BYTES+len(MAGIC_OUT)+40,output,errors)),(_stream_read,(streams[4],4096,diagnostic,errors))):
                th=threading.Thread(target=fn,args=args,daemon=True);th.start();threads.append(th)
            if started is not None:
                if proc.poll() is not None:raise VaultError('Native reel worker exited before active notification')
                started()
                guard()
            deadline=time.monotonic()+timeout
            while proc.poll() is None:
                guard()
                if errors or time.monotonic()>=deadline:raise VaultError('Private reel worker failed or timed out')
                time.sleep(.03)
            rc=proc.wait(timeout=12)
            # AppContainer.close synchronously checks native Job zero-process
            # accounting, profile inventory, ACL removal and profile cleanup.
            exited=proc;proc=None;exited.close()
            for th in threads:th.join(timeout=6)
            if rc!=0 or errors or any(th.is_alive() for th in threads) or diagnostic or list(Path(cwd).iterdir()):raise VaultError('Native reel worker result or cleanup unverified')
            guard()
            if identity!=installed_identity():raise VaultError('Installed worker changed')
            offset=len(MAGIC_OUT)
            if len(output)<offset+40 or output[:offset]!=MAGIC_OUT or output[offset:offset+32]!=source_hash:raise VaultError('Native reel response differs from original request')
            n=struct.unpack('!Q',output[offset+32:offset+40])[0];data=bytes(output[offset+40:])
            if not 0<n<=MAX_CHUNK_BYTES or n!=len(data):raise VaultError('Invalid native reel response size')
            return data,{'identity':identity,'request_sha256':source_hash.hex(),'media_sha256':hashlib.sha256(data).hexdigest(),'job_and_profile_cleanup_verified':True}
        except InterruptedError as exc:
            interrupted=NativeReelInterrupted("Working movie stopped")
            raise interrupted from exc
        finally:
            try:
                if proc is not None:
                    try:
                        if proc.poll() is None:
                            proc.terminate_tree();terminated=True
                        proc.wait(timeout=12)
                    finally:proc.close()
            finally:
                for th in threads:th.join(timeout=6)
                # Threads should have finished after real kernel teardown;
                # fail closed rather than publish a partial result.
                if any(th.is_alive() for th in threads):raise VaultError('Native reel pipe cleanup unverified')
                for stream in streams:stream.close()
            if interrupted is not None:interrupted.active_worker_stopped=terminated
