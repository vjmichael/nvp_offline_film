"""W1-G read-only/disposable physical Windows EFS acceptance fixture.

Runs with an OS-authenticated interactive Windows user. Does not inspect,
export, upload, create or claim to back up EFS private keys. Uses nonsecret
nonce data; owner must separately verify the EFS recovery-certificate backup.
An UNSUPPORTED EFS volume is a refused protected source, not a test pass.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile

from backend.nvp_w1g_encrypted_source import require_efs_stage,verify_efs_inputs

FORMAT="nvp.w1g.original_source_disposable_efs_acceptance.v1"


def prepare_disposable_efs(parent: Path) -> dict:
    if os.name!="nt":
        raise RuntimeError("Native physical encrypted-source acceptance requires Windows")
    parent=Path(parent)
    if not parent.is_dir() or parent.is_symlink():
        raise PermissionError("Owner-selected EFS volume root unavailable")
    stage=Path(tempfile.mkdtemp(prefix="nvp-w1g-efs-test-",dir=parent))
    try:
        require_efs_stage(stage)
        name="original-source-test.usda"
        data=b"NVP-NONSECRET-EFS-STAGING-TEST:"+secrets.token_bytes(48)
        with (stage/name).open("xb") as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        verify_efs_inputs(stage,(name,))
        return {
            "format":FORMAT,
            "status":"EFS_ENCRYPTED_INPUT_WRITTEN_AWAITING_RESTART_REOPEN",
            "stage":str(stage),
            "parent":str(parent.absolute()),
            "file":name,
            "sha256":sha256(data).hexdigest(),
            "original_film_data_used":False,
            "physical_efs_key_recovery_verified":False,
            "creator_authorization_verified":False,
        }
    except BaseException:
        # Only disposable NONSECRET test data is touched here.
        shutil.rmtree(stage,ignore_errors=True)
        raise


def reopen_disposable_efs(saved: dict) -> dict:
    if os.name!="nt":
        raise RuntimeError("Native Windows EFS restart/reopen required")
    if (type(saved) is not dict or saved.get("format")!=FORMAT or
        saved.get("status")!="EFS_ENCRYPTED_INPUT_WRITTEN_AWAITING_RESTART_REOPEN" or
        saved.get("file")!="original-source-test.usda" or
        type(saved.get("sha256")) is not str or len(saved["sha256"])!=64):
        raise PermissionError("Trusted original EFS test baseline missing")
    if type(saved.get("stage")) is not str or type(saved.get("parent")) is not str:
        raise PermissionError("Original EFS test directory identity is incomplete")
    stage=Path(saved["stage"])
    parent=Path(saved["parent"])
    if (not stage.is_absolute() or not parent.is_absolute() or
        parent.is_symlink() or not parent.is_dir() or
        stage.parent != parent or
        not stage.name.startswith("nvp-w1g-efs-test-") or
        len(stage.name)<len("nvp-w1g-efs-test-")+6 or
        stage.is_symlink() or not stage.is_dir()):
        raise RuntimeError("EFS original stage unavailable or not a disposable test after restart")
    verify_efs_inputs(stage,(saved["file"],))
    if sha256((stage/saved["file"]).read_bytes()).hexdigest()!=saved["sha256"]:
        raise RuntimeError("Native EFS re-opened encrypted bytes differ from original")
    (stage/saved["file"]).unlink()
    stage.rmdir()
    return {
        "format":FORMAT,
        "status":"NATIVE_WINDOWS_EFS_SAME_USER_REOPEN_VERIFIED",
        "encrypted_original_input_at_rest_verified":True,
        "original_film_data_used":False,
        "disposable_stage_removed":True,
        "owner_physical_session_proven":False,
        "efs_recovery_key_backup_verified":False,
        "production_encrypted_film_release_accepted":False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("prepare","reopen"))
    parser.add_argument("--parent",type=Path)
    parser.add_argument("--receipt",type=Path,required=True)
    args=parser.parse_args(argv)
    if args.action=="prepare":
        if args.parent is None or args.receipt.exists() or args.receipt.is_symlink():
            parser.error("Fresh --parent and unused --receipt required")
        receipt=prepare_disposable_efs(args.parent)
        args.receipt.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n",encoding="utf8")
        print(json.dumps({"status":receipt["status"],"receipt":str(args.receipt)}))
    else:
        if args.receipt.is_symlink() or not args.receipt.is_file():
            raise RuntimeError("Original owner EFS stage receipt missing")
        saved=json.loads(args.receipt.read_text("utf8"))
        result=reopen_disposable_efs(saved)
        print(json.dumps(result,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
