"""AUDIO-01H native host: sealed approval, resource admission, contained DSP.

Workers cannot mint approval. An interrupted worker leaves ACTIVE resources
held until a future trusted OS-stop/recovery audit; never auto-promote output.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings, canonical_bytes
from backend.nvp_audio01h_automation import validate_automation
from backend.nvp_audio01h_fault_matrix import crash_after
from backend.nvp_audio01h_stem_revision import FORMAT as AUTOMATED_FORMAT
from backend.nvp_audio01h_loudness import analyze_wav
from backend.nvp_audio01h_mix_decision import record_mix_decision
from backend.nvp_audio01e_wav_publication import FORMAT as STEM_FORMAT
from backend.nvp_resource_guard import AdmissionRequest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_supervisor import wait_guarded
from backend.nvp_worker_containment import launch_contained
from backend.nvp_film_index import _id

FORMAT = "nvp.audio01h.native_plan.v1"
ROOT = Path(__file__).resolve().parents[1]


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class NativeAudio01HHost:
    def __init__(self, capture, ledger: TaskLedger, root, *, verify_creator_action,
                 strict_linux_tree=None):
        if not isinstance(ledger, TaskLedger) or not callable(verify_creator_action):
            raise TypeError("Native ledger and creator verifier required")
        self.capture = capture
        self.ledger = ledger
        self.creator = verify_creator_action
        self.root = Path(root)
        if self.root.is_symlink():
            raise RuntimeError("Native worker root cannot be symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = self.root.resolve()
        self.python = Path(sys.executable).resolve()
        self.worker = ROOT / "tools" / "nvp_audio01h_native_worker.py"
        self.owner = "audio01h_" + hashlib.sha256(str(self.root).encode()).hexdigest()[:22]
        self.strict_linux_tree = sys.platform == "linux" if strict_linux_tree is None else strict_linux_tree
        if type(self.strict_linux_tree) is not bool:
            raise ValueError("Invalid strict Linux containment policy")
        self.events = {}
        with self.ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01h_grants(
                job_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL,
                spec_sha TEXT NOT NULL, plan_sha TEXT NOT NULL,
                python_sha TEXT NOT NULL, worker_sha TEXT NOT NULL,
                expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
                result_sha TEXT, stopped INTEGER NOT NULL DEFAULT 0)""")
            db.execute("""CREATE TABLE IF NOT EXISTS native_audio01h_creator_events(
                event_digest TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                decision_id TEXT NOT NULL, revision INTEGER NOT NULL)""")
        self.bindings = ApprovedTaskBindings(ledger, approval_check=self._check)

    def _grant(self, job):
        with self.ledger._db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM native_audio01h_grants WHERE job_id=?", (job,)).fetchone()
        if not row:
            raise KeyError("Unknown AUDIO-01H native job")
        return dict(row)

    def _check(self, approval, digest, spec):
        try:
            job = spec["task_id"]
            row = self._grant(job)
            path = self.root / job / "plan.json"
            if (row["approval_id"] != approval or row["spec_sha"] != digest or
                row["revoked"] or row["result_sha"] is not None or
                time.time() > row["expires_at"] or
                _sha(self.python) != row["python_sha"] or
                _sha(self.worker) != row["worker_sha"] or
                path.is_symlink() or _sha(path) != row["plan_sha"] or
                hashlib.sha256(canonical_bytes(spec)).hexdigest() != digest):
                return False
            plan = json.loads(path.read_bytes())
            if (canonical_bytes(plan) != path.read_bytes() or plan["format"] != FORMAT or
                plan["project_id"] != spec["project_id"] or
                plan["output_id"] != spec["output_id"] or
                plan["destination"] != spec["destination"] or
                Path(plan["destination"]).exists() or Path(plan["destination"]).is_symlink()):
                return False
            rec = self.capture.index.read_revision(plan["project_id"], plan["source_audio_id"], 1)
            if rec["document_sha256"] != spec["source_document_sha"]:
                return False
            event = self.events.get(job)
            return event is not None and self.creator(event, spec["creator_scope"]) is True
        except (KeyError, ValueError, TypeError, OSError, RuntimeError):
            return False

    def stage(self, project_id, source_audio_id, source_dir, destination, output_id,
              points, creator_event, *, stem_id=None, ram_mb=1024, duration_s=900):
        if (type(ram_mb) is not int or not 1024 <= ram_mb <= 8192 or
            type(duration_s) is not int or not 60 <= duration_s <= 3600):
            raise ValueError("Invalid native RAM or approval duration")
        _id(output_id, "AUDIO-01H output identity")
        if stem_id is not None:
            _id(stem_id, "AUDIO-01H stem identity")
        rec = self.capture.index.read_revision(project_id, source_audio_id, 1)
        data = rec["data"]
        if rec["kind"] != "audio" or data.get("format") != STEM_FORMAT or data.get("final_mix") is not False:
            raise RuntimeError("Frozen AUDIO-01E original required")
        selected = [x for x in data["wav_outputs"] if x["stem_id"] == stem_id]
        if len(selected) != 1:
            raise RuntimeError("Ambiguous original stem")
        requested_dir = Path(source_dir)
        if requested_dir.is_symlink() or not requested_dir.is_dir():
            raise RuntimeError("Unsafe source directory")
        source_dir = requested_dir.resolve(strict=True)
        source = source_dir / selected[0]["filename"]
        if (source.is_symlink() or not source.is_file() or
            _sha(source) != selected[0]["sha256"]):
            raise RuntimeError("Source WAV changed or unsafe")
        self.capture.index.verify_media_file(project_id, selected[0]["sha256"], "audio/wav")
        envelope = [list(x) for x in validate_automation(points, data["total_samples_per_channel"])]
        dest = Path(destination).absolute()
        if (dest.exists() or dest.is_symlink() or dest.parent.is_symlink() or
            not dest.parent.is_dir() or dest.suffix.lower() != ".wav"):
            raise RuntimeError("Unsafe output location")
        try:
            self.capture.index.read_revision(project_id, output_id)
        except KeyError:
            pass
        else:
            raise RuntimeError("Output identity already committed")
        scope = {"operation": "nvp.audio01h.automate_stem",
                 "project_id": project_id, "audio_id": source_audio_id,
                 "audio_document_sha": rec["document_sha256"],
                 "stem_id": stem_id, "source_sha256": selected[0]["sha256"],
                 "output_id": output_id, "destination": str(dest),
                 "envelope": envelope, "final_mix": False, "final_master": False}
        if self.creator(creator_event, dict(scope)) is not True:
            raise PermissionError("Creator rejected exact audio automation")
        job = "audiojob" + secrets.token_hex(16)
        plan = {"format": FORMAT, "studio_db_path": str(self.capture.studio.db_path),
                "project_id": project_id, "source_audio_id": source_audio_id,
                "source_dir": str(source_dir), "stem_id": stem_id,
                "points": envelope, "destination": str(dest), "output_id": output_id,
                "authorized_scope": scope, "director_approved": False, "final_master": False}
        spec = {"task_id": job, "kind": "compositing", "project_id": project_id,
                "source_document_sha": rec["document_sha256"],
                "output_id": output_id, "destination": str(dest),
                "creator_scope": scope}
        folder = self.root / job
        folder.mkdir(mode=0o700)
        with (folder / "plan.json").open("xb") as stream:
            stream.write(canonical_bytes(plan))
            stream.flush()
            os.fsync(stream.fileno())
        crash_after("plan_fsynced")
        approval = "audioapproval" + secrets.token_hex(16)
        seal = hashlib.sha256(canonical_bytes(spec)).hexdigest()
        self.events[job] = creator_event
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO native_audio01h_grants
                (job_id,approval_id,spec_sha,plan_sha,python_sha,worker_sha,expires_at)
                VALUES(?,?,?,?,?,?,?)""",
                (job, approval, seal, _sha(folder / "plan.json"), _sha(self.python),
                 _sha(self.worker), time.time() + duration_s))
            db.commit()
        crash_after("grant_committed")
        self.bindings.enqueue(AdmissionRequest(job,"compositing","Immutable audio finishing automation",ram_mb),
                              owner_key=self.owner,lane="standard",
                              approval_id=approval,document=spec)
        crash_after("queued_committed")
        return {"job_id": job, "state": "QUEUED", "output_id": output_id}

    def run_next(self, *, timeout_seconds=300):
        admission = self.bindings.claim_next(owner_key=self.owner)
        if admission is None or not admission["admitted"]:
            return admission
        job = admission["task_id"]
        crash_after("claimed_active")
        proc = None
        reaped = False
        try:
            self.bindings.verified_spec(job, owner_key=self.owner)
            folder = self.root / job
            plan = json.loads((folder / "plan.json").read_bytes())
            self.ledger.update(job,"rendering","Contained sample-accurate audio automation")
            with (folder / "stdout.log").open("wb") as out, (folder / "stderr.log").open("wb") as err:
                proc = launch_contained([str(self.python), str(self.worker),
                                         "--plan", str(folder / "plan.json")],
                                        cwd=str(folder),stdout=out,stderr=err,
                                        memory_mb=self.ledger.get_task(job)["ram_mb"],
                                        linux_cgroup_tree_required=self.strict_linux_tree)
                code = wait_guarded(proc,self.ledger,job,timeout_seconds=timeout_seconds)
                if code != 0:
                    raise RuntimeError("Contained audio worker exited " + str(code))
                proc.close()
                proc = None
                reaped = True
            crash_after("worker_handle_reaped")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE native_audio01h_grants SET stopped=1 WHERE job_id=?", (job,))
                db.commit()
            crash_after("stopped_witness_committed")
            self.ledger.update(job,"verifying_output","Independent immutable FilmIndex proof")
            rec = self.capture.index.read_revision(plan["project_id"],plan["output_id"],1)
            data = rec["data"]
            receipt = json.loads((folder / "worker_receipt.json").read_bytes())
            if (rec["kind"] != "audio" or data.get("format") != AUTOMATED_FORMAT or
                data["source_audio_id"] != plan["source_audio_id"] or
                data["source_stem_id"] != plan["stem_id"] or
                data["automation"] != plan["points"] or
                data["final_mix"] is not False or
                receipt.get("document_sha256") != rec["document_sha256"] or
                receipt.get("wav_sha256") != data["automated_wav_sha256"] or
                receipt.get("format") != "nvp.audio01h.worker_receipt.v1" or
                receipt.get("final_master") is not False or
                _sha(plan["destination"]) != data["automated_wav_sha256"]):
                raise RuntimeError("Native audio output failed independent verification")
            self.capture.index.verify_media_file(plan["project_id"], data["automated_wav_sha256"],"audio/wav")
            crash_after("output_independently_verified")
            self.ledger.finish(job, "SUCCEEDED", "Verified immutable unapproved automated audio")
            crash_after("ledger_succeeded")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE native_audio01h_grants SET result_sha=? WHERE job_id=?",
                           (rec["document_sha256"],job))
                db.commit()
            crash_after("grant_result_committed")
            return {"job_id":job,"state":"SUCCEEDED","output_id":plan["output_id"],
                    "document_sha256":rec["document_sha256"]}
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.terminate_tree()
                    reaped = proc.poll() is not None
                    proc.close()
                except BaseException:
                    reaped = False
            # Never treat a crashed worker or orphan output as approved.
            if reaped and self.ledger.get_task(job)["state"] == "ACTIVE":
                self.ledger.update(job,"recovering","Interrupted; output quarantined for native audit")
            raise

    def recover_completed(self, job):
        """After restart, reconcile ONLY a proven reaped and verified result.

        No evidence of OS stop -> no resource release. No implicit rerender.
        This is deliberately more restrictive than worker-side receipts.
        """
        grant = self._grant(job)
        task = self.ledger.get_task(job)
        if grant["stopped"] != 1 or task is None:
            raise PermissionError("No durable native OS worker stop witness")
        plan_file = self.root / job / "plan.json"
        if plan_file.is_symlink() or _sha(plan_file) != grant["plan_sha"]:
            raise RuntimeError("Recovered plan was changed")
        plan = json.loads(plan_file.read_bytes())
        source = self.capture.index.read_revision(plan["project_id"],
                                                  plan["source_audio_id"],1)
        scope = plan["authorized_scope"]
        if (source["document_sha256"] != scope["audio_document_sha"] or
            scope["source_sha256"] != next(x["sha256"] for x in source["data"]["wav_outputs"]
                                          if x["stem_id"] == plan["stem_id"])):
            raise RuntimeError("Recovered source did not match original approval")
        rec = self.capture.index.read_revision(plan["project_id"], plan["output_id"],1)
        data = rec["data"]
        receipt_file = self.root / job / "worker_receipt.json"
        if receipt_file.is_symlink():
            raise RuntimeError("Unsafe recovered worker receipt")
        receipt = json.loads(receipt_file.read_bytes())
        if (rec["kind"] != "audio" or data.get("format") != AUTOMATED_FORMAT or
            data.get("source_audio_sha256") != source["document_sha256"] or
            data.get("source_stem_id") != plan["stem_id"] or
            data.get("automation") != plan["points"] or
            data.get("final_mix") is not False or
            receipt.get("format") != "nvp.audio01h.worker_receipt.v1" or
            receipt.get("document_sha256") != rec["document_sha256"] or
            receipt.get("wav_sha256") != data["automated_wav_sha256"] or
            receipt.get("final_master") is not False):
            raise RuntimeError("Recovered media and receipt disagree")
        target = Path(plan["destination"])
        if target.is_symlink() or not target.is_file() or _sha(target) != data["automated_wav_sha256"]:
            raise RuntimeError("Recovered output changed")
        self.capture.index.verify_media_file(plan["project_id"],
                                             data["automated_wav_sha256"],"audio/wav")
        if grant["result_sha"] not in (None,rec["document_sha256"]):
            raise RuntimeError("Conflicting durable completion")
        if task["state"] == "SUCCEEDED":
            if grant["result_sha"] != rec["document_sha256"]:
                with self.ledger._db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("UPDATE native_audio01h_grants SET result_sha=? WHERE job_id=?",
                               (rec["document_sha256"],job))
                    db.commit()
            return {"job_id":job,"state":"SUCCEEDED","rerendered":False}
        if task["state"] != "ACTIVE":
            raise RuntimeError("Only a stopped ACTIVE native job may reconcile")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_audio01h_grants SET result_sha=? WHERE job_id=?",
                       (rec["document_sha256"],job))
            db.commit()
        self.ledger.finish(job,"SUCCEEDED","Independent stopped-worker replay verified")
        return {"job_id":job,"state":"SUCCEEDED","rerendered":False}

    def _measure_contained(self, wav_path, *, ffmpeg, expected_samples):
        """Resource-admitted, Job-Object-contained FFmpeg loudness measurement."""
        wav = Path(wav_path)
        if wav.is_symlink() or not wav.is_file():
            raise RuntimeError("Indexed WAV required for protected measurement")
        executable = shutil.which(ffmpeg)
        if not executable:
            raise RuntimeError("FFmpeg missing")
        executable = str(Path(executable).resolve(strict=True))
        job = "measurejob" + secrets.token_hex(16)
        folder = self.root / job
        folder.mkdir(mode=0o700)
        plan = {"format":"nvp.audio01h.measure_plan.v1",
                "wav":str(wav.resolve(strict=True)),
                "wav_sha256":_sha(wav),"samples":expected_samples,
                "ffmpeg":executable,"ffmpeg_sha256":_sha(executable),
                "final_master":False}
        plan_file = folder / "plan.json"
        with plan_file.open("xb") as file:
            file.write(canonical_bytes(plan))
            file.flush()
            os.fsync(file.fileno())
        admitted=self.ledger.admit(AdmissionRequest(
            job,"compositing","Contained final-mix loudness measurement",1024))
        if not admitted["admitted"]:
            raise RuntimeError("Native measurement resource budget unavailable")
        proc=None
        reaped=False
        try:
            if _sha(executable) != plan["ffmpeg_sha256"] or _sha(wav) != plan["wav_sha256"]:
                raise RuntimeError("Loudness input or native executable changed")
            self.ledger.update(job,"verifying_output","Contained FFmpeg EBU R128 inspection")
            script = ROOT / "tools" / "nvp_audio01h_measure_worker.py"
            with (folder/"stdout.log").open("wb") as out, (folder/"stderr.log").open("wb") as err:
                proc=launch_contained(
                    [str(self.python),str(script),"--plan",str(plan_file)],
                    cwd=str(folder),stdout=out,stderr=err,memory_mb=1024,
                    linux_cgroup_tree_required=self.strict_linux_tree)
                code=wait_guarded(proc,self.ledger,job,timeout_seconds=150)
                if code != 0:
                    raise RuntimeError("Native FFmpeg analysis failed: " + str(code))
                proc.close()
                proc=None
                reaped=True
            output=folder/"measurement.json"
            if output.is_symlink() or not output.is_file() or _sha(wav) != plan["wav_sha256"]:
                raise RuntimeError("Missing protected measurement or altered WAV")
            receipt=json.loads(output.read_bytes())
            if (receipt.get("wav_sha256") != plan["wav_sha256"] or
                receipt.get("samples_per_channel") != expected_samples or
                receipt.get("measure_method") != "ffmpeg_loudnorm_analysis_ebu_r128" or
                receipt.get("normalized") is not False or
                receipt.get("final_mix") is not False):
                raise RuntimeError("Measured loudness receipt does not match pinned media")
            self.ledger.finish(job,"SUCCEEDED","Verified real contained EBU R128 analysis")
            return receipt
        except BaseException:
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.terminate_tree()
                    reaped = proc.poll() is not None
                    proc.close()
                except BaseException:
                    reaped=False
            if reaped and self.ledger.get_task(job)["state"]=="ACTIVE":
                self.ledger.finish(job,"FAILED","Contained loudness measurement failed")
            # Unknown native process state keeps ACTIVE resource reservation.
            raise

    def creator_decision(self, project_id, automated_id, decision_id, evidence,
                         *, decision, creator_event, ffmpeg="ffmpeg"):
        """Creator-only host entrypoint, with durable replay prevention."""
        if type(creator_event) is not str or not creator_event:
            raise PermissionError("Authenticated creator event identifier required")
        # A FilmIndex audio object is insufficient: only a fully completed,
        # OS-reaped native producer may supply a candidate for final approval.
        source = self.capture.index.read_revision(project_id,automated_id,1)
        with self.ledger._db() as db:
            rows=db.execute("""SELECT g.job_id FROM native_audio01h_grants g
                JOIN tasks t ON t.id=g.job_id
                WHERE g.result_sha=? AND g.stopped=1 AND g.revoked=0
                AND t.state='SUCCEEDED' AND t.reserved=0""",
                (source["document_sha256"],)).fetchall()
        matches=[]
        for (candidate_job,) in rows:
            sealed=self.root/candidate_job/"plan.json"
            grant=self._grant(candidate_job)
            if sealed.is_symlink() or not sealed.is_file() or _sha(sealed)!=grant["plan_sha"]:
                continue
            pinned=json.loads(sealed.read_bytes())
            if (pinned.get("project_id")==project_id and
                pinned.get("output_id")==automated_id and
                pinned.get("stem_id") is None):
                matches.append(candidate_job)
        if len(matches)!=1:
            raise PermissionError("Final-mix candidate lacks one completed contained native producer")
        # Require trusted human-event admission BEFORE reserving its nonce.
        # This preflight is not sufficient for publication; full exact scope
        # is independently rechecked by record_mix_decision below.
        if self.creator(creator_event, {
            "operation":"nvp.audio01h.measure_for_mix_review",
            "project_id":project_id,"automated_id":automated_id,
            "decision_id":decision_id,"decision":decision}) is not True:
            raise PermissionError("Creator denied native audio inspection")
        event_digest = hashlib.sha256(creator_event.encode("utf8")).hexdigest()
        # Consume the event BEFORE FilmIndex publication. A crash may leave a
        # reserved, unusable event, but cannot reuse a real human approval.
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM native_audio01h_creator_events WHERE event_digest=?",
                          (event_digest,)).fetchone():
                raise PermissionError("Creator event already consumed")
            db.execute("INSERT INTO native_audio01h_creator_events VALUES(?,?,?,-1)",
                       (event_digest,project_id,decision_id))
            db.commit()
        crash_after("creator_event_reserved")
        def trusted(event,scope):
            return event == creator_event and self.creator(event,scope) is True
        def measured(path, *, ffmpeg, expected_samples):
            return self._measure_contained(path,ffmpeg=ffmpeg,
                                           expected_samples=expected_samples)
        result = record_mix_decision(
            self.capture,project_id,automated_id,decision_id,evidence,
            decision=decision,creator_event=creator_event,authorize=trusted,
            ffmpeg=ffmpeg,measure=measured)
        crash_after("creator_decision_registered")
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_audio01h_creator_events SET revision=? WHERE event_digest=? AND revision=-1",
                       (result["revision"],event_digest))
            db.commit()
        crash_after("creator_event_completed")
        return result
