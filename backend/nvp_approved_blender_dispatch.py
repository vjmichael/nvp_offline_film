"""STACK-02C3B2: bind approved queued work to the existing contained Blender worker.

Never accept an executable path, script, source or command from the web UI.
The host-specific approval checker must revalidate the current creator approval.
"""
from __future__ import annotations

import hashlib
import json

from backend.nvp_approved_tasks import ApprovedTaskBindings
from backend.nvp_blender_worker import BlenderOperation,BlenderWorkerSupervisor
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger


class ApprovedBlenderDispatcher:
    def __init__(self,supervisor:BlenderWorkerSupervisor,ledger:TaskLedger,*,approval_check,pre_worker_check=None):
        if not isinstance(supervisor,BlenderWorkerSupervisor):
            raise TypeError("Only the established native Blender supervisor may dispatch")
        if supervisor.activity is not ledger:
            raise ValueError("The contained supervisor and approved tasks must share the resource ledger")
        self.supervisor=supervisor
        self.ledger=ledger
        self.owner_key="blender_"+hashlib.sha256(str(supervisor.root).encode()).hexdigest()[:20]
        self.bindings=ApprovedTaskBindings(ledger,approval_check=approval_check)
        if pre_worker_check is not None and not callable(pre_worker_check):
            raise TypeError("Native pre-worker authorization check must be callable")
        self.pre_worker_check=pre_worker_check

    def enqueue(self,operation:BlenderOperation,*,approval_id,lane="standard"):
        if not isinstance(operation,BlenderOperation):
            raise TypeError("Typed BlenderOperation required")
        # Canonical spec includes approved worker script, original input SHA,
        # output manifest, budget, GPU device and timeout. The native worker
        # rechecks these separately before and after execution.
        spec=json.loads(operation.canonical())
        task_id=self.supervisor._activity_id(operation.job_id)
        request=AdmissionRequest(task_id,"blender","Blender: "+operation.job_id[:90],
            operation.memory_limit_mb,operation.gpu_memory_mb,operation.gpu_device_id)
        return self.bindings.enqueue(request,owner_key=self.owner_key,lane=lane,
            approval_id=approval_id,document={"task_id":task_id,"kind":"blender","operation":spec})

    def run_next(self):
        """One synchronous run; a future native dispatcher may invoke repeatedly."""
        ticket=self.bindings.claim_next(owner_key=self.owner_key)
        if ticket is None or not ticket["admitted"]:
            return ticket
        task_id=ticket["task_id"]
        try:
            document=self.bindings.verified_spec(task_id,owner_key=self.owner_key)
            operation=BlenderOperation(**document["operation"])
            if self.supervisor._activity_id(operation.job_id)!=task_id:
                raise RuntimeError("Approved operation does not match Blender worker task")
            row=self.ledger.get_task(task_id)
            if (row["ram_mb"]!=operation.memory_limit_mb or
                row["gpu_mb"]!=operation.gpu_memory_mb or
                row["device_id"]!=operation.gpu_device_id):
                raise RuntimeError("Approved operation memory budget changed")
            self.ledger.update(task_id,"checking_memory",
                               "Approved immutable Blender specification and resource claim verified")
            # Recheck live project/creator policy after successful resource
            # admission and immediately before native worker dispatch.
            # Any refusal is fail-closed; the safety reservation is retained
            # for host reconciliation rather than risking an orphaned job.
            if self.pre_worker_check is not None:
                self.pre_worker_check(task_id,document)
            # Single existing contained worker. It supplies the real job
            # ledger, native OS containment, input/output hashes and recovery.
            result=self.supervisor._run_worker(operation)
            checked=self.supervisor.inspect(operation.job_id)
            state=checked["state"]
            error=checked.get("error") or ""
            if state=="SUCCEEDED":
                self.supervisor.verify_completed(operation.job_id)
                self.ledger.finish(task_id,"SUCCEEDED","Native output and source independently verified")
            elif (state in ("FAILED","CANCELLED","TIMED_OUT") and
                  "cleanup unproven" not in error.lower() and
                  "final close failed" not in error.lower()):
                self.ledger.finish(task_id,
                    "CANCELLED" if state=="CANCELLED" else "FAILED",
                    ("Contained worker finished: "+state)[:240])
            else:
                raise RuntimeError("Native worker termination or audit is not proven")
            return result
        except Exception:
            # We cannot prove no Blender descendant exists when execution,
            # cleanup or journal operations failed. Keep ACTIVE reservation
            # until native supervisor recovery is independently reconciled.
            if self.ledger.get_task(task_id)["state"]=="ACTIVE":
                self.ledger.update(task_id,"recovering",
                    "Execution or approval proof incomplete; reservation held for native recovery")
            raise
