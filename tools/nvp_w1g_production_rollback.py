"""W1-G production Windows NSIS rollback under held kernel release custody.

Does not use the legacy callback-driven rollback path or test-only simulated
workers-stopped proof. Requires a real native dialog, original Windows Job
accounting, original worker-host locks HELD throughout the transaction,
frozen program hashes, and independent creator film-byte verification.

An interrupted swap is preserved for owner recovery, never silently replayed.
"""
from __future__ import annotations

import os
from pathlib import Path

from tools.nvp_w1g_nsis_recovery import (
    OwnedNSISRecovery, _digest, _program, _write,
)
from tools.nvp_w1g_native_package import _inventory
from tools.nvp_w1g_nsis_activation import (
    _version, _registry_version, _update_registration,
)
from tools.nvp_w1g_production_authority import (
    WindowsCreatorUpgradeApproval, WindowsReleaseWorkerStopEvidence,
)


class ProductionWindowsNSISRollback:
    def __init__(self, owner: OwnedNSISRecovery, *,
                 native_approval: WindowsCreatorUpgradeApproval,
                 kernel_custody: WindowsReleaseWorkerStopEvidence):
        if (type(owner) is not OwnedNSISRecovery or
            owner.test_only_simulation or
            type(native_approval) is not WindowsCreatorUpgradeApproval or
            type(kernel_custody) is not WindowsReleaseWorkerStopEvidence or
            os.name!="nt"):
            raise PermissionError(
                "Production rollback requires Windows original owner, real OS dialog and Job Object")
        if kernel_custody.program != owner.active:
            raise RuntimeError("Rollback kernel source does not own this installed program")
        self.owner=owner
        self.approval=native_approval
        self.kernel=kernel_custody

    def _validate_prepared(self):
        owner=self.owner
        record=owner._read()
        if record["state"]!="PREPARED":
            raise RuntimeError("Interrupted or already-used rollback needs new native recovery review")
        if (_digest(_program(owner.active))!=record["active_sha256"] or
            _digest(_program(owner.old))!=record["previous_sha256"] or
            owner.failed.exists() or owner.failed.is_symlink() or
            owner.pending.exists() or owner.pending.is_symlink()):
            raise RuntimeError("NSIS installed/previous program no longer matches pinned rollback")
        if _registry_version()!=_version(owner.active):
            raise RuntimeError("Registered live NVP version disagrees before rollback")
        return record

    def rollback(self):
        owner=self.owner
        record=self._validate_prepared()
        original_sha=record["active_sha256"]
        with self.kernel.transaction():
            # The original process-tree Job Object must already be empty.
            self.kernel(original_sha)
            scope={
                "operation":"nvp.w1g.nsis.rollback.v1",
                "new_program_sha256":original_sha,
                "old_program_sha256":record["previous_sha256"],
                "original_film_sha256":record["original_films_sha256"],
            }
            if self.approval(dict(scope)) is not True:
                raise PermissionError("Native creator declined exact Windows NSIS rollback")
            self.kernel(original_sha)
            self._validate_prepared()
            if _digest(_inventory(owner.films))!=record["original_films_sha256"]:
                raise RuntimeError("Creator originals changed during native rollback approval")
            record["state"]="SWAP_INTENT"
            _write(owner.journal,record)
            os.replace(owner.active,owner.failed)
            record["state"]="NEW_PARKED"
            _write(owner.journal,record)
            # The retained Job handle and host leases remain held even
            # while the active path temporarily disappears. The source
            # release is now the pinned, parked failed directory.
            self.kernel(original_sha)
            if (_digest(_program(owner.failed))!=original_sha or
                _digest(_program(owner.old))!=record["previous_sha256"] or
                _digest(_inventory(owner.films))!=record["original_films_sha256"]):
                raise RuntimeError("Native rollback candidates changed after first rename")
            os.replace(owner.old,owner.active)
            if (_digest(_program(owner.active))!=record["previous_sha256"] or
                _digest(_inventory(owner.films))!=record["original_films_sha256"]):
                raise RuntimeError("Native restored program or creator film bytes changed")
            _update_registration(_version(owner.active))
            if _registry_version()!=_version(owner.active):
                raise RuntimeError("Windows uninstall registration failed to reconcile")
            record["state"]="ROLLED_BACK"
            _write(owner.journal,record)
            return {
                "status":"NSIS_PREVIOUS_PROGRAM_RESTORED",
                "original_films_modified":False,
                "failed_program_preserved":True,
                "native_human_authorization":True,
                "original_windows_job_kernel_custody":True,
                "full_release_acceptance":False,
            }

    def inspect_interrupted(self):
        """Read-only: never infer safe recovery from an absent process PID."""
        owner=self.owner
        record=owner._read()
        active=(None if not owner.active.is_dir() else _digest(_program(owner.active)))
        previous=(None if not owner.old.is_dir() else _digest(_program(owner.old)))
        failed=(None if not owner.failed.is_dir() else _digest(_program(owner.failed)))
        state=record["state"]
        if state=="PREPARED":
            valid=(active==record["active_sha256"] and
                   previous==record["previous_sha256"] and failed is None)
        elif state=="SWAP_INTENT":
            valid=((active==record["active_sha256"] and
                    previous==record["previous_sha256"] and failed is None) or
                   (active is None and previous==record["previous_sha256"] and
                    failed==record["active_sha256"]))
        elif state=="NEW_PARKED":
            valid=(active is None and previous==record["previous_sha256"]
                   and failed==record["active_sha256"])
        elif state=="ROLLED_BACK":
            valid=(active==record["previous_sha256"] and previous is None
                   and failed==record["active_sha256"])
        else:
            valid=False
        if not valid:
            raise RuntimeError("Interrupted native rollback program identities are ambiguous")
        return {
            "state":state,
            "programs_match_journal":True,
            "recovery_auto_executed":False,
            "requires_new_creator_authorization":state!="ROLLED_BACK",
            "kernel_custody_after_restart_verified":False,
        }
