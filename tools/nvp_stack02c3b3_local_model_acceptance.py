"""Manual B3 native LM Studio acceptance on a deliberately selected small model.

DRY RUN by default. Do not run with a large model or on a RAM-constrained PC.
This is a developer acceptance probe; not a runtime service or end-user UI.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import uuid

from backend.nvp_model_consent import NativeModelConsent
from backend.nvp_model_estimates import TrustedLmsEstimator, EstimateStore, operation_from_estimate
from backend.nvp_guarded_model_lifecycle import create_strict_local_cpu_manager
from backend.nvp_resource_ledger import TaskLedger


def main():
    p=argparse.ArgumentParser(description="CPU-only NVP-owned model admission probe")
    p.add_argument("--model-key",required=True)
    p.add_argument("--context-length",type=int,default=4096)
    p.add_argument("--lms-native-exe",required=True,
        help="Pinned native executable; scripts/batch launchers fail closed")
    p.add_argument("--lms-exe-sha256",required=True)
    p.add_argument("--port",type=int,default=1234)
    p.add_argument("--state-dir",required=True,
        help="Dedicated writable runtime for acceptance evidence")
    p.add_argument("--execute",action="store_true",help="Allow a new CPU model instance to load")
    p.add_argument("--creator-consent",default="",
        help="Required with --execute: I_APPROVE_NEW_CPU_MODEL_AND_OWNED_UNLOAD")
    a=p.parse_args()
    if a.execute and a.creator_consent!="I_APPROVE_NEW_CPU_MODEL_AND_OWNED_UNLOAD":
        p.error("An explicit creator confirmation is required before any model loads")
    ledger=TaskLedger(a.state_dir)
    estimate=TrustedLmsEstimator(executable=a.lms_native_exe,
        executable_sha256=a.lms_exe_sha256,port=a.port).capture(
            a.model_key,a.context_length)
    summary={"format":"nvp.b3.cpu_model_acceptance.v1",
             "mode":"execute" if a.execute else "estimate_only",
             "estimate_digest":estimate.digest,
             "estimated_total_mib":estimate.estimated_total_mib,
             "conservative_ram_mb":estimate.conservative_ram_mb,
             "estimated_gpu_mib":estimate.estimated_gpu_mib,
             "model_key":estimate.model_key,"context_length":estimate.context_length,
             "model_loaded":False,"model_unloaded":False}
    if not a.execute:
        print(json.dumps(summary,indent=2,sort_keys=True))
        return 0
    task_id="nvpcpu_"+uuid.uuid4().hex
    op=operation_from_estimate(task_id,estimate)
    consents=NativeModelConsent(ledger)
    approval=consents.issue_from_trusted_ui(op,duration_s=120)
    # This script is only a manual approved developer acceptance path:
    # it never opens a web API to mint creator approval.
    manager=create_strict_local_cpu_manager(ledger,approval_check=consents.check,
        estimates=EstimateStore(ledger),port=a.port)
    manager.enqueue_estimated(task_id,estimate,approval_id=approval)
    outcome=manager.load_next()
    if outcome is None or not outcome.get("managed_by_nvp"):
        summary["admission"]="QUEUED"
        summary["reason"]=outcome.get("reason","No known safe resource admission") if outcome else "No task"
        print(json.dumps(summary,indent=2,sort_keys=True))
        return 2
    summary["model_loaded"]=True
    summary["instance_id"]=outcome["instance_id"]
    # The strict manager itself has verified identifier, unique provider
    # instanceReference, model key and CPU-only config requested in the SDK.
    # Never search for model names or call unload-all to clean up.
    try:
        release=manager.release(task_id)
        summary["model_unloaded"]=release["state"]=="UNLOADED"
        summary["final_reserved_ram_mb"]=ledger.snapshot()["reservations"]["ram_mb"]
        if not summary["model_unloaded"] or summary["final_reserved_ram_mb"]!=0:
            raise RuntimeError("Owned model unload or memory-release proof failed")
    except Exception:
        # Original live-handle ownership or provider acknowledgement is
        # uncertain. Never impersonate cleanup or release a reservation.
        summary["recovery_required"]=True
        summary["final_reserved_ram_mb"]=ledger.snapshot()["reservations"]["ram_mb"]
        print(json.dumps(summary,indent=2,sort_keys=True))
        raise
    print(json.dumps(summary,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
