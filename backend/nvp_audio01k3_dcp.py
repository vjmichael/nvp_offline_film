"""AUDIO-01K.3: DCP-o-matic-backed SMPTE DCP generation and fail-closed QC.

Worker-side candidate only.  DCP-o-matic's real codecs and libdcp generate
JPEG 2000 XYZ picture MXF, PCM sound MXF, CPL/PKL/ASSETMAP. NVP does not
handcraft fake MXF/XML and never treats a successful encoder exit as cinema QC.
The trusted host provides authorization and OS process-tree containment.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_audio01i_mastering import sha_file

FORMAT = "nvp.audio01k3.dcp_candidate.v1"
PROFILE = "smpte_2k_24fps_unencrypted_stereo_v1"
MAX_FILES = 96
MAX_XML_BYTES = 5 * 1024 * 1024
REQUIRED_XML = ("ASSETMAP.xml", "VOLINDEX.xml")
MAX_TOTAL_BYTES = 20 * 1024 * 1024 * 1024
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,79}\Z")


def _run(args, *, cwd, timeout=1800):
    done = subprocess.run([str(arg) for arg in args], cwd=str(cwd),
                          stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, check=False)
    if done.returncode:
        raise RuntimeError("Native cinema packager failed: " +
                           done.stderr.decode("utf8", "replace")[-1200:])
    return done.stdout.decode("utf8", "replace").strip()


def _safe_name(name):
    if type(name) is not str or not NAME.fullmatch(name):
        raise ValueError("Film name must be a bounded portable identifier")
    return name


def plan_commands(movie, film_dir, title, create_bin, cli_bin):
    """Fully explicit SMPTE, unencrypted 2K 24fps stereo; no config defaults."""
    _safe_name(title)
    return (
        [str(create_bin), "--no-encrypt", "--standard", "SMPTE",
         "--twok", "--twod", "--dcp-frame-rate", "24",
         "--container-ratio", "185", "--audio-channels", "2",
         "--colourspace", "rec709", "--dcp-content-type", "FTR",
         "--no-use-isdcf-name", "-n", title, "-o", str(film_dir),
         str(movie)],
        [str(cli_bin), "--no-remote", "--dcp-path", str(film_dir)],
    )


def _parse_xml(path):
    if path.stat().st_size > MAX_XML_BYTES or path.is_symlink():
        raise RuntimeError("Unsafe DCP XML asset")
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise RuntimeError("External entities or DTD are forbidden in DCP inspection")
    return ET.fromstring(raw)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _members(root, name):
    return [node for node in root.iter() if _local(node.tag) == name]


def inspect_dcp_directory(dcp, *, require_essence=True):
    """Structural and byte custody checks only; NOT SMPTE/DCI certification.

    A second independent validator must approve any completed cinema delivery.
    """
    dcp = Path(dcp)
    if dcp.is_symlink() or not dcp.is_dir():
        raise RuntimeError("Expected an actual DCP directory")
    files = list(dcp.iterdir())
    if len(files) > MAX_FILES or not files:
        raise RuntimeError("Unbounded or missing DCP assets")
    assets = {}
    total = 0
    for path in files:
        if path.is_symlink() or not path.is_file() or path.name in (".", ".."):
            raise RuntimeError("No nested, symlinked or nonregular DCP assets")
        if path.suffix.lower() not in (".xml", ".mxf"):
            raise RuntimeError("Unexpected file in distribution DCP package")
        total += path.stat().st_size
        if total > MAX_TOTAL_BYTES:
            raise RuntimeError("DCP exceeds bounded test-candidate capacity")
        assets[path.name] = {
            "sha256": sha_file(path), "size_bytes": path.stat().st_size
        }
    for required in REQUIRED_XML:
        if required not in assets:
            raise RuntimeError("Missing SMPTE DCP index: " + required)
    cpls = [p for p in files if p.suffix.lower() == ".xml" and
            _local(_parse_xml(p).tag) == "CompositionPlaylist"]
    pkls = [p for p in files if p.suffix.lower() == ".xml" and
            _local(_parse_xml(p).tag) == "PackingList"]
    mxfs = [p for p in files if p.suffix.lower() == ".mxf"]
    if len(cpls) != 1 or len(pkls) != 1 or len(mxfs) < 2:
        raise RuntimeError("Expected one CPL, one PKL and actual picture/sound MXFs")
    asset_map = _parse_xml(dcp / "ASSETMAP.xml")
    if _local(asset_map.tag) != "AssetMap":
        raise RuntimeError("Not a SMPTE DCP asset map")
    cpl = _parse_xml(cpls[0])
    pkl = _parse_xml(pkls[0])
    # Minimum cross-reference sanity; a real validator still must parse MXF.
    listed_paths = {node.text.strip() for node in _members(asset_map, "Path")
                    if node.text and node.text.strip()}
    if not {p.name for p in (cpls[0], pkls[0], *mxfs)}.issubset(listed_paths):
        raise RuntimeError("DCP asset map does not reference all cinema assets")
    for root in (cpl, pkl):
        if not _members(root, "Id"):
            raise RuntimeError("Missing DCP playlist/packing identifiers")
    if require_essence:
        # A magic or filename check alone is deliberately insufficient.
        if not all(p.stat().st_size > 1024 for p in mxfs):
            raise RuntimeError("DCP picture/sound essence suspiciously short")
    return {
        "format": "nvp.audio01k3.structural_receipt.v1",
        "structure_only": True, "independently_validated": False,
        "asset_count": len(assets), "assets": assets,
        "cpl": cpls[0].name, "pkl": pkls[0].name,
        "mxf_count": len(mxfs), "candidate": True,
        "dcp_delivered": False,
    }


def encode_candidate(input_mov, workspace, title, *, create_bin, cli_bin,
                     expected_mov_sha):
    """Invoke real DCP-o-matic tools; do not fabricate DCP assets."""
    mov = Path(input_mov)
    root = Path(workspace)
    if (mov.is_symlink() or not mov.is_file() or
        sha_file(mov) != expected_mov_sha):
        raise RuntimeError("Approved final MOV changed before DCP authoring")
    if (root.is_symlink() or not root.is_dir() or
        any(root.iterdir())):
        raise RuntimeError("DCP workspace must be a new empty directory")
    binaries = (Path(create_bin), Path(cli_bin))
    if any(not p.is_absolute() or p.is_symlink() or not p.is_file()
           for p in binaries):
        raise RuntimeError("Host must pin real DCP-o-matic executable paths")
    film_dir = root / "film"
    create_cmd, encode_cmd = plan_commands(
        mov, film_dir, title, binaries[0], binaries[1])
    _run(create_cmd, cwd=root, timeout=120)
    if not film_dir.is_dir() or film_dir.is_symlink():
        raise RuntimeError("DCP-o-matic did not create a real film project")
    output = _run(encode_cmd, cwd=root, timeout=1800)
    candidates = [Path(line.strip()) for line in output.splitlines()
                  if line.strip()]
    candidates = [p if p.is_absolute() else root / p for p in candidates]
    if len(candidates) != 1 or not candidates[0].is_dir():
        raise RuntimeError("No single completed DCP path from native encoder")
    dcp = candidates[0].resolve(strict=True)
    if not dcp.is_relative_to(film_dir.resolve(strict=True)):
        raise RuntimeError("DCP encoder escaped its contained film workspace")
    report = inspect_dcp_directory(dcp)
    if sha_file(mov) != expected_mov_sha:
        raise RuntimeError("DCP encoding altered original approved MOV")
    return dcp, report


def validate_strict_smpte(dcp, doctor_bin, *, timeout=1800):
    """Mandatory independent DcpDoctor SMPTE and deep-essence validation.

    Requires exit 0, fails on skipped validator checks; never supplies
    --no-hashes/--no-mxf/--no-deep-j2k flags. This is a technical gate,
    not a projector ingest / exhibition certification.
    """
    binary = Path(doctor_bin)
    if (not binary.is_absolute() or binary.is_symlink() or
        not binary.is_file()):
        raise RuntimeError("Pinned independent DcpDoctor binary is missing")
    package = Path(dcp)
    before = inspect_dcp_directory(package)
    result = subprocess.run(
        [str(binary), "validate", "--strict", str(package)],
        cwd=str(package.parent), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
        check=False)
    stdout = result.stdout.decode("utf8", "replace")[:65536]
    stderr = result.stderr.decode("utf8", "replace")[:65536]
    if result.returncode != 0:
        raise RuntimeError("Independent strict SMPTE validator rejected DCP: " +
                           (stdout + stderr)[-1500:])
    # An explicit skipped essential check cannot be interpreted as PASS.
    if re.search(r"(?:check_skipped|schema_validation_skipped|"
                 r"\\bSKIPPED\\b)", stdout + stderr, re.I):
        raise RuntimeError("Independent DCP QC skipped required validation")
    after = inspect_dcp_directory(package)
    if before["assets"] != after["assets"]:
        raise RuntimeError("DCP changed while independent validator inspected it")
    return {
        "format": "nvp.audio01k3.independent_smpte_qc.v1",
        "validator": "dcpdoctor_strict",
        "validator_sha256": sha_file(binary),
        "returncode": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "all_required_checks": True,
        "asset_sha256_proof": after["assets"],
        "smpte_validator_passed": True,
        "theatrical_exhibition_certified": False,
    }
