"""NVP-E2E-01B: durable bridge between existing authorized B13 and B14 hosts.

No new media worker or alternate authorization pipeline is created here:
NativeB13ImportHost and NativeB14ConformHost retain their own creator
approval, exact-source checks, SQLite task reservations, OS containment,
process-tree cancellation and independent output audits.

The coordinator binds the *finished* B13 FilmIndex revision to a new B14
approval and records a durable cross-phase handoff. Crash recovery NEVER
marks an unknown OS worker stopped, frees an ACTIVE RAM reservation, or
auto-renders after a missing receipt.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import time

from backend.nvp_b13_native_reimport import NativeB13ImportHost
from backend.nvp_b14_native_conform import NativeB14ConformHost
from backend.nvp_b13_editorial_roundtrip import verify_imported_edit
from backend.nvp_b14_picture_conform import verify_conformed_sdr16
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_film_index import _id

IDENT=re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,79}\Z")
STATES=frozenset({
    "IMPORT_STAGING_UNCERTAIN", "IMPORT_QUEUED", "IMPORT_VERIFIED",
    "CONFORM_STAGING_UNCERTAIN", "CONFORM_QUEUED",
    "CONFORM_VERIFIED", "CANCELLED_BEFORE_IMPORT", "BLOCKED_REVIEW"
})


class NativeEditorialChain:
    """One safely resumable technical edit -> picture-conform operation."""

    def __init__(self,capture:DigitalCapture,ledger:TaskLedger,
                 b13:NativeB13ImportHost,b14:NativeB14ConformHost):
        if (not isinstance(capture,DigitalCapture) or
            not isinstance(ledger,TaskLedger) or
            not isinstance(b13,NativeB13ImportHost) or
            not isinstance(b14,NativeB14ConformHost) or
            b13.capture.studio.db_path!=capture.studio.db_path or
            b14.capture.studio.db_path!=capture.studio.db_path or
            b13.ledger.db_path!=ledger.db_path or
            b14.ledger.db_path!=ledger.db_path):
            raise TypeError("Both native hosts must use the same FilmIndex and TaskLedger")
        self.capture,self.ledger,self.b13,self.b14=capture,ledger,b13,b14
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_e2e01b_chains(
                chain_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                delivery_id TEXT NOT NULL,
                edit_id TEXT NOT NULL,
                edit_revision INTEGER NOT NULL,
                edit_sha TEXT,
                package_dir TEXT NOT NULL,
                destination_dir TEXT NOT NULL,
                presentation_id TEXT NOT NULL,
                import_job TEXT NOT NULL UNIQUE,
                conform_job TEXT UNIQUE,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL)""")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS
                native_e2e01b_presentation_once
                ON native_e2e01b_chains(project_id,presentation_id)""")

    def _row(self,chain_id):
        with self.ledger._db() as db:
            db.row_factory=sqlite3.Row
            row=db.execute("""SELECT * FROM native_e2e01b_chains
                WHERE chain_id=?""",(chain_id,)).fetchone()
        if row is None:raise KeyError("Unknown E2E editorial chain")
        return dict(row)

    def _transition(self,chain_id,old,new,*,edit_sha=None,conform_job=None):
        if old not in STATES or new not in STATES:
            raise ValueError("Invalid editorial state")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            result=db.execute("""UPDATE native_e2e01b_chains
                SET state=?,edit_sha=COALESCE(?,edit_sha),
                    conform_job=COALESCE(?,conform_job),updated_at=?
                WHERE chain_id=? AND state=?""",
                (new,edit_sha,conform_job,time.time(),chain_id,old))
            if result.rowcount!=1:
                db.rollback()
                raise RuntimeError("Editorial phase changed concurrently; reopen")
            db.commit()

    def stage_edit(self,project_id,delivery_id,package_dir,incoming_otio,
                   creator_event,*,edit_id,presentation_id,destination_dir,
                   expected_edit_revision=0,ram_mb=1024):
        """Stage B13; no worker starts before the exact creator approval."""
        _id(edit_id,"NVP edited timeline")
        _id(presentation_id,"NVP B14 presentation")
        if edit_id==presentation_id or type(expected_edit_revision) is not int or expected_edit_revision<0:
            raise ValueError("Invalid native editorial source/revision identity")
        destination=Path(destination_dir).absolute()
        package_input=Path(package_dir)
        if package_input.is_symlink():
            raise RuntimeError("Original NVP source package must not be a symlink")
        package=package_input.resolve(strict=True)
        if (not package.is_dir() or package.is_symlink()
            or destination.exists() or destination.is_symlink()
            or not destination.parent.is_dir() or destination.parent.is_symlink()):
            raise RuntimeError("Editorial source/destination is missing or unsafe")
        # Durable intent is recorded first; if the native host stages a task
        # and the process dies before returning, do NOT stage a second task.
        chain_id="editorial_"+secrets.token_hex(16)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("""INSERT INTO native_e2e01b_chains VALUES
                    (?,?,?,?,?,NULL,?,?,?,?,NULL,?,?,?)""",
                    (chain_id,project_id,delivery_id,edit_id,
                     expected_edit_revision+1,str(package),str(destination),
                     presentation_id,"pending_"+chain_id,
                     "IMPORT_STAGING_UNCERTAIN",time.time(),time.time()))
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise RuntimeError(
                    "This presentation already has a durable native editorial chain; reopen it"
                ) from exc
            db.commit()
        ticket=self.b13.stage_and_approve(
            project_id,delivery_id,package,incoming_otio,creator_event,
            edit_id=edit_id,expected_revision=expected_edit_revision,
            ram_mb=ram_mb)
        if (ticket.get("state")!="QUEUED" or not ticket.get("job_id")):
            raise RuntimeError("Native B13 returned no durable queued worker ticket")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("""UPDATE native_e2e01b_chains
                SET import_job=?,state='IMPORT_QUEUED',updated_at=?
                WHERE chain_id=? AND state='IMPORT_STAGING_UNCERTAIN'""",
                (ticket["job_id"],time.time(),chain_id))
            if changed.rowcount!=1:
                db.rollback()
                raise RuntimeError("Import coordinator changed during native stage")
            db.commit()
        return {"chain_id":chain_id,"state":"IMPORT_QUEUED",
                "import_job":ticket["job_id"],
                "worker_started":False,"picture_locked":False,
                "final_master":False}

    def verify_import(self,chain_id):
        row=self._row(chain_id)
        try:
            proof=self.b13.verify_completed(row["import_job"])
        except KeyError as exc:
            raise RuntimeError(
                "Original native B13 import receipt missing; cannot authorize B14 conform"
            ) from exc
        if (proof["status"]!="VERIFIED_EDITED_OTIO_REVISION" or
            proof["edit_id"]!=row["edit_id"] or
            proof["revision"]!=row["edit_revision"] or
            proof["picture_approved"] is not False or
            proof["audio_included"] is not False):
            raise RuntimeError("Native imported picture is not a verified B13 edit")
        rec=self.capture.index.read_revision(
            row["project_id"],row["edit_id"],row["edit_revision"])
        if rec["kind"]!="edit" or (row["edit_sha"] and
            row["edit_sha"]!=rec["document_sha256"]):
            raise RuntimeError("Committed editorial source changed after handoff")
        if row["state"]=="IMPORT_QUEUED":
            self._transition(chain_id,"IMPORT_QUEUED","IMPORT_VERIFIED",
                             edit_sha=rec["document_sha256"])
        elif row["state"] not in (
            "IMPORT_VERIFIED","CONFORM_QUEUED","CONFORM_VERIFIED"):
            raise RuntimeError("Cancelled/blocked import cannot be verified as active")
        return rec,proof

    def stage_conform(self,chain_id,creator_event,*,ram_mb=1024):
        row=self._row(chain_id)
        if row["state"]=="CONFORM_QUEUED":
            # A caller cannot assume a previously staged job was accepted.
            return {"chain_id":chain_id,"state":"CONFORM_QUEUED",
                    "conform_job":row["conform_job"],"worker_started":False}
        if row["state"]=="CONFORM_VERIFIED":
            raise RuntimeError("Already published picture conform")
        if row["state"] not in ("IMPORT_QUEUED","IMPORT_VERIFIED"):
            raise RuntimeError("Import not eligible for native picture conform")
        rec,proof=self.verify_import(chain_id)
        row=self._row(chain_id)
        if row["state"]!="IMPORT_VERIFIED" or not row["edit_sha"]:
            raise RuntimeError("Imported edit lacks durable source checksum")
        self._transition(chain_id,"IMPORT_VERIFIED","CONFORM_STAGING_UNCERTAIN")
        ticket=self.b14.stage_and_approve(
            row["project_id"],row["edit_id"],row["edit_revision"],
            Path(row["package_dir"]),Path(row["destination_dir"]),
            creator_event,presentation_id=row["presentation_id"],ram_mb=ram_mb)
        if ticket.get("state")!="QUEUED" or not ticket.get("job_id"):
            raise RuntimeError("Native B14 returned no durable queued worker ticket")
        self._transition(chain_id,"CONFORM_STAGING_UNCERTAIN","CONFORM_QUEUED",
                         conform_job=ticket["job_id"])
        return {"chain_id":chain_id,"state":"CONFORM_QUEUED",
                "conform_job":ticket["job_id"],"worker_started":False,
                "final_master":False}

    def verify_conform(self,chain_id):
        row=self._row(chain_id)
        if row["state"] not in ("CONFORM_QUEUED","CONFORM_VERIFIED"):
            raise RuntimeError("No committed authorized B14 work for this chain")
        self.verify_import(chain_id)
        proof=self.b14.verify_completed(row["conform_job"])
        if proof["status"] not in (
            "VERIFIED_SOURCE_BOUND_PICTURE_CONFORM",
            "VERIFIED_B14_SOURCE_BOUND_PICTURE_CONFORM",
            "VERIFIED_SDR16_PICTURE_CONFORM"):
            # Accept independently audited result only if the exact B14
            # worker verified it; status names are intentionally explicit.
            raise RuntimeError("Native B14 conform did not return a verified receipt")
        rec=self.capture.index.read_revision(
            row["project_id"],row["presentation_id"],1)
        if (rec["kind"]!="presentation" or
            rec["data"].get("picture_locked") is not False or
            rec["data"].get("final_master") is not False):
            raise RuntimeError("Technical conform cannot claim final master")
        if row["state"]=="CONFORM_QUEUED":
            self._transition(chain_id,"CONFORM_QUEUED","CONFORM_VERIFIED")
        return {"chain_id":chain_id,"state":"CONFORM_VERIFIED",
                "document_sha256":rec["document_sha256"],
                "frames":proof["frames"],"picture_locked":False,
                "final_master":False}

    def run_import(self,chain_id,*,timeout_seconds=240):
        row=self._row(chain_id)
        if row["state"] not in ("IMPORT_QUEUED","IMPORT_VERIFIED"):
            raise RuntimeError("Native edit import not runnable")
        if row["state"]=="IMPORT_QUEUED":
            result=self.b13.run_next(timeout_seconds=timeout_seconds)
            if result is None or not result.get("admitted",True):
                return result
            if result.get("job_id")!=row["import_job"] or result.get("state")!="SUCCEEDED":
                raise RuntimeError("Native editorial worker ticket mismatch")
        self.verify_import(chain_id)
        return {"chain_id":chain_id,"state":"IMPORT_VERIFIED"}

    def run_conform(self,chain_id,*,timeout_seconds=600):
        row=self._row(chain_id)
        if row["state"] not in ("CONFORM_QUEUED","CONFORM_VERIFIED"):
            raise RuntimeError("Native picture conform not staged")
        if row["state"]=="CONFORM_QUEUED":
            result=self.b14.run_next(timeout_seconds=timeout_seconds)
            if result is None or not result.get("admitted",True):
                return result
            if result.get("job_id")!=row["conform_job"] or result.get("state")!="SUCCEEDED":
                raise RuntimeError("Native conform worker receipt or ticket mismatched")
        return self.verify_conform(chain_id)

    def cancel_queued_import(self,chain_id,creator_event):
        row=self._row(chain_id)
        if row["state"]!="IMPORT_QUEUED":
            raise RuntimeError("Only an unstarted import can be cancelled here")
        result=self.b13.revoke_from_trusted_native_action(
            row["import_job"],creator_event)
        if not result["queued_cancelled"]:
            raise RuntimeError("A running worker needs original native OS-stop witness")
        self._transition(chain_id,"IMPORT_QUEUED","CANCELLED_BEFORE_IMPORT")
        return {"chain_id":chain_id,"state":"CANCELLED_BEFORE_IMPORT",
                "live_worker_terminated_claimed":False}

    def reconcile_completed_stage(self,chain_id):
        """Recover uniquely completed B13/B14 grants, never relaunch workers."""
        row=self._row(chain_id)
        if row["state"]=="IMPORT_STAGING_UNCERTAIN":
            with self.ledger._db() as db:
                grants=db.execute("""SELECT g.job_id,g.result_document_sha256
                    FROM native_b13_import_grants g
                    JOIN tasks t ON t.id=g.job_id
                    WHERE g.project_id=? AND g.delivery_id=? AND g.edit_id=?
                      AND g.expected_revision=? AND g.package_dir=?
                      AND g.revoked_at IS NULL AND g.result_document_sha256 IS NOT NULL
                      AND t.state='SUCCEEDED' AND t.reserved=0""",
                    (row["project_id"],row["delivery_id"],row["edit_id"],
                     row["edit_revision"]-1,row["package_dir"])).fetchall()
            if len(grants)>1:
                raise RuntimeError("Ambiguous completed native B13 edit grants")
            if not grants:
                return {"chain_id":chain_id,"state":row["state"],
                        "requires_native_reconciliation":True,
                        "recovered_without_relaunch":False}
            job,approved_sha=grants[0]
            proof=self.b13.verify_completed(job)
            rec=self.capture.index.read_revision(row["project_id"],
                                                  row["edit_id"],row["edit_revision"])
            if (proof.get("status")!="VERIFIED_EDITED_OTIO_REVISION"
                or proof.get("edit_id")!=row["edit_id"]
                or proof.get("revision")!=row["edit_revision"]
                or rec["kind"]!="edit" or rec["document_sha256"]!=approved_sha):
                raise RuntimeError("Original B13 grant failed native recovery verification")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                changed=db.execute("""UPDATE native_e2e01b_chains
                    SET import_job=?,state='IMPORT_QUEUED',updated_at=?
                    WHERE chain_id=? AND state='IMPORT_STAGING_UNCERTAIN'""",
                    (job,time.time(),chain_id))
                if changed.rowcount!=1:
                    db.rollback()
                    raise RuntimeError("Concurrent B13 recovery changed staging intent")
                db.commit()
            self.verify_import(chain_id)
            return {"chain_id":chain_id,"state":"IMPORT_VERIFIED",
                    "recovered_without_relaunch":True}
        if row["state"]=="CONFORM_STAGING_UNCERTAIN":
            with self.ledger._db() as db:
                grants=db.execute("""SELECT g.job_id,g.result_sha
                    FROM native_b14_conform_grants g
                    JOIN tasks t ON t.id=g.job_id
                    WHERE g.project_id=? AND g.edit_id=? AND g.edit_revision=?
                      AND g.edit_sha=? AND g.package_dir=?
                      AND g.destination_dir=? AND g.presentation_id=?
                      AND g.revoked_at IS NULL AND g.result_sha IS NOT NULL
                      AND t.state='SUCCEEDED' AND t.reserved=0""",
                    (row["project_id"],row["edit_id"],row["edit_revision"],
                     row["edit_sha"],row["package_dir"],row["destination_dir"],
                     row["presentation_id"])).fetchall()
            if len(grants)>1:
                raise RuntimeError("Ambiguous completed native B14 conform grants")
            if not grants:
                return {"chain_id":chain_id,"state":row["state"],
                        "requires_native_reconciliation":True,
                        "recovered_without_relaunch":False}
            job,approved_sha=grants[0]
            proof=self.b14.verify_completed(job)
            rec=self.capture.index.read_revision(row["project_id"],
                                                  row["presentation_id"],1)
            if (proof.get("status")!="VERIFIED_SDR16_PICTURE_CONFORM"
                or rec["kind"]!="presentation"
                or rec["document_sha256"]!=approved_sha
                or rec["data"].get("picture_locked") is not False
                or rec["data"].get("final_master") is not False):
                raise RuntimeError("Original B14 grant failed native recovery verification")
            self._transition(chain_id,"CONFORM_STAGING_UNCERTAIN",
                             "CONFORM_QUEUED",conform_job=job)
            return {**self.verify_conform(chain_id),
                    "recovered_without_relaunch":True}
        raise RuntimeError("No uncertain B13/B14 native staging to reconcile")

    def reopen(self,chain_id):
        """After crash, verify custody; do not infer worker termination."""
        row=self._row(chain_id)
        if row["state"] in ("IMPORT_STAGING_UNCERTAIN","CONFORM_STAGING_UNCERTAIN"):
            return self.reconcile_completed_stage(chain_id)
        if row["state"]=="IMPORT_QUEUED":
            task=self.ledger.get_task(row["import_job"])
            if not task or task["state"]!="SUCCEEDED":
                return {"chain_id":chain_id,"state":row["state"],
                        "worker_state":None if not task else task["state"],
                        "recovered_without_relaunch":False}
            self.verify_import(chain_id)
            row=self._row(chain_id)
        if row["state"] in ("IMPORT_VERIFIED","CONFORM_QUEUED","CONFORM_VERIFIED"):
            self.verify_import(chain_id)
        if row["state"]=="CONFORM_QUEUED":
            task=self.ledger.get_task(row["conform_job"])
            if not task or task["state"]!="SUCCEEDED":
                return {"chain_id":chain_id,"state":row["state"],
                        "worker_state":None if not task else task["state"],
                        "recovered_without_relaunch":False}
            return {**self.verify_conform(chain_id),
                    "recovered_without_relaunch":True}
        if row["state"]=="CONFORM_VERIFIED":
            return {**self.verify_conform(chain_id),
                    "recovered_without_relaunch":True}
        return {"chain_id":chain_id,"state":row["state"],
                "recovered_without_relaunch":row["state"]=="IMPORT_VERIFIED"}
