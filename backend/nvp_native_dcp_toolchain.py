"""Batch 3: FFmpeg-free native cinema encoding toolchain admission.

OpenJPEG (BSD-2-Clause) and CineCert asdcplib (BSD-3-Clause) are
appropriate low-level, cross-platform components for future native
DCDM -> JPEG2000 codestream -> SMPTE picture/sound MXF packaging.

This module is an actual native *binary/provenance admission boundary*,
not a DCP encoder, a claim of calibrated XYZ, or a way to execute
browser-supplied paths. Binary distributions are installed with NVP,
verified against a trusted BUILD-TIME pinned manifest by the desktop
host and executed only by a separately authorized contained worker.
No runtime download, script execution, or legacy FFmpeg path is allowed.

A professional DCP still requires a verified native 12-bit XYZ DCDM,
native generated J2C and MXF, CPL/PKL/ASSETMAP, and independent DcpDoctor
QC. A successful tool admission can NEVER set dcp_delivered to True.
"""
from __future__ import annotations
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
import sys

FORMAT="nvp.native_data_first.dcp_toolchain_admission.v1"
MANIFEST="nvp.native_data_first.dcp_toolchain_manifest.v1"
BINARY_NAMES={
    "openjpeg_encode":"opj_compress",
    "openjpeg_decode":"opj_decompress",
    "asdcplib_wrap":"asdcp-wrap",
    "asdcplib_info":"asdcp-info",
    "asdcplib_unwrap":"asdcp-unwrap",
    "asdcplib_j2c_verify":"j2c-test",
    "dcpdoctor_strict":"dcpdoctor",
}
MAX_BINARY_BYTES=256*1024*1024
SHA=re.compile(r"[0-9a-f]{64}\Z")
LABEL=re.compile(r"[A-Za-z][A-Za-z0-9._-]{0,79}\Z")
LICENSE={
    "openjpeg_encode":"BSD-2-Clause",
    "openjpeg_decode":"BSD-2-Clause",
    "asdcplib_wrap":"BSD-3-Clause",
    "asdcplib_info":"BSD-3-Clause",
    "asdcplib_unwrap":"BSD-3-Clause",
    "asdcplib_j2c_verify":"BSD-3-Clause",
    # The independent QC program's distribution/license must be
    # separately reviewed and recorded by its actual packager.
    "dcpdoctor_strict":None,
}


def _hash_file(path):
    digest=sha256()
    with path.open("rb") as source:
        while packet:=source.read(1024*1024):digest.update(packet)
    return digest.hexdigest()


def admit_toolchain(bundle_root,trusted_manifest):
    """Verify a provisioned source-pinned cinema tool bundle without executing.

    Manifest is trusted build/installer input, NEVER a path/hash manifest
    supplied via browser, model tool call or user project contents.
    """
    root=Path(bundle_root)
    if (not root.is_absolute() or root.is_symlink() or
        not root.is_dir()):
        raise PermissionError("Trusted installed native codec bundle is unavailable")
    if type(trusted_manifest) is not dict or set(trusted_manifest)!={
            "format","bundle_id","platform","tools","dependency_audit_sha256",
            "license_review_sha256"} or (
            trusted_manifest["format"]!=MANIFEST):
        raise ValueError("NVP installation lacks an exact native DCP toolchain manifest")
    bundle_id=trusted_manifest["bundle_id"]
    if type(bundle_id) is not str or not LABEL.fullmatch(bundle_id):
        raise ValueError("Invalid trusted cinema bundle identity")
    expected_os="windows" if os.name=="nt" else "linux" if (
        sys.platform.startswith("linux")) else None
    if expected_os is None or trusted_manifest["platform"]!=expected_os:
        raise RuntimeError("Native cinema toolchain OS does not match host")
    for key in ("dependency_audit_sha256","license_review_sha256"):
        value=trusted_manifest[key]
        if type(value) is not str or not SHA.fullmatch(value):
            raise ValueError("Native cinema bundle lacks approved dependency/license digest")
    tools=trusted_manifest["tools"]
    if type(tools) is not dict or set(tools)!=set(BINARY_NAMES):
        raise ValueError("Native cinema encoder/validator bundle incomplete")
    found={}
    suffix=".exe" if os.name=="nt" else ""
    for role,base in BINARY_NAMES.items():
        entry=tools[role]
        if type(entry) is not dict or set(entry)!={
                "file_name","sha256","size_bytes","license"}:
            raise ValueError("Unexpected native tool identity")
        name=base+suffix
        if (entry["file_name"]!=name or
            type(entry["sha256"]) is not str or
            not SHA.fullmatch(entry["sha256"]) or
            type(entry["size_bytes"]) is not int or
            not 1<=entry["size_bytes"]<=MAX_BINARY_BYTES or
            type(entry["license"]) is not str or
            not entry["license"]):
            raise ValueError("Unpinned native cinema executable details")
        if LICENSE[role] is not None and entry["license"]!=LICENSE[role]:
            raise PermissionError("Native cinema dependency license review changed")
        path=root/name
        if (path.is_symlink() or not path.is_file() or
            path.resolve(strict=True).parent!=root.resolve(strict=True) or
            path.stat().st_size!=entry["size_bytes"] or
            (os.name!="nt" and not path.stat().st_mode&stat.S_IXUSR)):
            raise PermissionError("Native cinema executable was replaced or is non-executable")
        if _hash_file(path)!=entry["sha256"]:
            raise RuntimeError("SHA-pinned native cinema executable digest changed")
        found[role]={"sha256":entry["sha256"],
                     "file_name":entry["file_name"],
                     "license":entry["license"]}
    return {
        "format":FORMAT,"status":"VERIFIED_NATIVE_TOOLCHAIN_NOT_A_DCP",
        "bundle_id":bundle_id,"platform":expected_os,
        "roles":found,
        "dependency_audit_sha256":trusted_manifest[
            "dependency_audit_sha256"],
        "license_review_sha256":trusted_manifest[
            "license_review_sha256"],
        "runtime_executables_invoked":False,
        "supports_pinned_cinema_jpeg2000_and_mxf_workers":True,
        "calibrated_DCDM_XYZ12_available":False,
        "approved_DCP_package_available":False,
        "independent_smpte_qc_passed":False,
        "dcp_delivered":False,"ffmpeg_used":False,
    }


