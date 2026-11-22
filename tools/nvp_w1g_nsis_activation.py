"""W1-G native-owner activation of an NSIS-staged Windows update.

The NSIS installer STAGES NVP.pending but cannot swap a running program.
This trusted host-side coordinator requires exact build payload hashes,
creator authorization, current and new version identity, original-film
snapshot, and fresh independently measured Windows job-tree absence before
both directory renames. A PID list or stale permission is never admission.
It cannot install/approve itself or be invoked directly from a web endpoint.

Not a signed-release or physical Windows acceptance claim.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time

from tools.nvp_w1g_native_package import _inventory, verify_installed
from tools.nvp_w1g_nsis_recovery import (
    OwnedNSISRecovery, _digest, _program, _write,
)

FORMAT="nvp.w1g.nsis.native_activation.v1"
VERSION=re.compile(r"^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$")


def _version(root):
    path=root/"nvp-alpha-version.txt"
    if path.is_symlink() or not path.is_file() or path.stat().st_size>32:
        raise RuntimeError("NSIS release has no bounded pinned version")
    label=path.read_text("ascii")
    if not VERSION.fullmatch(label):
        raise RuntimeError("Unknown NSIS release version")
    return label


def _tuple(label):
    if not VERSION.fullmatch(label):
        raise RuntimeError("Invalid monotonic NVP release version")
    return tuple(int(n) for n in label.split("."))


def _require_complete_reviewed_native_roster(bundle):
    """One token/executable cannot represent all five independent roles."""
    from tools.nvp_w1g_worker_package import ROLES, verify_native_workers
    report=verify_native_workers(bundle,expected_platform="windows-amd64")
    if set(report["roles"]) != set(ROLES):
        raise PermissionError(
            "All five actual compiled native worker roles must be reviewed and provisioned")
    return report


def _snapshot_root(owner):
    if any(p.exists() or p.is_symlink() for p in (
            owner.old,owner.failed,owner.journal)):
        raise RuntimeError("Existing NSIS upgrade/rollback evidence must reconcile first")
    if not owner.active.is_dir() or not owner.pending.is_dir():
        raise RuntimeError("Both active and staged native releases are required")


def _registry_version():
    if os.name!="nt":
        raise RuntimeError("Only native Windows can attest the installed NSIS registration")
    import winreg
    key=r"Software\Microsoft\Windows\CurrentVersion\Uninstall\NVPAlpha"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as handle:
        value,kind=winreg.QueryValueEx(handle,"DisplayVersion")
    if type(value) is not str or not VERSION.fullmatch(value):
        raise RuntimeError("Installed NSIS version registry is invalid")
    return value


def _update_registration(version):
    if os.name!="nt":
        raise RuntimeError("No simulated Windows registry update allowed")
    import winreg
    key=r"Software\Microsoft\Windows\CurrentVersion\Uninstall\NVPAlpha"
    with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,key,0,winreg.KEY_SET_VALUE) as handle:
        winreg.SetValueEx(handle,"DisplayVersion",0,winreg.REG_SZ,version)


class NativeNSISActivation:
    def __init__(self,owner:OwnedNSISRecovery,*,native_authorize,
                 os_worker_tree_evidence, test_only_simulation=False,
                 pinned_reviewer_public_key=None):
        if (not isinstance(owner,OwnedNSISRecovery) or
            not callable(native_authorize) or
            not callable(os_worker_tree_evidence)):
            raise TypeError("Original Windows installer owner, human and OS source required")
        self.test_only_simulation=(test_only_simulation is True)
        self.pinned_reviewer_public_key=pinned_reviewer_public_key
        if not self.test_only_simulation:
            from tools.nvp_w1g_production_authority import (
                WindowsCreatorUpgradeApproval, WindowsReleaseWorkerStopEvidence,
            )
            if (owner.test_only_simulation or
                type(native_authorize) is not WindowsCreatorUpgradeApproval or
                type(os_worker_tree_evidence) is not WindowsReleaseWorkerStopEvidence or
                (pinned_reviewer_public_key is not None and
                 (type(pinned_reviewer_public_key) is not bytes or
                  len(pinned_reviewer_public_key)!=32))):
                raise PermissionError(
                    "Production NSIS cannot accept callback/synthetic human or kernel receipts")
        self.owner=owner
        self.authorize=native_authorize
        self.os_evidence=os_worker_tree_evidence
        self.journal=owner.journal_root/"nsis-activation.json"

    def _require_signed_review(self, receipt):
        """A prepared production candidate is independently reviewed already.

        Inspection never needs a reviewer key, but any mutation does. A
        subsequent activation re-verifies the same release and owner-pinned key.
        """
        if self.test_only_simulation:
            return
        key=self.pinned_reviewer_public_key
        if type(key) is not bytes or len(key)!=32:
            raise PermissionError("External owner-pinned reviewer public key required")
        if receipt.get("native_worker_manifest_verified") is not True:
            raise PermissionError(
                "Production upgrade lacks reviewed compiled native workers")
        from tools.nvp_w1g_reviewed_release import verify_signed_release_review
        verify_signed_release_review(
            receipt,receipt.get("signed_redistribution_review"),
            pinned_reviewer_public_key=key)


    def _require_offline_supply(self, supply):
        """Independently verify exact local wheels and reviewer signature.

        An unsigned lock, an arbitrary Boolean in the installed package, or
        a previous tool's JSON success result is never admission.
        """
        if self.test_only_simulation:
            return None
        expected={"wheel_lock","wheelhouse","signed_wheel_review"}
        if type(supply) is not dict or set(supply)!=expected:
            raise PermissionError(
                "Production NSIS requires actual signed offline wheelhouse supply")
        paths={name:Path(value) for name,value in supply.items()
               if type(value) is str}
        if len(paths)!=len(expected):
            raise PermissionError("Offline supply paths must be trusted absolute paths")
        from tools.nvp_w1g_signed_wheelhouse import verify_from_paths
        return verify_from_paths(
            lock_path=paths["wheel_lock"],wheelhouse=paths["wheelhouse"],
            signed_review_path=paths["signed_wheel_review"],
            reviewer_key=self.pinned_reviewer_public_key,
            platform="windows-amd64")


    def _require_physical_efs_review(self, recovery_supply):
        """Recheck signed independent recovery review AND live native EFS.

        A signed human statement alone does not prove the scratch volume is
        currently encrypting. A current OS probe alone does not prove backup
        recovery. Require both; never use a CI receipt as owner authority.
        """
        if self.test_only_simulation:
            return None
        if (type(recovery_supply) is not dict or
            set(recovery_supply)!={"efs_scratch_root","signed_efs_review"} or
            any(type(value) is not str for value in recovery_supply.values())):
            raise PermissionError(
                "Production NSIS requires physical EFS scratch and independently signed recovery review")
        from tools.nvp_w1g_physical_efs_review import verify_physical_efs_supply
        return verify_physical_efs_supply(
            scratch_root=Path(recovery_supply["efs_scratch_root"]),
            signed_review_path=Path(recovery_supply["signed_efs_review"]),
            reviewer_public_key=self.pinned_reviewer_public_key)

    def _kernel_empty(self,original_sha):
        # A native host must provide this from its actual Windows Job
        # supervisor. The receipt is re-fetched after human approval.
        proof=self.os_evidence(original_sha)
        if (type(proof) is not dict or
            (proof.get("test_fixture_only_not_kernel_evidence") is True
             and not self.test_only_simulation) or
            proof.get("os_provenance")!="windows-job-object" or
            proof.get("original_runtime_sha256")!=original_sha or
            proof.get("process_tree_custody_verified") is not True or
            proof.get("active_windows_jobs")!=0 or
            proof.get("unresolved_worker_jobs")!=0 or
            type(proof.get("measured_at_unix")) not in (int,float) or
            abs(time.time()-proof["measured_at_unix"])>5):
            raise PermissionError("Real native Windows kernel stop receipt unavailable/stale")
        return proof

    def prepare(self, trusted_external_receipt, *, offline_supply_paths=None,
                physical_efs_supply=None):
        if self.journal.exists() or self.journal.is_symlink():
            raise RuntimeError("Previously prepared native activation must reconcile")
        _snapshot_root(self.owner)
        current=_program(self.owner.active)
        next_files=_program(self.owner.pending)
        if not (self.owner.pending/"Uninstall NVP.exe").is_file():
            raise RuntimeError("Staged NSIS release lacks its version-correct uninstaller")
        if type(trusted_external_receipt) is not dict:
            raise RuntimeError("Externally reviewed package build receipt required")
        verify_installed(trusted_external_receipt,self.owner.pending)
        supply_evidence=self._require_offline_supply(offline_supply_paths)
        efs_evidence=self._require_physical_efs_review(physical_efs_supply)
        if not self.test_only_simulation:
            from tools.nvp_w1g_release_build_marker import verify_build_marker
            verify_build_marker(self.owner.active)
            verify_build_marker(self.owner.pending)
            _require_complete_reviewed_native_roster(self.owner.pending)
            self._require_signed_review(trusted_external_receipt)
        current_version=_version(self.owner.active)
        next_version=_version(self.owner.pending)
        registered=_registry_version()
        if registered!=current_version or _tuple(next_version)<=_tuple(current_version):
            raise RuntimeError("Cannot replace unknown/same/older native installed NVP")
        sources=_inventory(self.owner.films)
        if not sources:
            raise RuntimeError("No original film baseline available")
        record={
            "format":FORMAT,"state":"PREPARED",
            "active_sha256":_digest(current),
            "next_sha256":_digest(next_files),
            "original_films_sha256":_digest(sources),
            "current_version":current_version,"new_version":next_version,
            "reviewed_package_receipt":trusted_external_receipt,
            "offline_supply_paths":offline_supply_paths if not self.test_only_simulation else None,
            "offline_supply_evidence":supply_evidence,
            "physical_efs_supply":physical_efs_supply if not self.test_only_simulation else None,
            "physical_efs_evidence":efs_evidence,
            "active_path":str(self.owner.active),
            "pending_path":str(self.owner.pending),
            "previous_path":str(self.owner.old),
            "original_film_root":str(self.owner.films),
            "installed_app_acceptance":False,
        }
        _write(self.journal,record)
        return {"status":"W1G_NSIS_NATIVE_UPGRADE_PREPARED",
                "current_version":current_version,
                "new_version":next_version,
                "original_films_modified":False}

    def _checked(self):
        if self.journal.is_symlink() or not self.journal.is_file():
            raise RuntimeError("Trusted native upgrade preparation journal missing")
        record=json.loads(self.journal.read_text("utf8"))
        if (type(record) is not dict or record.get("format")!=FORMAT or
            record.get("active_path")!=str(self.owner.active) or
            record.get("pending_path")!=str(self.owner.pending) or
            record.get("previous_path")!=str(self.owner.old) or
            record.get("original_film_root")!=str(self.owner.films)):
            raise RuntimeError("NSIS native upgrade journal is foreign or corrupted")
        if _digest(_inventory(self.owner.films))!=record["original_films_sha256"]:
            raise RuntimeError("Original film content changed since upgrade preparation")
        return record

    def activate(self):
        if self.test_only_simulation:
            return self._activate_under_held_custody()
        # Keep the genuine original kernel-backed worker host admission
        # locks held across BOTH checks, creator approval and OS renames.
        with self.os_evidence.transaction():
            return self._activate_under_held_custody()

    def _activate_under_held_custody(self):
        record=self._checked()
        if record["state"]!="PREPARED":
            raise RuntimeError("Native installer activation is consumed or interrupted")
        if (_digest(_program(self.owner.active))!=record["active_sha256"] or
            _digest(_program(self.owner.pending))!=record["next_sha256"] or
            self.owner.old.exists() or self.owner.old.is_symlink() or
            _registry_version()!=record["current_version"]):
            raise RuntimeError("Release changed after authorizing staged upgrade")
        verify_installed(record["reviewed_package_receipt"],self.owner.pending)
        if not self.test_only_simulation:
            supply_again=self._require_offline_supply(record.get("offline_supply_paths"))
            previous=record.get("offline_supply_evidence")
            if (type(previous) is not dict or
                supply_again["wheel_lock_sha256"]!=previous.get("wheel_lock_sha256") or
                supply_again["review_scope_sha256"]!=previous.get("review_scope_sha256")):
                raise PermissionError("Offline release wheels changed since original production approval")
            efs_again=self._require_physical_efs_review(record.get("physical_efs_supply"))
            original_efs=record.get("physical_efs_evidence")
            if (type(original_efs) is not dict or
                efs_again["signed_efs_review_sha256"]!=original_efs.get("signed_efs_review_sha256")):
                raise PermissionError("Physical EFS recovery acceptance changed since preparation")

            from tools.nvp_w1g_release_build_marker import verify_build_marker
            verify_build_marker(self.owner.active)
            verify_build_marker(self.owner.pending)
            _require_complete_reviewed_native_roster(self.owner.pending)
            self._require_signed_review(record["reviewed_package_receipt"])
        self._kernel_empty(record["active_sha256"])
        consent={
            "operation":"nvp.w1g.nsis.activate_prepared_native.v1",
            "old_sha256":record["active_sha256"],
            "new_sha256":record["next_sha256"],
            "original_films_sha256":record["original_films_sha256"],
            "new_version":record["new_version"],
        }
        if self.authorize(dict(consent)) is not True:
            raise PermissionError("Creator refused exact NSIS upgrade")
        self._kernel_empty(record["active_sha256"])
        if (_digest(_program(self.owner.active))!=record["active_sha256"] or
            _digest(_program(self.owner.pending))!=record["next_sha256"] or
            _digest(_inventory(self.owner.films))!=record["original_films_sha256"]):
            raise RuntimeError("Installed original/approved candidate changed during authorization")
        record["state"]="SWAP_INTENT"
        _write(self.journal,record)
        os.replace(self.owner.active,self.owner.old)
        record["state"]="OLD_PARKED"
        _write(self.journal,record)
        try:
            os.replace(self.owner.pending,self.owner.active)
            if (_digest(_program(self.owner.active))!=record["next_sha256"] or
                _digest(_inventory(self.owner.films))!=record["original_films_sha256"]):
                raise RuntimeError("Activated native payload or creator film changed")
            verify_installed(record["reviewed_package_receipt"],self.owner.active)
            record["state"]="PROMOTED_UNREGISTERED"
            _write(self.journal,record)
            _update_registration(record["new_version"])
            if _registry_version()!=record["new_version"]:
                raise RuntimeError("Windows registered a different NVP application version")
            record["state"]="PROMOTED_UNACCEPTED"
            _write(self.journal,record)
        except BaseException:
            # Preserve both versions and journal, no invisible rollback or
            # replay of a previous creator approval.
            raise
        return {
            "status":"NSIS_NATIVE_PROGRAM_ACTIVATED_UNACCEPTED",
            "new_version":record["new_version"],
            "previous_preserved":True,
            "original_films_modified":False,
            "physical_installed_acceptance":False,
        }

    def inspect(self):
        record=self._checked()
        original=record["active_sha256"]
        candidate=record["next_sha256"]
        active_hash=(_digest(_program(self.owner.active))
                     if self.owner.active.is_dir() else None)
        pending_hash=(_digest(_program(self.owner.pending))
                      if self.owner.pending.is_dir() else None)
        previous_hash=(_digest(_program(self.owner.old))
                       if self.owner.old.is_dir() else None)
        failed_hash=(_digest(_program(self.owner.failed))
                     if self.owner.failed.is_dir() else None)
        state=record["state"]
        if state=="PREPARED":
            consistent=(active_hash==original and pending_hash==candidate
                        and previous_hash is None)
        elif state=="SWAP_INTENT":
            consistent=(active_hash==original and pending_hash==candidate
                        and previous_hash is None) or (
                            active_hash is None and pending_hash==candidate
                            and previous_hash==original)
        elif state=="OLD_PARKED":
            consistent=(active_hash is None and pending_hash==candidate
                        and previous_hash==original)
        elif state in ("PROMOTED_UNREGISTERED","PROMOTED_UNACCEPTED"):
            consistent=(active_hash==candidate and pending_hash is None
                        and previous_hash==original)
        elif state=="PRODUCTION_ROLLBACK_INTENT":
            # A crash may occur between the two rollback renames, before
            # uninstall registration, or before the second ledger fsync.
            # Inspection ONLY, no reuse of the old creator approval.
            consistent=(pending_hash is None and (
                (active_hash==candidate and previous_hash==original
                 and failed_hash is None) or
                (active_hash is None and previous_hash==original
                 and failed_hash==candidate) or
                (active_hash==original and previous_hash is None
                 and failed_hash==candidate)))
        elif state=="ROLLED_BACK":
            consistent=(active_hash==original and pending_hash is None
                        and previous_hash is None and failed_hash==candidate)
        else:
            consistent=False
        if not consistent:
            raise RuntimeError("Native NSIS interrupted state differs from source-verified journal")
        return {
            "status":"W1G_NSIS_NATIVE_ACTIVATION_JOURNAL",
            "state":state,
            "state_consistent_with_filesystem":True,
            "requires_kernel_owner_reconciliation":state!="PROMOTED_UNACCEPTED",
            "live_installed_accepted":False,
            "original_films_unchanged":True,
        }
