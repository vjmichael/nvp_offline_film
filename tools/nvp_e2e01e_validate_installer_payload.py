"""NVP-E2E-01E — verify the real Windows desktop payload before NSIS.

Cross-platform static package audit (runs on Linux as well as Windows).
This is not a runtime GUI test. It rejects a fake/placeholder executable,
wrong architecture/subsystem, missing PyInstaller runtime and missing UI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

MIN_EXE_BYTES = 100_000
MIN_BUNDLE_FILES = 8


def verify_pe64_gui(exe: Path) -> dict:
    if not exe.is_file() or exe.is_symlink():
        raise RuntimeError("Missing real Windows NVP.exe")
    size = exe.stat().st_size
    if size < MIN_EXE_BYTES:
        raise RuntimeError("NVP.exe is a placeholder or truncated")
    with exe.open("rb") as stream:
        mz = stream.read(64)
        if len(mz) != 64 or mz[:2] != b"MZ":
            raise RuntimeError("Desktop app is not a Windows PE executable")
        offset = struct.unpack_from("<I", mz, 0x3C)[0]
        if offset < 64 or offset > size - 256:
            raise RuntimeError("Invalid Windows PE offset")
        stream.seek(offset)
        header = stream.read(256)
        if header[:4] != b"PE\x00\x00":
            raise RuntimeError("Missing Windows PE signature")
        machine = struct.unpack_from("<H", header, 4)[0]
        optional_size = struct.unpack_from("<H", header, 20)[0]
        magic = struct.unpack_from("<H", header, 24)[0]
        subsystem = struct.unpack_from("<H", header, 24 + 68)[0]
        if machine != 0x8664 or magic != 0x20B or optional_size < 70:
            raise RuntimeError("NVP desktop must be AMD64 PE32+")
        if subsystem != 2:
            raise RuntimeError("NVP desktop must have Windows GUI subsystem")
    with exe.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "bytes": size,
        "sha256": digest,
        "machine": "AMD64",
        "subsystem": "Windows GUI",
    }


def verify_bundle(folder: Path) -> dict:
    # Refuse links anywhere in the payload: NSIS must install only audited,
    # repository-built regular files, never follow an external filesystem path.
    if folder.is_symlink():
        raise RuntimeError("Installer payload directory is a symlink")
    if not folder.is_dir():
        raise RuntimeError("Missing Windows bundle directory")
    for member in folder.rglob("*"):
        if member.is_symlink():
            raise RuntimeError("Installer payload contains symlink: " + str(member))
    exe = folder / "NVP.exe"
    evidence = verify_pe64_gui(exe)
    base = folder / "_internal"
    if not base.is_dir() or base.is_symlink():
        raise RuntimeError("Missing PyInstaller one-directory runtime")
    # PyInstaller embeds PYZ in the PE CArchive, not as an external .pyz.
    # A one-dir package must still ship its Python DLL and base library.
    if not (base / "base_library.zip").is_file():
        raise RuntimeError("Missing PyInstaller base_library.zip")
    if not list(base.glob("python3*.dll")):
        raise RuntimeError("Missing bundled Python Windows runtime DLL")
    assets = base / "frontend" / "dist" / "assets"
    entry = base / "frontend" / "dist" / "index.html"
    if not assets.is_dir() or not entry.is_file():
        raise RuntimeError("Bundled React desktop HTML/assets absent")
    html = entry.read_text("utf8")
    if 'id="root"' not in html or "/assets/" not in html:
        raise RuntimeError("NVP React root or Vite bundle entry missing")
    js = list(assets.glob("*.js"))
    if not js or not all(p.stat().st_size > 0 for p in js):
        raise RuntimeError("Missing compiled React JavaScript")
    native_renderer=base / "tools" / "nvp_int02_cycles_frame_worker.py"
    if (not native_renderer.is_file() or native_renderer.is_symlink() or
        native_renderer.stat().st_size<1000):
        raise RuntimeError("Missing first-party installed Cycles worker source")
    files = [p for p in folder.rglob("*") if p.is_file()]
    if len(files) < MIN_BUNDLE_FILES:
        raise RuntimeError("NVP package does not contain a real runtime")
    if len({p.relative_to(folder).as_posix().casefold() for p in files}) != len(files):
        raise RuntimeError("Case-folded destination path collision")
    return {
        "status": "VERIFIED_NVP_WINDOWS_BUNDLE_STRUCTURE",
        "exe": evidence,
        "files": len(files),
        "asset_js_count": len(js),
        "react_index_sha256": hashlib.sha256(entry.read_bytes()).hexdigest(),
        "runtime_verified_on_windows": False,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)
    report = verify_bundle(args.bundle)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf8") as fd:
            fd.write(serialized)
    print(serialized)


if __name__ == "__main__":
    main()
