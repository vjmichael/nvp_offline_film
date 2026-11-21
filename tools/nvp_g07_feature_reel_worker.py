"""Fixed in-memory reel worker protocol. No arbitrary path, command or project key.
The host must supply native OS isolation; this protocol alone is not custody.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import struct
from backend.nvp_g09e_chunk import check_assembly, render_reel, MAX_CHUNK_BYTES
from tools.nvp_g03_protected_scene_worker import _binary_stdio, read_exact

MAGIC_IN=b'NVPREELIN1'
MAGIC_OUT=b'NVPREELOUT1'
MAX_INPUT=64*1024*1024
MAX_SOURCE=32*1024*1024
FORMAT='nvp.g07.feature_worker.v1'


def _encode(value):
    if type(value) is bytes:
        return {'__nvp_bytes__':base64.b64encode(value).decode('ascii')}
    raise TypeError('Unsupported native source value')


def _object(pairs):
    obj={}
    for k,v in pairs:
        if k in obj:raise ValueError('Duplicate source field')
        obj[k]=v
    if '__nvp_bytes__' in obj:
        if set(obj)!={'__nvp_bytes__'} or type(obj['__nvp_bytes__']) is not str:
            raise ValueError('Invalid native binary source')
        return base64.b64decode(obj['__nvp_bytes__'],validate=True)
    return obj


def _canonical(value):
    return json.dumps(value,default=_encode,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def request(assembly,start,end,plan):
    if not 0<assembly['source_payload_budget_bytes']<=MAX_SOURCE:
        raise ValueError('Choose a smaller sealed native rendering source')
    raw=_canonical({'format':FORMAT,'assembly':assembly,'start':start,'end':end,'plan':plan})
    if not 0<len(raw)<=MAX_INPUT:raise ValueError('Native source exceeds bounded pipe budget')
    return raw


def process(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_INPUT:raise ValueError('Bounded native source required')
    doc=json.loads(raw,object_pairs_hook=_object)
    if type(doc) is not dict or set(doc)!={'format','assembly','start','end','plan'} or doc['format']!=FORMAT or _canonical(doc)!=raw:
        raise ValueError('Invalid native reel request')
    a=doc['assembly'];start=doc['start'];end=doc['end'];plan=doc['plan']
    from backend.nvp_g08_native_avi import TICKS_FRAME
    from backend.nvp_g09e_chunk import source_digests
    check_assembly(a,a['duration_tick']//TICKS_FRAME,start,end,source_digests(a))
    if a['acoustic_looks']:raise ValueError('Continuous acoustics not supported')
    size=0
    for take in a['original_takes'].values():
        for name,digest in [('original_usd','original_sha256'),('performance_usd','performance_sha256')]:
            b=take[name];size+=len(b)
            if type(b) is not bytes or hashlib.sha256(b).hexdigest()!=take[digest]:raise ValueError('Frozen source changed')
        for clip in take['audio']:
            b=clip['pcm16le'];size+=len(b)
            if type(b) is not bytes or hashlib.sha256(b).hexdigest()!=clip['pcm_sha256'] or len(b)!=clip['sample_count']*2:raise ValueError('Original recording changed')
    if size!=a['source_payload_budget_bytes'] or not 0<size<=MAX_SOURCE:raise ValueError('Source budget changed')
    sink=io.BytesIO();render_reel(a,start,end,plan,sink);out=sink.getvalue()
    if not 0<len(out)<=MAX_CHUNK_BYTES:raise ValueError('Native reel exceeds output limit')
    return out


def installed_worker_entry():
    """Frozen role may run only with the actual lowbox token and Job."""
    import sys
    if sys.platform!='win32' or not getattr(sys,'frozen',False):return 3
    try:
        import ctypes as C
        from ctypes import wintypes as W
        kernel=C.WinDLL('kernel32',use_last_error=True);advapi=C.WinDLL('advapi32',use_last_error=True)
        kernel.GetCurrentProcess.restype=W.HANDLE
        kernel.CloseHandle.argtypes=[W.HANDLE]
        kernel.IsProcessInJob.argtypes=[W.HANDLE,W.HANDLE,C.POINTER(W.BOOL)]
        advapi.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)]
        advapi.GetTokenInformation.argtypes=[W.HANDLE,C.c_int,W.LPVOID,W.DWORD,C.POINTER(W.DWORD)]
        token=W.HANDLE();inside=W.BOOL();app=W.DWORD();size=W.DWORD()
        process=kernel.GetCurrentProcess()
        if not kernel.IsProcessInJob(process,None,C.byref(inside)) or not inside.value:return 3
        if not advapi.OpenProcessToken(process,0x0008,C.byref(token)):return 3
        try:
            # TOKEN_INFORMATION_CLASS TokenIsAppContainer = 29.
            if not advapi.GetTokenInformation(token,29,C.byref(app),C.sizeof(app),C.byref(size)) or app.value!=1:return 3
        finally:kernel.CloseHandle(token)
    except Exception:return 3
    return worker_entry()


def worker_entry():
    try:
        inp,out,err=_binary_stdio()
        header=read_exact(inp,len(MAGIC_IN)+8)
        if header[:len(MAGIC_IN)]!=MAGIC_IN:raise ValueError('Invalid native reel magic')
        n=struct.unpack('!Q',header[len(MAGIC_IN):])[0]
        if not 0<n<=MAX_INPUT:raise ValueError('Invalid native reel length')
        raw=read_exact(inp,n)
        if inp.read(1):raise ValueError('Unexpected trailing data')
        result=process(raw)
        for data in (MAGIC_OUT+hashlib.sha256(raw).digest()+struct.pack('!Q',len(result)),result):
            view=memoryview(data)
            while view:
                written=out.write(view[:65536])
                if not written:raise OSError('Short native output pipe write')
                view=view[written:]
        out.flush();return 0
    except Exception:
        # Never emit project payloads or exception paths.
        return 3


if __name__=='__main__':raise SystemExit(worker_entry())
