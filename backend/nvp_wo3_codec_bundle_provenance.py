"""WO3 runtime bundle provenance gate; does not download codecs.

Installer builder must supply a trusted manifest whose exact SHA-256 binary
digests and included full license notices are verified on the installed
bundle before cinema tools are admitted. Manifest authoring is a release
operation, never an LLM/browser request. Does not claim signed provenance.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
from backend.nvp_wo3_dcp_structure import _linked_entry, _safe_leaf

FORMAT = "nvp.wo3.native_codec_bundle_provenance.v1"
REQUIRED = {
    "openjpeg-encoder": ("OpenJPEG", "BSD-2-Clause"),
    "openjpeg-decoder": ("OpenJPEG", "BSD-2-Clause"),
    "asdcp-wrap": ("asdcplib", "BSD-3-Clause"),
    "asdcp-info": ("asdcplib", "BSD-3-Clause"),
    "asdcp-unwrap": ("asdcplib", "BSD-3-Clause"),
}
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _hash(file):
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for packet in iter(lambda: stream.read(1024*1024), b""):
            digest.update(packet)
    return digest.hexdigest()


def verify_native_codec_bundle(folder, manifest):
    """Fail closed on missing/corrupted binaries, license notices or components.

    manifest is assumed loaded by the trusted release host from a signed/
    vetted build artifact; this function does not establish its authenticity.
    """
    root = Path(folder)
    if not root.is_absolute() or _linked_entry(root) or not root.is_dir():
        raise PermissionError("Trusted installed binary bundle directory required")
    root = root.resolve(strict=True)
    if type(manifest) is not dict or manifest.get("format") != FORMAT:
        raise PermissionError("Native codec release manifest format missing")
    tools = manifest.get("tools")
    if type(tools) is not dict or set(tools) != set(REQUIRED):
        raise PermissionError("All reviewed native codec binaries required")
    records = {}
    binary_names=set()
    notice_names=set()
    for role, (product, license_id) in REQUIRED.items():
        item = tools[role]
        if (type(item) is not dict or item.get("product") != product or
                item.get("license") != license_id or
                type(item.get("filename")) is not str or
                not SAFE_NAME.fullmatch(item["filename"]) or
                type(item.get("sha256")) is not str or
                not SHA.fullmatch(item["sha256"]) or
                type(item.get("license_notice")) is not str or
                not SAFE_NAME.fullmatch(item["license_notice"]) or
                type(item.get("license_sha256")) is not str or
                not SHA.fullmatch(item["license_sha256"])):
            raise PermissionError("Malformed native codec release provenance")
        filename=item["filename"]
        notice_name=item["license_notice"]
        if (not _safe_leaf(filename) or not _safe_leaf(notice_name)
                or filename.casefold() in binary_names
                or filename.casefold() in notice_names
                or notice_name.casefold() in binary_names
                or filename.casefold()==notice_name.casefold()):
            raise PermissionError("Aliased or unsafe installed codec names")
        binary_names.add(filename.casefold())
        notice_names.add(notice_name.casefold())
        binary = root / filename
        notice = root / notice_name
        if (_linked_entry(binary) or _linked_entry(notice) or
                not binary.is_file() or not notice.is_file() or
                not 256 <= binary.stat().st_size <= 256*1024*1024 or
                not 200 <= notice.stat().st_size <= 128*1024):
            raise PermissionError("Missing or invalid installed executable/license")
        if (_hash(binary) != item["sha256"] or
                _hash(notice) != item["license_sha256"]):
            raise PermissionError("Installed native codec or legal notice changed")
        records[role] = {"filename": item["filename"],
                         "binary_sha256": item["sha256"],
                         "license": license_id,
                         "license_sha256": item["license_sha256"]}
    # Fully independent signing and dependent DLL audits remain release gates.
    return {"format": FORMAT, "status": "BUNDLE_CONTENTS_AND_NOTICES_HASH_VERIFIED",
            "tools": records, "signed_release_provenance_verified": False,
            "transitive_dependencies_verified": False,
            "installed_windows_linux_acceptance": False,
            "production_dcp_accepted": False}
