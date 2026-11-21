#!/usr/bin/env python3
"""Source-locked NVP LuWorkspaceProvider qualification (no installer grant).

Default: independent NVP Protobuf descriptor + portable Python regressions.
--native: *also* run actual Rust/prost with reviewed Cargo.lock and exact Lu
checkout. No fake toolchain, no silent skip, no CI-bypass status. Running this
script cannot prove an installed signed Windows Core/NVP exchange.
"""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from google.protobuf import descriptor_pb2

LU_SHA='60afe6908a6abe3408bb952869d85b43781313ca'
LU_PROTO_BLOB='747b7472ab7e4bdfd7d646dd629b2c45a9c63dd1'
NVP_PROTO_BLOB='5734d04bb08795240cde1508053cd9449847d3eb'
LU_PROTO_PATH='src-tauri/lu-core/proto/lu/workspace/v0/workspace.proto'
NVP_PROTO_PATH='contracts/nvp/film/v1/nvp_film_v1.proto'


def _blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode('ascii')+b'\0'+data).hexdigest()


def require_exact_domain_source(root: Path) -> None:
    """Verify the pinned Git blob and byte-equivalent LF/CRLF worktree.

    Git on Windows may check out text with CRLF, while the reviewed immutable
    Git blob is LF. A mismatched commit, modified text, lone-CR, alternate
    normalization or added unknown fields is NOT accepted. Never allow the
    current worktree to redefine the reviewed digest.
    """
    source = root / NVP_PROTO_PATH
    if not source.is_file():
        raise RuntimeError('NVP_SOURCE_DENIED: reviewed domain Protobuf is missing')
    data = source.read_bytes()
    if b'\r' in data.replace(b'\r\n', b''):
        raise RuntimeError('NVP_SOURCE_DENIED: noncanonical carriage return')
    canonical = data.replace(b'\r\n', b'\n')
    if _blob(canonical) != NVP_PROTO_BLOB:
        raise RuntimeError('NVP_SOURCE_DENIED: exact reviewed nvp_film_v1.proto blob mismatch')
    if (root / '.git').exists():
        require_command('git')
        source_blob = subprocess.check_output(
            ['git', '-C', str(root), 'rev-parse', 'HEAD:' + NVP_PROTO_PATH],
            text=True).strip()
        if source_blob != NVP_PROTO_BLOB:
            raise RuntimeError('NVP_SOURCE_DENIED: source Git object was repinned')
        original = subprocess.check_output(
            ['git', '-C', str(root), 'show', 'HEAD:' + NVP_PROTO_PATH])
        if original != canonical:
            raise RuntimeError('NVP_SOURCE_DENIED: worktree differs from immutable Git blob')


def require_command(name):
    result=shutil.which(name)
    if not result:raise RuntimeError('NATIVE_BLOCKED: '+name+' executable unavailable')
    return result


def run(args,*,cwd=None,env=None):
    subprocess.run(args,cwd=cwd,env=env,check=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--nvp-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--lu-root',type=Path)
    parser.add_argument('--native',action='store_true',help='MANDATORY real Rust/prost; refuse if absent')
    parser.add_argument('--protoc',default=None)
    args=parser.parse_args()
    root=args.nvp_root.resolve()
    require_exact_domain_source(root)
    protoc=args.protoc or shutil.which('protoc')
    if not protoc:
        raise RuntimeError('PROTOC_BLOCKED: native Protobuf compiler unavailable')
    with tempfile.TemporaryDirectory() as temp:
        result=Path(temp)/'film.desc'
        run([protoc,'-I',str(root/'contracts'),'--include_imports',
             '--descriptor_set_out='+str(result),'nvp/film/v1/nvp_film_v1.proto'])
        descriptor=descriptor_pb2.FileDescriptorSet()
        descriptor.ParseFromString(result.read_bytes())
        files=[f for f in descriptor.file if f.package=='nvp.film.v1']
        if (len(files)!=1 or len(files[0].message_type)!=16 or
                len(files[0].enum_type)!=1 or files[0].service):
            raise RuntimeError('NVP_PROTO_DENIED: reviewed descriptors changed')
    print('NVP_DOMAIN_EXACT_PROTO_PASS blob='+NVP_PROTO_BLOB)
    if args.native:
        if not args.lu_root or not (args.lu_root/'.git').exists():
            raise RuntimeError('NATIVE_BLOCKED: complete immutable Lu checkout required')
        lu=args.lu_root.resolve()
        got=subprocess.check_output([require_command('git'),'-C',str(lu),
                'rev-parse','HEAD'],text=True).strip()
        if got!=LU_SHA:
            raise RuntimeError('NATIVE_DENIED: Lu checkout commit mismatch')
        native_sha=subprocess.check_output(['git','-C',str(lu),'rev-parse',
                'HEAD:'+LU_PROTO_PATH],text=True).strip()
        if native_sha!=LU_PROTO_BLOB:
            raise RuntimeError('NATIVE_DENIED: Lu Protobuf committed Git blob mismatch')
        run(['git','-C',str(lu),'diff','--exit-code','--',LU_PROTO_PATH])
        require_command('cargo');require_command('rustc')
        crate=root/'native/nvp_lu_ipc_client'
        if not (crate/'Cargo.toml').is_file() or not (crate/'Cargo.lock').is_file():
            raise RuntimeError('NATIVE_BLOCKED: complete exact NVP crate/lock unavailable')
        env=dict(os.environ,LU_WORKSPACE_PROTO=str(lu/LU_PROTO_PATH))
        run(['cargo','test','--locked','--offline','--all-targets'],cwd=crate,env=env)
        print('NVP_LU_RUST_PROST_NATIVE_PASS pinned_lu='+LU_SHA)
    else:
        print('NVP_LU_RUST_PROST_NATIVE_NOT_RUN (source-only mode)')
    env=dict(os.environ, PYTHONPATH=str(root),PYTHONWARNINGS='error')
    run([sys.executable,'-m','unittest','discover','-s','tests',
         '-p','test_nvp_int_lu_01f_r*.py','-q'],cwd=root,env=env)
    print('NVP_LU_R2R2_FOCUSED_PASS; INSTALLED_WINDOWS_NOT_PROVEN')


if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.CalledProcessError) as exc:
        print(exc,file=sys.stderr)
        sys.exit(1)
