"""WO4 native codec distribution bill of materials, hashes and notices.

No guessed licenses or downloaded executables. A packaging host provides
actual SHA-256-pinned binary, version and full upstream license/notice files
for every declared runtime and transitive component. This tool verifies the
on-disk evidence and writes an immutable BOM, but cannot certify that a
manually declared dependency list is complete; platform binary dependency
scanning and legal review are separate mandatory release gates.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path,PurePosixPath
import re

FORMAT="nvp.wo4.native_codec_distribution_bom.v1"
HEX=re.compile(r"[0-9a-f]{64}\Z")
NAME=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,95}\Z")
VERSION=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,65}\Z")
MAX_TEXT=2*1024*1024
MAX_BINS=128

def _inside(root,path):
    if type(path) is not str or not path or "\\" in path or ":" in path:
        raise PermissionError("Bundled component path must be relative POSIX")
    item=PurePosixPath(path)
    if item.is_absolute() or any(v in ("","..",".") for v in item.parts):
        raise PermissionError("Bundle path traversal refused")
    file=root.joinpath(*item.parts)
    if file.is_symlink() or not file.is_file():
        raise PermissionError("Exact bundled artifact missing or symlinked")
    resolved=file.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise PermissionError("Bundled artifact escaped trusted root")
    return resolved

def _sha(file):
    h=sha256()
    size=0
    with file.open("rb") as stream:
        while chunk:=stream.read(1024*1024):
            h.update(chunk)
            size+=len(chunk)
    return h.hexdigest(),size

def audit_native_bundle(bundle_root,components):
    root=Path(bundle_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise PermissionError("Trusted staged native runtime directory required")
    root=root.resolve(strict=True)
    if type(components) is not list or not 1<=len(components)<=MAX_BINS:
        raise ValueError("Bounded native component inventory required")
    names=set()
    recorded=[]
    for component in components:
        if type(component) is not dict or set(component)!={
                "name","version","binary_path","binary_sha256",
                "license_path","license_sha256","notice_path",
                "notice_sha256","requires"}:
            raise ValueError("Each runtime component must have exact binary/license/notice evidence")
        name=component["name"]
        version=component["version"]
        if (type(name) is not str or not NAME.fullmatch(name) or
                type(version) is not str or not VERSION.fullmatch(version) or
                name in names or type(component["requires"]) is not list or
                any(type(d) is not str or not NAME.fullmatch(d)
                    for d in component["requires"])):
            raise ValueError("Duplicate/invalid pinned native component")
        names.add(name)
        record={"name":name,"version":version,
                "requires":list(component["requires"])}
        for kind in ("binary","license","notice"):
            filename=component[kind+"_path"]
            digest=component[kind+"_sha256"]
            if type(digest) is not str or not HEX.fullmatch(digest):
                raise ValueError("Exact SHA-256 for native artifact required")
            file=_inside(root,filename)
            actual,size=_sha(file)
            if actual!=digest or size==0:
                raise PermissionError("Bundled "+kind+" file differs from pinned hash")
            if kind!="binary":
                if size>MAX_TEXT:
                    raise ValueError("Oversized native legal text")
                try:text=file.read_text("utf-8")
                except UnicodeError as exc:
                    raise ValueError("Native legal notice must be readable UTF-8") from exc
                if len(text.strip())<10:
                    raise ValueError("Incomplete native license/notice text")
            record[kind+"_path"]=filename
            record[kind+"_sha256"]=digest
            record[kind+"_bytes"]=size
        recorded.append(record)
    for record in recorded:
        if (record["name"] in record["requires"] or
                len(set(record["requires"]))!=len(record["requires"]) or
                not set(record["requires"]).issubset(names)):
            raise PermissionError("Uninventoried transitive native dependency")
    result={"format":FORMAT,"status":"EVIDENCE_HASHES_VERIFIED",
            "components":sorted(recorded,key=lambda x:x["name"]),
            "component_count":len(recorded),
            "native_binary_dependency_scan_passed":False,
            "upstream_license_legal_review_passed":False,
            "installed_app_acceptance":False,
            "source_modified":False}
    payload=json.dumps(result,sort_keys=True,separators=(",",":")).encode()
    result["manifest_sha256"]=sha256(payload).hexdigest()
    return result

def publish_native_bom(bundle_root,components):
    result=audit_native_bundle(bundle_root,components)
    root=Path(bundle_root).resolve(strict=True)
    dest=root/"NVP_NATIVE_COMPONENTS.json"
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("Existing native dependency BOM may not be overwritten")
    payload=(json.dumps(result,sort_keys=True,indent=2)+"\n").encode("utf-8")
    with dest.open("xb") as out:
        out.write(payload)
        out.flush();os.fsync(out.fileno())
    return {"status":"BOM_WRITTEN_NO_REPLACE",
            "destination":str(dest),
            "manifest_sha256":result["manifest_sha256"],
            "legal_approval":False}
