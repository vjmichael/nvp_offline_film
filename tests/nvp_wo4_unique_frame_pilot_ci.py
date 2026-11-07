"""WO4 genuine native unique-frame 2K/4K JPEG2000 pilot, NOT a feature benchmark.

Unlike the full-duration MXF/DCP wrapping stress, each synthetic XYZ12 frame
has different source bytes and must yield a distinct independently verified
native OpenJPEG codestream. The bounded patterned images are NOT real-world
footage, and a small pilot cannot certify full-length render performance.
No FFmpeg; source originals remain immutable.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import shutil
import time

from backend.nvp_wo3_native_codecs import ApprovedCodecBinary, digest_file
from backend.nvp_wo3_j2k_audit import PROFILES
from backend.nvp_wo4_picture_spool import encode_disk_xyz12, verify_frame_file

TILE_PIXELS = 128
SOURCE_BANDS = 8


def patterned_xyz12(path: Path, width: int, height: int, sequence: int) -> str:
    """Write native big-endian XYZ12 with row-banded RGB-like XYZ variation.

    Bounded to 8 line templates (not an entire 2K/4K raster in memory).
    Uses deterministic synthetic patterns; does not purport to simulate
    film-content compression behavior or calibrated XYZ artistic grading.
    """
    rows = []
    for band in range(SOURCE_BANDS):
        tile = bytearray()
        for x in range(TILE_PIXELS):
            values = (
                (257 + 11*x + 29*band + 47*sequence) % 4096,
                (991 + 23*x + 31*band + 53*sequence) % 4096,
                (2007 + 37*x + 41*band + 59*sequence) % 4096,
            )
            for val in values:
                tile.extend(val.to_bytes(2, "big"))
        row = (tile * ((width+TILE_PIXELS-1)//TILE_PIXELS))[:width*6]
        assert len(row) == width*6
        rows.append(row)
    digest = sha256()
    with path.open("xb") as out:
        for y in range(height):
            row = rows[(y//13) % SOURCE_BANDS]
            out.write(row)
            digest.update(row)
        out.flush()
        os.fsync(out.fileno())
    assert path.stat().st_size == width*height*6
    return digest.hexdigest()


def run(profile: str, samples: int, root: Path, audit: Path) -> dict:
    if profile not in ("2K_FLAT_24", "4K_SCOPE_24"):
        raise ValueError("Real approved 2K/4K profile required")
    if type(samples) is not int or not 6 <= samples <= 24:
        raise ValueError("Pilot must contain 6-24 genuinely unique frames")
    width, height, fps = PROFILES[profile]
    assert fps == 24
    root = root.absolute()
    if root.exists() or root.is_symlink():
        raise FileExistsError("Fresh native pilot scratch required")
    root.mkdir(parents=True, mode=0o700)
    if shutil.disk_usage(root).free < 2*1024**3:
        raise OSError("Insufficient native scratch for 4K source and codec workers")
    binary_path = Path(os.environ["NVP_NATIVE_OPENJPEG"]).resolve(strict=True)
    binary = ApprovedCodecBinary(
        binary_path, product="OpenJPEG-opj_compress",
        sha256=digest_file(binary_path))
    sources, works = root/"original_xyz12", root/"native_workers"
    sources.mkdir()
    works.mkdir()
    source_hashes = []
    j2k_hashes = []
    elapsed_encodes = []
    receipts = []
    started = time.monotonic()
    for i in range(samples):
        original = sources/f"unique_{i:03d}.xyz12"
        expected = patterned_xyz12(original, width, height, i)
        assert digest_file(original) == expected
        source_hashes.append(expected)
        work = works/f"unique_{i:03d}"
        work.mkdir()
        stamp = time.monotonic()
        receipt = encode_disk_xyz12(
            binary, profile=profile, source_path=str(original),
            source_sha256=expected, private_work=work,
            check_cancel=lambda: False, timeout=900)
        elapsed_encodes.append(round(time.monotonic()-stamp, 4))
        assert receipt["status"] == "ENCODED_J2K_STAGE_VERIFIED"
        assert receipt["source_sha256"] == expected
        codestream = work/"frame.j2c"
        assert verify_frame_file(
            codestream, receipt["codestream_sha256"], profile) > 0
        assert digest_file(codestream) == receipt["codestream_sha256"]
        assert digest_file(original) == expected, "Original XYZ12 changed"
        j2k_hashes.append(receipt["codestream_sha256"])
        receipts.append({
            "source_sha256": expected,
            "j2k_sha256": receipt["codestream_sha256"],
            "j2k_bytes": receipt["codestream_bytes"],
            "native_encode_seconds": elapsed_encodes[-1]
        })
    assert len(set(source_hashes)) == samples, "Source sample was repeated"
    assert len(set(j2k_hashes)) == samples, "J2K sample was reused"
    assert all(digest_file(sources/f"unique_{i:03d}.xyz12") == source_hashes[i]
               for i in range(samples)), "Source custody changed"
    result = {
        "format": "nvp.wo4.native_unique_frame_sample.v1",
        "status": "NATIVE_DISTINCT_SOURCE_AND_J2K_SAMPLE_VERIFIED",
        "profile": profile,
        "dimensions": [width, height],
        "frame_rate": fps,
        "sample_frames": samples,
        "all_sample_source_sha256_unique": True,
        "all_sample_j2k_sha256_unique": True,
        "all_sample_source_sha256_unchanged": True,
        "real_native_openjpeg_per_frame": True,
        "native_openjpeg_sha256": binary.sha256,
        "elapsed_seconds": round(time.monotonic()-started, 3),
        "native_encoding_seconds_total": round(sum(elapsed_encodes), 3),
        "native_encoding_seconds_mean": round(sum(elapsed_encodes)/samples, 4),
        "native_encoding_seconds_max": max(elapsed_encodes),
        "child_process_peak_rss_bytes": resource.getrusage(
            resource.RUSAGE_CHILDREN).ru_maxrss*1024,
        "raw_original_bytes": width*height*6*samples,
        "codestream_total_bytes": sum(r["j2k_bytes"] for r in receipts),
        "receipts": receipts,
        "patterned_test_media_not_real_footage": True,
        "full_feature_unique_frame_throughput_verified": False,
        "full_feature_filmindex_integration_verified": False,
        "independent_cinema_ingest_accepted": False,
    }
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("x", encoding="utf-8") as out:
        json.dump(result, out, sort_keys=True, indent=2)
    print(json.dumps({
        "event": "WO4_UNIQUE_FRAME_PILOT_PASS",
        "profile": profile,
        "sample_frames": samples,
        "elapsed_seconds": result["elapsed_seconds"],
        "native_encoding_seconds_mean": result["native_encoding_seconds_mean"],
        "distinct_native_j2k_sha256": True,
        "full_feature_throughput_certified": False
    }, sort_keys=True), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True,
                        choices=("2K_FLAT_24", "4K_SCOPE_24"))
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    run(args.profile, args.samples, args.root, args.audit)
