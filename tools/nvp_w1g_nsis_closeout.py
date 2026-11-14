"""W1-G post-NSIS acceptance closeout; no automatic recursive deletion.

The previous binary is archived only after a separately verified, exact
installed Windows launch/restart and film-data preservation receipt.
A failed pre-promotion stage is quarantined, never silently destroyed.
"""
from __future__ import annotations

from pathlib import Path
import os

from tools.nvp_w1g_nsis_recovery import (
    OwnedNSISRecovery, FORMAT, _program, _digest, _write,
)
from tools.nvp_w1g_native_package import _inventory


def _owner(owner):
    if not isinstance(owner,OwnedNSISRecovery):
        raise TypeError("Trusted NSIS owner-only lifecycle object required")


def archive_accepted_previous(owner:OwnedNSISRecovery,installed_acceptance):
    _owner(owner)
    if not callable(installed_acceptance):
        raise TypeError("Independent installed NVP acceptance verifier required")
    if any(x.exists() or x.is_symlink()
           for x in (owner.pending,owner.failed,owner.journal)):
        raise RuntimeError("NSIS upgrade or rollback remains unresolved")
    current=_digest(_program(owner.active))
    previous=_digest(_program(owner.old))
    films=_digest(_inventory(owner.films))
    scope={
        "operation":"nvp.w1g.nsis.archive_accepted_previous.v1",
        "current_sha256":current,"previous_sha256":previous,
        "original_films_sha256":films,
    }
    evidence=installed_acceptance(dict(scope))
    if (type(evidence) is not dict or
        evidence.get("current_runtime_sha256")!=current or
        evidence.get("installed_launch_verified") is not True or
        evidence.get("restart_verified") is not True or
        evidence.get("original_films_verified") is not True):
        raise RuntimeError("A real installed and reopened NVP release has not been accepted")
    if (owner.stopped() is not True or owner.authorize(dict(scope)) is not True or
        owner.stopped() is not True or
        _digest(_program(owner.active))!=current or
        _digest(_program(owner.old))!=previous or
        _digest(_inventory(owner.films))!=films):
        raise PermissionError("Exact NSIS release closeout lacks human/kernel evidence")
    archive=owner.journal_root/("previous_"+previous[:24])
    receipt=owner.journal_root/("previous_"+previous[:24]+".json")
    if any(x.exists() or x.is_symlink() for x in (archive,receipt)):
        raise RuntimeError("Previous program closeout identity already used")
    doc={"format":FORMAT,"state":"ARCHIVE_INTENT","archive":str(archive),**scope}
    _write(receipt,doc)
    os.replace(owner.old,archive)
    if (_digest(_program(archive))!=previous or
        _digest(_program(owner.active))!=current or
        _digest(_inventory(owner.films))!=films):
        raise RuntimeError("Previous program archive/creator films changed after move")
    doc["state"]="PREVIOUS_ARCHIVED"
    _write(receipt,doc)
    return {"status":"NSIS_PREVIOUS_VERSION_PRESERVED_IN_HISTORY",
            "next_upgrade_slot_clear":not owner.old.exists(),
            "original_films_modified":False}


def quarantine_failed_stage(owner:OwnedNSISRecovery):
    _owner(owner)
    if (not owner.active.is_dir() or owner.old.exists() or
        owner.failed.exists() or owner.journal.exists() or
        not owner.pending.is_dir() or owner.pending.is_symlink()):
        raise RuntimeError("Only abandoned pre-promotion stage may be quarantined")
    current=_digest(_program(owner.active))
    staged=_digest(_inventory(owner.pending))
    films=_digest(_inventory(owner.films))
    scope={"operation":"nvp.w1g.nsis.quarantine_aborted_stage.v1",
           "current_sha256":current,"staged_sha256":staged,
           "original_films_sha256":films}
    if (owner.stopped() is not True or
        owner.authorize(dict(scope)) is not True or
        owner.stopped() is not True or
        _digest(_program(owner.active))!=current or
        _digest(_inventory(owner.pending))!=staged or
        _digest(_inventory(owner.films))!=films):
        raise PermissionError("Unsafe cleanup of abandoned native installation stage")
    quarantine=owner.journal_root/("abandoned_stage_"+staged[:24])
    receipt=owner.journal_root/("abandoned_stage_"+staged[:24]+".json")
    if quarantine.exists() or quarantine.is_symlink() or receipt.exists():
        raise RuntimeError("Stage quarantine identity already occupied")
    doc={"format":FORMAT,"state":"QUARANTINE_INTENT",
         "quarantine":str(quarantine),**scope}
    _write(receipt,doc)
    os.replace(owner.pending,quarantine)
    if _digest(_inventory(quarantine))!=staged:
        raise RuntimeError("Quarantined native candidate bytes changed")
    doc["state"]="QUARANTINED"
    _write(receipt,doc)
    return {"status":"NSIS_FAILED_CANDIDATE_PRESERVED",
            "old_program_untouched":True,
            "creator_films_modified":False}
