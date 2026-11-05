"""NVP-E2E-01C: verified creative finishing handoff.

Native hosts remain authoritative for B14 picture lock, AUDIO-01I approved
PCM24, AUDIO-01J exact audiovisual worker, and AUDIO-01K distribution.
Never promote a technical preview, queued worker, or unapproved candidate.

This coordinator persists *intent* before invoking irreversible native
operations. An interrupted stage/publish remains UNCERTAIN and must be
reconciled through the original native host; it is never auto-replayed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import time

from backend.nvp_audio01j_picture_lock import validate_picture_lock
from backend.nvp_audio01i_native_host import NativeAudio01IHost
from backend.nvp_audio01j_native_host import NativeAudio01JHost
from backend.nvp_audio01k_native_host import NativeAudio01KHost
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_film_index import _id

FORMAT="nvp.e2e01c.finishing_handoff.v1"
STATES=frozenset({"APPROVALS_VERIFIED","AV_STAGING_UNCERTAIN","AV_QUEUED",
                  "AV_VERIFIED","DISTRIBUTION_UNCERTAIN","DISTRIBUTION_VERIFIED"})


class NativeFinishingHandoff:
    def __init__(self,capture:DigitalCapture,ledger:TaskLedger,
                 audio_host:NativeAudio01IHost,av_host:NativeAudio01JHost,
                 distribution_host:NativeAudio01KHost):
        if (not isinstance(capture,DigitalCapture) or not isinstance(ledger,TaskLedger)
            or not isinstance(audio_host,NativeAudio01IHost)
            or not isinstance(av_host,NativeAudio01JHost)
            or not isinstance(distribution_host,NativeAudio01KHost)
            or any(x.ledger.db_path!=ledger.db_path
                   or x.capture.studio.db_path!=capture.studio.db_path
                   for x in (audio_host,av_host,distribution_host))
            or av_host.audio_host is not audio_host
            or distribution_host.av_host is not av_host):
            raise TypeError("E2E finishing requires the real shared native host chain")
        self.capture,self.ledger=capture,ledger
        self.audio,self.av,self.distribution=audio_host,av_host,distribution_host
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_e2e01c_handoffs(
                project_id TEXT NOT NULL,
                export_id TEXT NOT NULL,
                lock_id TEXT NOT NULL,
                lock_sha TEXT NOT NULL,
                audio_delivery_id TEXT NOT NULL,
                audio_sha TEXT NOT NULL,
                movie_dir TEXT NOT NULL,
                audio_dir TEXT NOT NULL,
                final_dir TEXT NOT NULL,
                distribution_id TEXT NOT NULL,
                distribution_dir TEXT NOT NULL,
                av_job TEXT,
                av_sha TEXT,
                distribution_sha TEXT,
                state TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(project_id,export_id),
                UNIQUE(project_id,distribution_id))""")

    def _row(self,project_id,export_id):
        with self.ledger._db() as db:
            db.row_factory=sqlite3.Row
            row=db.execute("""SELECT * FROM native_e2e01c_handoffs
                WHERE project_id=? AND export_id=?""",(project_id,export_id)).fetchone()
        if row is None:raise KeyError("No registered NVP finishing handoff")
        return dict(row)

    def _move(self,project_id,export_id,old,new,**updates):
        if old not in STATES or new not in STATES:
            raise ValueError("Invalid creative-finishing transition")
        allowed={"av_job","av_sha","distribution_sha"}
        if set(updates)-allowed:
            raise ValueError("Unexpected finishing custody update")
        columns=["state=?","updated_at=?"]
        args=[new,time.time()]
        for key,value in updates.items():
            columns.append(key+"=?")
            args.append(value)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            cur=db.execute("UPDATE native_e2e01c_handoffs SET "+
                ",".join(columns)+" WHERE project_id=? AND export_id=? AND state=?",
                (*args,project_id,export_id,old))
            if cur.rowcount!=1:
                db.rollback()
                raise RuntimeError("Finishing state changed concurrently")
            db.commit()

    @staticmethod
    def _safe_parent(destination):
        p=Path(destination).absolute()
        if p.exists() or p.is_symlink() or not p.parent.is_dir() or p.parent.is_symlink():
            raise RuntimeError("New finishing output required in safe existing directory")
        return str(p)

    def _approved(self,row,*,ffmpeg="ffmpeg",ffprobe="ffprobe"):
        lock,_=validate_picture_lock(self.capture,row["project_id"],row["lock_id"])
        audio=self.capture.index.read_revision(row["project_id"],row["audio_delivery_id"],1)
        if (lock["document_sha256"]!=row["lock_sha"]
            or audio["document_sha256"]!=row["audio_sha"]):
            raise RuntimeError("NVP approved picture/audio authority changed")
        self.audio.verify_delivery(row["project_id"],row["audio_delivery_id"],
                                   row["audio_dir"],ffmpeg=ffmpeg,ffprobe=ffprobe)
        return lock,audio

    def register(self,project_id,lock_id,audio_delivery_id,*,movie_dir,audio_dir,
                 final_dir,export_id,distribution_id,distribution_dir,
                 ffmpeg="ffmpeg",ffprobe="ffprobe"):
        for id_ in (lock_id,audio_delivery_id,export_id,distribution_id):
            _id(id_,"finishing object ID")
        if len({lock_id,audio_delivery_id,export_id,distribution_id})!=4:
            raise ValueError("Finishing object identities must differ")
        lock,_=validate_picture_lock(self.capture,project_id,lock_id)
        self.audio.verify_delivery(project_id,audio_delivery_id,audio_dir,
                                   ffmpeg=ffmpeg,ffprobe=ffprobe)
        audio=self.capture.index.read_revision(project_id,audio_delivery_id,1)
        if audio["kind"]!="audio":
            raise RuntimeError("Approved native PCM24 audio object required")
        for target in (export_id,distribution_id):
            try:self.capture.index.read_revision(project_id,target)
            except KeyError:pass
            else:raise RuntimeError("Finishing output identity already exists")
        final=self._safe_parent(final_dir)
        distribution=self._safe_parent(distribution_dir)
        if final==distribution:
            raise ValueError("Final film and distribution cannot share output path")
        movie=Path(movie_dir)
        audio_path=Path(audio_dir)
        if (movie.is_symlink() or not movie.is_dir()
            or audio_path.is_symlink() or not audio_path.is_dir()):
            raise RuntimeError("Original picture/audio asset directories unavailable")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO native_e2e01c_handoffs(
                project_id,export_id,lock_id,lock_sha,audio_delivery_id,audio_sha,
                movie_dir,audio_dir,final_dir,distribution_id,distribution_dir,
                state,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (project_id,export_id,lock_id,lock["document_sha256"],
                 audio_delivery_id,audio["document_sha256"],
                 str(movie.resolve()),str(audio_path.resolve()),final,
                 distribution_id,distribution,"APPROVALS_VERIFIED",time.time()))
            db.commit()
        return {"format":FORMAT,"project_id":project_id,"export_id":export_id,
                "state":"APPROVALS_VERIFIED","dcp_delivered":False}

    def stage_final_av(self,project_id,export_id,creator_event,*,
                       ffmpeg="ffmpeg",ffprobe="ffprobe",ram_mb=1024):
        row=self._row(project_id,export_id)
        if row["state"]!="APPROVALS_VERIFIED":
            raise RuntimeError("Final AV already staged or needs manual reconciliation")
        self._approved(row,ffmpeg=ffmpeg,ffprobe=ffprobe)
        # Write-ahead uncertain state: worker may stage a task before its
        # response reaches the coordinator. Never auto-stage it twice.
        self._move(project_id,export_id,"APPROVALS_VERIFIED","AV_STAGING_UNCERTAIN")
        ticket=self.av.stage(project_id,row["lock_id"],row["audio_delivery_id"],
            row["movie_dir"],row["audio_dir"],row["final_dir"],export_id,
            creator_event,ffmpeg=ffmpeg,ffprobe=ffprobe,ram_mb=ram_mb)
        if (ticket.get("state")!="QUEUED" or ticket.get("export_id")!=export_id
            or not ticket.get("job_id")):
            raise RuntimeError("Native AV stage did not return an exact queued job")
        self._move(project_id,export_id,"AV_STAGING_UNCERTAIN","AV_QUEUED",
                   av_job=ticket["job_id"])
        return {"state":"AV_QUEUED","job_id":ticket["job_id"],
                "final_master":False,"dcp_delivered":False}

    def run_final_av(self,project_id,export_id,*,timeout_seconds=900,
                     ffmpeg="ffmpeg",ffprobe="ffprobe"):
        """Execute only the original J-host task, never an arbitrary render."""
        row=self._row(project_id,export_id)
        if row["state"]!="AV_QUEUED" or not row["av_job"]:
            raise RuntimeError("No exact queued native AV job")
        result=self.av.run_next(timeout_seconds=timeout_seconds)
        if result is None or not result.get("admitted",True):
            return result
        if (result.get("job_id")!=row["av_job"]
            or result.get("state")!="SUCCEEDED"):
            raise RuntimeError("Wrong native AV worker completed; manual reconciliation")
        return self.verify_final_av(project_id,export_id,
                                   ffmpeg=ffmpeg,ffprobe=ffprobe)

    def verify_final_av(self,project_id,export_id,*,ffmpeg="ffmpeg",ffprobe="ffprobe"):
        row=self._row(project_id,export_id)
        if row["state"] not in ("AV_QUEUED","AV_VERIFIED","DISTRIBUTION_UNCERTAIN",
                               "DISTRIBUTION_VERIFIED"):
            raise RuntimeError("No bound completed native AV task")
        if not row["av_job"]:
            raise RuntimeError("Missing original native AV job")
        self._approved(row,ffmpeg=ffmpeg,ffprobe=ffprobe)
        task=self.ledger.get_task(row["av_job"])
        if not task or task["state"]!="SUCCEEDED" or task["reserved"]!=0:
            raise RuntimeError("Native AV worker not stopped and fully reconciled")
        proof=self.av.verify_published(
            project_id,export_id,row["final_dir"],row["movie_dir"],row["audio_dir"],
            ffmpeg=ffmpeg,ffprobe=ffprobe)
        if proof.get("status")!="VERIFIED_FINAL_AV_MASTER":
            raise RuntimeError("Native audiovisual master verification failed")
        master=self.capture.index.read_revision(project_id,export_id,1)
        if (master["kind"]!="master" or master["data"].get("final_master") is not True
            or master["data"].get("dcp_delivered") is not False
            or master["data"].get("picture_lock_id")!=row["lock_id"]
            or master["data"].get("audio_delivery_id")!=row["audio_delivery_id"]
            or row["av_sha"] not in (None,master["document_sha256"])):
            raise RuntimeError("Final film source, approval or SHA mismatch")
        if row["state"]=="AV_QUEUED":
            self._move(project_id,export_id,"AV_QUEUED","AV_VERIFIED",
                       av_sha=master["document_sha256"])
        return {"state":"AV_VERIFIED" if row["state"]=="AV_QUEUED" else row["state"],
                "document_sha256":master["document_sha256"],
                "dcp_delivered":False}

    def publish_mezzanine(self,project_id,export_id,creator_event,*,
                          ffmpeg="ffmpeg",ffprobe="ffprobe"):
        row=self._row(project_id,export_id)
        if row["state"]!="AV_VERIFIED":
            if row["state"]=="AV_QUEUED":
                raise RuntimeError(
                    "Native AV worker not stopped or independently verified; cannot distribute"
                )
            raise RuntimeError("Only independently verified AV may be distributed")
        self.verify_final_av(project_id,export_id,ffmpeg=ffmpeg,ffprobe=ffprobe)
        # Do not retry automatically after an interrupted creator event or
        # in-host atomic promotion; use the original K host to reconcile.
        self._move(project_id,export_id,"AV_VERIFIED","DISTRIBUTION_UNCERTAIN")
        self.distribution.publish(project_id,export_id,row["distribution_id"],
            row["final_dir"],row["movie_dir"],row["audio_dir"],
            row["distribution_dir"],creator_event,ffmpeg=ffmpeg,ffprobe=ffprobe)
        proof=self.distribution.verify(project_id,row["distribution_id"],
            row["distribution_dir"],row["final_dir"],row["movie_dir"],row["audio_dir"],
            ffmpeg=ffmpeg,ffprobe=ffprobe)
        if proof.get("status")!="VERIFIED_MEZZANINE_DISTRIBUTION":
            raise RuntimeError("Native K distribution not verified")
        published=self.capture.index.read_revision(project_id,row["distribution_id"],1)
        if (published["kind"]!="master" or
            published["data"].get("export_id")!=export_id
            or published["data"].get("dcp_delivered") is not False):
            raise RuntimeError("Distribution changed its approved source")
        self._move(project_id,export_id,"DISTRIBUTION_UNCERTAIN",
                   "DISTRIBUTION_VERIFIED",
                   distribution_sha=published["document_sha256"])
        return {"state":"DISTRIBUTION_VERIFIED","dcp_delivered":False,
                "document_sha256":published["document_sha256"]}

    def reconcile_stopped_av_after_crash(self,project_id,export_id,*,
                                         ffmpeg="ffmpeg",ffprobe="ffprobe"):
        """Recover only a uniquely proven completed native J-host job.

        Queued/ACTIVE jobs cannot be replayed, because creator event state is
        held by the original host. No OS worker is launched or released here.
        """
        row=self._row(project_id,export_id)
        if row["state"]!="AV_STAGING_UNCERTAIN":
            raise RuntimeError("Only an uncertain stage can be reconciled")
        with self.ledger._db() as db:
            records=db.execute("""SELECT g.job_id,g.plan_sha
                FROM native_audio01j_grants g JOIN tasks t ON t.id=g.job_id
                WHERE g.revoked=0 AND g.stopped=1 AND t.state='SUCCEEDED'
                    AND t.reserved=0""").fetchall()
        candidates=[]
        from backend.nvp_audio01i_mastering import sha_file
        import json
        for job,plan_sha in records:
            sealed=self.av.root/job/"plan.json"
            if sealed.is_symlink() or not sealed.is_file():
                continue
            if sha_file(sealed)!=plan_sha:
                raise RuntimeError("Original completed native AV plan tampered")
            plan=json.loads(sealed.read_bytes())
            if (plan.get("job_id")!=job or plan.get("project_id")!=project_id
                or plan.get("export_id")!=export_id
                or plan.get("picture_lock_id")!=row["lock_id"]
                or plan.get("audio_delivery_id")!=row["audio_delivery_id"]
                or plan.get("movie_dir")!=row["movie_dir"]
                or plan.get("audio_dir")!=row["audio_dir"]
                or plan.get("destination")!=row["final_dir"]):
                continue
            candidates.append(job)
        if not candidates:
            return {"state":"AV_STAGING_UNCERTAIN",
                    "requires_native_reconciliation":True,
                    "dcp_delivered":False}
        if len(candidates)!=1:
            raise RuntimeError("Multiple completed native AV grants claim one film")
        job=candidates[0]
        self._approved(row,ffmpeg=ffmpeg,ffprobe=ffprobe)
        # Native J-host independently proves original creator publication,
        # authoritative stop witness, immutable plan, and finished FilmIndex.
        proof=self.av.verify_published(project_id,export_id,row["final_dir"],
            row["movie_dir"],row["audio_dir"],ffmpeg=ffmpeg,ffprobe=ffprobe)
        if proof.get("status")!="VERIFIED_FINAL_AV_MASTER":
            raise RuntimeError("Native J-host refuses recovered final AV")
        master=self.capture.index.read_revision(project_id,export_id,1)
        if (master["kind"]!="master"
            or master["data"].get("final_master") is not True
            or master["data"].get("dcp_delivered") is not False
            or master["data"].get("picture_lock_id")!=row["lock_id"]
            or master["data"].get("audio_delivery_id")!=row["audio_delivery_id"]):
            raise RuntimeError("Recovered AV does not match the approved original")
        self._move(project_id,export_id,"AV_STAGING_UNCERTAIN",
                   "AV_QUEUED",av_job=job)
        verified=self.verify_final_av(project_id,export_id,
                                      ffmpeg=ffmpeg,ffprobe=ffprobe)
        return {**verified,"recovered_without_rerender":True}

    def reopen(self,project_id,export_id,*,ffmpeg="ffmpeg",ffprobe="ffprobe"):
        row=self._row(project_id,export_id)
        if row["state"]=="AV_STAGING_UNCERTAIN":
            return self.reconcile_stopped_av_after_crash(
                project_id,export_id,ffmpeg=ffmpeg,ffprobe=ffprobe)
        if row["state"]=="DISTRIBUTION_UNCERTAIN":
            # Never infer a creator-approved publication from an existing
            # file alone; a K-host publication witness is required.
            try:
                self.verify_final_av(project_id,export_id,
                    ffmpeg=ffmpeg,ffprobe=ffprobe)
                proof=self.distribution.verify(
                    project_id,row["distribution_id"],row["distribution_dir"],
                    row["final_dir"],row["movie_dir"],row["audio_dir"],
                    ffmpeg=ffmpeg,ffprobe=ffprobe)
                if proof.get("status")!="VERIFIED_MEZZANINE_DISTRIBUTION":
                    raise RuntimeError("Distribution host did not confirm publication")
                rec=self.capture.index.read_revision(project_id,row["distribution_id"],1)
                if rec["data"].get("export_id")!=export_id:
                    raise RuntimeError("Distribution source identity changed")
                self._move(project_id,export_id,"DISTRIBUTION_UNCERTAIN",
                    "DISTRIBUTION_VERIFIED",
                    distribution_sha=rec["document_sha256"])
                return {"state":"DISTRIBUTION_VERIFIED","dcp_delivered":False,
                        "recovered_without_rerender":True}
            except (RuntimeError,PermissionError,KeyError,OSError):
                return {"state":"DISTRIBUTION_UNCERTAIN",
                        "requires_native_reconciliation":True,"dcp_delivered":False}
        if row["state"]=="AV_QUEUED":
            task=self.ledger.get_task(row["av_job"]) if row["av_job"] else None
            if task and task["state"]=="SUCCEEDED" and task["reserved"]==0:
                try:
                    verified=self.verify_final_av(
                        project_id,export_id,ffmpeg=ffmpeg,ffprobe=ffprobe)
                    return {**verified,"recovered_without_rerender":True}
                except (RuntimeError,PermissionError,KeyError,OSError):
                    pass
            return {"state":"AV_QUEUED","worker_state":None if not task else task["state"],
                    "requires_native_reconciliation":True,
                    "dcp_delivered":False}
        if row["state"] in ("AV_VERIFIED","DISTRIBUTION_VERIFIED"):
            self.verify_final_av(project_id,export_id,
                                 ffmpeg=ffmpeg,ffprobe=ffprobe)
            if row["state"]=="DISTRIBUTION_VERIFIED":
                proof=self.distribution.verify(
                    project_id,row["distribution_id"],row["distribution_dir"],
                    row["final_dir"],row["movie_dir"],row["audio_dir"],
                    ffmpeg=ffmpeg,ffprobe=ffprobe)
                if proof.get("status")!="VERIFIED_MEZZANINE_DISTRIBUTION":
                    raise RuntimeError("Published distribution lost native integrity")
                rec=self.capture.index.read_revision(project_id,row["distribution_id"],1)
                if rec["document_sha256"]!=row["distribution_sha"]:
                    raise RuntimeError("Published distribution manifest SHA changed")
            return {"state":row["state"],"dcp_delivered":False,
                    "recovered_without_rerender":True}
        return {"state":row["state"],"dcp_delivered":False,
                "requires_native_reconciliation":row["state"]=="AV_QUEUED"}
