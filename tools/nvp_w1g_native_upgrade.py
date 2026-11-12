"""W1-G same-filesystem, side-by-side native runtime upgrade and recovery.

No in-place overwrites. Original creator films live OUTSIDE this program
directory. Activation requires real native human consent and an OS-owned
proof the app and workers are stopped. NSIS-managed Windows directories
are deliberately refused until an installer-aware upgrade is integrated.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

try:
    from .nvp_w1g_native_package import _inventory
except ImportError:
    from nvp_w1g_native_package import _inventory

FORMAT = "nvp.w1g.side_by_side_upgrade.v1"
STATES = frozenset(("PREPARED", "SWAPPING", "OLD_PARKED", "ACTIVE", "ROLLBACK_PENDING", "ROLLED_BACK", "UNCERTAIN"))


def _fingerprint(files):
    return sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_journal(journal, record):
    # Caller-selected journal resides outside the application and creator data.
    tmp = journal.with_suffix(".new")
    if tmp.exists() or tmp.is_symlink():
        raise RuntimeError("Another unfinished upgrade journal update exists")
    with tmp.open("x", encoding="utf8") as fd:
        json.dump(record, fd, sort_keys=True, separators=(",", ":"))
        fd.flush()
        os.fsync(fd.fileno())
    os.replace(tmp, journal)


def _load(journal):
    if journal.is_symlink() or not journal.is_file():
        raise RuntimeError("Native upgrade journal unavailable")
    doc = json.loads(journal.read_text("utf8"))
    if type(doc) is not dict or doc.get("format") != FORMAT or doc.get("state") not in STATES:
        raise RuntimeError("Invalid durable native upgrade journal")
    return doc


def _inside(child, root):
    return child == root or root in child.parents


class SideBySideNativeUpgrade:
    """Creator-operated program-only transaction, no arbitrary user path API."""

    def __init__(self, install: Path, staging_root: Path,
                 film_root: Path, *, native_authorize, os_workers_stopped):
        if not callable(native_authorize) or not callable(os_workers_stopped):
            raise TypeError("Native human and independently verified OS stop callbacks required")
        self.install = Path(install).absolute()
        self.staging = Path(staging_root).absolute()
        self.films = Path(film_root).absolute()
        self.authorize = native_authorize
        self.stopped = os_workers_stopped
        if (not self.install.is_dir() or self.install.is_symlink() or
            not self.staging.is_dir() or self.staging.is_symlink() or
            not self.films.is_dir() or self.films.is_symlink() or
            self.install == self.staging or
            self.install.parent != self.staging.parent or
            _inside(self.films, self.install) or
            _inside(self.install, self.films) or
            _inside(self.staging, self.films)):
            raise RuntimeError("Native upgrade requires disjoint program and original-film roots")
        if ((self.install/"nvp-alpha-install.marker").exists() or
            (self.install/"Uninstall NVP.exe").exists()):
            raise RuntimeError("NSIS-owned program upgrade requires installer-aware transaction")
        self.journal = self.staging/"nvp-upgrade-journal.json"

    def prepare(self, new_bundle: Path):
        if self.journal.exists() or self.journal.is_symlink():
            raise RuntimeError("Unresolved native upgrade must reconcile before another preparation")
        incoming = Path(new_bundle)
        if not incoming.is_dir() or incoming.is_symlink():
            raise RuntimeError("New native executable bundle is missing or linked")
        old_files = _inventory(self.install)
        film_files = _inventory(self.films)
        new_files = _inventory(incoming)
        if not old_files or not new_files or not film_files:
            raise RuntimeError("Cannot upgrade without real runtimes and original-film baseline")
        if "NVP" not in old_files or "NVP" not in new_files:
            raise RuntimeError("Only established genuine NVP native runtime may upgrade")
        if _fingerprint(old_files) == _fingerprint(new_files):
            raise RuntimeError("Upgrade candidate is byte-for-byte identical to installed NVP")
        target = self.staging/"next"
        backup = self.staging/"previous"
        if any(p.exists() or p.is_symlink() for p in (target, backup)):
            raise RuntimeError("Prior upgraded or rollback runtime is unresolved")
        shutil.copytree(incoming, target, symlinks=False)
        if _inventory(target) != new_files:
            raise RuntimeError("Native upgrade staging differs from approved incoming build")
        if _inventory(self.films) != film_files:
            raise RuntimeError("Original films changed during upgrade preparation")
        plan = {
            "format": FORMAT, "state": "PREPARED",
            "old_sha256": _fingerprint(old_files),
            "new_sha256": _fingerprint(new_files),
            "film_sha256": _fingerprint(film_files),
            "program_location": str(self.install),
            "staging_location": str(self.staging),
            "original_film_location": str(self.films),
            "physical_installed_acceptance": False,
        }
        _write_journal(self.journal, plan)
        return dict(plan)

    def _checked(self):
        record = _load(self.journal)
        if (record["program_location"] != str(self.install) or
            record["staging_location"] != str(self.staging) or
            record["original_film_location"] != str(self.films)):
            raise RuntimeError("Upgrade journal belongs to another native program")
        if _fingerprint(_inventory(self.films)) != record["film_sha256"]:
            raise RuntimeError("Creator's original film files changed during runtime upgrade")
        return record

    def activate(self):
        record = self._checked()
        if record["state"] != "PREPARED":
            raise RuntimeError("Only a freshly prepared native runtime can activate")
        candidate = self.staging/"next"
        backup = self.staging/"previous"
        if (backup.exists() or backup.is_symlink() or
            _fingerprint(_inventory(self.install)) != record["old_sha256"] or
            _fingerprint(_inventory(candidate)) != record["new_sha256"]):
            raise RuntimeError("Native upgrade source changed before activation")
        scope = {
            "operation": "nvp.w1g.native_program_upgrade.v1",
            "old_sha256": record["old_sha256"], "new_sha256": record["new_sha256"],
            "original_film_sha256": record["film_sha256"],
            "creator_films_modified": False,
        }
        if self.stopped() is not True:
            raise PermissionError("OS did not independently prove all native workers stopped")
        if self.authorize(dict(scope)) is not True:
            raise PermissionError("Human refused exact native program upgrade")
        if self.stopped() is not True or self._checked() != record:
            raise RuntimeError("OS custody or original-film baseline changed during approval")
        # Journal an intent before the first rename so power loss is recoverable.
        record["state"] = "SWAPPING"
        _write_journal(self.journal, record)
        os.replace(self.install, backup)
        record["state"] = "OLD_PARKED"
        _write_journal(self.journal, record)
        try:
            os.replace(candidate, self.install)
            if (_fingerprint(_inventory(self.install)) != record["new_sha256"] or
                _fingerprint(_inventory(self.films)) != record["film_sha256"]):
                raise RuntimeError("Installed upgrade or original films failed identity check")
            record["state"] = "ACTIVE"
            _write_journal(self.journal, record)
        except BaseException:
            # Leave an independently recognizable OLD_PARKED journal and
            # backup rather than deleting/replaying any native executable.
            raise
        return {"status": "NATIVE_UPGRADE_ACTIVE_UNACCEPTED",
                "old_bytes_preserved_for_rollback": True,
                "physical_installed_acceptance": False}

    def reconcile(self):
        record = self._checked()
        if record["state"] not in ("SWAPPING", "OLD_PARKED", "ACTIVE", "ROLLBACK_PENDING"):
            return {"state": record["state"], "recovery_executed": False}
        previous = self.staging/"previous"
        if record["state"] == "SWAPPING" and not previous.exists():
            if (self.install.is_dir() and
                _fingerprint(_inventory(self.install)) == record["old_sha256"]):
                record["state"] = "ROLLED_BACK"
                _write_journal(self.journal, record)
                return {"state": "ROLLED_BACK", "recovery_executed": False}
            raise RuntimeError("Interrupted upgrade lacks independently verified original runtime")
        if (_fingerprint(_inventory(previous)) != record["old_sha256"]):
            raise RuntimeError("Previous native runtime missing or corrupted; refuse recovery")
        if record["state"] == "ROLLBACK_PENDING":
            retired = self.staging/"retired-new"
            if self.install.is_dir():
                if _fingerprint(_inventory(self.install)) == record["old_sha256"]:
                    record["state"] = "ROLLED_BACK"
                    _write_journal(self.journal, record)
                    return {"state": "ROLLED_BACK", "recovery_executed": False}
                raise RuntimeError("Ambiguous interrupted rollback; OS/manual review required")
            if not retired.is_dir() or _fingerprint(_inventory(retired)) != record["new_sha256"]:
                raise RuntimeError("Unverified interrupted rollback; manual recovery required")
            if self.stopped() is not True:
                raise PermissionError("OS has not verified stopped workers")
            os.replace(previous, self.install)
            record["state"] = "ROLLED_BACK"
            _write_journal(self.journal, record)
            return {"state": "ROLLED_BACK", "recovery_executed": True}
        if record["state"] in ("SWAPPING", "OLD_PARKED") and self.install.is_dir():
            if _fingerprint(_inventory(self.install)) == record["new_sha256"]:
                if self.stopped() is not True:
                    raise PermissionError("OS has not verified stopped upgraded runtime")
                record["state"] = "ACTIVE"
                _write_journal(self.journal, record)
                return {"state": "ACTIVE", "recovery_executed": False}
            raise RuntimeError("Interrupted runtime upgrade left an ambiguous installed tree")
        if record["state"] == "ACTIVE":
            if _fingerprint(_inventory(self.install)) != record["new_sha256"]:
                raise RuntimeError("Active upgraded runtime changed; manual OS recovery required")
            return {"state": "ACTIVE", "recovery_executed": False}
        if self.install.exists() or self.install.is_symlink():
            raise RuntimeError("Interrupted upgrade has ambiguous installed root; manual recovery required")
        # Safe old-runtime recovery is a single rename; no new authorization
        # can be recycled and no creator-owned source files are touched.
        if self.stopped() is not True:
            raise PermissionError("Cannot restore original program while workers remain")
        os.replace(previous, self.install)
        record["state"] = "ROLLED_BACK"
        _write_journal(self.journal, record)
        return {"state": "ROLLED_BACK", "recovery_executed": True}

    def rollback(self):
        record = self._checked()
        if record["state"] != "ACTIVE":
            raise RuntimeError("Only an accepted journal ACTIVE state may request rollback")
        old, retired = self.staging/"previous", self.staging/"retired-new"
        if (retired.exists() or retired.is_symlink() or
            _fingerprint(_inventory(old)) != record["old_sha256"] or
            _fingerprint(_inventory(self.install)) != record["new_sha256"]):
            raise RuntimeError("Native rollback source provenance changed")
        if self.stopped() is not True or self.authorize({
            "operation": "nvp.w1g.native_program_rollback.v1",
            "old_sha256": record["old_sha256"], "new_sha256": record["new_sha256"],
        }) is not True or self.stopped() is not True:
            raise PermissionError("Native human/OS stop approval required for rollback")
        record["state"] = "ROLLBACK_PENDING"
        _write_journal(self.journal, record)
        os.replace(self.install, retired)
        try:
            os.replace(old, self.install)
            if (_fingerprint(_inventory(self.install)) != record["old_sha256"] or
                _fingerprint(_inventory(self.films)) != record["film_sha256"]):
                raise RuntimeError("Rollback bytes or original films changed")
            record["state"] = "ROLLED_BACK"
            _write_journal(self.journal, record)
        except BaseException:
            # Both dirs remain separately identifiable; never delete evidence.
            raise
        return {"status": "NATIVE_PROGRAM_ROLLED_BACK",
                "original_films_preserved": True,
                "failed_upgrade_preserved_for_review": True}
