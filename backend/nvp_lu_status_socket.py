"""NVP B5 status-only AF_UNIX client; future Lu host must opt in.

The accepted Lu alpha does not ship this endpoint. No model-control APIs.
"""
from __future__ import annotations

from pathlib import Path
import socket
import struct

from backend.nvp_lu_status_wire import LIMIT,StatusGrant,request,verify_reply
from backend.nvp_lu_alpha_contract import PassiveLuStatusObserver


def exact(stream,count):
    chunks=[]
    while count:
        piece=stream.recv(count)
        if not piece:
            raise ConnectionError("Short Lu IPC frame")
        chunks.append(piece)
        count-=len(piece)
    return b"".join(chunks)


def send_frame(stream,payload):
    if not isinstance(payload,bytes) or not 0<len(payload)<=LIMIT:
        raise ValueError("Lu IPC frame size invalid")
    stream.sendall(struct.pack("!I",len(payload))+payload)


def read_frame(stream):
    count=struct.unpack("!I",exact(stream,4))[0]
    if not 0<count<=LIMIT:
        raise ValueError("Lu status reply too large")
    return exact(stream,count)


class LuStatusClient:
    def __init__(self,endpoint,grant):
        path=Path(endpoint)
        if (not path.is_absolute() or len(str(path))>=100 or
            not path.parent.is_dir() or path.parent.is_symlink()):
            raise ValueError("Lu host endpoint must have physical local parent")
        if not isinstance(grant,StatusGrant):
            raise TypeError("A host-issued status scope is required")
        self.path=path
        self.grant=grant

    def fetch_status(self):
        if not hasattr(socket,"AF_UNIX"):
            raise RuntimeError("Native local socket unsupported")
        if self.path.is_symlink():
            raise PermissionError("Lu host socket is symlink")
        pending=request(self.grant)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as stream:
            stream.settimeout(4)
            stream.connect(str(self.path))
            send_frame(stream,pending)
            reply=read_frame(stream)
        return verify_reply(self.grant,pending,reply)

    def make_passive_observer(self,ledger):
        return PassiveLuStatusObserver(ledger,read_status=self.fetch_status)
