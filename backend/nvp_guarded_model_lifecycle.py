"""STACK-02C3B3: estimate-gated owned-instance lifecycle, not a new model runtime.

The B2 manager remains a compatibility contract for its previous tests.
Only this strict manager is eligible for future native host/UI integration.
No unsupported GPU allowance, model reuse, or restart auto-unload.
"""
from __future__ import annotations

from dataclasses import asdict
import threading
import time

from backend.nvp_owned_models import OwnedCpuModelManager, OwnedCpuModelOperation
from backend.nvp_model_estimates import CpuEstimateReceipt, EstimateStore, operation_from_estimate
from backend.nvp_resource_ledger import TaskLedger


class StrictEstimatedCpuModelManager(OwnedCpuModelManager):
    """Estimate provenance and creator consent are both mandatory."""
    def __init__(self,ledger:TaskLedger,*,approval_check,client,estimates:EstimateStore):
        if not isinstance(estimates,EstimateStore) or estimates.ledger.db_path!=ledger.db_path:
            raise ValueError("Trusted estimates must share exactly the model task's durable ledger")
        super().__init__(ledger,approval_check=approval_check,client=client)
        self.estimates=estimates
        self._pulse_lock=threading.RLock()

    def enqueue_estimated(self,task_id,receipt:CpuEstimateReceipt,*,approval_id,lane="interactive"):
        if not isinstance(receipt,CpuEstimateReceipt):
            raise TypeError("Only native estimator receipts may be used")
        op=operation_from_estimate(task_id,receipt)
        self.estimates.record(task_id,receipt)
        self.estimates.verify(op)
        return super().enqueue(op,approval_id=approval_id,lane=lane)

    def enqueue(self,*args,**kwargs):
        """Reject B2's unproven arbitrary estimate_sha256 interface."""
        raise PermissionError("Use enqueue_estimated with a trusted native estimate receipt")

    def _head(self):
        with self.ledger._db() as db:
            row=db.execute("""SELECT t.id FROM tasks t JOIN task_schedule s
                ON s.task_id=t.id WHERE t.state='QUEUED' AND s.owner_key=?
                ORDER BY CASE s.lane WHEN 'interactive' THEN 2
                    WHEN 'standard' THEN 1 ELSE 0 END DESC,
                    s.queued_at,t.id LIMIT 1""",(self.OWNER_KEY,)).fetchone()
        return row[0] if row else None

    def load_next(self):
        head=self._head()
        if head is None:
            return None
        # Validate receipt *before* reserving RAM and again after the
        # approved operation is retrieved. Prevent random SHA-only claims.
        payload=self.bindings.verified_spec(
            head,owner_key=self.OWNER_KEY,require_active=False)
        operation=OwnedCpuModelOperation(**payload)
        self.estimates.verify(operation)
        done=threading.Event()
        # The blocking SDK can take longer than the 15-second generic
        # activity stale threshold. Heartbeat means the NVP supervisor thread
        # is still waiting, NOT that the provider loaded any fraction.
        # No fabricated numeric completion percentage is ever emitted.
        def supervisor_pulse():
            while not done.wait(2):
                try:
                    row=self.ledger.get_task(head)
                    with self.ledger._db() as db:
                        attempt=db.execute("""SELECT state FROM owned_model_attempts
                            WHERE task_id=?""",(head,)).fetchone()
                    if (row and row["state"]=="ACTIVE" and attempt and
                        attempt[0]=="LOAD_REQUESTED"):
                        self.ledger.heartbeat(head)
                except Exception:
                    # Heartbeats are telemetry, not authority to mutate a
                    # native model lifecycle or release its reservation.
                    return
        thread=threading.Thread(target=supervisor_pulse,
                                name="nvp-owned-model-observer",daemon=True)
        thread.start()
        try:
            # B2 applies atomic resource admission and loads a NEW instance.
            return super().load_next()
        finally:
            done.set()
            thread.join(timeout=4)

    def release(self,task_id):
        # Existing B2 exact live-handle identity checks apply. A restart
        # intentionally has no live handle and cannot unload from metadata.
        return super().release(task_id)


def create_strict_local_cpu_manager(ledger,*,approval_check,estimates,port=1234):
    if type(port) is not int or not 1024<=port<=65535:
        raise ValueError("Only an explicit numeric loopback port is allowed")
    try:
        import lmstudio
    except ImportError as exc:
        raise RuntimeError("Pinned official lmstudio SDK is required") from exc
    return StrictEstimatedCpuModelManager(
        ledger,approval_check=approval_check,estimates=estimates,
        client=lmstudio.Client("127.0.0.1:"+str(port)))
