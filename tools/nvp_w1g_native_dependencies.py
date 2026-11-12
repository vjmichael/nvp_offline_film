"""W1-G offline native dependency admission and atomic Python wheel provisioning.

Release creator supplies a reviewed, exact SHA wheel lock; this tool does NOT
choose versions, contact PyPI, silently use machine caches or install into the
user/global environment. pip enforces the complete transitive wheel lock.
Actual native redistribution/license review and installed workers stay gated.
"""
from __future__ import annotations

import argparse
from email.parser import Parser
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import shutil
import subprocess
import sys
import tempfile
import zipfile

FORMAT = "nvp.w1g.offline_native_wheel_lock.v1"
DIST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_!~-]{0,99}$")
HASH = re.compile(r"^[a-f0-9]{64}$")
PLATFORMS = ("windows-amd64", "linux-amd64")


def _canonical(s: str) -> str:
    return re.sub(r"[-_.]+", "-", s).lower()


def _sha(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fd:
        for part in iter(lambda: fd.read(1048576), b""):
            h.update(part)
    return h.hexdigest()


def validate_lock(lock: dict, wheelhouse: Path, *, platform: str) -> list:
    if (type(lock) is not dict or lock.get("format") != FORMAT or
        lock.get("platform") != platform or platform not in PLATFORMS or
        type(lock.get("wheels")) is not list or
        not 1 <= len(lock["wheels"]) <= 500 or
        not wheelhouse.is_dir() or wheelhouse.is_symlink()):
        raise RuntimeError("Native offline release requires a platform-specific reviewed wheel lock")
    seen = set()
    verified = []
    for entry in lock["wheels"]:
        if type(entry) is not dict or set(entry) != {
                "name", "version", "filename", "sha256", "license_review"}:
            raise RuntimeError("Wheel lock has unknown or missing provenance fields")
        name, version = entry["name"], entry["version"]
        filename, digest = entry["filename"], entry["sha256"]
        if (type(name) is not str or not DIST.fullmatch(name) or
            type(version) is not str or not VERSION.fullmatch(version) or
            type(filename) is not str or filename != Path(filename).name or
            not filename.endswith(".whl") or type(digest) is not str or
            not HASH.fullmatch(digest) or
            type(entry["license_review"]) is not str or
            not 5 <= len(entry["license_review"]) <= 500):
            raise RuntimeError("Invalid pinned wheel metadata or missing license-review reference")
        key = _canonical(name)
        if key in seen:
            raise RuntimeError("Duplicate distribution in the exact offline dependency lock")
        seen.add(key)
        wheel = wheelhouse/filename
        if not wheel.is_file() or wheel.is_symlink() or _sha(wheel) != digest:
            raise RuntimeError("Wheel is missing or differs from creator-reviewed SHA: " + name)
        if (platform == "windows-amd64" and
            not ("-win_amd64.whl" in filename or "-any.whl" in filename)):
            raise RuntimeError("Wrong architecture Windows native wheel: " + filename)
        if (platform == "linux-amd64" and
            not (("x86_64.whl" in filename and
                  ("manylinux" in filename or "linux_" in filename)) or
                 "-any.whl" in filename)):
            raise RuntimeError("Wrong architecture Linux native wheel: " + filename)
        if not zipfile.is_zipfile(wheel):
            raise RuntimeError("Pinned dependency is not a genuine wheel archive")
        with zipfile.ZipFile(wheel) as z:
            members=z.infolist()
            if not 1<=len(members)<=10000:
                raise RuntimeError("Wheel has unsafe/unbounded archive entry count")
            names=set()
            expanded=0
            for member in members:
                path=PurePosixPath(member.filename)
                if (not member.filename or
                    path.is_absolute() or
                    ".." in path.parts or
                    "\\" in member.filename or
                    ":" in member.filename or
                    member.filename.casefold() in names or
                    (member.create_system==3 and
                     stat.S_ISLNK(member.external_attr >> 16))):
                    raise RuntimeError("Unsafe linked/traversal/duplicate entry in native wheel")
                names.add(member.filename.casefold())
                expanded+=member.file_size
                if expanded>2*1024*1024*1024 or member.file_size>1024*1024*1024:
                    raise RuntimeError("Offline native wheel expands beyond release bound")
            metadata = [x.filename for x in members
                        if x.filename.endswith(".dist-info/METADATA")]
            if len(metadata) != 1:
                raise RuntimeError("Wheel lacks one authoritative distribution METADATA")
            if z.getinfo(metadata[0]).file_size > 1024*1024:
                raise RuntimeError("Wheel metadata exceeds native admission bound")
            header = Parser().parsestr(z.read(metadata[0]).decode("utf8"))
            if (_canonical(header.get("Name", "")) != key or
                header.get("Version") != version):
                raise RuntimeError("Wheel's embedded Name/Version disagrees with pinned lock")
        verified.append({**entry, "canonical_name": key})
    return verified


def provision(lock: dict, wheelhouse: Path, target: Path, *, platform: str,
              interpreter: str | Path = sys.executable) -> dict:
    wheels = validate_lock(lock, wheelhouse, platform=platform)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Never overwrite an approved native dependency runtime")
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise RuntimeError("Native dependency destination parent must already exist")
    # Explicit original executable path: no shell and no model-supplied
    # interpreter. The trusted packaging host must choose this itself.
    interpreter = Path(interpreter)
    if not interpreter.is_file() or interpreter.is_symlink():
        raise RuntimeError("Trusted packaging Python interpreter unavailable")
    with tempfile.TemporaryDirectory(prefix=".nvp-native-wheels-", dir=target.parent) as temp:
        root = Path(temp)
        stage = root/"lib"
        stage.mkdir()
        requirements = root/"locked.txt"
        requirements.write_text(
            "".join(f"{w['name']}=={w['version']} --hash=sha256:{w['sha256']}\n"
                    for w in wheels), encoding="ascii")
        # Never fall back to Internet, source builds, partial dependencies
        # or global/user pip site packages. Missing transitive pins fail.
        subprocess.run([
            str(interpreter), "-m", "pip", "install",
            "--no-index", "--no-cache-dir", "--disable-pip-version-check",
            "--require-hashes", "--only-binary=:all:",
            "--find-links", str(wheelhouse.resolve()), "--target", str(stage),
            "-r", str(requirements),
        ], check=True, timeout=600)
        installed = {}
        for dist in importlib.metadata.distributions(path=[str(stage)]):
            name = _canonical(dist.metadata["Name"])
            if name in installed:
                raise RuntimeError("Duplicate native dependency distribution after offline install")
            installed[name] = dist.version
        expected = {w["canonical_name"]: w["version"] for w in wheels}
        if installed != expected:
            raise RuntimeError("Offline native Python environment does not match exact reviewed lock")
        # Destination absent, staging entirely outside creator-film work.
        os.replace(stage, target)
    return {
        "format": FORMAT, "status": "OFFLINE_NATIVE_PYTHON_DEPENDENCIES_PROVISIONED",
        "platform": platform,
        "distribution_count": len(expected),
        "reviewed_lock_sha256": sha256(json.dumps(
            lock, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "network_used": False,
        "native_worker_executed": False,
        "license_acceptance_independently_verified": False,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("verify", "provision"))
    ap.add_argument("--lock", type=Path, required=True)
    ap.add_argument("--wheelhouse", type=Path, required=True)
    ap.add_argument("--platform", choices=PLATFORMS, required=True)
    ap.add_argument("--target", type=Path)
    args = ap.parse_args(argv)
    lock = json.loads(args.lock.read_text("utf8"))
    if args.action == "verify":
        result = {"status": "VERIFIED_OFFLINE_WHEEL_LOCK",
                  "wheel_count": len(validate_lock(
                      lock, args.wheelhouse, platform=args.platform))}
    else:
        if args.target is None:
            ap.error("--target required for native dependency provisioning")
        result = provision(lock, args.wheelhouse, args.target, platform=args.platform)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
