"""WO4-LF02/04: one SQLite supervisor journal for source-bound picture reels.

A FilmIndex-approved mastering decision authorizes exact ordered XYZ12 file
SHAs, 24fps Film Time, reviewed OpenJPEG/CineCert executable identities and a
private job-owned spool root. Picture codestream and MXF checkpoints refer to
durable files, not in-memory reel blobs. Never auto-promote, delete, or trust
uncommitted outputs after a crash. No DCP/physical approval is implied.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from backend.nvp_film_index import FilmIndex
from backend.nvp_production_journal import (
    ProductionJournal,FORMAT as JOB_FORMAT,MAX_MANIFEST_BYTES,
    TICKS_PER_SECOND,_canonical,_digest,_now,_safe_source)
from backend.nvp_wo3_j2k_audit import PROFILES
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file
from backend.nvp_wo3_atomic_publish import _fsync_directory
from backend.nvp_wo4_mastering_decision import FORMAT as DECISION_FORMAT
from backend.nvp_wo4_picture_spool import verify_frame_file

TASK_KIND="ENCODE_APPROVED_XYZ12_PICTURE_REEL_V1"
FORMAT="nvp.wo4.native_picture_reel_journal.v1"
MAX_REEL_FRAMES=7200
SHA_RE=re.compile(r"[0-9a-f]{64}\Z")

class CinemaJournal(ProductionJournal):
    def __init__(self,state_root):
        super().__init__(state_root)
        self.spools=self.root/"cinema-spools"
        if self.spools.is_symlink():
            raise PermissionError("Native cinema spool parent cannot be symlinked")
        self.spools.mkdir(mode=0o700,exist_ok=True)
        if os.name!="nt":
            import stat
            if stat.S_IMODE(self.spools.stat().st_mode)&0o077:
                raise PermissionError("Native spool directory not owner private")
        with self._tx() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS production_cinema_reels(
                job_id TEXT PRIMARY KEY REFERENCES production_jobs(job_id),
                take_id TEXT NOT NULL,
                take_revision INTEGER NOT NULL,
                take_sha256 TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                decision_sha256 TEXT NOT NULL,
                profile TEXT NOT NULL,
                frame_count INTEGER NOT NULL,
                picture_uuid TEXT NOT NULL,
                codec_path TEXT NOT NULL,codec_sha256 TEXT NOT NULL,
                wrapper_path TEXT NOT NULL,wrapper_sha256 TEXT NOT NULL,
                info_path TEXT NOT NULL,info_sha256 TEXT NOT NULL,
                reel_state TEXT NOT NULL DEFAULT 'ENCODING',
                track_sha256 TEXT,track_bytes INTEGER,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS production_cinema_frames(
                job_id TEXT NOT NULL REFERENCES production_jobs(job_id),
                position INTEGER NOT NULL,
                file_sha256 TEXT NOT NULL,
                file_bytes INTEGER NOT NULL CHECK(file_bytes>0),
                source_sha256 TEXT NOT NULL,
                committed_at TEXT NOT NULL,
                PRIMARY KEY(job_id,position),
                FOREIGN KEY(job_id,position)
                    REFERENCES production_segments(job_id,position)
            );
            """)

    def spool(self,job_id):
        if type(job_id) is not str:
            raise ValueError("Native cinema job ID required")
        from uuid import UUID
        if str(UUID(job_id))!=job_id:
            raise ValueError("Canonical cinema job ID required")
        p=self.spools/job_id
        if p.is_symlink():
            raise PermissionError("Refusing symlinked cinema spool")
        return p

    def reel(self,job_id):
        with self._read() as db:
            job=db.execute("SELECT * FROM production_cinema_reels WHERE job_id=?",
                           (job_id,)).fetchone()
            if job is None:
                raise KeyError("Native cinema reel job not found")
            return dict(job)

    def submit_reel(self,index:FilmIndex,pid,*,mastering_decision_id,
                    frame_sources,openjpeg,wrapper,info,approve):
        if not isinstance(index,FilmIndex) or not callable(approve):
            raise PermissionError("Trusted FilmIndex and host approval required")
        bins=(openjpeg,wrapper,info)
        products=("OpenJPEG-opj_compress","ASDCP-asdcp_wrap","ASDCP-asdcp_info")
        for bin,product in zip(bins,products):
            if not isinstance(bin,ApprovedCodecBinary) or bin.product!=product:
                raise PermissionError("Only reviewed OpenJPEG/CineCert binaries")
            bin.check()
        decision=index.read_revision(pid,mastering_decision_id)
        data=decision["data"]
        if (decision["kind"]!="presentation" or
                data.get("format")!=DECISION_FORMAT or
                data.get("production_master_accepted") is not False or
                data.get("source_modified") is not False):
            raise PermissionError("Actual approved immutable cinema decision required")
        source_take=index.read_revision(
            pid,data["source_take_id"],data["source_take_revision"])
        if (source_take["kind"]!="take" or
                source_take["document_sha256"]!=data["source_take_sha256"] or
                source_take["data"].get("frozen") is not True):
            raise PermissionError("Original frozen Digital Take differs")
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        attested=OpenUSDTakeCapture(
            index,verify_creator_action=lambda *_:False
        ).verify_take(pid,data["source_take_id"])
        if (attested["status"]!="VERIFIED_FROZEN_DATA_TAKE" or
                attested["take_document_sha256"]!=data["source_take_sha256"]):
            raise PermissionError("Digital Take's native USD and temporal sources differ")
        shas=data.get("ordered_picture_sha256")
        profile=data.get("picture_profile")
        if (profile not in PROFILES or type(shas) is not list or
                type(frame_sources) is not list or
                not 3<=len(shas)<=MAX_REEL_FRAMES or len(frame_sources)!=len(shas)
                or any(type(x) is not str or not SHA_RE.fullmatch(x) for x in shas)
                or data.get("picture_tick_step")!=TICKS_PER_SECOND//24 or
                type(data.get("film_start_tick")) is not int or
                data["film_start_tick"]<0):
            raise PermissionError("Exact bounded 24fps master picture manifest required")
        frame_bytes=PROFILES[profile][0]*PROFILES[profile][1]*6
        frames=[]
        for i,(path,expected) in enumerate(zip(frame_sources,shas)):
            path=_safe_source(path)
            file=Path(path)
            if file.stat().st_size!=frame_bytes or digest_file(file)!=expected:
                raise PermissionError("Approved ordered source XYZ12 SHA/size mismatch")
            frames.append({"position":i,
                "source_path":path,"source_sha256":expected,
                "source_bytes":frame_bytes,
                "start_tick":data["film_start_tick"]+i*(TICKS_PER_SECOND//24),
                "end_tick":data["film_start_tick"]+(i+1)*(TICKS_PER_SECOND//24)})
        manifest={"format":JOB_FORMAT,"task_kind":TASK_KIND,
                  "project_id":pid,"assembly_id":mastering_decision_id,
                  "assembly_revision":decision["revision"],
                  "assembly_sha256":decision["document_sha256"],
                  "source_take_sha256":data["source_take_sha256"],
                  "picture_profile":profile,
                  "frames":frames,
                  "codec_identities":{
                      bin.product:bin.sha256 for bin in bins},
                  "production_dcp_accepted":False,"ffmpeg_used":False}
        encoded=_canonical(manifest)
        if len(encoded)>MAX_MANIFEST_BYTES:
            raise ValueError("Cinema worker manifest too large")
        manifest_sha=_digest(encoded)
        scope={"operation":"nvp.supervisor.submit_picture_reel.v1",
               "project_id":pid,"mastering_decision_id":mastering_decision_id,
               "mastering_decision_sha256":decision["document_sha256"],
               "source_take_sha256":data["source_take_sha256"],
               "frame_count":len(frames),"profile":profile,
               "manifest_sha256":manifest_sha,
               "encoder_sha256":openjpeg.sha256,
               "wrapper_sha256":wrapper.sha256,"info_sha256":info.sha256}
        if approve(deepcopy(scope)) is not True:
            return {"format":FORMAT,"status":"DENIED","original_source_modified":False}
        if index.read_revision(pid,mastering_decision_id,decision["revision"])[
                "document_sha256"]!=decision["document_sha256"]:
            raise PermissionError("Mastering decision changed during approval")
        for frame in frames:
            if digest_file(frame["source_path"])!=frame["source_sha256"]:
                raise PermissionError("Original XYZ12 changed during approval")
        uid=str(uuid4())
        picture_uid=str(uuid4())
        now=_now()
        with self._tx() as db:
            db.execute("""INSERT INTO production_jobs(
                job_id,project_id,assembly_id,assembly_revision,assembly_sha256,
                manifest_sha256,manifest_json,task_kind,state,updated_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (uid,pid,mastering_decision_id,decision["revision"],
                 decision["document_sha256"],manifest_sha,encoded.decode("ascii"),
                 TASK_KIND,"QUEUED",now,now))
            db.executemany("""INSERT INTO production_segments(
                 job_id,position,start_tick,end_tick,source_path,expected_sha256,
                 expected_bytes,state) VALUES(?,?,?,?,?,?,?,?)""",
                [(uid,x["position"],x["start_tick"],x["end_tick"],
                  x["source_path"],x["source_sha256"],x["source_bytes"],"PENDING")
                  for x in frames])
            db.execute("""INSERT INTO production_cinema_reels(
                 job_id,take_id,take_revision,take_sha256,decision_id,
                 decision_sha256,profile,frame_count,picture_uuid,
                 codec_path,codec_sha256,wrapper_path,wrapper_sha256,
                 info_path,info_sha256,updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid,data["source_take_id"],data["source_take_revision"],
                 data["source_take_sha256"],mastering_decision_id,
                 decision["document_sha256"],profile,len(frames),picture_uid,
                 str(openjpeg.executable),openjpeg.sha256,
                 str(wrapper.executable),wrapper.sha256,
                 str(info.executable),info.sha256,now))
            self._event(db,uid,"NATIVE_PICTURE_REEL_APPROVED",
                        f"{len(frames)} immutable source frames")
        return {"format":FORMAT,"status":"QUEUED","job_id":uid,
                "manifest_sha256":manifest_sha,
                "frame_count":len(frames),"source_modified":False,
                "production_dcp_accepted":False}

    def finish_frame(self,owner,segment,receipt):
        job_id=segment["job_id"]
        position=segment["position"]
        reel=self.reel(job_id)
        path=self.spool(job_id)/"frames"/f"{position:06d}.j2c"
        if (type(receipt) is not dict or
                receipt.get("status")!="ENCODED_J2K_STAGE_VERIFIED" or
                receipt.get("source_sha256")!=segment["expected_sha256"] or
                receipt.get("native_codec_sha256")!=reel["codec_sha256"]):
            raise PermissionError("Missing exact approved encoded frame receipt")
        size=verify_frame_file(path,receipt["codestream_sha256"],reel["profile"])
        if size!=receipt["codestream_bytes"]:
            raise PermissionError("Actual spooled frame bytes changed")
        with self._tx() as db:
            row=db.execute("""SELECT j.owner_token AS owner,j.cancel_requested,
                   s.owner_token AS frame_owner,s.state,s.expected_sha256
                   FROM production_jobs j JOIN production_segments s
                   ON j.job_id=s.job_id WHERE s.job_id=? AND s.position=?""",
                   (job_id,position)).fetchone()
            if (row is None or row["owner"]!=owner or
                    row["frame_owner"]!=owner or row["state"]!="RUNNING"
                    or row["cancel_requested"] or
                    row["expected_sha256"]!=receipt["source_sha256"]):
                raise PermissionError("Stale/cancelled cinema worker may not checkpoint")
            db.execute("""INSERT INTO production_cinema_frames(
                 job_id,position,file_sha256,file_bytes,source_sha256,committed_at)
                 VALUES(?,?,?,?,?,?)""",
                 (job_id,position,receipt["codestream_sha256"],size,
                  receipt["source_sha256"],_now()))
            db.execute("""UPDATE production_segments SET state='VERIFIED',
                 verified_sha256=?,verified_bytes=?,verified_at=?,
                 owner_token=NULL WHERE job_id=? AND position=?""",
                 (receipt["codestream_sha256"],size,_now(),job_id,position))
            self._event(db,job_id,"PICTURE_FRAME_CHECKPOINT",
                        str(position)+":"+receipt["codestream_sha256"])
        return {"status":"PICTURE_FRAME_CHECKPOINTED","job_id":job_id,
                "position":position,"codestream_sha256":receipt["codestream_sha256"],
                "production_dcp_accepted":False}

    def next_track(self,owner,pid):
        """Claim MXF stage only after every frame has a durable SHA receipt."""
        with self._tx() as db:
            row=db.execute("""SELECT r.*,j.state,j.owner_token,j.cancel_requested,
                    j.project_id FROM production_cinema_reels r
                    JOIN production_jobs j ON j.job_id=r.job_id
                    WHERE r.reel_state='ENCODING'
                      AND j.state IN ('QUEUED','RUNNING')
                      AND j.cancel_requested=0
                      AND NOT EXISTS (SELECT 1 FROM production_segments s
                                     WHERE s.job_id=r.job_id AND s.state!='VERIFIED')
                    ORDER BY j.created_at LIMIT 1""").fetchone()
            if row is None:
                return None
            if row["owner_token"] not in (None,owner):
                return None
            db.execute("""UPDATE production_cinema_reels SET reel_state='TRACK_RUNNING',
                          updated_at=? WHERE job_id=?""",(_now(),row["job_id"]))
            db.execute("""UPDATE production_jobs SET state='RUNNING',
                          owner_token=?,owner_pid=?,updated_at=? WHERE job_id=?""",
                       (owner,pid,_now(),row["job_id"]))
            self._event(db,row["job_id"],"PICTURE_MXF_CLAIMED","Trusted verified frame set")
            return dict(row)

    def commit_track(self,owner,job_id,receipt):
        reel=self.reel(job_id)
        target=self.spool(job_id)/"picture.mxf"
        if (receipt.get("status")!="NATIVE_PICTURE_MXF_STAGE_VERIFIED" or
                receipt.get("asset_uuid")!=reel["picture_uuid"] or
                receipt.get("wrapper_sha256")!=reel["wrapper_sha256"] or
                receipt.get("info_sha256")!=reel["info_sha256"] or
                target.is_symlink() or not target.is_file() or
                digest_file(target)!=receipt.get("file_sha256") or
                target.stat().st_size!=receipt.get("file_bytes")):
            raise PermissionError("Uncommitted picture MXF cannot be trusted")
        with self._tx() as db:
            row=db.execute("""SELECT r.reel_state,j.owner_token,
                       j.cancel_requested FROM production_cinema_reels r
                       JOIN production_jobs j ON j.job_id=r.job_id
                       WHERE r.job_id=?""",(job_id,)).fetchone()
            if (row is None or row["reel_state"]!="TRACK_RUNNING" or
                    row["owner_token"]!=owner or row["cancel_requested"]):
                raise PermissionError("Wrong owner or cancelled track checkpoint")
            db.execute("""UPDATE production_cinema_reels SET reel_state='TRACK_VERIFIED',
                track_sha256=?,track_bytes=?,updated_at=? WHERE job_id=?""",
                (receipt["file_sha256"],receipt["file_bytes"],_now(),job_id))
            db.execute("""UPDATE production_jobs SET state='OUTPUT_READY',
                owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            self._event(db,job_id,"PICTURE_MXF_CHECKPOINT",
                        receipt["file_sha256"])
        return {"status":"FILE_BACKED_PICTURE_MXF_READY","job_id":job_id,
                "sha256":receipt["file_sha256"],"bytes":receipt["file_bytes"],
                "path":str(target),"production_dcp_accepted":False}

    def track_review(self,owner,job_id,reason):
        with self._tx() as db:
            row=db.execute("""SELECT j.owner_token,r.reel_state
                    FROM production_jobs j JOIN production_cinema_reels r
                    ON j.job_id=r.job_id WHERE j.job_id=?""",
                    (job_id,)).fetchone()
            if row is None or row["owner_token"]!=owner or row["reel_state"]!="TRACK_RUNNING":
                raise PermissionError("Only current supervisor can mark track review")
            db.execute("""UPDATE production_cinema_reels SET reel_state='REVIEW_REQUIRED',
                updated_at=? WHERE job_id=?""",(_now(),job_id))
            db.execute("""UPDATE production_jobs SET state='REVIEW_REQUIRED',
                owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            self._event(db,job_id,"PICTURE_MXF_REVIEW_REQUIRED",reason)

    def heartbeat_track(self,owner,job_id):
        with self._tx() as db:
            row=db.execute("""SELECT j.owner_token,j.cancel_requested,
                r.reel_state FROM production_jobs j
                JOIN production_cinema_reels r ON j.job_id=r.job_id
                WHERE j.job_id=?""",(job_id,)).fetchone()
            if (row is None or row["owner_token"]!=owner or
                    row["reel_state"]!="TRACK_RUNNING"):
                raise PermissionError("Stale Cinema MXF worker heartbeat")
            db.execute("UPDATE production_jobs SET updated_at=? WHERE job_id=?",
                       (_now(),job_id))
            return bool(row["cancel_requested"])

    def approve_rebuild_uncommitted(self,job_id,authorize):
        """Host-approved rescue; preserve orphan stages before selective retry.

        The operation is not available to the browser or automatic restart.
        It refuses changed original sources or corrupted already committed
        checkpoints. Any interrupted disposable outputs are MOVED to unique
        hidden review names on the SAME volume; no source is deleted.
        """
        if not callable(authorize):
            raise PermissionError("Native creator review authorization required")
        snap=self.status(job_id)
        if snap["task_kind"]!=TASK_KIND or snap["state"]!="REVIEW_REQUIRED":
            raise PermissionError("Only an inspected cinema job may resume")
        reel=self.reel(job_id)
        root=self.spool(job_id)
        with self._read() as db:
            sources=[dict(x) for x in db.execute("""SELECT position,
                state,source_path,expected_sha256,expected_bytes
                FROM production_segments WHERE job_id=? ORDER BY position""",
                (job_id,))]
            committed={r["position"]:dict(r) for r in db.execute(
                """SELECT position,file_sha256,file_bytes FROM production_cinema_frames
                   WHERE job_id=?""",(job_id,))}
        scope={"operation":"nvp.supervisor.review_quarantine_and_rebuild.v1",
               "job_id":job_id,"manifest_sha256":snap["manifest_sha256"],
               "approved_take_sha256":reel["take_sha256"],
               "verified_frame_count":len(committed),
               "unfinished_frames":len(sources)-len(committed),
               "preserve_all_uncommitted_files":True}
        if authorize(deepcopy(scope)) is not True:
            return {"status":"DENIED","job_id":job_id}
        # Do potentially expensive original and completed output hashing
        # outside a SQLite write transaction.
        for entry in sources:
            file=Path(entry["source_path"])
            if (file.is_symlink() or not file.is_file() or
                    file.stat().st_size!=entry["expected_bytes"] or
                    digest_file(file)!=entry["expected_sha256"]):
                raise PermissionError("Approved source changed; cannot rebuild")
            i=entry["position"]
            target=root/"frames"/f"{i:06d}.j2c"
            if i in committed:
                record=committed[i]
                if (entry["state"]!="VERIFIED" or
                        verify_frame_file(target,record["file_sha256"],
                                          reel["profile"])!=record["file_bytes"]):
                    raise PermissionError("Completed checkpoint corrupted; manual repair")
        if reel["track_sha256"] is not None:
            raise PermissionError("Committed MXF cannot be replaced by reviewed retry")
        # Only this same-host trusted method can move disposable stages.
        # Refuse symlinked work roots even if the apparent file names match.
        frame_parent=root/"frame-work"
        frames=root/"frames"
        mxf_stage=root/"mxf-stage"
        if any(x.is_symlink() for x in (root,frame_parent,frames,mxf_stage)):
            raise PermissionError("Untrusted spool directory redirection")
        from backend.nvp_wo3_atomic_publish import atomic_publish_directory
        def archive_directory(path):
            if not path.exists() and not path.is_symlink():
                return None
            if path.is_symlink() or not path.is_dir():
                raise PermissionError("Unsafe uncommitted codec work stage")
            destination=path.parent/(".nvp-reviewed-"+path.name+"-"+str(uuid4()))
            atomic_publish_directory(path,destination)
            return str(destination.name)
        def archive_file(path):
            if not path.exists() and not path.is_symlink():
                return None
            if path.is_symlink() or not path.is_file():
                raise PermissionError("Unsafe uncommitted codec output")
            destination=path.parent/(".nvp-reviewed-"+path.name+"-"+str(uuid4()))
            os.link(path,destination) # kernel-enforced no replacement
            _fsync_directory(path.parent)
            path.unlink() # one link removed, REVIEWED bytes kept in new link
            _fsync_directory(path.parent)
            return str(destination.name)
        archived=[]
        for entry in sources:
            i=entry["position"]
            if i in committed:
                continue
            work=frame_parent/f"{i:06d}"
            target=frames/f"{i:06d}.j2c"
            moved=archive_directory(work)
            if moved is not None:
                archived.append(moved)
            moved=archive_file(target)
            if moved is not None:
                archived.append(moved)
        moved=archive_directory(mxf_stage)
        if moved is not None:
            archived.append(moved)
        moved=archive_file(root/"picture.mxf")
        if moved is not None:
            archived.append(moved)
        # All interrupted data is preserved under review filenames. Only
        # NOW may the journal requeue the missing segments and MXF stage.
        with self._tx() as db:
            row=db.execute("""SELECT j.state,j.manifest_sha256,
                j.cancel_requested,r.track_sha256
                FROM production_jobs j JOIN production_cinema_reels r
                ON j.job_id=r.job_id WHERE j.job_id=?""",
                (job_id,)).fetchone()
            if (row is None or row["state"]!="REVIEW_REQUIRED" or
                    row["manifest_sha256"]!=scope["manifest_sha256"] or
                    row["cancel_requested"] or row["track_sha256"] is not None):
                raise PermissionError("Job changed during source review")
            current={r["position"]:dict(r) for r in db.execute(
                """SELECT position,file_sha256,file_bytes FROM production_cinema_frames
                WHERE job_id=?""",(job_id,))}
            if current!=committed:
                raise PermissionError("Completed checkpoints changed during review")
            for entry in sources:
                if entry["position"] not in committed:
                    db.execute("""UPDATE production_segments SET state='PENDING',
                        owner_token=NULL,verified_sha256=NULL,
                        verified_bytes=NULL,verified_at=NULL
                        WHERE job_id=? AND position=?""",
                        (job_id,entry["position"]))
            db.execute("""UPDATE production_jobs SET state='QUEUED',
                owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                (_now(),job_id))
            db.execute("""UPDATE production_cinema_reels SET reel_state='ENCODING',
                updated_at=? WHERE job_id=?""",(_now(),job_id))
            self._event(db,job_id,"PICTURE_REBUILD_APPROVED",
                        str(len(archived))+" old stages preserved for review")
        return {"status":"QUEUED","job_id":job_id,
                "already_verified_frames":len(committed),
                "requeued_frames":len(sources)-len(committed),
                "preserved_review_artifacts":archived,
                "production_dcp_accepted":False}

    def cinema_reconcile(self):
        """Read-only file audit + conservative transactional restart decisions.

        If an uncommitted output/stage exists, mark REVIEW_REQUIRED; never
        overwrite/reuse/remove it. Previously committed frame/MXF receipts are
        re-hashed; a missing/different file halts the job.
        """
        reports=[]
        with self._read() as db:
            jobs=[dict(x) for x in db.execute("""SELECT j.job_id,j.state,
                r.profile,r.reel_state,r.track_sha256,r.track_bytes
                FROM production_jobs j JOIN production_cinema_reels r
                ON j.job_id=r.job_id WHERE j.state NOT IN (
                 'CANCELLED','DELIVERY_RUNNING','DCP_PUBLISHED','DCP_INDEXED')""")]
        for job in jobs:
            uid=job["job_id"]
            root=self.spool(uid)
            with self._read() as db:
                segments=[dict(x) for x in db.execute("""SELECT s.position,
                    s.state,s.source_path,s.expected_sha256,s.verified_sha256,
                    s.verified_bytes,f.file_sha256,f.file_bytes
                    FROM production_segments s LEFT JOIN production_cinema_frames f
                    ON s.job_id=f.job_id AND s.position=f.position
                    WHERE s.job_id=? ORDER BY s.position""",(uid,))]
            needs_review=job["state"]=="REVIEW_REQUIRED"
            resumed=[]
            for item in segments:
                pos=item["position"]
                filename=root/"frames"/f"{pos:06d}.j2c"
                work=root/"frame-work"/f"{pos:06d}"
                if item["state"]=="VERIFIED":
                    try:
                        if (Path(item["source_path"]).is_symlink() or
                                not Path(item["source_path"]).is_file() or
                                item["file_sha256"]!=item["verified_sha256"] or
                                digest_file(item["source_path"])!=item["expected_sha256"] or
                                item["file_bytes"]!=item["verified_bytes"] or
                                verify_frame_file(filename,item["file_sha256"],
                                                  job["profile"])!=item["file_bytes"]):
                            raise ValueError("Frame file receipt invalid")
                    except (OSError,ValueError,PermissionError,TypeError):
                        needs_review=True
                elif item["state"] in ("RUNNING","PENDING"):
                    if (filename.exists() or filename.is_symlink() or
                            work.exists() or work.is_symlink()):
                        needs_review=True
                    elif item["state"]=="RUNNING":
                        # Only interrupted claims are being requeued; segments
                        # already PENDING have no interrupted worker to recover.
                        resumed.append(pos)
                elif item["state"]=="REVIEW_REQUIRED":
                    needs_review=True
            track=root/"picture.mxf"
            stage=root/"mxf-stage"
            if job["reel_state"]=="TRACK_VERIFIED":
                try:
                    if (not track.is_file() or track.is_symlink() or
                            digest_file(track)!=job["track_sha256"] or
                            track.stat().st_size!=job["track_bytes"]):
                        needs_review=True
                except OSError:
                    needs_review=True
            elif (track.exists() or track.is_symlink() or
                  stage.exists() or stage.is_symlink() or
                  job["reel_state"]=="REVIEW_REQUIRED"):
                needs_review=True
            with self._tx() as db:
                for item in segments:
                    if item["state"]=="RUNNING":
                        db.execute("""UPDATE production_segments SET
                           state=?,owner_token=NULL WHERE job_id=? AND position=?""",
                           ("REVIEW_REQUIRED" if item["position"] not in resumed else "PENDING",
                            uid,item["position"]))
                if needs_review:
                    db.execute("""UPDATE production_jobs SET state='REVIEW_REQUIRED',
                       owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                       (_now(),uid))
                    db.execute("""UPDATE production_cinema_reels
                        SET reel_state='REVIEW_REQUIRED',updated_at=? WHERE job_id=?""",
                        (_now(),uid))
                    self._event(db,uid,"PICTURE_RESTART_REVIEW",
                                "Uncommitted or altered output; no auto-promotion")
                elif job["reel_state"]=="TRACK_VERIFIED":
                    db.execute("""UPDATE production_jobs SET state='OUTPUT_READY',
                       owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                       (_now(),uid))
                else:
                    db.execute("""UPDATE production_jobs SET state='QUEUED',
                       owner_token=NULL,owner_pid=NULL,updated_at=? WHERE job_id=?""",
                       (_now(),uid))
                reports.append({"job_id":uid,
                    "status":"REVIEW_REQUIRED" if needs_review else "RECONCILED",
                    "reused_verified_frames":sum(
                        x["state"]=="VERIFIED" for x in segments),
                    "interrupted_requeued":resumed,
                    "filesystem_mutated":False})
        return {"format":FORMAT,"status":"NO_AUTO_DELETE_OR_PROMOTE",
                "jobs":reports,"production_dcp_accepted":False}
