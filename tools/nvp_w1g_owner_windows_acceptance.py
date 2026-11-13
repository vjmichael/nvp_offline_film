"""W1-G OWNER-OPERATED Windows release coordinator (never browser callable).

This program does not create legal approvals, worker binaries, encryption keys,
or silently authorize an update. All production operations require an original
full five-domain worker roster, kernel release gate, signed exact-byte license
review, original film baseline, and native Windows modal owner consent.
DO NOT invoke from CI. The original installed GUI must be closed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from tools.nvp_w1g_production_authority import (
    WindowsCreatorUpgradeApproval, WindowsReleaseWorkerStopEvidence,
)
from tools.nvp_w1g_nsis_activation import NativeNSISActivation
from tools.nvp_w1g_production_rollback import ProductionWindowsNSISRollback
from tools.nvp_w1g_nsis_recovery import OwnedNSISRecovery, _digest, _program
from tools.nvp_w1g_nsis_activation import (
    _snapshot_root, _require_complete_reviewed_native_roster,
    _registry_version, _tuple, _version,
)
from tools.nvp_w1g_native_package import _inventory, verify_installed
from tools.nvp_w1g_release_build_marker import verify_build_marker


def _domains(values):
    mapping={}
    for raw in values:
        name, sep, path = raw.partition("=")
        if not sep or name in mapping or not Path(path).is_absolute():
            raise ValueError("Exact native workspace syntax is domain=absolute_path")
        mapping[name]=Path(path)
    if set(mapping)!=WindowsReleaseWorkerStopEvidence.REQUIRED_DOMAINS:
        raise PermissionError("Each original cycles/filming/editorial/audio/delivery workspace is required")
    return mapping


def _read_owner_pinned_key(path: Path, *, forbidden_roots) -> bytes:
    """Never take the trust anchor from the candidate, films or job workspace."""
    path=Path(path)
    if (not path.is_absolute() or path.is_symlink() or
        not path.is_file() or path.stat().st_size!=32):
        raise PermissionError("Owner-pinned external reviewer Ed25519 key must be an absolute 32-byte file")
    key_path=path.resolve(strict=True)
    for root in forbidden_roots:
        trusted_root=Path(root).resolve(strict=True)
        if key_path==trusted_root or key_path.is_relative_to(trusted_root):
            raise PermissionError("Reviewer trust anchor cannot reside in mutable NVP release or film roots")
    return path.read_bytes()


def read_only_production_preflight(owner, upgrade, kernel, reviewed_receipt, *,
                                   offline_supply_paths=None):
    """Real-source Windows readiness check; never writes an upgrade journal.

    Kernel custody is acquired and released during this check. The returned
    observation is NOT an authorization or a reusable stop receipt; activate
    must reacquire everything and obtain fresh creator consent.
    """
    if (type(owner) is not OwnedNSISRecovery or
        type(upgrade) is not NativeNSISActivation or
        type(kernel) is not WindowsReleaseWorkerStopEvidence or
        type(reviewed_receipt) is not dict or
        owner.test_only_simulation or upgrade.test_only_simulation or
        os.name!="nt"):
        raise PermissionError("Physical production preflight requires original native Windows authorities")
    _snapshot_root(owner)
    if upgrade.journal.exists() or upgrade.journal.is_symlink():
        raise RuntimeError(
            "Existing production activation journal requires owner reconciliation")
    verify_build_marker(owner.active)
    verify_build_marker(owner.pending)
    verify_installed(reviewed_receipt,owner.pending)
    roster=_require_complete_reviewed_native_roster(owner.pending)
    upgrade._require_signed_review(reviewed_receipt)
    wheel_proof=upgrade._require_offline_supply(offline_supply_paths)
    current=_version(owner.active)
    candidate=_version(owner.pending)
    if (_registry_version()!=current or
        _tuple(candidate)<=_tuple(current)):
        raise RuntimeError("Staged production candidate is not a genuine later NSIS version")
    original=_inventory(owner.films)
    if not original:
        raise RuntimeError("Creator original film baseline is missing")
    original_sha=_digest(_program(owner.active))
    with kernel.transaction():
        proof=kernel(original_sha)
    if (proof.get("process_tree_custody_verified") is not True or
        proof.get("active_windows_jobs")!=0 or
        proof.get("unresolved_worker_jobs")!=0):
        raise PermissionError("Production preflight cannot establish empty release custody")
    return {
        "status":"W1G_NATIVE_PRODUCTION_PREFLIGHT_SOURCE_VERIFIED",
        "current_version":current,
        "candidate_version":candidate,
        "native_worker_roles":sorted(roster["roles"]),
        "signed_release_review_verified":True,
        "signed_offline_wheelhouse_review_verified":True,
        "wheel_lock_sha256":wheel_proof["wheel_lock_sha256"],
        "reviewed_offline_wheel_count":wheel_proof["wheel_count"],
        "original_film_file_count":len(original),
        "kernel_release_custody_checked_at_unix":proof["measured_at_unix"],
        "one_use_creator_authorization_obtained":False,
        "physical_efs_key_recovery_accepted":False,
        "upgrade_or_rollback_executed":False,
        "preflight_receipt_reusable_for_activation":False,
    }


def main(argv=None):
    ap=argparse.ArgumentParser(
        description="Owner-only W1-G Windows upgrade, rollback and read-only inspection")
    ap.add_argument("action",choices=("preflight","prepare","activate","inspect",
                                      "prepare-rollback","rollback","inspect-rollback"))
    ap.add_argument("--programs",type=Path,required=True)
    ap.add_argument("--original-films",type=Path,required=True)
    ap.add_argument("--journal",type=Path,required=True)
    ap.add_argument("--workspace",action="append",default=[],
                    help="cycles|filming|editorial|audio|delivery=absolute_path; repeat five times")
    ap.add_argument("--reviewed-receipt",type=Path)
    ap.add_argument("--pinned-reviewer-public-key",type=Path)
    ap.add_argument("--wheel-lock",type=Path)
    ap.add_argument("--wheelhouse",type=Path)
    ap.add_argument("--signed-wheel-review",type=Path)
    args=ap.parse_args(argv)
    if os.name!="nt":
        raise RuntimeError("Only the creator's native Windows session can execute production upgrade")
    if (not args.programs.is_absolute() or not args.original_films.is_absolute()
        or not args.journal.is_absolute()):
        raise RuntimeError("Trusted original absolute program, film and journal paths required")
    workspaces=_domains(args.workspace)
    key=None
    if args.pinned_reviewer_public_key is not None:
        key=_read_owner_pinned_key(args.pinned_reviewer_public_key,
            forbidden_roots=(args.programs,args.original_films,args.journal,
                             *workspaces.values()))
    if args.action in ("preflight","prepare","activate") and key is None:
        raise PermissionError("Production upgrade requires an external pinned reviewer key")
    supply_paths=None
    if args.action in ("preflight","prepare"):
        if any(p is None or not p.is_absolute() for p in (
                args.wheel_lock,args.wheelhouse,args.signed_wheel_review)):
            raise PermissionError(
                "Production preparation requires wheel lock, actual wheelhouse and signed review")
        supply_paths={
            "wheel_lock":str(args.wheel_lock),
            "wheelhouse":str(args.wheelhouse),
            "signed_wheel_review":str(args.signed_wheel_review),
        }
    real_approve=WindowsCreatorUpgradeApproval()
    kernel=WindowsReleaseWorkerStopEvidence(
        args.programs/"NVP",worker_workspaces=workspaces)
    owner=OwnedNSISRecovery(
        args.programs,args.original_films,args.journal,
        native_approve=real_approve,os_workers_stopped=kernel)
    update=NativeNSISActivation(
        owner,native_authorize=real_approve,
        os_worker_tree_evidence=kernel,pinned_reviewer_public_key=key)
    if args.action in ("preflight","prepare"):
        if args.reviewed_receipt is None:
            raise PermissionError("Externally reviewed exact native package receipt is required")
        if (args.reviewed_receipt.is_symlink() or
            not args.reviewed_receipt.is_file()):
            raise PermissionError("Original reviewed release receipt file unavailable")
        receipt=json.loads(args.reviewed_receipt.read_text("utf8"))
        if args.action=="preflight":
            result=read_only_production_preflight(
                owner,update,kernel,receipt,offline_supply_paths=supply_paths)
        else:
            result=update.prepare(receipt,offline_supply_paths=supply_paths)
    elif args.action=="activate":
        result=update.activate()
    elif args.action=="inspect":
        result=update.inspect()
    elif args.action=="prepare-rollback":
        result=owner.prepare()
    elif args.action=="rollback":
        result=ProductionWindowsNSISRollback(
            owner,native_approval=real_approve,kernel_custody=kernel).rollback()
    else:
        result=ProductionWindowsNSISRollback(
            owner,native_approval=real_approve,
            kernel_custody=kernel).inspect_interrupted()
    # This is a bounded operator receipt; not a film or private key.
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
