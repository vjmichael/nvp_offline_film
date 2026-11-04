"""NVP-STACK-02C3B4: Lu alpha source seal and passive, non-authoritative status.

Lu 0.1.0-alpha.2 is a Tauri desktop. Its internal lu_status and inference
Protobuf are NOT a published external API. The separately tested AF_UNIX
ToolCall/ToolReply carrier in jan_alt is not shipped in this alpha and
does not expose model lifecycle. Never use a guessed socket or API key.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
import time
from typing import Callable

from backend.nvp_resource_ledger import TaskLedger

# Exact Git blob identities retrieved from vjmichael/Lu-AI-GUI at pinned main
# source commit ac015280e4594b7cb5fb730a240b8d2a8a819975.
# This attests a local *source checkout only*, not the installed Windows PE.
LU_ALPHA_SOURCE_COMMIT="ac015280e4594b7cb5fb730a240b8d2a8a819975"
LU_ALPHA_BLOBS={
    "src-tauri/lu-core/proto/lu/v1/core.proto":
        "6495ad09b4403dd8f6c714d3358d31da2a43e63a",
    "src-tauri/lu-core/src/persistent_llama_backend.rs":
        "ea28e818b1a62538ab3f1afc10c7b588f9ff0e1a",
    "src-tauri/lu-core/examples/persistent_llama_smoke.rs":
        "79a31fed778c6feeb1a05d717f3f942c3949af69",
    "lu-desktop/src-tauri/src/lib.rs":
        "fb93dc2be3778cddbd9b502dec3bf5bd45656095",
}
MODEL_ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
PHASES={
    "Idle":"external_model_wait",
    "Loading":"loading_model",
    "Ready":"warming_model",
    "Generating":"generating",
    "Unloading":"offloading_model",
    "Failed":"recovering",
}


def git_blob_sha1(raw:bytes):
    return hashlib.sha1(b"blob "+str(len(raw)).encode("ascii")+b"\0"+raw).hexdigest()


def inspect_lu_alpha_source(root:str|Path):
    """Immutable source compatibility check. Never spawns, loads, or connects."""
    base=Path(root)
    if not base.is_dir() or base.is_symlink():
        raise ValueError("A physical local Lu source tree is required")
    source=base.resolve()
    validated={}
    for relative,expected in LU_ALPHA_BLOBS.items():
        file=source/relative
        if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(source):
            raise RuntimeError("Lu source file missing or unsafe: "+relative)
        if file.stat().st_size>512*1024:
            raise RuntimeError("Lu source marker unexpectedly large: "+relative)
        # Git checkout on Windows may materialize CRLF; compare canonical
        # Git content, not the platform's checkout newline representation.
        actual=git_blob_sha1(file.read_bytes().replace(b"\r\n",b"\n"))
        if actual!=expected:
            raise RuntimeError("Lu source does not match alpha contract: "+relative)
        validated[relative]=actual
    proto=(source/"src-tauri/lu-core/proto/lu/v1/core.proto").read_text("utf8")
    desktop=(source/"lu-desktop/src-tauri/src/lib.rs").read_text("utf8")
    engine=(source/"src-tauri/lu-core/src/persistent_llama_backend.rs").read_text("utf8")
    if ("message InferenceFrame {" not in proto or
        "message InferenceResourceUsage {" not in proto or
        "fn lu_status(" not in desktop or
        "async fn lu_load_model(" not in desktop or
        "async fn lu_unload_model(" not in desktop or
        "PersistentLlamaBackend" not in desktop or
        ".arg(\"--n-gpu-layers\")" not in engine):
        raise RuntimeError("Lu inference/status contract unexpectedly changed")
    # Deliberately do not treat an AF_UNIX crate in some OTHER Lu worktree
    # as proof of an enabled external inference service in this desktop.
    return {
        "format":"nvp.lu.alpha.source_contract.v1",
        "lu_commit":LU_ALPHA_SOURCE_COMMIT,
        "source_blobs":validated,
        "source_contract_matched":True,
        "installed_binary_proven":False,
        "lu_real_inference_proven_by_this_gate":False,
        "alpha_internal_tauri_status":True,
        "af_unix_external_inference_supported":False,
        "safe_to_control_lu_model":False,
        "nvp_owned_model":False,
        "windows_alpha_requests_gpu_layers":True,
        "recommended_live_test":"Lu Core persistent_llama_smoke using a separately approved, contained small model"
    }


@dataclass(frozen=True)
class LuRuntimeView:
    """The alpha's Tauri lu_status response, NOT a granted model capability."""
    model_ref:str|None
    session_id:str|None
    generation_id:str|None
    phase:str
    pid:int|None

    @classmethod
    def from_trusted_host(cls,payload):
        if not isinstance(payload,dict) or set(payload)!={
            "modelRef","sessionId","generationId","phase","pid"}:
            raise ValueError("Unsupported Lu native status view")
        phase=payload["phase"]
        if phase not in PHASES:
            raise ValueError("Unknown Lu runtime phase")
        model=payload["modelRef"]
        session=payload["sessionId"]
        generation=payload["generationId"]
        for ident in (model,session,generation):
            if ident is not None and (not isinstance(ident,str) or
                not MODEL_ID.fullmatch(ident)):
                raise ValueError("Malformed Lu host-issued reference")
        pid=payload["pid"]
        if pid is not None and (type(pid) is not int or pid<1):
            raise ValueError("Invalid Lu worker process ID")
        if phase in ("Ready","Generating","Unloading") and not model:
            raise ValueError("Lu status lacks model reference for active phase")
        if phase=="Generating" and (not session or not generation):
            raise ValueError("Lu generation status lacks active session/generation")
        if phase=="Idle" and (model or generation):
            raise ValueError("Idle Lu status contains active model reference")
        return cls(model,session,generation,phase,pid)


class PassiveLuStatusObserver:
    """Observe only a host-vetted Tauri status binding.

    There is NO direct AF_UNIX/TCP connection or API to load/unload.
    read_status must be a trusted in-process Lu bridge added later; a model
    or browser supplied lambda is not host authorization.
    """

    def __init__(self,ledger:TaskLedger,*,read_status:Callable,
                 task_id="lu_alpha_observation"):
        if not isinstance(ledger,TaskLedger) or not callable(read_status):
            raise TypeError("Trusted Lu host status callback and resource ledger required")
        if not MODEL_ID.fullmatch(task_id):
            raise ValueError("Invalid task identity")
        self.ledger=ledger
        self.read_status=read_status
        self.task_id=task_id
        self._registered=False

    def observe(self):
        status=LuRuntimeView.from_trusted_host(self.read_status())
        phase=PHASES[status.phase]
        message=("Lu alpha native state observed: "+status.phase+
                 "; no model lifecycle ownership, percent or RAM/VRAM assumption")
        if not self._registered:
            self.ledger.observe_external(self.task_id,"Lu alpha (externally managed)",
                                         phase=phase,detail=message)
            self._registered=True
        else:
            self.ledger.update(self.task_id,phase,message,fraction=None)
        return {
            "provider":"Lu independent desktop alpha",
            "native_phase":status.phase,
            "model_ref":status.model_ref,
            "session_id":status.session_id,
            "generation_id":status.generation_id,
            "pid":status.pid,
            "observed_at":time.time(),
            "status_origin":"trusted native Tauri callback, not external AF_UNIX",
            "progress_fraction":None,
            "model_loading_authorized":False,
            "model_unloading_authorized":False,
            "nvp_owned":False,
            "reservation_released":False,
        }
