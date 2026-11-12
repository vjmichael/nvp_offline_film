"""W1-G Windows NSIS program-only rollback and interrupted-swap recovery.

Use after NSIS has preserved NVP.previous. Never delete Films/Projects,
silently delete the failed executable, or substitute PID-only assertions for
the installed OS supervisor's verified worker-empty receipt. All actual
rename operations require a one-use trusted native authorization.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

from tools.nvp_e2e01e_validate_installer_payload import verify_pe64_gui
from tools.nvp_w1g_native_package import _inventory

FORMAT="nvp.w1g.nsis.rollback.v1"
MARKER=b"NVP-ALPHA-INSTALL-v1"


def _digest(files):
    return sha256(json.dumps(files,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def _program(root):
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Dedicated Windows NVP runtime directory absent or linked")
    marker=root/"nvp-alpha-install.marker"
    if marker.is_symlink() or not marker.is_file() or marker.read_bytes()!=MARKER:
        raise RuntimeError("NVP installer ownership marker is missing or invalid")
    verify_pe64_gui(root/"NVP.exe")
    return _inventory(root)


def _write(path,doc):
    tmp=path.with_suffix(".new")
    if tmp.exists() or tmp.is_symlink():
        raise RuntimeError("Prior interrupted NSIS journal write requires owner review")
    with tmp.open("x",encoding="utf8") as f:
        json.dump(doc,f,sort_keys=True,separators=(",",":"))
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)


class OwnedNSISRecovery:
    def __init__(self,programs:Path,original_films:Path,
                 journal_root:Path,*,native_approve,os_workers_stopped,
                 test_only_simulation=False):
        if not callable(native_approve) or not callable(os_workers_stopped):
            raise TypeError("Real native authorization and independent OS process custody required")
        self.test_only_simulation=(test_only_simulation is True)
        if not self.test_only_simulation:
            from tools.nvp_w1g_production_authority import (
                WindowsCreatorUpgradeApproval, WindowsReleaseWorkerStopEvidence,
            )
            if (type(native_approve) is not WindowsCreatorUpgradeApproval or
                type(os_workers_stopped) is not WindowsReleaseWorkerStopEvidence):
                raise PermissionError(
                    "Production NSIS rollback owner cannot accept synthetic callbacks")
        self.programs=Path(programs).absolute()
        self.films=Path(original_films).absolute()
        self.journal_root=Path(journal_root).absolute()
        self.active=self.programs/"NVP"
        self.old=self.programs/"NVP.previous"
        self.failed=self.programs/"NVP.failed"
        self.pending=self.programs/"NVP.pending"
        if (not self.programs.is_dir() or self.programs.is_symlink() or
            not self.films.is_dir() or self.films.is_symlink() or
            not self.journal_root.is_dir() or self.journal_root.is_symlink() or
            self.films == self.programs or self.programs in self.films.parents or
            self.journal_root == self.programs or self.programs in self.journal_root.parents):
            raise RuntimeError("NSIS rollback roots must be disjoint from original films")
        self.journal=self.journal_root/"nsis-rollback.json"
        self.authorize=native_approve
        self.stopped=os_workers_stopped

    def _read(self):
        if self.journal.is_symlink() or not self.journal.is_file():
            raise RuntimeError("No verifiable NSIS rollback checkpoint")
        row=json.loads(self.journal.read_text("utf8"))
        if (row.get("format")!=FORMAT or row.get("program_root")!=str(self.programs) or
            row.get("original_root")!=str(self.films)):
            raise RuntimeError("Untrusted NSIS rollback journal identity")
        if _digest(_inventory(self.films))!=row["original_films_sha256"]:
            raise RuntimeError("Creator original films changed; rollback cannot be accepted")
        return row

    def prepare(self):
        if self.journal.exists() or self.journal.is_symlink():
            raise RuntimeError("Previous NSIS rollback journal requires reconciliation")
        if any(path.exists() or path.is_symlink() for path in (self.failed,self.pending)):
            raise RuntimeError("Another incomplete NSIS upgrade has unresolved program artifacts")
        current=_program(self.active)
        previous=_program(self.old)
        if _digest(current)==_digest(previous):
            raise RuntimeError("NSIS previous/current program revisions are identical")
        doc={"format":FORMAT,"state":"PREPARED",
             "program_root":str(self.programs),"original_root":str(self.films),
             "active_sha256":_digest(current),"previous_sha256":_digest(previous),
             "original_films_sha256":_digest(_inventory(self.films)),
             "independent_os_acceptance":False}
        _write(self.journal,doc)
        return dict(doc)

    def rollback(self):
        if not self.test_only_simulation:
            raise PermissionError(
                "Production rollback requires kernel-held ProductionWindowsNSISRollback")
        record=self._read()
        if record["state"]!="PREPARED":
            raise RuntimeError("Interrupted/consumed NSIS recovery cannot be replayed")
        if (_digest(_program(self.active))!=record["active_sha256"] or
            _digest(_program(self.old))!=record["previous_sha256"] or
            self.failed.exists() or self.failed.is_symlink()):
            raise RuntimeError("Original program candidates changed since rollback preparation")
        scope={"operation":"nvp.w1g.nsis.rollback.v1",
               "new_program_sha256":record["active_sha256"],
               "old_program_sha256":record["previous_sha256"],
               "original_film_sha256":record["original_films_sha256"]}
        if (self.stopped() is not True or
            self.authorize(dict(scope)) is not True or
            self.stopped() is not True):
            raise PermissionError("Rollback requires one human action and proven empty OS worker tree")
        record["state"]="SWAP_INTENT"
        _write(self.journal,record)
        os.replace(self.active,self.failed)
        record["state"]="NEW_PARKED"
        _write(self.journal,record)
        self._restore(record)
        return {"status":"NSIS_PREVIOUS_PROGRAM_RESTORED",
                "failed_new_program_preserved":True,
                "creator_films_modified":False}

    def _restore(self,record):
        if self.active.exists() or self.active.is_symlink():
            raise RuntimeError("Cannot restore prior NVP over an existing directory")
        if _digest(_program(self.old))!=record["previous_sha256"]:
            raise RuntimeError("Previously installed executable integrity changed")
        if self.stopped() is not True:
            raise PermissionError("OS cannot establish workers are stopped")
        os.replace(self.old,self.active)
        if (_digest(_program(self.active))!=record["previous_sha256"] or
            _digest(_inventory(self.films))!=record["original_films_sha256"]):
            raise RuntimeError("Previous program or creator films changed during rollback")
        record["state"]="ROLLED_BACK"
        _write(self.journal,record)
        if os.name=="nt":
            from tools.nvp_w1g_nsis_activation import (
                _version, _registry_version, _update_registration)
            # The restored real program's version and uninstall registration
            # must agree. A registry failure cannot be accepted as rollback.
            expected=_version(self.active)
            _update_registration(expected)
            if _registry_version()!=expected:
                raise RuntimeError("Native Windows rollback registration did not reconcile")


    def recover_stranded_previous(self):
        """Recover NSIS's interrupted first/second rename without prior Python journal.

        NSIS owns the original promotion operation, so a Windows power cut
        can leave NVP.previous and NVP.pending while NVP itself is absent.
        This recovery never deletes pending bytes or invents install success.
        """
        if not self.test_only_simulation:
            raise PermissionError(
                "Production interrupted recovery requires a new kernel-held human approval")
        if self.journal.exists() or self.journal.is_symlink():
            raise RuntimeError("Existing rollback journal must reconcile first")
        if (self.active.exists() or self.active.is_symlink() or
            not self.old.is_dir() or self.old.is_symlink() or
            self.failed.exists() or self.failed.is_symlink()):
            raise RuntimeError("Only a missing active program with intact previous NVP may be recovered")
        old_files=_program(self.old)
        original_files=_inventory(self.films)
        scope={
            "operation":"nvp.w1g.nsis.restore_stranded_previous.v1",
            "previous_sha256":_digest(old_files),
            "original_films_sha256":_digest(original_files),
            "active_program_absent":True,
        }
        if (self.stopped() is not True or
            self.authorize(dict(scope)) is not True or
            self.stopped() is not True):
            raise PermissionError("Stranded NSIS recovery requires human approval and OS custody")
        if (_digest(_program(self.old))!=scope["previous_sha256"] or
            _digest(_inventory(self.films))!=scope["original_films_sha256"] or
            self.active.exists() or self.active.is_symlink()):
            raise RuntimeError("Previous program/creator originals changed during recovery approval")
        row={
            "format":FORMAT,"state":"RESTORING_STRANDED",
            "program_root":str(self.programs),"original_root":str(self.films),
            "active_sha256":None,
            "previous_sha256":scope["previous_sha256"],
            "original_films_sha256":scope["original_films_sha256"],
            "independent_os_acceptance":False,
        }
        _write(self.journal,row)
        os.replace(self.old,self.active)
        if _digest(_program(self.active))!=row["previous_sha256"]:
            raise RuntimeError("Recovered previous NVP differs from attested executable")
        row["state"]="ROLLED_BACK"
        _write(self.journal,row)
        return {"status":"NSIS_STRANDED_PREVIOUS_RESTORED",
                "creator_films_modified":False,
                "candidate_preserved_for_owner_review":self.pending.exists()}

    def reconcile(self):
        if not self.test_only_simulation:
            raise PermissionError(
                "Production interrupted recovery cannot use test-only callback reconciliation")
        record=self._read()
        if record["state"]=="RESTORING_STRANDED":
            if self.active.is_dir() and not self.old.exists():
                if _digest(_program(self.active))!=record["previous_sha256"]:
                    raise RuntimeError("Stranded previous runtime corrupted during OS restoration")
                record["state"]="ROLLED_BACK"
                _write(self.journal,record)
                return {"state":"ROLLED_BACK","recovery_executed":False}
            if self.active.exists() or self.active.is_symlink():
                raise RuntimeError("Stranded recovery has ambiguous installed program identity")
            if self.stopped() is not True:
                raise PermissionError("Kernel worker containment still unverified")
            self._restore(record)
            return {"state":"ROLLED_BACK","recovery_executed":True}
        if record["state"]=="ROLLED_BACK":
            if _digest(_program(self.active))!=record["previous_sha256"]:
                raise RuntimeError("Recovered NVP runtime changed since rollback")
            return {"state":"ROLLED_BACK","recovery_executed":False}
        if record["state"]=="SWAP_INTENT" and self.active.is_dir():
            if (_digest(_program(self.active))==record["active_sha256"] and
                not self.failed.exists()):
                # Crash before first rename, not evidence of an upgrade.
                return {"state":"SWAP_INTENT","recovery_executed":False}
            raise RuntimeError("NSIS journal and active runtime diverged; owner review required")
        if record["state"] not in ("SWAP_INTENT","NEW_PARKED"):
            return {"state":record["state"],"recovery_executed":False}
        if self.active.exists() or self.active.is_symlink() or not self.failed.is_dir():
            raise RuntimeError("Ambiguous interrupted NSIS swap; no automatic destructive recovery")
        if _digest(_program(self.failed))!=record["active_sha256"]:
            raise RuntimeError("Parked failed release changed; cannot reconcile")
        self._restore(record)
        return {"state":"ROLLED_BACK","recovery_executed":True}
