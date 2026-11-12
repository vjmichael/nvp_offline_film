"""W1-G: hash-pinned installed native payload and film-preservation audit.

Audit a real PyInstaller Windows GUI bundle already admitted by E2E-01E.
The build receipt stays OUTSIDE the installed directory so an installed
payload cannot silently rewrite its own expected hashes. No tool here
installs dependencies, launches workers, deletes work or approves production.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

try:
    from .nvp_e2e01e_validate_installer_payload import verify_bundle
except ImportError:  # Direct invocation from the tools/ directory.
    from nvp_e2e01e_validate_installer_payload import verify_bundle

FORMAT = "nvp.w1g.native_payload.v1"
PRESERVE_FORMAT = "nvp.w1g.original_film_snapshot.v1"
INSTALLER_OWNED = frozenset(("nvp-alpha-install.marker", "nvp-alpha-version.txt", "Uninstall NVP.exe"))


def _digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fd:
        for chunk in iter(lambda: fd.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def _inventory(root: Path) -> dict:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("Required native payload directory is unavailable or linked")
    result = {}
    for member in sorted(root.rglob("*")):
        if member.is_symlink():
            raise RuntimeError("Linked files/directories cannot enter a native payload")
        if not member.is_file():
            if not member.is_dir():
                raise RuntimeError("Unsupported native payload filesystem object")
            continue
        relative = member.relative_to(root).as_posix()
        if relative.casefold() in (key.casefold() for key in result):
            raise RuntimeError("Case-folded installed destination collision")
        result[relative] = {"bytes": member.stat().st_size, "sha256": _digest(member)}
    return result


def _forbidden_native_binaries(paths) -> None:
    for path in paths:
        leaf = path.rsplit("/", 1)[-1].casefold()
        if (leaf in ("ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe") or
            leaf.startswith(("avcodec-", "avformat-", "avutil-",
                             "libavcodec.", "libavformat.", "libavutil."))):
            raise RuntimeError("Retired FFmpeg native library/tool bundled in NVP: " + path)


def build_receipt(bundle: Path) -> dict:
    evidence = verify_bundle(bundle)
    files = _inventory(bundle)
    _forbidden_native_binaries(files)
    if "NVP.exe" not in files or "_internal/base_library.zip" not in files:
        raise RuntimeError("Incomplete native Windows runtime inventory")
    worker_root = folder / "_internal" / "nvp_workers"
    workers = None
    if worker_root.exists() or worker_root.is_symlink():
        try:
            from tools.nvp_w1g_worker_package import verify_native_workers
        except ModuleNotFoundError:
            from nvp_w1g_worker_package import verify_native_workers
        workers = verify_native_workers(folder, expected_platform="windows-amd64")
    return {
        "format": FORMAT,
        "platform": "windows-amd64",
        "source": "audited-real-pyinstaller-onedir",
        "app_sha256": evidence["exe"]["sha256"],
        "files": files,
        "native_worker_code_pinned_by_content": workers is not None,
        "native_worker_manifest_verified": workers is not None,
        "native_runtime_executed": False,
        "redistribution_licenses_verified": False,
        "physical_install_verified": False,
    }


def verify_installed(receipt: dict, installed: Path) -> dict:
    if (type(receipt) is not dict or receipt.get("format") != FORMAT or
        receipt.get("platform") != "windows-amd64" or
        type(receipt.get("files")) is not dict):
        raise ValueError("Trusted external W1-G build receipt required")
    actual = _inventory(installed)
    unexpected = set(actual) - set(receipt["files"])
    if unexpected - INSTALLER_OWNED:
        raise RuntimeError("Installed native payload includes unexpected files")
    if set(receipt["files"]) - set(actual):
        raise RuntimeError("Installed native payload is missing audited files")
    for path, expected in receipt["files"].items():
        if (type(expected) is not dict or
            type(expected.get("sha256")) is not str or
            type(expected.get("bytes")) is not int or
            actual[path] != expected):
            raise RuntimeError("Installed native worker/runtime byte mismatch: " + path)
    if actual["NVP.exe"]["sha256"] != receipt.get("app_sha256"):
        raise RuntimeError("Installed native host identity differs from build")
    _forbidden_native_binaries(actual)
    if receipt.get("native_worker_manifest_verified") is True:
        try:
            from tools.nvp_w1g_worker_package import verify_native_workers
        except ModuleNotFoundError:
            from nvp_w1g_worker_package import verify_native_workers
        verify_native_workers(installed, expected_platform="windows-amd64")
    elif (installed / "_internal" / "nvp_workers").exists():
        raise RuntimeError("Installed native workers lack a reviewed executable roster")
    return {
        "status": "W1G_INSTALLED_BYTES_MATCH_BUILD",
        "files_verified": len(receipt["files"]),
        "app_sha256": receipt["app_sha256"],
        "native_worker_manifest_verified": receipt.get("native_worker_manifest_verified") is True,
        "live_worker_custody_verified": False,
        "license_compliance_verified": False,
    }


def original_film_snapshot(project_directory: Path) -> dict:
    """Read-only hashes of user projects OUTSIDE the program install root."""
    files = _inventory(project_directory)
    if not files:
        raise RuntimeError("No original film project data found to preserve")
    return {"format": PRESERVE_FORMAT, "files": files}


def verify_original_films_preserved(snapshot: dict, project_directory: Path) -> dict:
    if (type(snapshot) is not dict or snapshot.get("format") != PRESERVE_FORMAT
        or type(snapshot.get("files")) is not dict or not snapshot["files"]):
        raise ValueError("Original film baseline required")
    current = _inventory(project_directory)
    for path, original in snapshot["files"].items():
        if path not in current or current[path] != original:
            raise RuntimeError("User-owned original film changed across package lifecycle: " + path)
    return {"status": "W1G_ORIGINAL_FILM_BYTES_PRESERVED",
            "original_files_verified": len(snapshot["files"])}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("build", "verify-install",
                                        "snapshot-films", "verify-films"))
    ap.add_argument("--bundle", type=Path)
    ap.add_argument("--installed", type=Path)
    ap.add_argument("--projects", type=Path)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args(argv)
    if args.action == "build":
        if args.bundle is None:
            ap.error("--bundle required")
        result = build_receipt(args.bundle)
    elif args.action == "snapshot-films":
        if args.projects is None:
            ap.error("--projects required")
        result = original_film_snapshot(args.projects)
    else:
        if args.receipt is None:
            ap.error("--receipt required")
        source = json.loads(args.receipt.read_text("utf8"))
        if args.action == "verify-install":
            if args.installed is None:
                ap.error("--installed required")
            result = verify_installed(source, args.installed)
        else:
            if args.projects is None:
                ap.error("--projects required")
            result = verify_original_films_preserved(source, args.projects)
    data = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf8") as fd:
            fd.write(data)
    print(data)


if __name__ == "__main__":
    main()
