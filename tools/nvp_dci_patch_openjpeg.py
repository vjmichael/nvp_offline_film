"""Build-only patch for the exact reviewed upstream OpenJPEG 24 fps cinema CLI.

Do not modify an arbitrary checkout; do not change the native invocation grammar,
external DCI limits, non-cinema mode or 48fps. The emitted bytes are independently
validated by NVP, not assumed conforming from this internal encoder target.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

UPSTREAM = '6c4a29b00211eb0430fa0e5e890f1ce5c80f409f'
SOURCE = 'src/bin/jp2/opj_compress.c'
SOURCE_BLOB = '7de9786905a9d7f45cf187f1689cf1364bad0a21'
TARGET = 1_298_000
ANCHOR = b'        if (! opj_setup_encoder(l_codec, &parameters, image)) {\n'
GUARD = b'''        /* NVP DCI-P4B-R1: reserve header/rate-control overhead at 24 fps. */
        if ((parameters.rsiz == OPJ_PROFILE_CINEMA_2K &&
                parameters.max_cs_size == OPJ_CINEMA_24_CS) ||
                (parameters.rsiz == OPJ_PROFILE_CINEMA_4K &&
                 (parameters.max_cs_size <= 0 ||
                  parameters.max_cs_size == OPJ_CINEMA_24_CS))) {
            parameters.max_cs_size = 1298000;
        }
'''

def git_blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode('ascii')+b'\0'+raw).hexdigest()


def patch_bytes(original):
    if original.count(ANCHOR)!=1 or GUARD in original:
        raise ValueError('Pinned encoder setup anchor missing, ambiguous or already modified')
    return original.replace(ANCHOR, GUARD+ANCHOR, 1)


def apply(root):
    root = Path(root).resolve(strict=True)
    def git(*args):
        return subprocess.check_output(['git','-C',str(root),*args])
    if git('rev-parse','HEAD').strip().decode('ascii')!=UPSTREAM:
        raise RuntimeError('OpenJPEG source commit drift')
    # Tracked changes (including unexpected staged changes) are not acceptable.
    # Untracked build directory can exist; this patch never runs a build itself.
    if git('status','--porcelain','--untracked-files=no'):
        raise RuntimeError('OpenJPEG tracked source must be clean')
    original = git('show',f'{UPSTREAM}:{SOURCE}')
    if git_blob(original)!=SOURCE_BLOB:
        raise RuntimeError('OpenJPEG source blob drift')
    path = root/SOURCE
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('Expected regular upstream encoder source')
    # Windows autocrlf is allowed only if already normalized content is identical.
    if path.read_bytes().replace(b'\r\n',b'\n')!=original:
        raise RuntimeError('Working source differs from pinned blob')
    patched = patch_bytes(original)
    path.write_bytes(patched)
    if path.read_bytes()!=patched or git('diff','--name-only','HEAD').decode().splitlines()!=[SOURCE]:
        raise RuntimeError('Unexpected patched source identity')
    return {'source_commit':UPSTREAM,'original_blob':SOURCE_BLOB,
            'patched_blob':git_blob(patched),'patched_sha256':hashlib.sha256(patched).hexdigest(),
            'target_24fps_bytes':TARGET,'hard_ceiling_bytes':1302083,
            'profile_48fps_unchanged':True,'source_signature_verified':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path)
    print(json.dumps(apply(p.parse_args().source),sort_keys=True),flush=True)
