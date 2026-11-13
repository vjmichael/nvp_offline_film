"""W1-G read-only/disposable physical Windows EFS acceptance fixture.

Runs with an OS-authenticated interactive Windows user. Does not inspect,
export, upload, create or claim to back up EFS private keys. Uses nonsecret
nonce data; owner must separately verify the EFS recovery-certificate backup.
An UNSUPPORTED EFS volume is a refused protected source, not a test pass.
"""
from __future__ import annotations

import argparse
import ctypes
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import time

from backend.nvp_w1g_encrypted_source import require_efs_stage,verify_efs_inputs

FORMAT="nvp.w1g.original_source_disposable_efs_acceptance.v1"


def _windows_boot_estimate_epoch() -> int:
    """Conservative observed boot-time estimate; not a key-recovery receipt.

    The native monotonic GetTickCount64 clock resets on boot. Comparing the
    epoch estimate between two separate processes denies same-boot reenactment,
    but an OS wall-clock adjustment could still make this observation wrong.
    Human/independent EFS recovery acceptance is always required separately.
    """
    if os.name!="nt":
        raise RuntimeError("Only native Windows can provide EFS boot observation")
    fn=ctypes.windll.kernel32.GetTickCount64
    fn.restype=ctypes.c_ulonglong
    uptime_ms=fn()
    if type(uptime_ms) is not int or uptime_ms<0:
        raise RuntimeError("Windows uptime could not be measured")
    return int(time.time()-uptime_ms/1000)


def _require_new_boot(saved: dict, observed_boot_epoch: int):
    previous=saved.get("windows_boot_estimate_epoch")
    if (type(previous) is not int or previous<=0 or
        type(observed_boot_epoch) is not int or observed_boot_epoch<=0):
        raise PermissionError("EFS test lacks an original Windows boot observation")
    # A short difference can be sampling, rounding or clock drift. Refuse it
    # instead of claiming that a second Python process proves restart.
    if abs(observed_boot_epoch-previous)<=60:
        raise PermissionError("EFS stage has not demonstrated a distinct Windows boot")
    return True



def _windows_process_token_sid() -> str:
    """Observe the real OS process token, never an environment username."""
    if os.name!="nt":
        raise RuntimeError("Windows token SID requires native Windows")
    import win32api
    import win32con
    import win32security
    token=win32security.OpenProcessToken(
        win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
    sid,_=win32security.GetTokenInformation(token,win32security.TokenUser)
    return win32security.ConvertSidToStringSid(sid)


def _require_efs_recovery_principal(saved: dict, current_sid: str, *,
                                    cross_principal: bool):
    """Different security principals are a prerequisite, not key-backup proof."""
    recorded=saved.get("original_windows_token_sid")
    if (type(recorded) is not str or not recorded.startswith("S-1-") or
        type(current_sid) is not str or not current_sid.startswith("S-1-")):
        raise PermissionError("Original/current Windows token identity missing")
    if cross_principal and current_sid==recorded:
        raise PermissionError(
            "EFS recovery must be demonstrated by a different Windows token")
    if not cross_principal and current_sid!=recorded:
        raise PermissionError(
            "Same-user EFS reopen must be verified by the original Windows token")
    return True


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
            "windows_boot_estimate_epoch":_windows_boot_estimate_epoch(),
            "original_windows_token_sid":_windows_process_token_sid(),
            "physical_efs_key_recovery_verified":False,
            "creator_authorization_verified":False,
        }
    except BaseException:
        # Only disposable NONSECRET test data is touched here.
        shutil.rmtree(stage,ignore_errors=True)
        raise


def reopen_disposable_efs(saved: dict, *, cross_principal=False,
                          retain_for_recovery=False) -> dict:
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
    _require_new_boot(saved,_windows_boot_estimate_epoch())
    _require_efs_recovery_principal(
        saved,_windows_process_token_sid(),cross_principal=cross_principal)
    verify_efs_inputs(stage,(saved["file"],))
    if sha256((stage/saved["file"]).read_bytes()).hexdigest()!=saved["sha256"]:
        raise RuntimeError("Native EFS re-opened encrypted bytes differ from original")
    if cross_principal and retain_for_recovery:
        raise ValueError("Recovery verification must remove its disposable source")
    if not retain_for_recovery:
        (stage/saved["file"]).unlink()
        stage.rmdir()
    return {
        "format":FORMAT,
        "status":("NATIVE_WINDOWS_EFS_DIFFERENT_PRINCIPAL_DECRYPTED"
                  if cross_principal else
                  "NATIVE_WINDOWS_EFS_POST_REBOOT_REOPEN_VERIFIED"),
        "encrypted_original_input_at_rest_verified":True,
        "distinct_windows_boot_observed":True,
        "windows_boot_epoch_method":"GetTickCount64-wall-clock-estimate",
        "different_windows_token_observed":bool(cross_principal),
        "cross_principal_nonsecret_efs_decryption_verified":bool(cross_principal),
        "key_backup_origin_independently_proven":False,
        "original_film_data_used":False,
        "disposable_stage_removed":not retain_for_recovery,
        "owner_physical_session_proven":False,
        "efs_recovery_key_backup_verified":False,
        "production_encrypted_film_release_accepted":False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("prepare","reopen","recover"))
    parser.add_argument("--parent",type=Path)
    parser.add_argument("--receipt",type=Path,required=True)
    parser.add_argument("--retain-for-recovery",action="store_true",
                        help="Only with reopen: preserve disposable nonce for cross-principal decryption")
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
        if args.retain_for_recovery and args.action!="reopen":
            parser.error("Only same-user reopen may retain the disposable EFS nonce")
        result=reopen_disposable_efs(
            saved,cross_principal=args.action=="recover",
            retain_for_recovery=args.retain_for_recovery)
        print(json.dumps(result,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
