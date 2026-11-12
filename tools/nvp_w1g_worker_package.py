"""W1-G: exact-SHA first-party *executable* native worker packaging.

The trusted build pipeline, not JavaScript or a model, supplies a reviewed
roster and binaries. Only previously compiled PE64/ELF64 native executables
may be installed under an NVP private worker directory. No Python source
script is falsely advertised as executable in a frozen PyInstaller process.
Process-tree containment and work execution remain separate acceptance gates.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct

try:
    from .nvp_w1g_native_package import _inventory, _forbidden_native_binaries, _digest
except ImportError:
    from nvp_w1g_native_package import _inventory, _forbidden_native_binaries, _digest

FORMAT = "nvp.w1g.native_executable_worker_roster.v1"
ROLES = frozenset(("original_capture", "scene_render", "editorial", "audio", "delivery"))
MIN_EXECUTABLE_BYTES = 100000


def _pe64(exe: Path):
    with exe.open("rb") as fd:
        mz = fd.read(64)
        if len(mz) != 64 or mz[:2] != b"MZ":
            raise RuntimeError("Native Windows worker lacks PE image")
        offset = struct.unpack_from("<I", mz, 0x3c)[0]
        if offset < 64 or offset > exe.stat().st_size - 256:
            raise RuntimeError("Invalid native worker PE offset")
        fd.seek(offset)
        pe = fd.read(256)
    if (pe[:4] != b"PE\x00\x00" or
        struct.unpack_from("<H", pe, 4)[0] != 0x8664 or
        struct.unpack_from("<H", pe, 24)[0] != 0x20B or
        struct.unpack_from("<H", pe, 24+68)[0] not in (2,3)):
        raise RuntimeError("Native worker is not an amd64 PE32+ executable")


def _elf64(exe: Path):
    with exe.open("rb") as fd:
        header = fd.read(64)
    if (len(header) != 64 or header[:6] != b"\x7fELF\x02\x01" or
        struct.unpack_from("<H", header, 18)[0] != 62 or
        struct.unpack_from("<H", header, 16)[0] not in (2, 3)):
        raise RuntimeError("Native worker is not an x86-64 Linux ELF executable")


def _verify_binary(exe: Path, platform: str):
    if (not exe.is_file() or exe.is_symlink() or
        exe.stat().st_size < MIN_EXECUTABLE_BYTES):
        raise RuntimeError("Native worker is missing or truncated")
    if platform == "windows-amd64":
        _pe64(exe)
    elif platform == "linux-amd64":
        _elf64(exe)
    else:
        raise RuntimeError("Unknown native OS architecture for worker")


def _check_roster(roster):
    if (type(roster) is not dict or roster.get("format") != FORMAT or
        roster.get("platform") not in ("windows-amd64","linux-amd64") or
        type(roster.get("workers")) is not list or
        not 1 <= len(roster["workers"]) <= len(ROLES)):
        raise RuntimeError("Reviewed native worker binary roster required")
    seen = set()
    for worker in roster["workers"]:
        if type(worker) is not dict or set(worker) != {"role","filename","sha256"}:
            raise RuntimeError("Unknown native worker manifest fields")
        role, name, digest = worker["role"], worker["filename"], worker["sha256"]
        if (role not in ROLES or role in seen or
            type(name) is not str or name != Path(name).name or
            "/" in name or "\\" in name or not name or
            not name.isascii() or len(name) > 120 or
            (not name.endswith(".exe") if roster["platform"] == "windows-amd64"
             else name.endswith(".exe")) or
            type(digest) is not str or len(digest) != 64 or
            any(c not in "0123456789abcdef" for c in digest)):
            raise RuntimeError("Untrusted or duplicate native worker identity")
        seen.add(role)
    _forbidden_native_binaries([w["filename"] for w in roster["workers"]])
    return roster


def provision_native_workers(trusted_binaries: Path, install_bundle: Path,
                             roster: dict) -> dict:
    """Stage already compiled, reviewed native executables without launching."""
    _check_roster(roster)
    if (not trusted_binaries.is_dir() or trusted_binaries.is_symlink() or
        not install_bundle.is_dir() or install_bundle.is_symlink()):
        raise RuntimeError("Trusted native worker artifact roots required")
    target = install_bundle/"_internal"/"nvp_workers"
    if target.exists() or target.is_symlink():
        raise FileExistsError("Native worker bundle is already provisioned")
    checked = []
    for worker in roster["workers"]:
        path = trusted_binaries/worker["filename"]
        _verify_binary(path, roster["platform"])
        if _digest(path) != worker["sha256"]:
            raise RuntimeError("Native worker executable differs from creator-reviewed SHA")
        checked.append((worker, path))
    target.mkdir(parents=True)
    for worker, path in checked:
        destination = target/worker["filename"]
        with path.open("rb") as source, destination.open("xb") as out:
            shutil.copyfileobj(source, out)
        if _digest(destination) != worker["sha256"]:
            raise RuntimeError("Staged native worker differs from original binary")
    report = {**roster, "executable_bytes_verified": True,
              "native_worker_executed": False, "process_tree_custody_verified": False}
    (target/"manifest.json").write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")), encoding="utf8")
    return report


def verify_native_workers(install_bundle: Path, *, expected_platform: str) -> dict:
    target = install_bundle/"_internal"/"nvp_workers"
    if not target.is_dir() or target.is_symlink():
        raise RuntimeError("Native supervised worker package absent")
    manifest = target/"manifest.json"
    if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > 10240:
        raise RuntimeError("Native worker roster absent or unbounded")
    doc = json.loads(manifest.read_text("utf8"))
    _check_roster(doc)
    if doc["platform"] != expected_platform or doc.get("executable_bytes_verified") is not True:
        raise RuntimeError("Native worker roster platform or provenance changed")
    expected = {"manifest.json"} | {x["filename"] for x in doc["workers"]}
    if {x.name for x in target.iterdir()} != expected:
        raise RuntimeError("Unreviewed or missing native worker executable")
    for worker in doc["workers"]:
        path = target/worker["filename"]
        _verify_binary(path, expected_platform)
        if _digest(path) != worker["sha256"]:
            raise RuntimeError("Installed native worker executable SHA changed")
    return {
        "status": "NATIVE_EXECUTABLE_WORKERS_HASH_VERIFIED",
        "roles": [w["role"] for w in doc["workers"]],
        "native_worker_executed": False,
        "process_tree_custody_verified": False,
    }


def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("action", choices=("provision","verify"))
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--platform", required=True, choices=("windows-amd64","linux-amd64"))
    ap.add_argument("--trusted-binaries", type=Path)
    ap.add_argument("--roster", type=Path)
    args=ap.parse_args(argv)
    if args.action=="provision":
        if args.trusted_binaries is None or args.roster is None:
            ap.error("provision requires --trusted-binaries and --roster")
        roster=json.loads(args.roster.read_text("utf8"))
        if roster.get("platform")!=args.platform:
            raise RuntimeError("Build host and approved worker OS differ")
        result=provision_native_workers(args.trusted_binaries,args.bundle,roster)
    else:
        result=verify_native_workers(args.bundle,expected_platform=args.platform)
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
