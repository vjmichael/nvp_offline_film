"""INT-01D: native-host-bound Lu Workspace admission to the director Film Home.

This is NOT a Lu transport, network service, scope issuer, model manager or
connector to an unshipped Lu Tauri API. Only a trusted installed native Lu
Workspace integration may inject host and issue_scope callbacks. NVP never
loads/starts a second model, invents a Lu scope, or turns generated text into
director approval. Protected G03 movies refuse all external Lu source reads
until independent confidential-host source policy is implemented.
"""
from __future__ import annotations

from hashlib import sha256
import re

from backend.nvp_lu_g02_port import LuG02FilmPort
from backend.nvp_lu_workspace import LuHostError,NvpLuWorkspace

PROJECT_ID=re.compile(r"[0-9a-f]{32}\Z")
SHA=re.compile(r"[0-9a-f]{64}\Z")

UNCONNECTED={
    "state":"disconnected",
    "message":"Lu Workspace is not connected. You can keep making your film manually.",
    "model_ref":None,
    "host_reported_only":False,
    "weights_verified_here":False,
    "vram_verified_here":False,
    "inference_authorized_by_status":False,
    "external_lu_runtime_required":True,
    "nvp_owns_model":False,
}


class NativeLuFilmService:
    """Real host capabilities supplied from outside NVP, not from HTTP.

    issue_scope(project, operation) MUST return an already host-issued opaque
    active Lu scope after checking the native Lu Workspace instance and user.
    Scope/epoch/project are verified by the Lu adapter on *every* operation.
    """

    def __init__(self,studio,film_access,live_films,*,lu_host,issue_scope):
        if not callable(issue_scope):
            raise TypeError("Trusted Lu native scope resolver required")
        self.studio=studio
        self.access=film_access
        self.live_films=live_films
        self.issue_scope=issue_scope
        self.port=LuG02FilmPort(lu_host)
        self.workspace=NvpLuWorkspace(
            self.port,require_completed_receipt=True)

    def _local(self,pid,token):
        if type(pid) is not str or not PROJECT_ID.fullmatch(pid):
            raise ValueError("Select a valid local film project")
        if self.live_films().exists(pid):
            raise PermissionError(
                "An encrypted movie cannot be sent to Lu until independent "
                "private Workspace source-custody approval is implemented")
        if self.access().protected(pid) and not self.access().permitted(
                pid,token,renew=False):
            raise PermissionError("Unlock the movie before accessing Lu")
        return self.studio.get_project(pid)

    def _scope(self,pid,operation):
        # No Lu scopes or JWT-like tokens originate in HTTP cookies/bodies.
        scope=self.issue_scope(pid,operation)
        claim=self.port._scope(scope,operation)
        if claim["project"]!=pid:
            raise LuHostError("Lu Workspace is attached to another film")
        return scope,claim

    def _check(self,pid,token,scope,claim,operation):
        self._local(pid,token)
        if self.port._scope(scope,operation)!=claim:
            raise LuHostError("Lu Workspace was revoked or changed")

    def status(self,pid,token):
        self._local(pid,token)
        scope,claim=self._scope(pid,"status")
        result=self.port.status(scope)
        self._check(pid,token,scope,claim,"status")
        return {**result,"external_lu_runtime_required":True,
                "nvp_owns_model":False}

    def propose_screenplay(self,pid,token,direction,*,expected_revision=None):
        if type(direction) is not str or len(direction)>1200:
            raise ValueError("Describe your screenplay direction briefly")
        before=self._local(pid,token)
        if (expected_revision is not None and
                (type(expected_revision) is not int or
                 expected_revision!=before["revision"])):
            raise RuntimeError("Your screenplay changed; reload before requesting Lu")
        if not before["idea"].strip() and not before["screenplay"].strip():
            raise ValueError("Describe your movie idea before requesting AI writing")
        # A screenplay operation requests a GENERATE-scoped native Lu
        # grant, not a harmless read grant that might later be upgraded
        # implicitly by NVP. Lu verifies read/generate/receipt/save
        # independently under the same immutable host-issued scope.
        scope,claim=self._scope(pid,"generate")
        self._check(pid,token,scope,claim,"read")
        source=self.port.read_project(scope)
        if any(source.get(k)!=before[k] for k in
               ("id","revision","title","idea","screenplay")):
            raise LuHostError("Lu's film source is not the current NVP project")
        self._check(pid,token,scope,claim,"read")
        # No NVP writer_for, LM Studio endpoint, llama.cpp loader or URL.
        # The Lu port verifies Ready, epoch, model session, every event,
        # completion and durable Lu-side proposal consumption.
        saved=self.workspace.propose(scope,stage="screenplay",
                                    instructions=direction)
        self._check(pid,token,scope,claim,"save")
        if (type(saved) is not dict or saved.get("status")!="proposed" or
                saved.get("stage")!="screenplay" or
                saved.get("source_mutated") is not False or
                type(saved.get("content")) is not str or
                not SHA.fullmatch(saved.get("consumed_proposal_sha256","")) or
                sha256(saved["content"].encode("utf8")).hexdigest()!=
                    saved["consumed_proposal_sha256"]):
            raise LuHostError("Lu did not return an exact reviewable proposal")
        # A project may have changed during expensive Lu inference; G04's
        # own SQLite BEGIN IMMEDIATE CAS also rechecks this same source.
        after=self._local(pid,token)
        if (after["revision"]!=before["revision"] or
                after["idea"]!=before["idea"] or
                after["screenplay"]!=before["screenplay"]):
            raise RuntimeError("Movie changed during Lu writing; original is preserved")
        from backend.nvp_g04_preproduction import G04Preproduction
        receipt={
            "format":"nvp.int01d.lu_host_proposal.v1",
            "source":"lu-native-workspace-host",
            "workspace":claim["workspace"],"epoch":claim["epoch"],
            "content_sha256":saved["consumed_proposal_sha256"],
            "source_revision":before["revision"],
            "source_mutated":False,
            "creator_approved":False,
            "native_model_receipt_verified_in_lu":True,
            "model_weights_verified_in_nvp":False,
            "gpu_verified_in_nvp":False,
        }
        return G04Preproduction(self.studio).stage_lu_screenplay(
            pid,content=saved["content"],instructions=direction,
            expected_revision=before["revision"],
            expected_source_sha256=sha256(
                (before["screenplay"]+"\x00"+before["idea"]).encode("utf8")
            ).hexdigest(),host_receipt=receipt)

    def cancel(self,pid,token):
        self._local(pid,token)
        scope,claim=self._scope(pid,"cancel")
        outcome=self.port.cancel(scope)
        self._check(pid,token,scope,claim,"cancel")
        return outcome


def install_native_lu_film_service(app,studio,film_access,live_films,
                                   *,lu_host,issue_scope):
    """Trusted Python host bootstrap only; NEVER an HTTP or JS API.

    No installed Lu bridge is known to exist today, so NVP leaves the
    service absent and advertises disconnected until a real Lu-owned
    Workspace implementation explicitly installs these callbacks.
    """
    current=getattr(app.state,"nvp_lu_native_film",None)
    if current is not None:
        raise RuntimeError("Lu Workspace was already bound to this NVP host")
    service=NativeLuFilmService(studio,film_access,live_films,
        lu_host=lu_host,issue_scope=issue_scope)
    app.state.nvp_lu_native_film=service
    return service
