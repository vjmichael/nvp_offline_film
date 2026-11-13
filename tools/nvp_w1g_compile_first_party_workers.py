"""Compile five distinct native, role-specific W1-G executables from source.

These are REAL PE32+/ELF64 executables, not Python scripts or padded fake
headers. The operations implemented are bounded film capability *slices*:
PCM intake validation, math-picture rendering, non-destructive PCM cut,
PCM gain and finite media bundle. They are NOT full filmmaking-role acceptance,
independent license approval, EFS custody, or permission for NSIS deployment.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from tools.nvp_w1g_worker_package import (
    FORMAT, ROLES, _check_roster, _verify_binary,
)

SOURCE_ROOT=Path(__file__).resolve().parents[1]
SOURCE=SOURCE_ROOT/"native"/"w1g_first_party_worker.cpp"


def digest_file(path):
    h=sha256()
    with path.open("rb") as reader:
        for part in iter(lambda:reader.read(1048576),b""):
            h.update(part)
    return h.hexdigest()


def _compile_one(role, output, *, platform, compiler):
    source=SOURCE_ROOT/"native"/f"{role}.cpp"
    if not source.is_file() or source.is_symlink() or not SOURCE.is_file():
        raise RuntimeError("Original audited first-party worker source unavailable")
    exe=output/(role+(".exe" if platform=="windows-amd64" else ""))
    if exe.exists() or exe.is_symlink():
        raise FileExistsError("Refusing to overwrite a previously compiled native executable")
    if platform=="windows-amd64":
        if os.name!="nt" or not shutil.which(compiler):
            raise RuntimeError("Genuine Windows x64 MSVC developer environment required")
        command=[compiler,"/nologo","/std:c++17","/EHsc","/O2","/Zi",
                 "/MD",f"/Fe:{exe}",str(source),"/link","bcrypt.lib","/DEBUG"]
    elif platform=="linux-amd64":
        if not sys.platform.startswith("linux") or not shutil.which(compiler):
            raise RuntimeError("Genuine Linux x64 GNU C++ compiler required")
        command=[compiler,"-std=c++17","-O2","-g","-Wall","-Wextra",
                 str(source),"-lcrypto","-o",str(exe)]
    else:
        raise RuntimeError("Unknown exact native compiler platform")
    result=subprocess.run(command,cwd=SOURCE_ROOT,stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          timeout=240,check=False)
    if result.returncode:
        print(result.stdout.decode("utf8",errors="replace")[-16000:])
        raise RuntimeError(f"Real original {role} native compiler failed ({result.returncode})")
    _verify_binary(exe,platform)
    return {"role":role,"filename":exe.name,"sha256":digest_file(exe)}


def compile_native_workers(output:Path, *, platform:str, compiler:str) -> dict:
    output=Path(output)
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise RuntimeError("Fresh native build output and valid parent required")
    if (platform=="windows-amd64")!=(os.name=="nt"):
        raise RuntimeError("Cross-platform claimed native artifact rejected")
    output.mkdir()
    workers=[]
    for role in sorted(ROLES):
        workers.append(_compile_one(role,output,platform=platform,compiler=compiler))
    roster={"format":FORMAT,"platform":platform,"workers":workers}
    _check_roster(roster)
    result={
        "status":"FIVE_REAL_NATIVE_EXECUTABLES_COMPILED_CANDIDATE",
        "roster":roster,
        "source_sha256":digest_file(SOURCE),
        "compiler":compiler,
        "role_count":len(workers),
        "native_executables_compiled":True,
        "native_executables_functionally_verified":False,
        "production_native_roles_complete":False,
        "offline_dependencies_redistribution_approved":False,
        "signed_release_review_verified":False,
        "physical_efs_acceptance_verified":False,
        "production_upgrade_authorized":False,
    }
    (output/"build-candidate.json").write_text(
        json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf8")
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--platform",choices=("windows-amd64","linux-amd64"),required=True)
    p.add_argument("--compiler",default=("cl" if os.name=="nt" else "g++"))
    args=p.parse_args(argv)
    result=compile_native_workers(args.out,platform=args.platform,compiler=args.compiler)
    print(json.dumps({"status":result["status"],"roles":sorted(ROLES),
                      "source_sha256":result["source_sha256"]},sort_keys=True))


if __name__=="__main__":
    main()
