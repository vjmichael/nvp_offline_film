"""WO3 crash/restart read-only reconciliation for creator-approved DCP exports.

Never deletes, rewrites or silently promotes staged work. The caller must
supply trusted FilmIndex presentation receipts; filenames alone are NOT proof
of a committed export. This scan is evidence for native recovery UI, not an
automatic transaction or release acceptance.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from backend.nvp_wo3_dcp_structure import inspect_dcp_structure

FORMAT = "nvp.wo3.export_reconciliation.v1"
DCP_NAME = re.compile(r"DCP_([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\Z")
STAGE_NAME = re.compile(r"\.nvp-wo3-[A-Za-z0-9_-]{1,80}\Z")
MAX_CANDIDATES = 1000


def _sha(file):
    digest = hashlib.sha256()
    with file.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reconcile_dcp_exports(output_root, committed_receipts=()):
    """Return evidence only. Never cleanup or create directories.

    committed_receipts: trusted FilmIndex-derived dictionaries with
    destination_name and file_sha256. In particular, browser-provided
    receipts are not authoritative; the host must fetch the FilmIndex entries.
    """
    root = Path(output_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise PermissionError("Trusted existing absolute export directory required")
    root = root.resolve(strict=True)
    if type(committed_receipts) not in (list, tuple):
        raise TypeError("Trusted committed receipts must be a sequence")
    receipt_by_name = {}
    for record in committed_receipts:
        if type(record) is not dict:
            raise TypeError("Committed receipt must be FilmIndex data")
        name = record.get("destination_name")
        hashes = record.get("file_sha256")
        if (type(name) is not str or not DCP_NAME.fullmatch(name) or
                type(hashes) is not dict or not hashes or
                any(type(k) is not str or type(v) is not str or
                    not re.fullmatch(r"[0-9a-f]{64}", v)
                    for k, v in hashes.items()) or name in receipt_by_name):
            raise ValueError("Malformed or duplicate trusted DCP receipt")
        receipt_by_name[name] = hashes
    children = sorted(root.iterdir(), key=lambda p: p.name)
    candidates = [p for p in children if DCP_NAME.fullmatch(p.name) or
                  STAGE_NAME.fullmatch(p.name)]
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError("Too many candidate exports; manual inspection required")
    items = []
    seen = set()
    for path in candidates:
        is_stage = bool(STAGE_NAME.fullmatch(path.name))
        item = {"name": path.name, "stage": is_stage, "status": None,
                "production_dcp_accepted": False, "may_auto_delete": False}
        seen.add(path.name)
        if path.is_symlink() or not path.is_dir():
            item["status"] = "UNSAFE_OR_INCOMPLETE"
            items.append(item)
            continue
        try:
            verified = inspect_dcp_structure(path)
            if verified["status"] != "STRUCTURE_AND_SHA_VERIFIED":
                raise ValueError("Independent DCP package check did not pass")
            assets = verified["assets"]
            actual = {entry["filename"]: entry["sha256"]
                      for entry in assets.values()}
            # PKL, AssetMap and volume metadata must also be bound to the
            # durable original presentation receipt, not only the CPL/MXF.
            for metadata in ("PKL.xml", "ASSETMAP.xml", "VOLINDEX.xml"):
                file = path / metadata
                if file.is_symlink() or not file.is_file():
                    raise ValueError("Incomplete SMPTE metadata")
                actual[metadata] = _sha(file)
            item["verified_file_sha256"] = actual
            expected = receipt_by_name.get(path.name)
            if is_stage:
                item["status"] = "STAGED_UNCOMMITTED_REVIEW_REQUIRED"
            elif expected is None:
                item["status"] = "PUBLISHED_WITHOUT_LEDGER_REVIEW_REQUIRED"
            elif actual != expected:
                item["status"] = "LEDGER_HASH_MISMATCH"
            else:
                item["status"] = "PUBLISHED_LEDGER_AND_STRUCTURE_VERIFIED"
        except (OSError, ValueError, RuntimeError, PermissionError) as error:
            item["status"] = "UNSAFE_OR_INCOMPLETE"
            item["reason"] = type(error).__name__
        items.append(item)
    for name in sorted(set(receipt_by_name) - seen):
        items.append({"name": name, "stage": False,
                      "status": "LEDGER_EXPORT_MISSING",
                      "production_dcp_accepted": False,
                      "may_auto_delete": False})
    return {"format": FORMAT, "status": "READ_ONLY_RECONCILIATION",
            "exports": items, "filesystem_mutated": False,
            "source_modified": False, "production_dcp_accepted": False}
