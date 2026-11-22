"""G03-F1 trusted native OpenUSD scene-coverage worker.

Runs only as a reviewed child of the NVP host inside a Windows Job Object.
The host transfers approved USD bytes over stdin and receives a derived USD
layer over stdout. No source, output, key, journal or model instruction is
written to a working plaintext file by this worker.

It does not run arbitrary Blender scripts or claim full film rendering.
"""
from __future__ import annotations
import io
import os
import re
import struct
import sys

MAX_SOURCE=4*1024*1024
MAX_OUTPUT=8*1024*1024
MAGIC_IN=b"NVPUSDIN1"
MAGIC_OUT=b"NVPUSDOUT1"


def _binary_stdio():
    """Recover the real inherited OS pipes in a --windowed PyInstaller EXE.

    Windows PyInstaller deliberately replaces sys.stdin/sys.stdout with None.
    The host has already created suspended child std handles inside its native
    Job Object; use those verified Win32 handles, not a plaintext file.
    """
    if sys.stdin is not None and sys.stdout is not None:
        return sys.stdin.buffer,sys.stdout.buffer,(
            sys.stderr.buffer if sys.stderr is not None else None)
    if sys.platform != "win32":
        raise RuntimeError("Binary worker pipe unavailable")
    import ctypes
    import msvcrt
    kernel=ctypes.windll.kernel32
    kernel.GetStdHandle.restype=ctypes.c_void_p
    kernel.GetStdHandle.argtypes=[ctypes.c_ulong]
    def fd(standard,mode,flags):
        handle=kernel.GetStdHandle(standard)
        if not handle or handle==ctypes.c_void_p(-1).value:
            raise RuntimeError("Native Windows Job standard pipe missing")
        return os.fdopen(msvcrt.open_osfhandle(handle,flags|os.O_BINARY),
                         mode,buffering=0)
    return (fd(-10,"rb",os.O_RDONLY),fd(-11,"wb",os.O_WRONLY),
            fd(-12,"wb",os.O_WRONLY))


def read_exact(file, n):
    chunks=[]
    while n:
        piece=file.read(n)
        if not piece:
            raise ValueError("Incomplete worker input")
        chunks.append(piece)
        n-=len(piece)
    return b"".join(chunks)


def process(source):
    if not isinstance(source,bytes) or not 1<=len(source)<=MAX_SOURCE:
        raise ValueError("Native source exceeds limit")
    from pxr import Sdf, Usd, UsdGeom, Gf
    text=source.decode("utf-8","strict")
    if not text.lstrip().startswith("#usda 1.0"):
        raise ValueError("Native source is not USDA")
    # Disallow external asset resolution in a process with filesystem access:
    # no references, payloads, clips, sublayers, or external @ paths. A later
    # worker will use a host-owned asset resolver with explicit grants.
    if ("@" in text or re.search(
            r"\b(?:references|payload|subLayers|clips|assetInfo)\b",text)):
        raise ValueError("External USD asset references require protected resolver")
    layer=Sdf.Layer.CreateAnonymous("protected_original.usda")
    if not layer.ImportFromString(text):
        raise ValueError("USDA parse failed")
    stage=Usd.Stage.Open(layer)
    if stage is None:
        raise ValueError("OpenUSD could not open supplied stage")
    if stage.GetPrimAtPath("/NVP_Coverage"):
        raise ValueError("Original already defines reserved camera namespace")
    root=stage.DefinePrim("/NVP_Coverage","Xform")
    if not root:
        raise ValueError("Unable to define protected camera group")
    for name,position,focal in (
        ("Wide",(0.0,3.0,12.0),28.0),
        ("Medium",(0.0,2.0,6.0),50.0),
        ("CloseUp",(0.0,1.8,3.5),85.0),
    ):
        camera=UsdGeom.Camera.Define(stage,"/NVP_Coverage/"+name)
        camera.CreateFocalLengthAttr(focal)
        camera.AddTranslateOp().Set(Gf.Vec3d(*position))
    result=layer.ExportToString().encode("utf-8")
    if not 1<=len(result)<=MAX_OUTPUT:
        raise ValueError("Derived original exceeded worker output limit")
    # Independently reparse exact output to avoid claiming invalid OpenUSD.
    check=Sdf.Layer.CreateAnonymous("verified_derivative.usda")
    if not check.ImportFromString(result.decode("utf8")):
        raise ValueError("Derived OpenUSD failed independent native parse")
    return result


def run():
    inp,out,err=_binary_stdio()
    header=read_exact(inp,len(MAGIC_IN)+8)
    if header[:len(MAGIC_IN)]!=MAGIC_IN:
        raise ValueError("Unrecognized host worker protocol")
    count=struct.unpack("!Q",header[len(MAGIC_IN):])[0]
    if not 0<count<=MAX_SOURCE:
        raise ValueError("Bounded source required")
    raw=read_exact(inp,count)
    if inp.read(1):
        raise ValueError("Trailing worker input rejected")
    rendered=process(raw)
    out.write(MAGIC_OUT+struct.pack("!Q",len(rendered))+rendered)
    out.flush()
    return 0


def worker_entry():
    try:
        return run()
    except Exception:
        # Don't echo source text, paths, Python traceback or project data.
        try:
            _in,_out,err=_binary_stdio()
            if err is not None:
                err.write(b"NVP_PROTECTED_SCENE_WORKER_REFUSED\n")
                err.flush()
        except Exception:
            pass
        return 3


if __name__=="__main__":
    raise SystemExit(worker_entry())
