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
import sqlite3
import sys
import time

from backend.nvp_approved_tasks import ApprovedTaskBindings, canonical_bytes
from backend.nvp_audio01h_automation import validate_automation
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
        source_dir = Path(source_dir).resolve(strict=True)
        source = source_dir / selected[0]["filename"]
        if source_dir.is_symlink() or source.is_symlink() or _sha(source) != selected[0]["sha256"]:
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
        self.bindings.enqueue(AdmissionRequest(job,"compositing","Immutable audio finishing automation",ram_mb),
                              owner_key=self.owner,lane="standard",
                              approval_id=approval,document=spec)
        return {"job_id": job, "state": "QUEUED", "output_id": output_id}

    def run_next(self, *, timeout_seconds=300):
        admission = self.bindings.claim_next(owner_key=self.owner)
        if admission is None or not admission["admitted"]:
            return admission
        job = admission["task_id"]
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
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE native_audio01h_grants SET stopped=1 WHERE job_id=?", (job,))
                db.commit()
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
            self.ledger.finish(job, "SUCCEEDED", "Verified immutable unapproved automated audio")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE native_audio01h_grants SET result_sha=? WHERE job_id=?",
                           (rec["document_sha256"],job))
                db.commit()
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

    def creator_decision(self, project_id, automated_id, decision_id, evidence,
                         *, decision, creator_event, ffmpeg="ffmpeg"):
        """Creator-only host entrypoint, with durable replay prevention."""
        if type(creator_event) is not str or not creator_event:
            raise PermissionError("Authenticated creator event identifier required")
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
        def trusted(event,scope):
            return event == creator_event and self.creator(event,scope) is True
        result = record_mix_decision(
            self.capture,project_id,automated_id,decision_id,evidence,
            decision=decision,creator_event=creator_event,authorize=trusted,ffmpeg=ffmpeg)
        with self.ledger._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE native_audio01h_creator_events SET revision=? WHERE event_digest=? AND revision=-1",
                       (result["revision"],event_digest))
            db.commit()
        return result