def require_native_dcdm_source(document,original_take_sha256):
    """Admit a *verified native DCDM record*, not a PNG/EXR proxy.

    This schema cannot be produced from existing 640x360 source previews.
    Its independent DCDM publisher must establish calibrated 12-bit XYZ
    at 1998x1080 or 2048x858 and cinema 24-bit audio without touching
    the frozen original Take. The authenticated FilmIndex reference is
    checked by the caller; this routine additionally checks typed scope.
    """
    if (type(original_take_sha256) is not str or
        not SHA.fullmatch(original_take_sha256) or
        type(document) is not dict or
        set(document)!={
            "format","original_take_sha256","native_publisher_sha256",
            "color_transform_sha256","measured_color_calibration_sha256",
            "picture_raster","frame_rate","picture_components",
            "picture_bit_depth","sound_channels","sound_sample_rate",
            "sound_sample_bit_depth","native_dcdm_authorized",
            "independently_qc_verified","source_modified"}):
        raise ValueError("Native DCDM source requires exact original/authored profile")
    if (document["format"]!="nvp.data_first.calibrated_xyz12_dcdm.v1" or
        document["original_take_sha256"]!=original_take_sha256 or
        any(type(document[k]) is not str or not SHA.fullmatch(document[k])
            for k in ("native_publisher_sha256","color_transform_sha256",
                      "measured_color_calibration_sha256")) or
        document["picture_raster"] not in ([1998,1080],[2048,858]) or
        document["frame_rate"]!=[24,1] or
        document["picture_components"]!="XYZ" or
        document["picture_bit_depth"]!=12 or
        document["sound_channels"] not in (2,6) or
        document["sound_sample_rate"]!=48000 or
        document["sound_sample_bit_depth"]!=24 or
        document["native_dcdm_authorized"] is not True or
        document["independently_qc_verified"] is not True or
        document["source_modified"] is not False):
        raise RuntimeError("Uncalibrated source picture/audio cannot become cinema essence")
    return {
        "format":"nvp.native_data_first.dcdm_admission.v1",
        "status":"VERIFIED_DCDM_SOURCE_NOT_DCP",
        "original_take_sha256":original_take_sha256,
        "native_publisher_sha256":document["native_publisher_sha256"],
        "native_color_transform_sha256":document["color_transform_sha256"],
        "measured_calibration_sha256":document[
            "measured_color_calibration_sha256"],
        "picture_raster":document["picture_raster"],
        "frame_rate":[24,1],
        "sound_sample_rate":48000,
        "sound_bit_depth":24,
        "ffmpeg_used":False,"dcp_delivered":False,
    }
