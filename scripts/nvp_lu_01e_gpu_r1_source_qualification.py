#!/usr/bin/env python3
"""Strict exact-checkout Lu GPU lease/protoc qualification; no native signer.

Never claims successful Windows/installed acceptance. No network or synthetic
fallback for missing pinned Lu checkout.
"""
from __future__ import annotations
import argparse
from hashlib import sha1
from pathlib import Path
import shutil
import subprocess
import tempfile
from google.protobuf import descriptor_pb2

LU_SHA='60afe6908a6abe3408bb952869d85b43781313ca'
LU_BLOB='747b7472ab7e4bdfd7d646dd629b2c45a9c63dd1'
REL='src-tauri/lu-core/proto/lu/workspace/v0/workspace.proto'


def call(*args):
    return subprocess.check_output(list(args))


def run(lu_root:Path):
    git=shutil.which('git')
    protoc=shutil.which('protoc')
    if not git or not protoc or not (lu_root/'.git').exists():
        raise RuntimeError('NATIVE_BLOCKED: pinned genuine Lu Git checkout + protoc required')
    sha=call(git,'-C',str(lu_root),'rev-parse','HEAD').decode().strip()
    blob=call(git,'-C',str(lu_root),'rev-parse','HEAD:'+REL).decode().strip()
    if sha!=LU_SHA or blob!=LU_BLOB:
        raise RuntimeError('SOURCE_DENIED: Lu GPU lease source commit/blob changed')
    raw=call(git,'-C',str(lu_root),'show','HEAD:'+REL)
    actual=(lu_root/REL).read_bytes()
    if b'\r' in actual.replace(b'\r\n',b'') or actual.replace(b'\r\n',b'\n')!=raw:
        raise RuntimeError('SOURCE_DENIED: Lu GPU source worktree differs from immutable Git blob')
    if sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=LU_BLOB:
        raise RuntimeError('SOURCE_DENIED: Lu source Git object hash mismatch')
    with tempfile.TemporaryDirectory() as tmp:
        dest=Path(tmp)/'lu_gpu.desc'
        subprocess.run([protoc,'-I',str(lu_root/'src-tauri/lu-core/proto'),
            '--include_imports','--descriptor_set_out='+str(dest),
            'lu/workspace/v0/workspace.proto'],check=True)
        ds=descriptor_pb2.FileDescriptorSet();ds.ParseFromString(dest.read_bytes())
        proto=[f for f in ds.file if f.package=='lu.workspace.v0']
        if len(proto)!=1:raise RuntimeError('SOURCE_DENIED: noncanonical Lu workspace package')
        frame=next((m for m in proto[0].message_type if m.name=='WorkspaceFrame'),None)
        if frame is None:raise RuntimeError('SOURCE_DENIED: missing Lu WorkspaceFrame')
        by_name={f.name:f.number for f in frame.field}
        if {k:by_name.get(k) for k in ('gpu_lease_request','gpu_lease_outcome',
                'gpu_lease_release','gpu_lease_poll')} != {
            'gpu_lease_request':38,'gpu_lease_outcome':39,'gpu_lease_release':40,
            'gpu_lease_poll':41}:
            raise RuntimeError('SOURCE_DENIED: Lu GPU oneof tags changed')
        methods={(s.name,m.name) for s in proto[0].service for m in s.method}
        if not {('LuCoreGateway','RequestGpuLease'),
                ('LuCoreGateway','ReleaseGpuLease'),
                ('LuCoreGateway','PollGpuLease')}.issubset(methods):
            raise RuntimeError('SOURCE_DENIED: Lu Core GPU lease gateway routes absent')
    print('NVP_LU_GPU_01E_R1_GENUINE_PROTOC_PASS Lu='+sha+' GitBlob='+blob)
    print('INSTALLED_LU_SCM_GPU_NOT_PROVEN')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--lu-root',type=Path,required=True)
    args=parser.parse_args()
    try:run(args.lu_root)
    except (RuntimeError,subprocess.CalledProcessError) as exc:
        parser.exit(1,str(exc)+'\n')
