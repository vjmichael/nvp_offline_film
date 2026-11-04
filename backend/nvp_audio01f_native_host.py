"""Trusted AUDIO-01F native review host: B14 creator policy + TaskLedger + Job Object.

No model, browser or worker may produce its own creator approval. OS worker
execution is admitted only from a pinned, still-approved immutable operation.
Linux strict cgroup guardian remains deferred acceptance, not silently disabled.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings,canonical_bytes
from backend.nvp_audio01f_picture_sound import verify_picture_sound_preview
from backend.nvp_audio01g_mux_intent import prepare as prepare_mux, transition as advance_mux
from backend.nvp_audio01g_fault_matrix import crash_after
from backend.nvp_b14_edited_movie import verify_edited_technical_mov
from backend.nvp_audio01e_wav_publication import verify_published_wavs
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import _id
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded
from backend.nvp_worker_containment import launch_contained

FORMAT="nvp.audio01f.native_plan.v1"

def _hash_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def plan_path_ffmpeg(plan_path,key):
    plan=json.loads(Path(plan_path).read_text("ascii"))
    path=Path(plan[key])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RuntimeError("Pinned native media executable unavailable")
    return path


class NativeAudio01FHost:
    def __init__(self,capture:DigitalCapture,ledger:TaskLedger,root,*,verify_creator_action,
                 strict_linux_tree=None):
        if (not isinstance(capture,DigitalCapture) or
            not isinstance(ledger,TaskLedger) or not callable(verify_creator_action)):
            raise TypeError("Native AUDIO-01F requires FilmIndex, TaskLedger, creator policy")
        self.capture=capture
        self.ledger=ledger
        self.creator=verify_creator_action
        self.strict_linux_tree=(sys.platform=="linux" if strict_linux_tree is None
                                else strict_linux_tree)
        if type(self.strict_linux_tree) is not bool:
            raise TypeError("Strict Linux cgroup policy must be boolean")
        root=Path(root)
        if root.is_symlink():raise RuntimeError("Unsafe native mux staging root")
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root=root.resolve()
        self.python=Path(sys.executable).resolve()
        self.worker=Path(__file__).resolve().parents[1]/"tools"/"nvp_audio01f_native_worker.py"
        self.owner="audio01f_"+hashlib.sha256(str(self.root).encode()).hexdigest()[:22]
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01f_grants(
                job_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL,
                document_json TEXT NOT NULL, spec_sha TEXT NOT NULL,
                plan_sha TEXT NOT NULL, python_sha TEXT NOT NULL,
                worker_sha TEXT NOT NULL, expires_at REAL NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0, result_sha TEXT)""")
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01g_os_stops(
                job_id TEXT PRIMARY KEY, verified_reaped INTEGER NOT NULL
                CHECK(verified_reaped=1), stopped_at REAL NOT NULL,
                source TEXT NOT NULL
            )""")
        self.bindings=ApprovedTaskBindings(ledger,approval_check=self._check)
        self._creator_events={}  # ephemeral native-only approvals; restart fails closed

    def _grant(self,job):
        with self.ledger._db() as db:
            db.row_factory=__import__("sqlite3").Row
            row=db.execute("SELECT * FROM native_audio01f_grants WHERE job_id=?",
                           (job,)).fetchone()
        if row is None:raise KeyError("Unknown native picture/sound job")
        return dict(row)

    def _check(self,approval,seal,spec):
        try:
            with self.ledger._db() as db:
                found=db.execute("SELECT job_id FROM native_audio01f_grants WHERE approval_id=?",
                                 (approval,)).fetchone()
            if not found:return False
            row=self._grant(found[0])
            job=row["job_id"]
            if (row["revoked"] or row["result_sha"] is not None or
                time.time()>row["expires_at"] or
                hashlib.sha256(canonical_bytes(spec)).hexdigest()!=seal or
                row["spec_sha"]!=seal or spec.get("task_id")!=job or
                spec.get("kind")!="compositing" or
                _hash_file(self.python)!=row["python_sha"] or
                _hash_file(self.worker)!=row["worker_sha"] or
                _hash_file(plan_path_ffmpeg(self.root/job/"native_plan.json", "ffmpeg"))!=spec["ffmpeg_sha"] or
                _hash_file(plan_path_ffmpeg(self.root/job/"native_plan.json", "ffprobe"))!=spec["ffprobe_sha"]):
                return False
            folder=self.root/job
            path=folder/"native_plan.json"
            if path.is_symlink() or _hash_file(path)!=row["plan_sha"]:
                return False
            plan=json.loads(path.read_text("ascii"))
            if (plan["format"]!=FORMAT or plan["project_id"]!=spec["project_id"] or
                plan["presentation_id"]!=spec["presentation_id"] or
                plan["destination"]!=spec["destination"] or
                plan["candidate_document_sha"]!=spec["picture_sha"] or
                plan["audio_document_sha"]!=spec["audio_sha"] or
                Path(plan["destination"]).exists() or Path(plan["destination"]).is_symlink()):
                return False
            picture=self.capture.index.read_revision(plan["project_id"],plan["candidate_id"],1)
            audio=self.capture.index.read_revision(plan["project_id"],plan["audio_id"],1)
            if (picture["document_sha256"]!=spec["picture_sha"] or
                audio["document_sha256"]!=spec["audio_sha"]):
                return False
            event=self._creator_events.get(job)
            return event is not None and self.creator(event,dict(spec["creator_scope"])) is True
        except (KeyError,ValueError,TypeError,RuntimeError,OSError):
            return False

    def stage_and_approve(self,project_id,candidate_id,audio_id,package,conform_dir,
                          movie_dir,audio_dir,audio_plan,audio_sources,audio_chunks,
                          destination,creator_event,*,presentation_id,
                          ram_mb=1024,duration_s=1800,
                          ffmpeg="ffmpeg",ffprobe="ffprobe"):
        if (type(ram_mb) is not int or not 1024<=ram_mb<=8192 or
            type(duration_s) is not int or not 60<=duration_s<=3600):
            raise ValueError("Native audio review memory and timeout bounds invalid")
        _id(presentation_id,"native picture/sound presentation")
        picture=self.capture.index.read_revision(project_id,candidate_id,1)
        audio=self.capture.index.read_revision(project_id,audio_id,1)
        if picture["kind"]!="presentation" or audio["kind"]!="audio":
            raise RuntimeError("Immutable picture and audio FilmIndex records required")
        # No creator approval prompt for unverified/altered picture or sound.
        # This also pins actual source chunks and WAVs, not only object IDs.
        checked_picture=verify_edited_technical_mov(
            self.capture,project_id,candidate_id,package,conform_dir,movie_dir,
            ffmpeg=ffmpeg,ffprobe=ffprobe)
        samples=checked_picture["frames"]*2000
        checked_audio=verify_published_wavs(
            self.capture,project_id,audio_id,audio_plan,audio_sources,
            samples,audio_chunks,audio_dir)
        if (checked_picture["status"]!="VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE" or
            checked_audio["status"]!="VERIFIED_UNAPPROVED_INDEXED_WAV_PREVIEW"):
            raise RuntimeError("Native mux inputs not source-verified")
        output=Path(destination)
        if (output.exists() or output.is_symlink() or not output.parent.is_dir() or
            output.parent.is_symlink()):
            raise RuntimeError("Native mux destination must be absent and safe")
        try:self.capture.index.read_revision(project_id,presentation_id)
        except KeyError:pass
        else:raise RuntimeError("Native mux presentation is already registered")
        # Resolve native media tools as absolute, immutable-by-digest inputs.
        # Never accept arbitrary commands or allow shell interpretation.
        actual_ffmpeg=shutil.which(ffmpeg)
        actual_ffprobe=shutil.which(ffprobe)
        if not actual_ffmpeg or not actual_ffprobe:
            raise RuntimeError("Native FFmpeg and FFprobe unavailable")
        ffmpeg=str(Path(actual_ffmpeg).resolve(strict=True))
        ffprobe=str(Path(actual_ffprobe).resolve(strict=True))
        ffmpeg_sha=_hash_file(ffmpeg)
        ffprobe_sha=_hash_file(ffprobe)
        # Pin the original source paths and 1:1 exact picture/audio identities.
        sources={sid:str(Path(path).resolve(strict=True)) for sid,path in audio_sources.items()}
        job="muxjob"+secrets.token_hex(16)
        target=str(output.absolute())
        scope={"operation":"nvp.native.audio01f.picture_sound_review",
               "project_id":project_id,"candidate_id":candidate_id,
               "picture_sha":picture["document_sha256"],"audio_id":audio_id,
               "audio_sha":audio["document_sha256"],"presentation_id":presentation_id,
               "destination":target,"ram_mb":ram_mb,
               "picture_locked":False,"final_mix":False,"final_master":False}
        if self.creator(creator_event,dict(scope)) is not True:
            raise PermissionError("Creator did not approve the exact picture/audio mux")
        plan={"format":FORMAT,"studio_db_path":str(self.capture.studio.db_path),
              "project_id":project_id,"candidate_id":candidate_id,"audio_id":audio_id,
              "candidate_document_sha":picture["document_sha256"],
              "audio_document_sha":audio["document_sha256"],
              "package":str(Path(package).resolve(strict=True)),
              "conform_dir":str(Path(conform_dir).resolve(strict=True)),
              "movie_dir":str(Path(movie_dir).resolve(strict=True)),
              "audio_dir":str(Path(audio_dir).resolve(strict=True)),
              "audio_chunks":str(Path(audio_chunks).resolve(strict=True)),
              "audio_plan":audio_plan,"audio_sources":sources,
              "destination":target,"presentation_id":presentation_id,
              "ffmpeg":ffmpeg,"ffprobe":ffprobe,
              "final_master":False,"director_approved":False}
        spec={"task_id":job,"kind":"compositing","project_id":project_id,
              "picture_sha":picture["document_sha256"],
              "audio_sha":audio["document_sha256"],
              "presentation_id":presentation_id,"destination":target,
              "ram_mb":ram_mb,"ffmpeg_sha":ffmpeg_sha,
              "ffprobe_sha":ffprobe_sha,"creator_scope":scope}
        folder=self.root/job
        folder.mkdir(mode=0o700)
        with (folder/"native_plan.json").open("xb") as stream:
            stream.write(canonical_bytes(plan))
            stream.flush();os.fsync(stream.fileno())
        approval="muxapproval"+secrets.token_hex(16)
        seal=hashlib.sha256(canonical_bytes(spec)).hexdigest()
        self._creator_events[job]=creator_event
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO native_audio01f_grants(
                job_id,approval_id,document_json,spec_sha,plan_sha,
                python_sha,worker_sha,expires_at) VALUES(?,?,?,?,?,?,?,?)""",
                (job,approval,canonical_bytes(spec).decode("ascii"),seal,
                 _hash_file(folder/"native_plan.json"),_hash_file(self.python),
                 _hash_file(self.worker),time.time()+duration_s))
            db.commit()
        crash_after("approved_grant_sqlite")
        prepare_mux(self.ledger,job,_hash_file(folder/"native_plan.json"))
        crash_after("intent_prepared_sqlite")
        self.bindings.enqueue(AdmissionRequest(job,"compositing",
                              "Exact indexed picture/sound technical mux",ram_mb),
                              owner_key=self.owner,lane="standard",
                              approval_id=approval,document=spec)
        crash_after("task_queued_sqlite")
        return {"job_id":job,"state":"QUEUED","presentation_id":presentation_id,
                "native_worker_started":False}

    def revoke(self,job):
        """Creator-only host revocation; queued tasks then fail policy recheck."""
        self._grant(job)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_audio01f_grants SET revoked=1 WHERE job_id=?",
                       (job,))
            db.commit()
        self._creator_events.pop(job,None)
        return {"job_id":job,"revoked":True}

    def _record_reaped(self,job):
        # Only native host, after waiting and closing its OWN process handle,
        # may durably attest that the worker has been stopped.
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT OR IGNORE INTO native_audio01g_os_stops(
                job_id,verified_reaped,stopped_at,source)
                VALUES(?,1,?,'owned_native_handle_reaped')""",(job,time.time()))
            db.commit()

    def _attest_reaped(self,job):
        with self.ledger._db() as db:
            row=db.execute("""SELECT verified_reaped,source
                FROM native_audio01g_os_stops WHERE job_id=?""",(job,)).fetchone()
        return row==(1,"owned_native_handle_reaped")

    def run_next(self,*,timeout_seconds=900):
        admit=self.bindings.claim_next(owner_key=self.owner)
        if admit is None or not admit["admitted"]:
            return admit
        job=admit["task_id"]
        crash_after("task_claimed_sqlite")
        proc=None
        reaped=False
        attempted=False
        try:
            self.bindings.verified_spec(job,owner_key=self.owner)
            row=self._grant(job)
            folder=self.root/job
            advance_mux(self.ledger,job,"prepared","running")
            crash_after("intent_running_sqlite")
            self.ledger.update(job,"rendering","Native contained picture/audio mux")
            with (folder/"stdout.log").open("wb") as out,(folder/"stderr.log").open("wb") as err:
                attempted=True
                proc=launch_contained([str(self.python),str(self.worker),
                    "--plan",str(folder/"native_plan.json")],
                    cwd=str(folder),stdout=out,stderr=err,
                    memory_mb=self._ram(job),
                    linux_cgroup_tree_required=self.strict_linux_tree)
                code=wait_guarded(proc,self.ledger,job,timeout_seconds=timeout_seconds)
                if code!=0:
                    raise RuntimeError("Native mux exited unsuccessfully: "+str(code))
                proc.close()
                reaped=True
                proc=None
                crash_after("native_worker_reaped")
                self._record_reaped(job)
                crash_after("os_stop_witness_sqlite")
            self.ledger.update(job,"verifying_output","Independent FilmIndex/decoded sync verification")
            plan=json.loads((folder/"native_plan.json").read_text("ascii"))
            verified=verify_picture_sound_preview(self.capture,plan["project_id"],
                plan["presentation_id"],plan["candidate_id"],plan["audio_id"],
                plan["package"],plan["conform_dir"],plan["movie_dir"],
                plan["audio_dir"],plan["audio_plan"],plan["audio_sources"],
                plan["audio_chunks"],plan["destination"],
                ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
            rec=self.capture.index.read_revision(plan["project_id"],plan["presentation_id"],1)
            receipt=json.loads((folder/"worker_receipt.json").read_text("ascii"))
            if (receipt.get("format")!="nvp.audio01f.native_worker_receipt.v1" or
                receipt.get("presentation_id")!=plan["presentation_id"] or
                receipt.get("document_sha256")!=rec["document_sha256"] or
                receipt.get("samples_per_channel")!=verified["samples_per_channel"] or
                receipt.get("final_master") is not False):
                raise RuntimeError("Untrusted worker-reported technical mux receipt")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                changed=db.execute("""UPDATE native_audio01f_grants SET result_sha=?
                    WHERE job_id=? AND result_sha IS NULL""",
                    (rec["document_sha256"],job)).rowcount
                if changed!=1:
                    raise RuntimeError("Conflicting native mux completion receipt")
                db.commit()
            crash_after("grant_result_sqlite")
            advance_mux(self.ledger,job,"running","verified",rec["document_sha256"])
            crash_after("intent_verified_sqlite")
            self.ledger.finish(job,"SUCCEEDED","Source-verified unapproved picture/audio technical mux")
            crash_after("ledger_succeeded_sqlite")
            advance_mux(self.ledger,job,"verified","committed",rec["document_sha256"])
            crash_after("intent_committed_sqlite")
            return {**verified,"job_id":job,"state":"SUCCEEDED"}
        except BaseException as exc:
            if proc is not None:
                try:
                    if proc.poll() is None:proc.terminate_tree()
                    reaped=proc.poll() is not None
                    proc.close()
                    if reaped:
                        self._record_reaped(job)
                except BaseException:
                    reaped=False
            if not attempted:
                reaped=True
            # On uncertain worker cleanup do not free an ACTIVE reservation.
            if reaped and self.ledger.get_task(job)["state"]=="ACTIVE":
                from backend.nvp_audio01g_mux_intent import read as read_mux
                state=read_mux(self.ledger,job)["state"]
                if state=="running":
                    advance_mux(self.ledger,job,"running","quarantined")
                # The OS-reaped handle is currently only held in memory.
                # Leave ACTIVE reservation held until a trusted OS-stop
                # attestation and independent media examination. Never
                # release potentially completed FilmIndex publication here.
                self.ledger.update(job,"recovering",
                    ("Mux stopped; native recovery requires OS witness: "+
                     type(exc).__name__)[:240])
            raise

    def _ram(self,job):
        with self.ledger._db() as db:
            row=db.execute("SELECT ram_mb FROM tasks WHERE id=?",(job,)).fetchone()
        if row is None:raise RuntimeError("Native mux reservation absent")
        return row[0]

    def inspect_interrupted(self,job):
        from backend.nvp_audio01g_mux_recovery import inspect_stopped_worker
        return inspect_stopped_worker(self,job,self._attest_reaped)

    def finalize_interrupted(self,job):
        from backend.nvp_audio01g_mux_recovery import finalize_verified_worker
        return finalize_verified_worker(self,job,self._attest_reaped)

    def reconcile_committed_after_restart(self,job):
        from backend.nvp_audio01g_mux_recovery import reconcile_post_commit_gap
        return reconcile_post_commit_gap(self,job)

    def verify_completed(self,job):
        row=self._grant(job)
        if self.ledger.get_task(job)["state"]!="SUCCEEDED" or not row["result_sha"]:
            raise RuntimeError("No verified completed native AUDIO-01F mux")
        plan=json.loads((self.root/job/"native_plan.json").read_text("ascii"))
        result=verify_picture_sound_preview(self.capture,plan["project_id"],
                plan["presentation_id"],plan["candidate_id"],plan["audio_id"],
                plan["package"],plan["conform_dir"],plan["movie_dir"],
                plan["audio_dir"],plan["audio_plan"],plan["audio_sources"],
                plan["audio_chunks"],plan["destination"],
                ffmpeg=plan["ffmpeg"],ffprobe=plan["ffprobe"])
        record=self.capture.index.read_revision(plan["project_id"],plan["presentation_id"],1)
        if record["document_sha256"]!=row["result_sha"]:
            raise RuntimeError("Native mux durable FilmIndex result changed")
        return result
