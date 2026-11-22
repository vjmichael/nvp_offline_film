"""W1-G actual compiled PE64/ELF64 native import inventory — candidate only.

Run dumpbin/readelf against the exact five source-built native executables.
This is NOT an independently reviewed redistribution license, a physical
owner-runtime DLL inventory or a signed native dependency approval. Python
wheel locks cannot substitute for MSVC runtime or Linux shared objects.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess

from tools.nvp_w1g_worker_package import _check_roster,_verify_binary,ROLES

FORMAT="nvp.w1g.native_linked_dependency_candidate.v1"
LIBRARY=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}$")
WINDOWS_LINE=re.compile(r"^\s+([A-Za-z0-9_.+-]+\.dll)\s*$",re.I)
LINUX_LINE=re.compile(r"\(NEEDED\).*?\[([^\]\r\n]+)\]")


def _sha(path:Path)->str:
    h=sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""):
            h.update(chunk)
    return h.hexdigest()


def parse_native_imports(output:str,platform:str)->tuple[str,...]:
    if type(output) is not str or len(output)>4*1024*1024:
        raise RuntimeError("Native linker import output absent or unbounded")
    if platform=="windows-amd64":
        found=[m.group(1) for row in output.splitlines()
               if (m:=WINDOWS_LINE.fullmatch(row))]
    elif platform=="linux-amd64":
        found=[m.group(1) for row in output.splitlines()
               if (m:=LINUX_LINE.search(row))]
    else:
        raise RuntimeError("Unsupported native linker provenance architecture")
    if (not 1<=len(found)<=128 or
        any(not LIBRARY.fullmatch(lib) or "/" in lib or "\\" in lib
            for lib in found) or
        len({x.casefold() for x in found})!=len(found)):
        raise RuntimeError("Unrecognized, missing or ambiguous native executable imports")
    return tuple(sorted(found,key=str.casefold))


def compiled_native_import_candidate(binary_dir:Path,*,platform:str,
                                     inspection_tool:str|None=None)->dict:
    root=Path(binary_dir)
    receipt=root/"build-candidate.json"
    if (not root.is_dir() or root.is_symlink() or
        not receipt.is_file() or receipt.is_symlink() or
        receipt.stat().st_size>128000):
        raise PermissionError("Exact source-built native candidate unavailable")
    row=json.loads(receipt.read_text("utf8"))
    if (row.get("status")!="FIVE_REAL_NATIVE_EXECUTABLES_COMPILED_CANDIDATE"
        or row.get("native_executables_compiled") is not True):
        raise PermissionError("Original native source compile proof missing")
    roster=_check_roster(row.get("roster"))
    if roster["platform"]!=platform or {
            r["role"] for r in roster["workers"]}!=set(ROLES):
        raise PermissionError("All five source-built native worker import identities required")
    if (platform=="windows-amd64")!=(os.name=="nt"):
        raise PermissionError("Native import inspection must run on the target architecture")
    program=inspection_tool or ("dumpbin" if os.name=="nt" else "readelf")
    imports=[]
    for worker in sorted(roster["workers"],key=lambda r:r["role"]):
        executable=root/worker["filename"]
        _verify_binary(executable,platform)
        if _sha(executable)!=worker["sha256"]:
            raise PermissionError("Native executable changed since compilation")
        command=([program,"/DEPENDENTS",str(executable)]
                 if platform=="windows-amd64" else
                 [program,"-d",str(executable)])
        result=subprocess.run(command,stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              timeout=30,check=False)
        if result.returncode!=0:
            raise RuntimeError("Original linker import inspection failed: "+worker["role"])
        libs=parse_native_imports(
            result.stdout.decode("utf8",errors="replace"),platform)
        imports.append({
            "role":worker["role"],"filename":worker["filename"],
            "executable_sha256":worker["sha256"],
            "imported_libraries":list(libs),
        })
    return {
        "format":FORMAT,"platform":platform,
        "source_sha256":row.get("source_sha256"),
        "imports":imports,
        "status":"NATIVE_LINKER_DEPENDENCY_CANDIDATE_ONLY",
        "runtime_library_bytes_pinned":False,
        "external_native_dependency_license_reviewed":False,
        "native_library_redistribution_approved":False,
        "physical_owner_library_versions_verified":False,
        "production_upgrade_authorized":False,
    }


def main(argv=None):
    ap=argparse.ArgumentParser(description="Five native worker import inventory")
    ap.add_argument("--binary-dir",type=Path,required=True)
    ap.add_argument("--platform",choices=("windows-amd64","linux-amd64"),required=True)
    ap.add_argument("--tool",type=str)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("Never overwrite original native linker evidence")
    doc=compiled_native_import_candidate(
        args.binary_dir,platform=args.platform,inspection_tool=args.tool)
    args.output.write_text(
        json.dumps(doc,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"status":doc["status"],"platform":args.platform,
                      "roles":[r["role"] for r in doc["imports"]]},sort_keys=True))


if __name__=="__main__":
    main()
