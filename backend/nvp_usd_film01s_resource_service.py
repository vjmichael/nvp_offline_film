"""USD-FILM-01S host facade: autodetect, queue camera shots, report to Lu.

No new renderer, remote control, or duplicate native process broker.
All execution still needs NVP's existing per-operation director approval
and protected worker supervisor. This facade only plans/admits shots and
publishes NVP-owned measured resources and queue progress for Lu to display.
"""
from __future__ import annotations

import os

from backend.nvp_blender_worker import BlenderWorkerSupervisor
from backend.nvp_resource_guard import collect_resources
from backend.nvp_usd_film01s_adaptive_batch import (
    BatchPreferences,DurableShotBatchQueue,Shot,
    FINAL,PREVIEW,plan_batches,safe_parallelism)


FORMAT="nvp.film01s.lu_read_only_resource_and_batch_report.v1"


def usable_cpu_threads():
    """Honor Linux CPU affinity restrictions, not just host core count."""
    try:
        allowed=os.sched_getaffinity(0)
        if allowed:
            return len(allowed)
    except (AttributeError,OSError,ValueError):
        pass
    value=os.cpu_count()
    return value if type(value) is int and value>0 else None


class NVPAdaptiveShotService:
    def __init__(self,supervisor:BlenderWorkerSupervisor,
                 queue:DurableShotBatchQueue,*,
                 collect_host_resources=collect_resources,
                 verified_cycles_gpu_ids=()):
        if (not isinstance(supervisor,BlenderWorkerSupervisor) or
            not isinstance(queue,DurableShotBatchQueue) or
            not callable(collect_host_resources)):
            raise TypeError("Existing native supervisor and durable NVP queue required")
        self.supervisor=supervisor
        self.queue=queue
        self._collect=collect_host_resources
        self._verified_devices=frozenset(verified_cycles_gpu_ids)

    def prepare(self,plan_id,source_performance_sha256,shots,preferences):
        """Auto-measured plan; no renderer command and no implicit consent."""
        snapshot=self._collect()
        return plan_batches(
            plan_id,source_performance_sha256,shots,preferences,
            snapshot,verified_cycles_gpu_ids=self._verified_devices,
            cpu_threads=usable_cpu_threads())

    def enqueue(self,planned,*,director_event,authorize):
        return self.queue.enqueue(
            planned,director_event=director_event,authorize=authorize)

    def suggest_next(self,plan_id):
        """Bounded next one-shot suggestion, never a process-launch action."""
        status=self.queue.status(plan_id)
        manifest=self.queue._load(plan_id)
        prefs=BatchPreferences(**manifest["preferences"])
        snapshot=self._collect()
        threads=usable_cpu_threads()
        caps={
            stage:safe_parallelism(snapshot,prefs,quality=stage,
                verified_cycles_gpu_ids=self._verified_devices,
                cpu_threads=threads)
            for stage in (PREVIEW,FINAL)}
        for ticket in status["shot_tickets"]:
            if ticket["state"]=="INTERRUPTED" or ticket["state"]=="FAILED":
                return {"state":"BLOCKED_NEEDS_EXPLICIT_RECOVERY",
                        "ticket":ticket,
                        "process_custody_proof_required":True}
        for ticket in status["shot_tickets"]:
            if ticket["state"]=="QUEUED":
                quality=ticket["quality"]
                if caps[quality]["safe_workers"]==0:
                    return {"state":"QUEUED_FOR_HARDWARE",
                            "reason":caps[quality]["reason"],
                            "ticket":ticket}
                if quality==FINAL:
                    low=next((x for x in status["shot_tickets"]
                        if x["quality"]==PREVIEW and
                           x["shot_id"]==ticket["shot_id"]),None)
                    if low is None or low["state"]!="SUCCEEDED":
                        return {"state":"QUEUED_FOR_LOWFI",
                                "ticket":ticket}
                return {"state":"READY_FOR_NVP_AUTHORIZATION",
                        "ticket":ticket,
                        "safe_parallel_workers":caps[quality]["safe_workers"],
                        "authority_from_lu":False}
        return {"state":"NO_PENDING_SHOTS",
                "all_verified":status["all_shots_finished"]}

    def claim_next(self,plan_id,*,director_event,authorize,
                   prove_prior_worker_stopped):
        proposed=self.suggest_next(plan_id)
        if proposed["state"]!="READY_FOR_NVP_AUTHORIZATION":
            return proposed
        ticket=proposed["ticket"]
        return self.queue.claim(
            plan_id,quality=ticket["quality"],
            shot_id=ticket["shot_id"],attempt=ticket["attempt"]+1,
            authorizer=authorize,director_event=director_event,
            prove_prior_worker_stopped=prove_prior_worker_stopped,
            snapshot=self._collect(),
            verified_cycles_gpu_ids=self._verified_devices,
            cpu_threads=usable_cpu_threads())

    def read_only_lu_status(self,plan_id):
        """Versioned telemetry payload: NVP remains the one execution owner."""
        owned=self.supervisor.read_only_resources_for_lu()
        queue=self.queue.status(plan_id)
        manifest=self.queue._load(plan_id)
        policy=BatchPreferences(**manifest["preferences"])
        snapshot=self._collect()
        capacity={
            quality:safe_parallelism(
                snapshot,policy,quality=quality,
                verified_cycles_gpu_ids=self._verified_devices,
                cpu_threads=usable_cpu_threads())
            for quality in (PREVIEW,FINAL)}
        return {
            "format":FORMAT,
            "report_read_only":True,
            "reporting_application":"NVP",
            "execution_authority":"NVP_SUPERVISOR",
            "lu_can_view_only":True,
            "system_capacity":snapshot.public(),
            "owned_nvp_resource_usage":owned,
            "camera_shot_queue":queue,
            "director_batch_preferences":manifest["preferences"],
            "requested_shots_per_batch":manifest[
                "director_requested_shots_per_batch"],
            "effective_shots_per_batch":manifest["shots_per_batch"],
            "safe_parallel_workers_now":capacity,
            "optional_full_camera_rolls_not_required_for_selected_film":True,
            "lu_cannot_launch_cancel_or_override_approval":True,
        }
