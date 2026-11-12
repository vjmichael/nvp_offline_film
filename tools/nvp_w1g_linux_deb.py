"""W1-G Linux amd64 .deb release builder for a genuine native NVP bundle.

No cross-compiled, Windows, dummy, or browser-supplied executable is admitted.
Only package-owned files go under /opt/nvp and /usr; the user's original films
are never installed, migrated or removed by this package. Owner acceptance,
real GTK/WebKit runtime, workers, signing and rollback are separate gates.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory

try:
    from .nvp_w1g_native_package import _inventory, _forbidden_native_binaries, _digest
except ImportError:
    from nvp_w1g_native_package import _inventory, _forbidden_native_binaries, _digest

FORMAT = "nvp.w1g.linux_deb_candidate.v1"


def check_real_linux_bundle(bundle: Path) -> dict:
    files = _inventory(bundle)
    exe = bundle/"NVP"
    if not exe.is_file() or exe.is_symlink() or exe.stat().st_size < 100000:
        raise RuntimeError("Real Linux NVP GUI executable required")
    with exe.open("rb") as fd:
        head = fd.read(64)
    if (len(head) != 64 or head[:4] != b"\x7fELF" or
        head[4:6] != b"\x02\x01" or
        struct.unpack_from("<H", head, 18)[0] != 62 or
        struct.unpack_from("<H", head, 16)[0] not in (2, 3)):
        raise RuntimeError("NVP must be a real Linux ELF64 x86-64 executable")
    internal = bundle/"_internal"
    entry = internal/"frontend"/"dist"/"index.html"
    assets = internal/"frontend"/"dist"/"assets"
    if (not (internal/"base_library.zip").is_file() or
        not entry.is_file() or not assets.is_dir() or
        not list(assets.glob("*.js"))):
        raise RuntimeError("Missing Linux native Python runtime or offline React UI")
    html = entry.read_text("utf8")
    if 'id="root"' not in html or "/assets/" not in html:
        raise RuntimeError("Linux packaged NVP UI entry invalid")
    script=internal/"tools"/"nvp_int02_cycles_frame_worker.py"
    if not script.is_file() or script.is_symlink() or script.stat().st_size<1000:
        raise RuntimeError("Missing installed first-party Cycles worker script")
    _forbidden_native_binaries(files)
    return {"exe_sha256": _digest(exe), "files": files}


def build_deb(bundle: Path, output: Path, *, version: str,
              maintainer: str, packager="dpkg-deb") -> dict:
    if not re.fullmatch(r"[0-9][A-Za-z0-9.+:~\-]{0,63}", version):
        raise ValueError("Invalid Debian package version")
    if (not re.fullmatch(r"[A-Za-z0-9 ._@<>+\-]{3,160}", maintainer) or
        "\n" in maintainer):
        raise ValueError("Explicit factual Debian maintainer required")
    if output.exists() or output.is_symlink():
        raise FileExistsError("Never overwrite an existing native release package")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise RuntimeError("Release destination must be a trusted directory")
    audit = check_real_linux_bundle(bundle)
    binary = shutil.which(packager)
    if binary is None:
        raise RuntimeError("Native dpkg-deb tool is unavailable")
    with TemporaryDirectory(prefix=".nvp-w1g-deb-", dir=output.parent) as temp:
        stage = Path(temp)/"root"
        payload = stage/"opt"/"nvp"
        payload.parent.mkdir(parents=True)
        shutil.copytree(bundle, payload, symlinks=False)
        if _inventory(payload) != audit["files"]:
            raise RuntimeError("Native Linux package staging modified source worker bytes")
        bindir = stage/"usr"/"bin"
        bindir.mkdir(parents=True)
        launch = bindir/"nvp"
        launch.write_text('#!/bin/sh\nexec /opt/nvp/NVP "$@"\n', encoding="utf8")
        launch.chmod(0o755)
        desktop = stage/"usr"/"share"/"applications"
        desktop.mkdir(parents=True)
        (desktop/"nvp.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=NVP\n"
            "Exec=/usr/bin/nvp\nTerminal=false\n"
            "Icon=video-x-generic\nCategories=AudioVideo;Video;\n",
            encoding="utf8")
        meta = stage/"DEBIAN"
        meta.mkdir()
        (meta/"control").write_text(
            "Package: nvp\n"
            f"Version: {version}\n"
            "Architecture: amd64\n"
            f"Maintainer: {maintainer}\n"
            "Section: video\nPriority: optional\n"
            "Depends: libgtk-3-0, libwebkit2gtk-4.1-0, gir1.2-gtk-3.0, gir1.2-webkit2-4.1\n"
            "Description: NVP original-data-first offline film desktop\n",
            encoding="utf8")
        subprocess.run(
            [binary, "--root-owner-group", "--build", str(stage), str(output)],
            check=True, capture_output=True, text=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("dpkg-deb did not produce a real installation candidate")
    return {
        "format": FORMAT, "status": "UNINSTALLED_LINUX_DEB_CANDIDATE",
        "version": version, "architecture": "amd64",
        "source_exe_sha256": audit["exe_sha256"],
        "source_payload_files": len(audit["files"]),
        "package_sha256": _digest(output),
        "linux_app_executed": False,
        "cgroup_worker_admission_verified": False,
        "installed_film_preservation_verified": False,
        "redistribution_licenses_verified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--maintainer", required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    result = build_deb(
        args.bundle, args.output, version=args.version, maintainer=args.maintainer)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        with args.receipt.open("x", encoding="utf8") as stream:
            stream.write(rendered)
    print(rendered)


if __name__ == "__main__":
    main()
