"""WO5 installed finished-DCP codec bundle staging. No runtime download.

The BUILD host stages its already-built, source-reviewed binaries and
complete upstream license texts into an immutable installer payload.
The manifest digest is inserted into compiled NVP host code BEFORE freezing.
It MUST NOT be derived from a user project, browser, or runtime folder.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import stat

from backend.nvp_wo3_codec_bundle_provenance import (
    FORMAT, REQUIRED, verify_native_codec_bundle)

SHA=re.compile(r"[0-9a-f]{64}\Z")
EXES={
    "openjpeg-encoder":"opj_compress.exe",
    "openjpeg-decoder":"opj_decompress.exe",
    "asdcp-wrap":"asdcp-wrap.exe",
    "asdcp-info":"asdcp-info.exe",
    "asdcp-unwrap":"asdcp-unwrap.exe",
}
ALLOWED_DLL=re.compile(r"[a-zA-Z0-9_-]{1,80}\.dll\Z")

def hash_file(path):
    h=sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def canonical(manifest):
    return json.dumps(manifest,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True).encode("ascii")

def require_source(path):
    f=Path(path)
    if not f.is_absolute() or f.is_symlink() or not f.is_file():
        raise PermissionError("Build input must be a local reviewed regular file")
    return f.resolve(strict=True)

def stage_bundle(destination,source,openjpeg_license,asdcp_license,
                 dlls=()):
    """Source is mapping role-> reviewed exact Windows binary path."""
    target=Path(destination)
    if (not target.is_absolute() or target.exists() or target.is_symlink() or
            type(source) is not dict or set(source)!=set(REQUIRED)):
        raise PermissionError("Fresh trusted codec build stage and all five tools required")
    openjpeg_license=require_source(openjpeg_license)
    asdcp_license=require_source(asdcp_license)
    licenses={
        "OpenJPEG":(openjpeg_license,"openjpeg.BSD-2-Clause.LICENSE"),
        "asdcplib":(asdcp_license,"asdcplib.BSD-3-Clause.LICENSE"),
    }
    for item in source.values():require_source(item)
    # Only statically linked reviewed codec tools are eligible for WO5
    # alpha. A DLL carried outside the signed/hash-scoped manifest can
    # override a reviewed executable through Windows DLL search.
    # Proper transitive DLL approval belongs to a later explicit manifest.
    if type(dlls) not in (list,tuple) or dlls:
        raise PermissionError("WO5 release requires fully static pinned codecs; no extra DLLs")
    loaded_dll=[]
    for item in dlls:
        f=require_source(item)
        if not ALLOWED_DLL.fullmatch(f.name):
            raise PermissionError("Untrusted native codec dependency name")
        loaded_dll.append(f)
    if len({f.name.casefold() for f in loaded_dll})!=len(loaded_dll):
        raise PermissionError("Codec dependency DLL collision")
    target.mkdir(mode=0o700,parents=True)
    tools={}
    for role,(product,license_id) in REQUIRED.items():
        binary=require_source(source[role])
        if binary.name.lower()!=EXES[role].lower():
            raise PermissionError("Unexpected source-reviewed codec executable")
        license_file,notice_name=licenses[product]
        notice=target/notice_name
        if not notice.exists():
            shutil.copyfile(license_file,notice)
        destination_binary=target/EXES[role]
        shutil.copyfile(binary,destination_binary)
        tools[role]={
            "product":product,"license":license_id,
            "filename":destination_binary.name,
            "sha256":hash_file(destination_binary),
            "license_notice":notice_name,
            "license_sha256":hash_file(notice),
        }
    for dll in loaded_dll:
        if (target/dll.name).exists():
            raise PermissionError("Codec dependency shadows staged executable")
        shutil.copyfile(dll,target/dll.name)
    manifest={"format":FORMAT,"tools":tools}
    report=verify_native_codec_bundle(target,manifest)
    if len(report["tools"])!=len(REQUIRED):
        raise RuntimeError("Incomplete license-reviewed native codec stage")
    manifest_file=target/"nvp-codec-manifest.json"
    manifest_file.write_bytes(canonical(manifest))
    digest=sha256(manifest_file.read_bytes()).hexdigest()
    return {"manifest_sha256":digest,"codec_manifest":str(manifest_file),
            "tool_count":len(tools),"reviewed_dependency_dlls":{
                f.name:hash_file(target/f.name) for f in loaded_dll},
            "bundle_status":report["status"],
            "independent_source_signature_verified":False,
            "projector_playback_verified":False}

def write_compiled_pin(path,manifest_digest):
    if not SHA.fullmatch(manifest_digest):
        raise PermissionError("Approved manifest digest absent")
    target=Path(path)
    if not target.is_absolute() or target.is_symlink() or not target.parent.is_dir():
        raise PermissionError("Pin must be written inside trusted build tree")
    body=(
        '"""GENERATED AT NVP CODEC BUILD; never accept runtime manifest as authority."""\n'
        'RELEASE_CODEC_MANIFEST_SHA256='+repr(manifest_digest)+'\n')
    target.write_text(body,encoding="ascii")
    return body

def verify_bundle(root,pin):
    root=Path(root)
    if (not root.is_absolute() or root.is_symlink() or
            not root.is_dir() or not SHA.fullmatch(pin)):
        raise PermissionError("Exact approved offline codec payload required")
    file=root/"nvp-codec-manifest.json"
    if file.is_symlink() or not file.is_file() or file.stat().st_size>128*1024:
        raise PermissionError("Installed manifest missing")
    raw=file.read_bytes()
    manifest=json.loads(raw)
    if raw!=canonical(manifest) or sha256(raw).hexdigest()!=pin:
        raise PermissionError("Installed codec manifest is not build-pinned")
    verified=verify_native_codec_bundle(root,manifest)
    return {
        "status":"RELEASE_CODEC_BUNDLE_PIN_AND_LICENSE_VERIFIED",
        "manifest_sha256":pin,
        "tools":list(verified["tools"]),
        "installed_windows_webview2_playback_verified":False,
        "sustained_24fps_film_verified":False,
    }

def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="cmd",required=True)
    stage=sub.add_parser("stage")
    stage.add_argument("--destination",required=True,type=Path)
    stage.add_argument("--openjpeg-license",required=True,type=Path)
    stage.add_argument("--asdcp-license",required=True,type=Path)
    for role in EXES:stage.add_argument("--"+role,required=True,type=Path)
    stage.add_argument("--dll",action="append",default=[],type=Path)
    stage.add_argument("--pin-module",required=True,type=Path)
    audit=sub.add_parser("verify")
    audit.add_argument("--bundle",required=True,type=Path)
    audit.add_argument("--pin",required=True)
    args=ap.parse_args()
    if args.cmd=="stage":
        report=stage_bundle(args.destination,
            {role:getattr(args,role.replace("-","_")) for role in EXES},
            args.openjpeg_license,args.asdcp_license,args.dll)
        write_compiled_pin(args.pin_module,report["manifest_sha256"])
    else:report=verify_bundle(args.bundle,args.pin)
    print(json.dumps(report,sort_keys=True,indent=2),flush=True)

if __name__=="__main__":main()
