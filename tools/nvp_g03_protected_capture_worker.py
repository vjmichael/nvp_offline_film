"""G03-F2 original PCM capture inside a supervised native Windows child.

No filesystem path, FFmpeg, WAV export, model text, or project key can enter
this process. OS microphone permission and one-use director approval are
verified by the host *before* launch. The child uses PortAudio in direct
memory, sends only bounded original PCM16LE over an inherited binary pipe,
and never declares a frozen Digital Take.

Actual hardware capture requires native owner-operated acceptance; it cannot
be replaced by simulated CI samples or an available microphone name.
"""
from __future__ import annotations
import json
import os
import struct
import sys


def _binary_stdio():
    if sys.stdin is not None and sys.stdout is not None:
        return sys.stdin.buffer,sys.stdout.buffer,(
            sys.stderr.buffer if sys.stderr is not None else None)
    if sys.platform!="win32":
        raise RuntimeError("Native binary capture pipes unavailable")
    import ctypes
    import msvcrt
    kernel=ctypes.windll.kernel32
    kernel.GetStdHandle.restype=ctypes.c_void_p
    kernel.GetStdHandle.argtypes=[ctypes.c_ulong]
    def inherited(handle_number,mode,flags):
        handle=kernel.GetStdHandle(handle_number)
        if not handle or handle==ctypes.c_void_p(-1).value:
            raise RuntimeError("Native capture pipe missing")
        return os.fdopen(msvcrt.open_osfhandle(handle,flags|os.O_BINARY),
                         mode,buffering=0)
    return (inherited(-10,"rb",os.O_RDONLY),
            inherited(-11,"wb",os.O_WRONLY),
            inherited(-12,"wb",os.O_WRONLY))


def read_exact(stream,length):
    result=bytearray()
    while length:
        data=stream.read(length)
        if not data:
            raise ValueError("Incomplete native capture input")
        result.extend(data)
        length-=len(data)
    return bytes(result)

CAP_IN=b"NVPCAPIN1"
CAP_OUT=b"NVPCAPOUT1"
MAX_REQUEST=1024
SAMPLE_RATE=48000
MAX_SECONDS=6
MAX_PCM_BYTES=SAMPLE_RATE*MAX_SECONDS*2*2


def _validate(doc):
    if type(doc) is not dict or set(doc)!={"device_id","channels","frames"}:
        raise ValueError("Exact native capture request fields required")
    if (type(doc["device_id"]) is not int or
        not -1<=doc["device_id"]<=65535):
        raise ValueError("Invalid native device identity")
    if type(doc["channels"]) is not int or doc["channels"] not in (1,2):
        raise ValueError("Only one/two physical input channels accepted")
    if (type(doc["frames"]) is not int or
        not 1<=doc["frames"]<=MAX_SECONDS*SAMPLE_RATE):
        raise ValueError("Invalid bounded original capture frame count")
    return doc


def _record(doc):
    """Only a REAL PortAudio input stream; never synthesize source samples."""
    import sounddevice as sd
    device=None if doc["device_id"]==-1 else doc["device_id"]
    device_info=sd.query_devices(device,kind="input")
    if int(device_info["max_input_channels"])<doc["channels"]:
        raise RuntimeError("Native physical microphone channels unavailable")
    sd.check_input_settings(
        device=device,channels=doc["channels"],
        dtype="int16",samplerate=SAMPLE_RATE)
    remaining=doc["frames"]
    raw=bytearray()
    with sd.InputStream(device=device,channels=doc["channels"],
                        samplerate=SAMPLE_RATE,dtype="int16",
                        blocksize=1024,latency="low") as stream:
        while remaining:
            count=min(remaining,1024)
            samples,overflow=stream.read(count)
            if overflow:
                raise RuntimeError("Original capture overflow: refuse freeze")
            raw.extend(samples.tobytes(order="C"))
            if len(raw)>MAX_PCM_BYTES:
                raise RuntimeError("Source buffer exceeded capture bound")
            remaining-=count
    expected=doc["frames"]*doc["channels"]*2
    if len(raw)!=expected:
        raise RuntimeError("Native PCM original is incomplete")
    return bytes(raw)


def run():
    inp,out,err=_binary_stdio()
    packet=read_exact(inp,len(CAP_IN)+4)
    if packet[:len(CAP_IN)]!=CAP_IN:
        raise ValueError("Invalid native capture pipe protocol")
    size=struct.unpack("!I",packet[len(CAP_IN):])[0]
    if size<2 or size>MAX_REQUEST:
        raise ValueError("Bounded native capture request required")
    request=json.loads(read_exact(inp,size).decode("utf8"))
    if inp.read(1):
        raise ValueError("Trailing capture command refused")
    doc=_validate(request)
    pcm=_record(doc)
    out.write(CAP_OUT+struct.pack("!Q",len(pcm))+pcm)
    out.flush()
    return 0


def worker_entry():
    try:
        return run()
    except Exception:
        # No exception text can disclose a device name or audio content.
        try:
            _,_,stderr=_binary_stdio()
            if stderr is not None:
                stderr.write(b"NVP_PROTECTED_PCM_CAPTURE_FAILED\n")
                stderr.flush()
        except Exception:
            pass
        return 3


if __name__=="__main__":
    raise SystemExit(worker_entry())
