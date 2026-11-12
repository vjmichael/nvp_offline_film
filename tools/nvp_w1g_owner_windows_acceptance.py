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
from tools.nvp_w1g_nsis_recovery import OwnedNSISRecovery


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


def main(argv=None):
    ap=argparse.ArgumentParser(
        description="Owner-only W1-G Windows upgrade, rollback and read-only inspection")
    ap.add_argument("action",choices=("prepare","activate","inspect",
                                      "prepare-rollback","rollback","inspect-rollback"))
    ap.add_argument("--programs",type=Path,required=True)
    ap.add_argument("--original-films",type=Path,required=True)
    ap.add_argument("--journal",type=Path,required=True)
    ap.add_argument("--workspace",action="append",default=[],
                    help="cycles|filming|editorial|audio|delivery=absolute_path; repeat five times")
    ap.add_argument("--reviewed-receipt",type=Path)
    ap.add_argument("--pinned-reviewer-public-key",type=Path)
    args=ap.parse_args(argv)
    if os.name!="nt":
        raise RuntimeError("Only the creator's native Windows session can execute production upgrade")
    if (not args.programs.is_absolute() or not args.original_films.is_absolute()
        or not args.journal.is_absolute()):
        raise RuntimeError("Trusted original absolute program, film and journal paths required")
    key=b""
    if args.pinned_reviewer_public_key is not None:
        path=args.pinned_reviewer_public_key
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=32:
            raise PermissionError("Owner-pinned external reviewer Ed25519 public key must be 32 bytes")
        key=path.read_bytes()
    real_approve=WindowsCreatorUpgradeApproval()
    kernel=WindowsReleaseWorkerStopEvidence(
        args.programs/"NVP",worker_workspaces=_domains(args.workspace))
    owner=OwnedNSISRecovery(
        args.programs,args.original_films,args.journal,
        native_approve=real_approve,os_workers_stopped=kernel)
    update=NativeNSISActivation(
        owner,native_authorize=real_approve,
        os_worker_tree_evidence=kernel,pinned_reviewer_public_key=key)
    if args.action=="prepare":
        if args.reviewed_receipt is None:
            raise PermissionError("Externally reviewed exact native package receipt is required")
        receipt=json.loads(args.reviewed_receipt.read_text("utf8"))
        result=update.prepare(receipt)
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
