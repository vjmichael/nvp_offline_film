"""NVP native FFMS2/FFmpeg binary build licensing inventory and release gate.

Not a legal opinion and not a substitute for verifying the actual linked DLLs.
A development CI build may use GPL components, but NVP's redistributable
installer is blocked until the *actual* artifacts have an approved provenance
manifest and a documented distribution policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_ffmpeg_build(text):
    """Report build flags without pretending they settle binary copyright."""
    if type(text) is not str or not text.strip():
        return "BUILD_CONFIG_UNKNOWN"
    options = set(text.split())
    if "--enable-nonfree" in options:
        return "NONFREE_REVIEW_STOP"
    if "--enable-gpl" in options:
        return "GPL_COMPONENTS_ENABLED"
    if "--enable-version3" in options:
        return "LGPL_VERSION3_CANDIDATE"
    # A static FFmpeg configure transcript is not proof all bundled shared
    # libraries are built the same way; still needs linked-binary audit.
    return "LGPL_CANDIDATE_UNVERIFIED_LINKAGE"


def inspect(ffmpeg, ffms2_library, *, release_manifest=None):
    ffmpeg, ffms2_library = Path(ffmpeg), Path(ffms2_library)
    if not ffmpeg.is_absolute() or not ffms2_library.is_absolute():
        raise ValueError("Inspect explicit absolute files from the build under audit")
    if not ffmpeg.is_file() or not ffms2_library.is_file():
        raise FileNotFoundError("Native FFmpeg/FFMS2 build inputs absent")
    result = subprocess.run([str(ffmpeg), "-buildconf"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=25, check=False)
    text = result.stdout[:250_000].decode("utf-8", "replace")
    if result.returncode:
        raise RuntimeError("Cannot inspect FFmpeg native build configuration")
    flags = classify_ffmpeg_build(text)
    report = {
        "format": "nvp.native_codec_license_inventory.v1",
        "ffmpeg_executable_sha256": sha_file(ffmpeg),
        "ffms2_library_sha256": sha_file(ffms2_library),
        "ffmpeg_config_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "ffmpeg_build_classification": flags,
        "ffms2_source_license": "MIT",
        "ffms2_binary_license": "DEPENDS_ON_ACTUAL_LINKED_FFMPEG_BUILD",
        "distribution_approved": False,
        "reviewed_binary_linkage": False,
        "license_notices_included": False,
    }
    if release_manifest is not None:
        doc = json.loads(Path(release_manifest).read_text(encoding="utf-8"))
        required = {
            "ffmpeg_executable_sha256": report["ffmpeg_executable_sha256"],
            "ffms2_library_sha256": report["ffms2_library_sha256"],
            "ffmpeg_config_sha256": report["ffmpeg_config_sha256"],
        }
        if (type(doc) is dict and
            all(doc.get(k) == v for k, v in required.items()) and
            isinstance(doc.get("ffmpeg_source_commit"), str) and
            len(doc["ffmpeg_source_commit"]) >= 12 and
            isinstance(doc.get("ffms2_source_commit"), str) and
            len(doc["ffms2_source_commit"]) >= 12 and
            doc.get("reviewed_binary_linkage") is True and
            doc.get("license_notices_included") is True and
            doc.get("corresponding_sources_available") is True and
            doc.get("release_license_review_approved") is True and
            ((flags == "GPL_COMPONENTS_ENABLED" and
              doc.get("distribution_policy") == "GPL_COMPLIANT_REVIEWED") or
             (flags in ("LGPL_CANDIDATE_UNVERIFIED_LINKAGE",
                        "LGPL_VERSION3_CANDIDATE") and
              doc.get("distribution_policy") == "LGPL_COMPLIANT_REVIEWED"))):
            report.update({
                "distribution_approved": True,
                "reviewed_binary_linkage": True,
                "license_notices_included": True,
            })
        else:
            report["release_manifest_mismatch"] = True
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffms2-library", required=True)
    parser.add_argument("--release-manifest")
    parser.add_argument("--release-gate", action="store_true")
    opts = parser.parse_args()
    report = inspect(opts.ffmpeg, opts.ffms2_library,
                     release_manifest=opts.release_manifest)
    print(json.dumps(report, sort_keys=True, indent=2))
    if opts.release_gate and not report["distribution_approved"]:
        print("NVP release blocked: native codec distribution review required", file=sys.stderr)
        raise SystemExit(3)


if __name__ == "__main__":
    main()
