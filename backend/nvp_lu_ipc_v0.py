"""NVP INT-LU-01A/B: guarded Lu workspace v0 client wire prototype.

Uses real google.protobuf encoding for the exact Lu v1.0 handshake/health
field numbers observed in pinned Lu source. Source-only; NOT a compiled Lu
client, verified installed Windows peer, production enrollment or grant. The
full Lu proto/prost and package-OS attestation must be installed and qualified
before enabling any protected capability or model inference.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct
import sys
import time
from typing import Callable
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

WIRE_MAJOR, WIRE_MINOR = 1, 0
MAX_FRAME_BYTES = 256 * 1024
MAX_TYPED_BYTES = 64 * 1024
MAX_OBJECT_REFS = 16
MAX_STREAM_CREDIT = 64
IO_DEADLINE_SECONDS = 3.0
# Provenance: vjmichael/Lu-AI-GUI draft PR #244 (not installed).
LU_IPC_SOURCE_SHA = "6932ace156ddaae728a2967660fc37aa986471ae"
LU_WORKSPACE_PROTO_BLOB_SHA = "4e01d921197fb1c58c99958479b1cede36e13c9a"
SAFE_REF = re.compile(r"[A-Za-z0-9_.:/-]{1,128}\Z")
PIPE_NAME = re.compile(r"\\\\\.\\pipe\\lu-ipc-[a-f0-9]{32}\Z")


def _lu_handshake_message_classes():
    """Compile only exact pinned Lu handshake/Health wire-number projections.

    There is no embedded Lu proto copy and no generated production stub here:
    this narrow descriptor projection is for local, source-only wire fixtures.
    Other Lu frame body variants are *intentionally rejected*.
    """
    file = descriptor_pb2.FileDescriptorProto(name="nvp/lu_workspace_v0_handshake_fixture.proto",
        package="lu.workspace.v0", syntax="proto3")
    all_types = {}
    def message(name, fields):
        msg = file.message_type.add();msg.name = name
        for field_name, number, kind, repeated in fields:
            f = msg.field.add(); f.name = field_name; f.number = number
            f.label = 3 if repeated else 1
            if kind == "string": f.type = 9
            elif kind == "bytes": f.type = 12
            elif kind == "uint32": f.type = 13
            elif kind == "uint64": f.type = 4
            elif kind == "int32": f.type = 5
            elif kind == "bool": f.type = 8
            else: raise ValueError("Unknown Lu field type")
        all_types[name] = msg
    message("Hello", [("claimed_module_id",1,"string",False),
        ("claimed_role",2,"int32",False),
        ("claimed_package_sha256",3,"bytes",False),
        ("minimum_major",4,"uint32",False),
        ("maximum_major",5,"uint32",False),
        ("maximum_minor",6,"uint32",False),
        ("requested_features",7,"string",True),
        ("client_nonce",8,"bytes",False)])
    message("AuthChallenge",[("server_nonce",1,"bytes",False)])
    message("AuthProof",[("client_hmac_sha256",1,"bytes",False)])
    message("Welcome",[("selected_major",1,"uint32",False),
        ("selected_minor",2,"uint32",False),
        ("core_epoch_ref",3,"string",False),
        ("enabled_features",4,"string",True),
        ("server_hmac_sha256",5,"bytes",False)])
    message("HealthRequest",[])
    message("HealthReport",[("module_id",1,"string",False),
        ("connected",2,"bool",False), ("status_code",3,"string",False),
        ("epoch",4,"uint64",False)])
    msg = file.message_type.add();msg.name="WorkspaceFrame"
    msg.oneof_decl.add().name="body"
    for name,number,kind in [("protocol_major",1,"uint32"),
            ("protocol_minor",2,"uint32"),("request_id",3,"string"),
            ("session_ref",4,"string"),("sequence",5,"uint64")]:
        f=msg.field.add();f.name=name;f.number=number;f.label=1
        f.type={"uint32":13,"uint64":4,"string":9}[kind]
    for field_name,number,type_name in [("hello",10,"Hello"),
        ("welcome",11,"Welcome"),("health",25,"HealthRequest"),
        ("health_report",26,"HealthReport"),
        ("auth_challenge",36,"AuthChallenge"),("auth_proof",37,"AuthProof")]:
        f=msg.field.add();f.name=field_name;f.number=number;f.label=1
        f.type=11;f.type_name=f".lu.workspace.v0.{type_name}";f.oneof_index=0
    pool=descriptor_pool.DescriptorPool();pool.AddSerializedFile(file.SerializeToString())
    return {name:message_factory.GetMessageClass(pool.FindMessageTypeByName(
        "lu.workspace.v0."+name)) for name in [*all_types,"WorkspaceFrame"]}

LU=_lu_handshake_message_classes()


def _canonical(frame) -> bytes:
    if frame.protocol_major != WIRE_MAJOR or frame.protocol_minor != WIRE_MINOR:
        raise PermissionError("Incompatible Lu wire version")
    if not SAFE_REF.fullmatch(frame.request_id):
        raise PermissionError("Invalid Lu request identity")
    kind=frame.WhichOneof("body")
    if kind is None:
        raise PermissionError("Missing or unsupported Lu body")
    if kind in ("hello","auth_challenge","auth_proof"):
        if frame.session_ref:
            raise PermissionError("Handshake cannot set session reference")
    elif not SAFE_REF.fullmatch(frame.session_ref):
        raise PermissionError("Missing host-minted session reference")
    if frame.sequence != 0:
        raise PermissionError("Nonstream sequence must be zero")
    data=frame.SerializeToString(deterministic=True)
    if not data or len(data)>MAX_FRAME_BYTES:
        raise ValueError("Invalid Lu frame size")
    return data


def _decode(data:bytes):
    if type(data) is not bytes or not 0<len(data)<=MAX_FRAME_BYTES:
        raise ValueError("Unbounded Lu frame")
    frame=LU["WorkspaceFrame"]()
    try:frame.ParseFromString(data)
    except Exception as e:raise ValueError("Malformed Lu Protobuf") from e
    cleared=LU["WorkspaceFrame"]();cleared.CopyFrom(frame)
    cleared.DiscardUnknownFields()
    if cleared.SerializeToString(deterministic=True)!=data:
        raise PermissionError("Noncanonical or unrecognized Lu wire bytes")
    if _canonical(frame)!=data:
        raise PermissionError("Unrecognized Lu Protobuf representation")
    return frame


def read_frame(stream,*,now:Callable[[],float]=time.monotonic):
    deadline=now()+IO_DEADLINE_SECONDS
    def receive(size):
        out=bytearray()
        while len(out)<size:
            remain=deadline-now()
            if remain<=0:raise TimeoutError("Lu frame deadline expired")
            stream.settimeout(remain)
            try:part=stream.recv(size-len(out))
            except socket.timeout as exc:raise TimeoutError("Lu frame deadline expired") from exc
            if not part:raise ConnectionError("Truncated Lu frame")
            out+=part
        return bytes(out)
    size=struct.unpack("!I",receive(4))[0]
    if not 0<size<=MAX_FRAME_BYTES:
        raise ValueError("Lu frame length outside fixed bound")
    return _decode(receive(size))


def write_frame(stream,frame,*,now:Callable[[],float]=time.monotonic):
    raw=_canonical(frame)
    payload=memoryview(struct.pack("!I",len(raw))+raw)
    deadline=now()+IO_DEADLINE_SECONDS
    while len(payload):
        remain=deadline-now()
        if remain<=0:raise TimeoutError("Lu frame write timed out")
        stream.settimeout(remain)
        try:count=stream.send(payload)
        except socket.timeout as e:raise TimeoutError("Lu frame write timed out") from e
        if count<=0:raise ConnectionError("Lu frame send stopped")
        payload=payload[count:]


@dataclass(frozen=True)
class EnrolledClient:
    module_id:str
    package_sha256:bytes
    secret:bytes=field(repr=False)
    features:tuple[str,...]=()

    def __post_init__(self):
        if (self.module_id!="nvp.film" or type(self.package_sha256) is not bytes or
            len(self.package_sha256)!=32 or not any(self.package_sha256) or
            type(self.secret) is not bytes or len(self.secret)!=32 or
            not any(self.secret) or type(self.features) is not tuple or
            len(self.features)>32 or any(type(x) is not str or
                not SAFE_REF.fullmatch(x) for x in self.features)):
            raise PermissionError("Require externally enrolled NVP identity and credential")


@dataclass(frozen=True)
class LuSession:
    ref:str
    epoch:str
    module_id:str
    enabled_features:tuple[str,...]


def handshake(stream,enrolled:EnrolledClient):
    if not isinstance(enrolled,EnrolledClient):
        raise PermissionError("Installed enrollment missing")
    request_id=secrets.token_hex(16)
    nonce=secrets.token_bytes(32)
    hello=LU["WorkspaceFrame"](protocol_major=1,protocol_minor=0,
        request_id=request_id,hello=LU["Hello"](
        claimed_module_id=enrolled.module_id,claimed_role=1,
        claimed_package_sha256=enrolled.package_sha256,
        minimum_major=1,maximum_major=1,maximum_minor=0,
        requested_features=list(enrolled.features),client_nonce=nonce))
    hello_wire=_canonical(hello)
    write_frame(stream,hello)
    challenge=read_frame(stream)
    if (challenge.WhichOneof("body")!="auth_challenge" or
            challenge.request_id!=request_id or challenge.session_ref or
            len(challenge.auth_challenge.server_nonce)!=32 or
            not any(challenge.auth_challenge.server_nonce)):
        raise PermissionError("No authentic matched Lu challenge")
    server_nonce=challenge.auth_challenge.server_nonce
    proof=hmac.new(enrolled.secret,b"lu.workspace.client.v0\0"+hello_wire+server_nonce,
                   hashlib.sha256).digest()
    auth=LU["WorkspaceFrame"](protocol_major=1,protocol_minor=0,
        request_id=request_id,auth_proof=LU["AuthProof"](client_hmac_sha256=proof))
    write_frame(stream,auth)
    welcome=read_frame(stream)
    if welcome.WhichOneof("body")!="welcome" or welcome.request_id!=request_id:
        raise PermissionError("Unexpected Lu welcome")
    status=welcome.welcome
    if (status.selected_major!=1 or status.selected_minor!=0 or
            not SAFE_REF.fullmatch(welcome.session_ref) or
            not SAFE_REF.fullmatch(status.core_epoch_ref) or
            len(status.enabled_features)>32 or
            any(x not in enrolled.features for x in status.enabled_features)):
        raise PermissionError("Lu negotiated unsupported session/features")
    unsigned=LU["Welcome"]();unsigned.CopyFrom(status)
    unsigned.server_hmac_sha256=b""
    transcript=(b"lu.workspace.server.v0\0"+hello_wire+server_nonce+
        welcome.session_ref.encode("utf-8")+
        unsigned.SerializeToString(deterministic=True))
    expected=hmac.new(enrolled.secret,transcript,hashlib.sha256).digest()
    if not hmac.compare_digest(expected,status.server_hmac_sha256):
        raise PermissionError("Lu host HMAC proof invalid")
    return LuSession(welcome.session_ref,status.core_epoch_ref,
                     enrolled.module_id,tuple(status.enabled_features))


def health_request(session:LuSession):
    if not isinstance(session,LuSession) or session.module_id!="nvp.film":
        raise PermissionError("Cannot issue a non-authorized Lu request")
    return LU["WorkspaceFrame"](protocol_major=1,protocol_minor=0,
       request_id=secrets.token_hex(16),session_ref=session.ref,
       health=LU["HealthRequest"]())


def read_only_health(stream, session:LuSession, *, expected_core_module="lu.core"):
    """Fixture-only bounded HealthRequest->HealthReport after mutual HMAC.

    An HMAC fixture / Python-created LuSession is NOT an installed session,
    package authentication, tool grant, model control, or productive Windows
    named-pipe client. No generic CapabilityInvoke is exposed here.
    """
    if (not isinstance(session,LuSession) or session.module_id!="nvp.film" or
        not SAFE_REF.fullmatch(session.ref) or
        not SAFE_REF.fullmatch(session.epoch) or
        expected_core_module!="lu.core"):
        raise PermissionError("Missing trusted Lu read-only session")
    request=health_request(session)
    write_frame(stream,request)
    response=read_frame(stream)
    if (response.WhichOneof("body")!="health_report" or
        response.request_id!=request.request_id or
        response.session_ref!=session.ref):
        raise PermissionError("Lu health response is not bound to the active session")
    health=response.health_report
    if (health.module_id!=expected_core_module or
        health.connected is not True or health.epoch<=0 or
        not SAFE_REF.fullmatch(health.status_code)):
        raise PermissionError("Lu health response missing trusted host identity/state")
    return {"module_id": health.module_id, "status_code": health.status_code,
            "epoch": health.epoch, "transport_only": True,
            "user_effect_authorized": False, "installed_host_verified": False}


def linux_connect(endpoint:Path,*,peer_policy:Callable[[int,int,int],bool]):
    """Linux source-only transport; requires separately qualified peer/image policy.

    Caller MUST NOT interpret peer creds as full signed-package enrollment.
    If the callback is absent or fails, refuse before issuing Hello.
    """
    if sys.platform!="linux" or not hasattr(socket,"SO_PEERCRED"):
        raise PermissionError("Linux native peer credential support unavailable")
    if not callable(peer_policy):raise PermissionError("No Lu OS peer policy")
    endpoint=Path(endpoint)
    if not endpoint.is_absolute() or len(os.fsencode(str(endpoint)))>=108:
        raise PermissionError("Invalid absolute Lu AF_UNIX endpoint")
    parent=endpoint.parent
    p=os.stat(parent,follow_symlinks=False)
    if not stat.S_ISDIR(p.st_mode) or p.st_uid!=os.getuid() or (p.st_mode&0o777)!=0o700:
        raise PermissionError("Lu socket parent not private and owned")
    ep=os.stat(endpoint,follow_symlinks=False)
    if not stat.S_ISSOCK(ep.st_mode) or ep.st_uid!=os.getuid() or (ep.st_mode&0o777)!=0o600:
        raise PermissionError("Lu socket endpoint not protected")
    conn=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        conn.settimeout(IO_DEADLINE_SECONDS)
        conn.connect(str(endpoint))
        creds=conn.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize("3i"))
        pid,uid,gid=struct.unpack("3i",creds)
        if uid!=os.getuid() or pid<=0 or peer_policy(uid,gid,pid) is not True:
            raise PermissionError("OS peer/package policy denies Lu host")
        return conn
    except BaseException:
        conn.close();raise


def validate_windows_pipe_name(name:str)->str:
    if type(name) is not str or PIPE_NAME.fullmatch(name) is None:
        raise PermissionError("Unexpected Lu named-pipe path")
    return name


def windows_connect(*args,**kwargs):
    """DENY until an independent installed Win32 server-token and signer attestor.

    A guessed or user-chosen pipe may not be used as production Lu enrollment.
    """
    raise PermissionError("Installed Windows named-pipe host authentication is not qualified")
