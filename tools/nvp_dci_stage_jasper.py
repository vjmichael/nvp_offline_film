"""Build-only exact-pinned JasPer raw-component adapter preparation.

Qualification-only; this neither admits a release binary nor runs any decoder.
"""
import argparse
from hashlib import sha1,sha256
import json
from pathlib import Path
import subprocess
PIN='63e106c80eb72af9fd4fa28772499ab0138b9994'
LICENSE_BLOB='ce90e4b484d588e0fc67d3e433b2517a915d924d'
CMAKE_BLOB='f6bc660d6e158e943c2d64fb484eda339734c3b5'
SUFFIX=b'\n# NVP DCI-P4B-R1 independent raw cinema component qualification adapter.\nadd_executable(nvp_jasper_decode nvp_jasper_decode.c)\ntarget_include_directories(nvp_jasper_decode BEFORE PRIVATE "${CMAKE_BINARY_DIR}/src/libjasper/include" "${CMAKE_SOURCE_DIR}/src/libjasper/include")\ntarget_link_libraries(nvp_jasper_decode PRIVATE libjasper)\n'

def blob(raw):return sha1(b'blob '+str(len(raw)).encode()+b'\x00'+raw).hexdigest()

def stage(root,adapter):
    root=Path(root).resolve(strict=True);adapter=Path(adapter).resolve(strict=True)
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args])
    if git('rev-parse','HEAD').strip().decode()!=PIN or git('status','--porcelain','--untracked-files=no'):
        raise RuntimeError('Exact pristine JasPer checkout required')
    for name,expected in [('LICENSE.txt',LICENSE_BLOB),('CMakeLists.txt',CMAKE_BLOB)]:
        if blob(git('show',f'{PIN}:{name}'))!=expected:
            raise RuntimeError('JasPer reviewed Git blob mismatch')
        if (root/name).read_bytes().replace(b'\r\n',b'\n')!=git('show',f'{PIN}:{name}'):
            raise RuntimeError('JasPer working bytes differ')
    raw=adapter.read_bytes()
    dest=root/'nvp_jasper_decode.c'
    with dest.open('xb') as out:out.write(raw)
    cmake=git('show',f'{PIN}:CMakeLists.txt')+SUFFIX
    (root/'CMakeLists.txt').write_bytes(cmake)
    return {'jasper_commit':PIN,'license_blob':LICENSE_BLOB,'adapter_sha256':sha256(raw).hexdigest(),'cmake_blob':blob(cmake),'qualification_only':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('adapter');a=p.parse_args()
    print(json.dumps(stage(a.root,a.adapter),sort_keys=True),flush=True)
