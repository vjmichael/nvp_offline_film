"""STACK-02C3B2 opt-in NVP-owned LM Studio model instance, CPU-only initial gate.

A managed load must use the SDK's load_new_instance with a fresh NVP-only
identifier. The existing .model() API can return somebody else's model and is
forbidden for ownership. Only the exact live returned handle may be unloaded.
No automatic recovery/unload of a model after a host restart is permitted.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass
import re
import time
import uuid

from backend.nvp_approved_tasks import ApprovedTaskBindings
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger

_TASK_ID=re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,79}")
_ESTIMATE_HASH=re.compile(r"[a-f0-9]{64}")


@dataclass(frozen=True)
class OwnedCpuModelOperation:
    task_id:str
    model_key:str
    context_length:int
    conservative_ram_mb:int
    estimate_sha256:str
    kind:str="ai_loading"

    def __post_init__(self):
        if not isinstance(self.task_id,str) or not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("Invalid durable NVP model task ID")
        if (not isinstance(self.model_key,str) or not 1<=len(self.model_key)<=256
            or any(ord(c)<32 for c in self.model_key)):
            raise ValueError("Invalid local model key")
        if (type(self.context_length) is not int or
            not 512<=self.context_length<=262144):
            raise ValueError("Invalid approved context size")
        if (type(self.conservative_ram_mb) is not int or
            not 1024<=self.conservative_ram_mb<=65536):
            raise ValueError("Trusted conservative RAM estimate required")
        if (not isinstance(self.estimate_sha256,str) or
            not _ESTIMATE_HASH.fullmatch(self.estimate_sha256)):
            raise ValueError("SHA of independently captured estimate required")
        if self.kind!="ai_loading":
            raise ValueError("Only explicit AI load operations are supported")


class OwnedCpuModelManager:
    """Trusted native integration only; no routes or unattended eviction.

    The approval_check callback must verify *both* creator opt-in and the
    provider's conservative estimate against the immutable operation digest.
    The injected SDK client must be configured for the verified loopback LM
    Studio server. Never pass client APIs directly to a model/browser.
    """
    OWNER_KEY="nvp_owned_ai_cpu"

    def __init__(self,ledger:TaskLedger,*,approval_check,client):
        if client is None or not callable(getattr(getattr(client,"llm",None),"load_new_instance",None)):
            raise TypeError("A trusted LM Studio SDK client with load_new_instance is required")
        self.ledger=ledger
        self.bindings=ApprovedTaskBindings(ledger,approval_check=approval_check)
        self.client=client
        self._live_handles={}
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS owned_model_attempts (
                task_id TEXT PRIMARY KEY,
                instance_id TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL,
                attempted_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )""")

    def enqueue(self,operation:OwnedCpuModelOperation,*,approval_id,lane="interactive"):
        if not isinstance(operation,OwnedCpuModelOperation):
            raise TypeError("Native producer must supply typed CPU model load")
        request=AdmissionRequest(operation.task_id,"ai_loading",
            "NVP-owned AI: "+operation.model_key[:95],
            operation.conservative_ram_mb)
        return self.bindings.enqueue(request,owner_key=self.OWNER_KEY,lane=lane,
            approval_id=approval_id,document=asdict(operation))

    @staticmethod
    def _actual_identifier(handle):
        # The official Python SDK exposes LlmInstanceInfo.identifier.
        data=handle.get_info()
        identifier=data.get("identifier") if isinstance(data,dict) else getattr(data,"identifier",None)
        if not isinstance(identifier,str) or not identifier:
            raise RuntimeError("Provider did not prove the created model identifier")
        return identifier

    def load_next(self):
        """Claim one CPU-only model load. No arbitrary GPU or model eviction."""
        ticket=self.bindings.claim_next(owner_key=self.OWNER_KEY)
        if ticket is None or not ticket["admitted"]:
            return ticket
        task_id=ticket["task_id"]
        # Re-authorize immediately before crossing into the provider SDK.
        spec=OwnedCpuModelOperation(**self.bindings.verified_spec(
            task_id,owner_key=self.OWNER_KEY))
        if spec.task_id!=task_id or self.ledger.get_task(task_id)["ram_mb"]!=spec.conservative_ram_mb:
            raise RuntimeError("Sealed model request no longer matches memory admission")
        identifier="nvp-"+uuid.uuid4().hex
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO owned_model_attempts
                (task_id,instance_id,state,attempted_at,updated_at)
                VALUES(?,?,?,?,?)""",(task_id,identifier,"LOAD_REQUESTED",time.time(),time.time()))
            db.commit()
        self.ledger.update(task_id,"loading_model",
            "Loading a fresh NVP-specific CPU model instance; progress not reported")
        try:
            # SDK .model(key) is forbidden: it may reuse someone else's model.
            # SDK .load_new_instance(key, unique_id, config) rejects a
            # duplicate identifier instead of attaching to an existing one.
            handle=self.client.llm.load_new_instance(
                spec.model_key,identifier,
                config={"contextLength":spec.context_length,"gpu":{"ratio":0.0}})
            if self._actual_identifier(handle)!=identifier:
                raise RuntimeError("Provider returned a model instance with the wrong identity")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE owned_model_attempts SET state='LOADED',updated_at=?
                    WHERE task_id=? AND state='LOAD_REQUESTED'""",(time.time(),task_id))
                db.commit()
            self._live_handles[task_id]=(identifier,handle)
            self.ledger.update(task_id,"warming_model",
                "Verified NVP-owned model instance ready; RAM remains reserved")
            return {"task_id":task_id,"state":"ACTIVE","instance_id":identifier,
                    "model_key":spec.model_key,"managed_by_nvp":True}
        except Exception:
            # No provider process kill and NO guess that a failed request
            # means no allocation. A lost acknowledgment might have loaded
            # the model. Keep the reservation for manual reconciliation.
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE owned_model_attempts SET state='UNVERIFIED',
                    updated_at=? WHERE task_id=?""",(time.time(),task_id))
                db.commit()
            self.ledger.update(task_id,"recovering",
                "Model load outcome not proven; reservation retained, never auto-unload")
            raise

    def release(self,task_id):
        """Only unload via the exact NVP-created in-process SDK handle."""
        item=self._live_handles.get(task_id)
        if item is None:
            raise PermissionError("No live NVP-owned handle; external and restarted models cannot be unloaded")
        identifier,handle=item
        if self._actual_identifier(handle)!=identifier:
            raise RuntimeError("Model handle ownership identity changed; unload refused")
        row=self.ledger.get_task(task_id)
        if not row or row["state"]!="ACTIVE":
            raise RuntimeError("Cannot unload without matching active NVP resource reservation")
        self.ledger.update(task_id,"offloading_model",
            "Explicitly unloading only the exact NVP-created model instance")
        try:
            handle.unload()
        except Exception:
            self.ledger.update(task_id,"recovering",
                "Provider unload acknowledgment missing; reservation retained")
            raise
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE owned_model_attempts SET state='UNLOADED',updated_at=?
                WHERE task_id=? AND instance_id=?""",(time.time(),task_id,identifier))
            db.commit()
        self._live_handles.pop(task_id,None)
        self.ledger.finish(task_id,"SUCCEEDED",
            "The exact NVP-owned model instance was unloaded by its live SDK handle")
        return {"task_id":task_id,"instance_id":identifier,
                "state":"UNLOADED","released_ram":True}

    def durable_attempts(self):
        """Observation only. After restart never reconstruct an ownership handle."""
        with self.ledger._db() as db:
            return [{"task_id":task_id,"instance_id":identifier,"state":state}
                for task_id,identifier,state in db.execute(
                    "SELECT task_id,instance_id,state FROM owned_model_attempts ORDER BY attempted_at")]


def create_local_owned_cpu_manager(ledger:TaskLedger,*,approval_check,port:int=1234):
    """Construct official SDK client for a verified loopback-only API host.

    No environment-supplied remote URL, DNS host or network interface is
    accepted. This function is called by a trusted NVP native host only.
    """
    if type(port) is not int or not 1024<=port<=65535:
        raise ValueError("LM Studio SDK port must be a local unprivileged TCP port")
    try:
        import lmstudio
    except ImportError as exc:
        raise RuntimeError("Optional official LM Studio Python SDK is not installed") from exc
    # Client(host:port) is documented by the official SDK and refuses implicit
    # default-port discovery. The host is always the numeric IPv4 loopback.
    client=lmstudio.Client("127.0.0.1:"+str(port))
    return OwnedCpuModelManager(ledger,approval_check=approval_check,client=client)
