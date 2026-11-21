"""Developer/test compiler discovery only; never used for production IPC.

Native acceptance with NVP_REQUIRE_NATIVE_PROTOC=1 must fail, not silently
skip, if no actual executable compiler exists. Supports Windows and Debian.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import sys


def find_native_protoc() -> Path | None:
    env=os.environ.get('PROTOC')
    candidates=[env] if env else []
    candidates.append(shutil.which('protoc'))
    # The container has an actual compiler distributed with PyTorch, but do
    # not force an absolute interpreter-specific path onto Windows CI.
    candidates.append(str(Path(sys.prefix)/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'site-packages'/'torch'/'bin'/'protoc'))
    candidates.append('/opt/pyvenv/lib/python3.13/site-packages/torch/bin/protoc')
    for raw in candidates:
        if raw:
            p=Path(raw).expanduser()
            if p.is_file() and (os.name=='nt' or os.access(p,os.X_OK)):
                return p.resolve()
    return None


def require_test_protoc(test):
    protoc=find_native_protoc()
    if protoc is not None:
        return protoc
    if os.environ.get('NVP_REQUIRE_NATIVE_PROTOC')=='1':
        test.fail('Native Protobuf acceptance required but no executable protoc exists')
    test.skipTest('Native protoc unavailable; source-only test is NOT accepted')
