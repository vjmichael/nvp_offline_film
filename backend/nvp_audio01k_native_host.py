"""AUDIO-01K trusted host for exact AV mezzanine distribution approval.

This is a bounded, in-host atomic copy and custody gate; no transcoder or
model worker runs here. The creator event is consumed before the first write.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import secrets
import sqlite3

from backend.nvp_audio01k_distribution import publish_mezzanine,verify_mezzanine,PROFILE
from backend.nvp_audio01k_fault_matrix import crash_after
from backend.nvp_film_index import _id
from backend.nvp_resource_ledger import TaskLedger


class NativeAudio01KHost:
    def __init__(self,capture,ledger:TaskLedger,*,av_host,verify_creator_action):
        if (not isinstance(ledger,TaskLedger)
            or not callable(getattr(av_host,"verify_published",None))
            or not callable(verify_creator_action)):
            raise TypeError("Native AV verifier, ledger and creator policy required")
        self.capture=capture
        self.ledger=ledger
        self.av_host=av_host
        self.creator=verify_creator_action
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01k_events(
                event_sha TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                export_id TEXT NOT NULL,distribution_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('RESERVED','PUBLISHED')),
                document_sha TEXT)""")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS native_audio01k_one_package_id
                ON native_audio01k_events(project_id,distribution_id)""")

    def _verify(self,project_id,export_id,final_av_dir,movie_dir,audio_dir,
                ffmpeg,ffprobe):
        return self.av_host.verify_published(
            project_id,export_id,final_av_dir,movie_dir,audio_dir,
            ffmpeg=ffmpeg,ffprobe=ffprobe)

    def publish(self,project_id,export_id,distribution_id,final_av_dir,
                movie_dir,audio_dir,destination,creator_event,*,
                ffmpeg="ffmpeg",ffprobe="ffprobe"):
        _id(distribution_id,"distribution package identity")
        if type(creator_event) is not str or not creator_event:
            raise PermissionError("Authenticated creator action ID required")
        source=self.capture.index.read_revision(project_id,export_id,1)
        expected=source["document_sha256"]
        scope={"operation":"nvp.audio01k.publish_mezzanine",
               "project_id":project_id,"export_id":export_id,
               "export_document_sha256":expected,
               "distribution_id":distribution_id,"profile":PROFILE,
               "destination":str(Path(destination).absolute()),
               "dcp_delivered":False}
        if self.creator(creator_event,scope) is not True:
            raise PermissionError("Creator did not approve this exact distribution")
        # The original native AV proof is required, in addition to an
        # affirmative creator action. An arbitrary FilmIndex master is unsafe.
        check=lambda:self._verify(project_id,export_id,final_av_dir,
                                 movie_dir,audio_dir,ffmpeg,ffprobe)
        if check().get("status")!="VERIFIED_FINAL_AV_MASTER":
            raise RuntimeError("Source AV native custody could not be verified")
        event_sha=hashlib.sha256(creator_event.encode("utf8")).hexdigest()
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM native_audio01k_events WHERE event_sha=?",
                          (event_sha,)).fetchone():
                raise PermissionError("Distribution creator event already consumed")
            db.execute("INSERT INTO native_audio01k_events VALUES(?,?,?,?,?,NULL)",
                       (event_sha,project_id,export_id,distribution_id,"RESERVED"))
            db.commit()
        crash_after("creator_event_reserved")
        result=publish_mezzanine(
            self.capture,project_id,export_id,distribution_id,
            final_av_dir,destination,verify_native_master=check)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE native_audio01k_events SET status='PUBLISHED',
                document_sha=? WHERE event_sha=? AND status='RESERVED'""",
                (result["document_sha256"],event_sha))
            db.commit()
        crash_after("creator_event_published")
        return result

    def verify(self,project_id,distribution_id,destination,final_av_dir,
               movie_dir,audio_dir,*,ffmpeg="ffmpeg",ffprobe="ffprobe"):
        record=self.capture.index.read_revision(project_id,distribution_id,1)
        doc=record["data"]
        with self.ledger._db() as db:
            rows=db.execute("""SELECT document_sha FROM native_audio01k_events
                WHERE project_id=? AND distribution_id=? AND export_id=?
                  AND status='PUBLISHED'""",
                (project_id,distribution_id,doc["export_id"])).fetchall()
        if len(rows)!=1 or rows[0][0]!=record["document_sha256"]:
            raise PermissionError("Mezzanine lacks completed native creator publication")
        return verify_mezzanine(
            self.capture,project_id,distribution_id,destination,
            verify_native_master=lambda:self._verify(
                project_id,doc["export_id"],final_av_dir,movie_dir,
                audio_dir,ffmpeg,ffprobe))
