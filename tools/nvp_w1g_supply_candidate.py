"""W1-G supply-chain review CANDIDATE creation — never approves licenses.

Consumes only already-downloaded, local wheel bytes and an audited original
installed build receipt. Emits exact SHA/value inventories and placeholder
review fields for a human reviewer, without network access, key generation,
an executable worker replacement, or a forged license grant.

Release admission deliberately refuses REVIEW_REQUIRED entries.
"""
from __future__ import annotations

import argparse
from email.parser import Parser
import json
from pathlib import Path
import zipfile

from tools.nvp_w1g_native_dependencies import (
    FORMAT as WHEEL_FORMAT, _sha,
)
from tools.nvp_w1g_reviewed_release import (
    FORMAT as REVIEW_FORMAT, license_review_digest,
)
from tools.nvp_w1g_worker_package import (
    FORMAT as WORKER_FORMAT, ROLES, _check_roster, _verify_binary,
)

UNKNOWN="REVIEW_REQUIRED"


def candidate_wheel_lock(wheelhouse: Path, *, platform: str) -> dict:
    wheelhouse=Path(wheelhouse)
    if not wheelhouse.is_dir() or wheelhouse.is_symlink():
        raise RuntimeError("Audited local wheelhouse is required")
    found=[]
    seen=set()
    for path in sorted(wheelhouse.glob("*.whl")):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Native wheelhouse contains linked dependency")
        with zipfile.ZipFile(path) as z:
            matches=[m for m in z.infolist()
                     if m.filename.endswith(".dist-info/METADATA")]
            if len(matches)!=1 or matches[0].file_size>1048576:
                raise RuntimeError("Actual wheel has missing/unbounded provenance METADATA")
            info=Parser().parsestr(z.read(matches[0]).decode("utf8"))
        name, version=info.get("Name"),info.get("Version")
        if not name or not version or name.casefold() in seen:
            raise RuntimeError("Ambiguous actual local wheel Name/Version")
        seen.add(name.casefold())
        found.append({
            "name":name,"version":version,"filename":path.name,
            "sha256":_sha(path),"license_review":UNKNOWN,
        })
    if not found:
        raise RuntimeError("No actual native wheels to inventory")
    return {"format":WHEEL_FORMAT,"platform":platform,"wheels":found,
            "candidate_only":True,"redistribution_approved":False}


def candidate_native_worker_roster(binary_root: Path, filenames_by_role: dict,
                                   *, platform: str) -> dict:
    """Inventory five supplied native-image candidates; never mint a review or license.

    The input is an explicit owner-supplied role -> filename mapping, not a
    discoverable or guessed assignment of one binary to five worker roles.
    PE/ELF header checks and hashes are NOT independent functional execution
    or a signature, license approval, provenance, or physical acceptance.
    """
    binary_root=Path(binary_root)
    if (not binary_root.is_dir() or binary_root.is_symlink() or
        type(filenames_by_role) is not dict or
        set(filenames_by_role)!=set(ROLES)):
        raise RuntimeError("All five original compiled worker roles and actual binary directory required")
    workers=[]
    for role,name in sorted(filenames_by_role.items()):
        if type(name) is not str or name!=Path(name).name or (
                "/" in name or "\\" in name):
            raise RuntimeError("Untrusted original native worker filename")
        binary=binary_root/name
        _verify_binary(binary,platform)
        workers.append({"role":role,"filename":name,"sha256":_sha(binary)})
    roster={"format":WORKER_FORMAT,"platform":platform,"workers":workers}
    _check_roster(roster)
    return {"status":"UNSIGNED_NATIVE_EXECUTABLE_ROSTER_CANDIDATE",
            "roster":roster,
            "executable_bytes_examined":True,
            "native_executables_executed":False,
            "creator_review_completed":False,
            "redistribution_approved":False}


def candidate_redistribution_review(receipt: dict) -> dict:
    files=receipt.get("files")
    if type(files) is not dict or not files:
        raise RuntimeError("Actual audited external NVP package receipt missing")
    return {
        "payload":{
            "format":REVIEW_FORMAT,
            "platform":receipt.get("platform"),
            "payload_sha256":license_review_digest(receipt),
            "reviewer_reference":UNKNOWN,
            "reviewed_artifacts":[
                {"file":name,"sha256":details["sha256"],
                 "spdx_license":UNKNOWN,
                 "redistribution_reference":UNKNOWN}
                for name, details in sorted(files.items())
            ],
        },
        "signature_base64":None,
        "status":"UNREVIEWED_CANDIDATE_NOT_PRODUCTION_ACCEPTED",
    }


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--wheelhouse",type=Path,required=True)
    ap.add_argument("--build-receipt",type=Path,required=True)
    ap.add_argument("--platform",choices=("windows-amd64","linux-amd64"),required=True)
    ap.add_argument("--worker-binaries",type=Path)
    ap.add_argument("--worker-role",action="append",default=[],
                    help="Explicit first-party role=compiled_executable, repeat for all five")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("Never overwrite original supply review evidence")
    receipt=json.loads(args.build_receipt.read_text("utf8"))
    if receipt.get("platform") != args.platform:
        raise RuntimeError("Native package platform differs from offline wheelhouse")
    candidate_workers=None
    if args.worker_binaries is not None or args.worker_role:
        if args.worker_binaries is None:
            raise RuntimeError("Compiled worker binary directory is required")
        mapping={}
        for raw in args.worker_role:
            role,sep,name=raw.partition("=")
            if not sep or role in mapping:
                raise RuntimeError("Explicit duplicate or untyped worker role")
            mapping[role]=name
        candidate_workers=candidate_native_worker_roster(
            args.worker_binaries,mapping,platform=args.platform)
    result={
        "status":"OWNER_REVIEW_REQUIRED",
        "candidate_wheel_lock":candidate_wheel_lock(args.wheelhouse,platform=args.platform),
        "unsigned_redistribution_review":candidate_redistribution_review(receipt),
        "candidate_native_worker_roster":candidate_workers,
        "native_worker_executable_roster_reviewed":False,
        "redistribution_licenses_verified":False,
        "signed_release":False,
    }
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"status":"OWNER_REVIEW_REQUIRED","output":str(args.output)}))


if __name__=="__main__":
    main()
