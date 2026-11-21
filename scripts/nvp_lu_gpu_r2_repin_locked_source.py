#!/usr/bin/env python3
"""R2 exact-source Lu gpu-lease-v1/poll schema re-pin of six NVP files.

This edits only a verified existing NVP checkout after the approved predecessor
candidate is applied. It cannot enroll, grant VRAM, mutate Lu or publish Git.
"""
from __future__ import annotations
import argparse
from hashlib import sha1
import os
from pathlib import Path
import subprocess

OLD_COMMIT = '9f43d078aa5e979de0ff72ca4c19e8c5829572af'
OLD_PROTO = '4e01d921197fb1c58c99958479b1cede36e13c9a'
NEW_COMMIT = '60afe6908a6abe3408bb952869d85b43781313ca'
NEW_PROTO = '747b7472ab7e4bdfd7d646dd629b2c45a9c63dd1'
# Existing Git blobs taken from the published, exact candidate predecessor.
# New blobs independently computed by unreferenced GitHub Git-object writes.
PINS = {
    'native/nvp_lu_ipc_client/build.rs':
        ('1525380406ab0c084cee969f23e7b5c52fe1c5a4', 'd2b9c0eaf2c4edcd5449a001516bc25947e7e905'),
    'scripts/nvp_lu_native_exact_source.sh':
        ('94558c8a161a2d4471b8bdefe3a76d37bfd45cf9', '8766caf8a4da234945bf5f3690777b5259a0423b'),
    'scripts/nvp_lu_native_exact_source.ps1':
        ('acb346f0130aa2d7d745ba75a671d9f72a3fa561', 'b4c890770f6d237c28ce526552a55396bd8d53cc'),
    'scripts/nvp_lu_01f_r2r2_qualification.py':
        ('8a49aaa6ed9b46d291a02ae897a67853b488687f', '752438d07dcd17a8192fd2c0d8c7f7b6a69e130f'),
    '.github/workflows/nvp-int-lu-01f-r2r2r1-native.yml':
        ('3550d810dd676298991d1292438f8e133c48d77c', '673b03692b291522e13fe269c1492f1bb2779a37'),
    '.github/workflows/nvp-int-lu-01a-r3r2-native.yml':
        ('8a4931d7fc873c52c89e32f8353107db597ea6ef', '388661f7ebf9a07726ba6bf7d5ce3d21ce817815'),
}

def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(['git','-C',str(root),*args])

def git_hash(raw: bytes) -> str:
    return sha1(b'blob '+str(len(raw)).encode('ascii')+b'\0'+raw).hexdigest()

def upgrade(root: Path, *, check: bool = False) -> None:
    if not (root/'.git').exists():
        raise PermissionError('Existing genuine NVP Git checkout required')
    new = {}
    for path,(expected_old,expected_new) in PINS.items():
        current = git(root, 'rev-parse', 'HEAD:'+path).decode('ascii').strip()
        if current != expected_old:
            raise PermissionError('NVP pinned-source drift at '+path)
        committed = git(root, 'show', 'HEAD:'+path)
        on_disk = (root/path).read_bytes()
        if on_disk.replace(b'\r\n',b'\n') != committed:
            raise PermissionError('NVP worktree differs from original Git blob at '+path)
        if git_hash(committed)!=expected_old or b'\r' in committed:
            raise PermissionError('Noncanonical original source at '+path)
        count = sum(committed.count(x.encode()) for x in (OLD_COMMIT,OLD_PROTO))
        if not count:
            raise PermissionError('Old reviewed Lu source pin missing at '+path)
        updated = committed.replace(OLD_COMMIT.encode(),NEW_COMMIT.encode())
        updated = updated.replace(OLD_PROTO.encode(),NEW_PROTO.encode())
        if git_hash(updated) != expected_new:
            raise PermissionError('Reviewed successor source hash mismatch at '+path)
        new[path]=updated
    if check:
        print('NVP_LU_GPU_R2_SIX_SOURCE_PINS_READY Lu='+NEW_COMMIT+' Proto='+NEW_PROTO)
        return
    # Preflight validates every file before any write. No Git add/commit/push.
    for path,bytes_ in new.items():
        dest=root/path
        tmp=dest.with_name(dest.name+'.gpu-r2-repin-pending')
        if tmp.exists():raise PermissionError('Unreconciled source repair at '+path)
        with tmp.open('xb') as f:
            f.write(bytes_);f.flush();os.fsync(f.fileno())
        os.replace(tmp,dest)
    print('NVP_LU_GPU_R2_SOURCE_PINS_REVIEWED_NOT_COMMITTED Lu='+NEW_COMMIT+' Proto='+NEW_PROTO)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--nvp-root',type=Path,required=True)
    p.add_argument('--check',action='store_true')
    args=p.parse_args()
    upgrade(args.nvp_root,check=args.check)
