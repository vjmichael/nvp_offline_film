"""W1-G genuine Windows NSIS staging, activation and rollback FILESYSTEM matrix.

This executes the REAL Windows-installed PyInstaller app trees, NSIS marker,
registry, original film snapshots, and Windows atomic renames. Its human
authorization and worker-tree callbacks are deliberately TEST-ONLY
SIMULATIONS. It CANNOT satisfy production one-use human or kernel custody
acceptance. That latter gate must be performed on the creator's actual host.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import time

from tools.nvp_w1g_native_package import (
    verify_installed, original_film_snapshot, verify_original_films_preserved,
)
from tools.nvp_w1g_nsis_recovery import OwnedNSISRecovery, _program, _digest
from tools.nvp_w1g_nsis_activation import (
    NativeNSISActivation, _registry_version, _version,
)

FORMAT="nvp.w1g.windows_actual_nsis_transaction_test.v1"


def run(programs:Path, projects:Path, receipt:dict, journal_root:Path):
    if os.name!="nt":
        raise RuntimeError("Only real native Windows may run the NSIS filesystem matrix")
    programs=programs.resolve()
    projects=projects.resolve()
    if programs.is_symlink() or projects.is_symlink() or (
            not projects.is_dir() or not programs.is_dir()):
        raise RuntimeError("Invalid installed program and creator-original paths")
    active=programs/"NVP"
    pending=programs/"NVP.pending"
    if not active.is_dir() or not pending.is_dir():
        raise RuntimeError("NSIS upgrade did not stage an actual candidate")
    if journal_root.exists() or journal_root.is_symlink():
        raise RuntimeError("Use an unused dedicated test acceptance journal root")
    journal_root.mkdir()
    before=original_film_snapshot(projects)
    old=verify_installed(receipt,active)
    staged=verify_installed(receipt,pending)
    if _version(active)!="0.1.0" or _version(pending)!="0.1.1":
        raise RuntimeError("Genuine NSIS install/stage version negotiation failed")
    if _registry_version()!="0.1.0":
        raise RuntimeError("NSIS staged candidate overwrote the running registration")
    old_program_hash=_digest(_program(active))
    staged_program_hash=_digest(_program(pending))
    owner=OwnedNSISRecovery(
        programs, projects, journal_root,
        native_approve=lambda scope:True,
        os_workers_stopped=lambda:True)
    # IMPORTANT: never export this callback as a production OS proof.
    def simulated_kernel_for_test(original_sha):
        return {
            "os_provenance":"windows-job-object",
            "original_runtime_sha256":original_sha,
            "process_tree_custody_verified":True,
            "active_windows_jobs":0,
            "unresolved_worker_jobs":0,
            "measured_at_unix":time.time(),
            "test_fixture_only_not_kernel_evidence":True,
        }
    transaction=NativeNSISActivation(
        owner,native_authorize=lambda scope:True,
        os_worker_tree_evidence=simulated_kernel_for_test)
    transaction.prepare(receipt)
    promoted=transaction.activate()
    if promoted["status"]!="NSIS_NATIVE_PROGRAM_ACTIVATED_UNACCEPTED":
        raise RuntimeError("Native staged upgrade did not execute")
    if _registry_version()!="0.1.1" or _version(active)!="0.1.1":
        raise RuntimeError("Installed activation failed to update live program/registry")
    if _digest(_program(active))!=staged_program_hash or (
            _digest(_program(programs/"NVP.previous"))!=old_program_hash):
        raise RuntimeError("Windows upgrade renamed different runtime bytes")
    if not verify_original_films_preserved(before,projects):
        raise RuntimeError("Windows staged upgrade modified original film bytes")
    owner.prepare()
    rollback=owner.rollback()
    if rollback["status"]!="NSIS_PREVIOUS_PROGRAM_RESTORED":
        raise RuntimeError("Windows native rollback failed")
    if _version(active)!="0.1.0" or _registry_version()!="0.1.0":
        raise RuntimeError("NSIS rollback did not restore exact installed version/registry")
    if _digest(_program(active))!=old_program_hash or (
            _digest(_program(programs/"NVP.failed"))!=staged_program_hash):
        raise RuntimeError("Rollback lost previous program or failed-release evidence")
    verify_installed(receipt,active)
    preserved=verify_original_films_preserved(before,projects)
    result={
        "format":FORMAT,
        "status":"ACTUAL_WINDOWS_NSIS_STAGE_UPGRADE_ROLLBACK_FILESYSTEM_VERIFIED",
        "old_runtime_sha256":old_program_hash,
        "candidate_runtime_sha256":staged_program_hash,
        "candidate_staged_then_activated_then_rolled_back":True,
        "after_rollback_registration":"0.1.0",
        "original_files_verified":preserved["original_files_verified"],
        "actual_windows_filesystem_renames":True,
        "actual_nsis_staging":True,
        "human_authorization_real":False,
        "kernel_worker_tree_evidence_real":False,
        "physical_release_acceptance":False,
        "release_upgrade_accepted":False,
    }
    return result


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--programs",required=True,type=Path)
    ap.add_argument("--projects",required=True,type=Path)
    ap.add_argument("--build-receipt",required=True,type=Path)
    ap.add_argument("--journal",required=True,type=Path)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    doc=json.loads(args.build_receipt.read_text("utf8"))
    report=run(args.programs,args.projects,doc,args.journal)
    data=json.dumps(report,sort_keys=True,indent=2)+"\n"
    if args.output:
        with args.output.open("x",encoding="utf8") as out:
            out.write(data)
    print(data)
