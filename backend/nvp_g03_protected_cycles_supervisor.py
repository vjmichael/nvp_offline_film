"""G03-F3: host-owned real Blender/Cycles scene preview -> sealed PNG.

This deliberately refuses private encrypted-movie execution until an
independently verified Windows filesystem and network sandbox is available.
Windows Job Object (existing native custody) is NOT an AppContainer and does
NOT stop Blender/plugins from reading other local user files or egressing.

A separately isolated, explicitly synthetic CI path executes the exact same
native Blender binary, real Cycles renderer and in-memory PNG pipeline, with
no user film/project/secret in its inputs. No plaintext source or render file
is written by the NVP host or trusted fixed worker code.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import struct
import sys
import tempfile
import threading
import time
import zlib

from backend.nvp_blender_worker import sha_file
from backend.nvp_g03_live_store import LiveFilmError
from backend.nvp_g03_protected_scene_supervisor import (
    _sanitized_worker_env,_stream_read,_stream_write
)
from backend.nvp_worker_containment import launch_contained
from tools.nvp_g03_cycles_inmemory_worker import MAGIC_IN,MAGIC_OUT,MAX_SPEC,MAX_PNG


class ProtectedCyclesError(LiveFilmError):
    pass


def _geometry_from_opensud(source):
    """Reject all external assets and unsupported USD prims, never skip them."""
    if type(source) is not bytes or not 1<=len(source)<=2*1024*1024:
        raise ProtectedCyclesError("Approved USDA source exceeds native render bound")
    content=source.decode("utf-8","strict")
    if not content.lstrip().startswith("#usda 1.0"):
        raise ProtectedCyclesError("A verified USDA original is required")
    if ("@" in content or re.search(
            r"\b(?:references|payload|subLayers|clips|assetInfo)\b",content)):
        raise ProtectedCyclesError("External USD assets require protected resolver")
    from pxr import Sdf,Usd,UsdGeom
    layer=Sdf.Layer.CreateAnonymous("nvp-protected-original.usda")
    if not layer.ImportFromString(content):
        raise ProtectedCyclesError("OpenUSD original failed native parsing")
    stage=Usd.Stage.Open(layer)
    if stage is None:
        raise ProtectedCyclesError("OpenUSD stage did not open")
    objects=[]
    for prim in stage.Traverse():
        typ=prim.GetTypeName()
        if typ in ("Xform","Scope","Camera"):
            continue
        if typ not in ("Cube","Sphere","Mesh"):
            raise ProtectedCyclesError(
                "Scene has a geometry kind that requires reviewed native resolver")
        xform=UsdGeom.Xformable(prim)
        mat=xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        # USD vector * row-major matrix -> Blender matrix * column vector.
        transform=[[float(mat[j][i]) for j in range(4)] for i in range(4)]
        if any(not math.isfinite(x) or abs(x)>100000
               for row in transform for x in row):
            raise ProtectedCyclesError("Invalid native transform")
        name=prim.GetName()
        if len(name)>90 or not name:
            raise ProtectedCyclesError("Invalid native prim name")
        verts=[];faces=[];size=1.0
        if typ=="Cube":
            size=float(UsdGeom.Cube(prim).GetSizeAttr().Get() or 2.0)
        elif typ=="Sphere":
            size=2.0*float(UsdGeom.Sphere(prim).GetRadiusAttr().Get() or 1.0)
        elif typ=="Mesh":
            mesh=UsdGeom.Mesh(prim)
            points=mesh.GetPointsAttr().Get()
            counts=mesh.GetFaceVertexCountsAttr().Get()
            indices=mesh.GetFaceVertexIndicesAttr().Get()
            if not(points and counts and indices):
                raise ProtectedCyclesError("Native USD Mesh has no approved topology")
            if len(points)>80000 or len(counts)>80000 or sum(counts)!=len(indices):
                raise ProtectedCyclesError("Native USD mesh too large or malformed")
            verts=[[float(v) for v in p] for p in points]
            cursor=0
            for count in counts:
                if not 3<=count<=256:
                    raise ProtectedCyclesError("Native polygon out of bounds")
                face=[int(i) for i in indices[cursor:cursor+count]]
                if any(i<0 or i>=len(verts) for i in face):
                    raise ProtectedCyclesError("Invalid original USD vertex index")
                faces.append(face);cursor+=count
        objects.append({"kind":typ,"name":name,"matrix":transform,
                        "vertices":verts,"faces":faces,"size":size})
    if not objects or len(objects)>128:
        raise ProtectedCyclesError("No bounded renderable source geometry")
    result={"format":"nvp.g03.cycles.source.v1",
            "width":128,"height":96,"samples":8,"objects":objects}
    payload=json.dumps(result,sort_keys=True,separators=(",",":"),
                       allow_nan=False).encode("utf8")
    if len(payload)>MAX_SPEC:
        raise ProtectedCyclesError("Approved Blender scene exceeds renderer budget")
    return payload


def _verify_png(raw,width=128,height=96):
    if (len(raw)<70 or len(raw)>MAX_PNG or
            raw[:8]!=b"\x89PNG\r\n\x1a\n"):
        raise ProtectedCyclesError("Native Cycles did not deliver an actual PNG")
    offset=8
    pixels=None
    while offset<len(raw):
        if offset+12>len(raw):
            raise ProtectedCyclesError("Incomplete native PNG chunk")
        n=struct.unpack("!I",raw[offset:offset+4])[0]
        kind=raw[offset+4:offset+8]
        if n>MAX_PNG or offset+12+n>len(raw):
            raise ProtectedCyclesError("Native PNG length overflow")
        data=raw[offset+8:offset+8+n]
        crc=struct.unpack("!I",raw[offset+8+n:offset+12+n])[0]
        if zlib.crc32(kind+data)&0xffffffff !=crc:
            raise ProtectedCyclesError("Native Cycles PNG CRC mismatch")
        if kind==b"IHDR":
            actual_width,actual_height=struct.unpack("!II",data[:8])
            if (actual_width,actual_height)!=(width,height):
                raise ProtectedCyclesError("Native renderer changed approved resolution")
        if kind==b"IDAT":
            pixels=(pixels or b"")+data
        if kind==b"IEND":
            if offset+12+n!=len(raw) or pixels is None:
                raise ProtectedCyclesError("Native PNG missing proper final chunk")
        offset+=12+n
    if pixels is None:
        raise ProtectedCyclesError("No pixel data from real Cycles")


class ProtectedCyclesSupervisor:
    def __init__(self,store,*,blender_executable,blender_sha256,
                 review_authority,os_isolation_attestor=None):
        if not callable(review_authority):
            raise TypeError("Host creator approval checker required")
        binary=Path(blender_executable).resolve(strict=True)
        if (not binary.is_file() or binary.is_symlink() or
                not isinstance(blender_sha256,str) or
                not re.fullmatch(r"[a-f0-9]{64}",blender_sha256)):
            raise ProtectedCyclesError("A separately SHA-pinned real Blender is required")
        self.store=store
        self.binary=binary
        self.expected_sha=blender_sha256
        self.review_authority=review_authority
        self.os_isolation_attestor=os_isolation_attestor

    def render(self,pid,token,source_name,output_name,approval_id,
               *,cancel=None,synthetic_ci_only=False):
        if sys.platform!="win32":
            raise ProtectedCyclesError("Protected Windows native Job and DPAPI required")
        isolated=(callable(self.os_isolation_attestor) and
                  self.os_isolation_attestor())
        if not isolated:
            if not (synthetic_ci_only and os.environ.get("GITHUB_ACTIONS")=="true"):
                raise ProtectedCyclesError(
                    "Private Blender/Cycles is blocked: independently verified "
                    "AppContainer filesystem/network confinement is unavailable")
        if type(approval_id) is not str or len(approval_id)<24:
            raise ProtectedCyclesError("Missing creator-reviewed rendering approval")
        if not self.review_authority(pid,source_name,output_name,approval_id):
            raise ProtectedCyclesError("Creator refused or replayed Blender operation")
        if cancel is not None and cancel.is_set():
            raise ProtectedCyclesError("Creator cancelled before Blender launch")
        if sha_file(self.binary)!=self.expected_sha:
            raise ProtectedCyclesError("Trusted Blender binary checksum changed")
        source_lease=self.store.worker_grant(
            pid,token,source_name,"read_original",human_approved=True)
        source=self.store.worker_execute(
            pid,source_lease,"read_original",source_name)
        canonical=_geometry_from_opensud(source)
        original_sha=hashlib.sha256(source).hexdigest()
        run_id=secrets.token_hex(16)
        self.store.worker_run_transition(
            pid,token,run_id,source_name,original_sha,"RUNNING")
        ins=os.pipe();outs=os.pipe();errs=os.pipe()
        streams=(os.fdopen(ins[0],"rb",buffering=0),
                 os.fdopen(ins[1],"wb",buffering=0),
                 os.fdopen(outs[0],"rb",buffering=0),
                 os.fdopen(outs[1],"wb",buffering=0),
                 os.fdopen(errs[0],"rb",buffering=0),
                 os.fdopen(errs[1],"wb",buffering=0))
        inp,send,recv,out,errin,errout=streams
        stdout=bytearray();stderr=bytearray();errors=[]
        proc=None
        complete=False;cancelled=False;exit_code=None
        threads=[]
        try:
            with tempfile.TemporaryDirectory(prefix="nvp-secure-cycles-") as cwd:
                trusted=Path(__file__).resolve().parents[1]/"tools"/"nvp_g03_cycles_inmemory_worker.py"
                if not trusted.is_file() or trusted.is_symlink():
                    raise ProtectedCyclesError("Reviewed Cycles script unavailable")
                args=[str(self.binary),"-b","--factory-startup",
                      "--disable-autoexec","-t","2","--python",str(trusted)]
                env=_sanitized_worker_env()
                env.update({"TMP":cwd,"TEMP":cwd,
                            "BLENDER_USER_CONFIG":str(Path(cwd)/"config"),
                            "BLENDER_USER_SCRIPTS":str(Path(cwd)/"scripts"),
                            "BLENDER_USER_DATAFILES":str(Path(cwd)/"datafiles")})
                proc=launch_contained(args,cwd=cwd,stdin=inp,stdout=out,
                    stderr=errout,memory_mb=4096,env=env,
                    windows_appcontainer_required=isolated)
                inp.close();out.close();errout.close()
                request=MAGIC_IN+struct.pack("!I",len(canonical))+canonical
                for fn,params in (
                    (_stream_write,(send,request,errors)),
                    (_stream_read,(recv,MAX_PNG+65536,stdout,errors)),
                    (_stream_read,(errin,16384,stderr,errors))):
                    thread=threading.Thread(target=fn,args=params,daemon=True)
                    thread.start();threads.append(thread)
                deadline=time.monotonic()+90
                while proc.poll() is None:
                    if cancel is not None and cancel.is_set():
                        cancelled=True;break
                    if errors or time.monotonic()>deadline:break
                    time.sleep(.03)
                if proc.poll() is None:
                    proc.terminate_tree()
                exit_code=proc.wait(timeout=12)
                for thread in threads:thread.join(timeout=6)
                if any(thread.is_alive() for thread in threads):
                    raise ProtectedCyclesError("Native Blender output pipe custody unproven")
                proc.close();proc=None
                complete=True
                if cancelled:
                    raise ProtectedCyclesError("Human cancelled contained Blender")
                if errors or exit_code!=0:
                    raise ProtectedCyclesError("Real Blender/Cycles reported a failure")
                if any(path.is_file() for path in Path(cwd).rglob("*")):
                    raise ProtectedCyclesError("Blender wrote a file; plaintext safety not proved")
                marker=stdout.rfind(MAGIC_OUT)
                if marker<0 or marker+len(MAGIC_OUT)+4>len(stdout):
                    raise ProtectedCyclesError("No native Blender in-memory PNG")
                expected=struct.unpack("!I",
                    stdout[marker+len(MAGIC_OUT):marker+len(MAGIC_OUT)+4])[0]
                png=bytes(stdout[marker+len(MAGIC_OUT)+4:])
                if expected!=len(png):
                    raise ProtectedCyclesError("Blender output length changed")
                _verify_png(png)
                if cancel is not None and cancel.is_set():
                    raise ProtectedCyclesError("Creator cancelled render before encryption")
                grant=self.store.worker_grant(
                    pid,token,output_name,"write_original",human_approved=True)
                sealed=self.store.worker_execute(
                    pid,grant,"write_original",output_name,data=png,
                    media_type="image/png")
                self.store.worker_run_transition(
                    pid,token,run_id,source_name,original_sha,"SUCCEEDED",
                    output_sha256=sealed["sha256"],exit_code=exit_code)
                return {"state":"SUCCEEDED","output_sha256":sealed["sha256"],
                        "blender_sha256":self.expected_sha,
                        "encrypted_png":True,"native_cycles":True,
                        "physical_owner_acceptance":False,
                        "real_scene_still_only":True}
        except Exception:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    proc.close();proc=None;complete=True
                except Exception:complete=False
            state=("CANCELLED" if cancelled and complete else
                   "FAILED" if complete else "CUSTODY_UNPROVEN")
            try:
                self.store.worker_run_transition(
                    pid,token,run_id,source_name,original_sha,state,
                    exit_code=exit_code)
            except Exception:
                pass
            raise
        finally:
            for stream in streams:
                try:stream.close()
                except OSError:pass
